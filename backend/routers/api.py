"""
routers/api.py
Endpoints que usa el panel de administración:
  GET/POST/PUT/DELETE /stores      (base de datos)
  GET/POST/PUT/DELETE /events      (base de datos)
  GET/POST/PUT/DELETE /knowledge   (base de conocimiento libre)
  GET  /stores/export  · POST /stores/import      (CSV masivo)
  GET  /events/export  · POST /events/import      (CSV masivo)
  GET  /knowledge/export · POST /knowledge/import (CSV masivo)
  GET                 /stats
  GET                 /conversations
"""
import csv
import io
import logging
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from pydantic import BaseModel

from models.database import get_db
from models.conversation import Conversation
from models.store import Store
from models.event import Event
from models.knowledge import KnowledgeEntry
from models.conversation_flag import ConversationFlag
from models.zone import Zone
from models.zone_scan import ZoneScan
from models.mall_info import MallInfo
from models.info_point import InfoPoint
from models.delivery_transfer import DeliveryTransfer
from models.raffle import Raffle
from services.rag import load_stores_to_rag
from services.whatsapp import send_text_message

logger = logging.getLogger("mall_bot")
router = APIRouter(tags=["panel"])

# ── Pydantic schemas ──────────────────────────────────────────────

class StoreIn(BaseModel):
    name: str
    local_number: Optional[str] = ""
    floor: str
    category: str
    description: Optional[str] = ""
    schedule: Optional[str] = ""
    phone: Optional[str] = ""
    location_hint: Optional[str] = ""
    tags: Optional[str] = ""
    photo_url: Optional[str] = ""
    extra_info: Optional[str] = ""

class EventIn(BaseModel):
    name: str
    date: str
    time: str
    location: str
    description: Optional[str] = ""
    priority: Optional[int] = 3
    photo_url: Optional[str] = ""

class ReplyIn(BaseModel):
    message: str
    pause_minutes: Optional[int] = 45   # cuánto tiempo se pausa el bot para este número

class KnowledgeIn(BaseModel):
    title: str
    content: str
    photo_url: Optional[str] = ""

class ZoneIn(BaseModel):
    code: str
    floor: str
    description: str
    photo_url: Optional[str] = ""

class MallInfoIn(BaseModel):
    name: str
    address: Optional[str] = ""
    general_schedule: Optional[str] = ""
    phone: Optional[str] = ""
    parking: Optional[str] = ""
    wifi: Optional[str] = ""
    latitude: Optional[str] = ""
    longitude: Optional[str] = ""

class InfoPointIn(BaseModel):
    name: str
    floor: Optional[str] = ""
    location: Optional[str] = ""

class RaffleIn(BaseModel):
    name: str
    prize: str
    requirements: Optional[str] = ""
    end_date: Optional[str] = ""
    location: Optional[str] = ""
    description: Optional[str] = ""
    priority: Optional[int] = 3
    photo_url: Optional[str] = ""


def _reindex(db: Session):
    """
    Dispara el re-indexado del RAG en un HILO APARTE, sin bloquear la
    respuesta HTTP.

    Antes esto se hacía de forma síncrona (reconstruyendo TODO el
    índice desde cero cada vez) — con importaciones grandes (ej. 138
    locales de una sola vez) el navegador terminaba cortando la
    conexión por tardanza, y eso se veía en pantalla como un confuso
    error de "CORS bloqueado" que en realidad no tenía nada que ver
    con CORS — era un timeout disfrazado.

    Usamos threading (no BackgroundTasks de FastAPI) para no tener que
    tocar la firma de los 20 endpoints que llaman a esta función — el
    cambio queda contenido aquí, en un solo lugar.
    """
    import threading
    from models.database import SessionLocal

    def _run_in_background():
        bg_db = SessionLocal()
        try:
            load_stores_to_rag(bg_db)
            print("  🔄  RAG reindexado en segundo plano")
        except Exception as e:
            logger.warning(f"RAG no se pudo actualizar en background: {e}")
        finally:
            bg_db.close()

    threading.Thread(target=_run_in_background, daemon=True).start()


# ══════════════════════════════════════════════════════════════════
# IMPORT / EXPORT — helpers genéricos
# ══════════════════════════════════════════════════════════════════
#
# Diseñado para aceptar archivos CSV "de cualquier forma razonable":
# no importa el orden de las columnas, mayúsculas/minúsculas, tildes,
# o si usan "Local"/"Número de Local"/"local_number" — todo se
# reconoce con la lista de alias de abajo. Ideal para pegar
# directamente un CSV exportado de Google Sheets/Excel sin arreglarlo
# a mano primero.

def _normalize_header(h: str) -> str:
    h = h.strip().lower()
    h = unicodedata.normalize("NFKD", h).encode("ascii", "ignore").decode()
    h = h.replace(" ", "_").replace("-", "_")
    return h

FIELD_ALIASES = {
    "store": {
        "name":          ["name", "nombre", "tienda", "marca", "local_nombre"],
        "local_number":  ["local_number", "local", "numero_local", "numero", "no_local", "no."],
        "floor":         ["floor", "piso"],
        "category":      ["category", "categoria"],
        "description":   ["description", "descripcion"],
        "schedule":      ["schedule", "horario"],
        "phone":         ["phone", "telefono", "celular", "tel"],
        "location_hint": ["location_hint", "ubicacion", "ubicacion_hint", "ubicacion_exacta"],
        "tags":          ["tags", "etiquetas", "palabras_clave"],
        "photo_url":     ["photo_url", "foto", "foto_url", "imagen", "url_foto"],
        "extra_info":    ["extra_info", "carta", "cartelera", "informacion_adicional", "info_adicional"],
    },
    "event": {
        "name":        ["name", "nombre", "evento"],
        "date":        ["date", "fecha"],
        "time":        ["time", "hora"],
        "location":    ["location", "lugar", "ubicacion"],
        "description": ["description", "descripcion"],
        "priority":    ["priority", "prioridad", "nivel_promocion"],
    },
    "knowledge": {
        "title":   ["title", "titulo", "nombre"],
        "content": ["content", "contenido", "texto", "descripcion"],
    },
}


def _map_row(row: dict, entity: str) -> dict:
    """Convierte una fila cruda del CSV (con headers en cualquier formato) a los campos canónicos del modelo."""
    normalized = {_normalize_header(k): (v or "").strip() for k, v in row.items()}
    mapped = {}
    for canonical, aliases in FIELD_ALIASES[entity].items():
        for alias in aliases:
            if alias in normalized and normalized[alias]:
                mapped[canonical] = normalized[alias]
                break
    return mapped


def _read_csv_upload(file_bytes: bytes) -> list[dict]:
    # Soporta UTF-8 y Latin-1 (típico de exportaciones de Excel en Windows)
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            text = file_bytes.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise HTTPException(status_code=400, detail="No se pudo leer el archivo — usa UTF-8 o Excel/CSV estándar")
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def _csv_response(rows: list[dict], fieldnames: list[str], filename: str) -> StreamingResponse:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ══════════════════════════════════════════════════════════════════
# STATS
# ══════════════════════════════════════════════════════════════════

@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    """Métricas generales para el dashboard."""
    total_messages = db.query(Conversation).count()

    unique_users = db.query(
        func.count(func.distinct(Conversation.phone_number))
    ).scalar() or 0

    today = datetime.utcnow().date()
    messages_today = db.query(Conversation).filter(
        func.date(Conversation.timestamp) == today
    ).count()

    week_ago = datetime.utcnow() - timedelta(days=7)
    messages_this_week = db.query(Conversation).filter(
        Conversation.timestamp >= week_ago
    ).count()

    # Tiendas y eventos activos (ahora desde la base de datos)
    total_stores = db.query(Store).filter(Store.active == True).count()
    total_events = db.query(Event).count()

    # Mensajes por día (últimos 7 días)
    daily = []
    for i in range(6, -1, -1):
        day = datetime.utcnow().date() - timedelta(days=i)
        count = db.query(Conversation).filter(
            func.date(Conversation.timestamp) == day,
            Conversation.role == "user"
        ).count()
        daily.append({"day": day.strftime("%a"), "mensajes": count})

    # Horas pico (últimas 24h)
    hourly = []
    for h in range(0, 24, 2):
        start_h = datetime.utcnow().replace(hour=h, minute=0, second=0, microsecond=0)
        end_h   = start_h + timedelta(hours=2)
        count = db.query(Conversation).filter(
            Conversation.timestamp >= start_h,
            Conversation.timestamp < end_h,
            Conversation.role == "user"
        ).count()
        hourly.append({"hora": f"{h:02d}:00", "mensajes": count})

    return {
        "total_messages": total_messages,
        "unique_users": unique_users,
        "messages_today": messages_today,
        "messages_this_week": messages_this_week,
        "total_stores": total_stores,
        "total_events": total_events,
        "daily_chart": daily,
        "hourly_chart": hourly,
    }


# ══════════════════════════════════════════════════════════════════
# CONVERSATIONS
# ══════════════════════════════════════════════════════════════════

@router.get("/conversations")
def get_conversations(db: Session = Depends(get_db)):
    """Lista de usuarios únicos que han hablado con el bot."""
    rows = (
        db.query(
            Conversation.phone_number,
            Conversation.user_name,
            func.count(Conversation.id).label("total"),
            func.max(Conversation.timestamp).label("last_seen"),
        )
        .group_by(Conversation.phone_number, Conversation.user_name)
        .order_by(desc("last_seen"))
        .limit(100)
        .all()
    )

    # Traer todas las banderas de una vez (evita N+1 queries)
    flags = {f.phone_number: f for f in db.query(ConversationFlag).all()}
    now = datetime.now(timezone.utc)

    result = []
    for r in rows:
        flag = flags.get(r.phone_number)
        bot_paused = False
        if flag and flag.bot_paused_until:
            paused_until = flag.bot_paused_until
            if paused_until.tzinfo is None:
                paused_until = paused_until.replace(tzinfo=timezone.utc)
            bot_paused = now < paused_until

        result.append({
            "phone": r.phone_number,
            "name":  r.user_name,
            "total": r.total,
            "last_seen": str(r.last_seen),
            "needs_human": bool(flag.needs_human) if flag else False,
            "escalation_reason": flag.reason if flag else None,
            "bot_paused": bot_paused,
        })

    # Las que necesitan atención humana aparecen primero
    result.sort(key=lambda x: x["needs_human"], reverse=True)
    return result


@router.get("/conversations/{phone}")
def get_conversation_history(phone: str, db: Session = Depends(get_db)):
    """Historial completo de un usuario."""
    records = (
        db.query(Conversation)
        .filter(Conversation.phone_number == phone)
        .order_by(Conversation.timestamp.asc())
        .all()
    )
    if not records:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    return {"phone": phone, "messages": [r.to_dict() for r in records]}


@router.post("/conversations/{phone}/reply")
async def send_manual_reply(phone: str, body: ReplyIn, db: Session = Depends(get_db)):
    """
    Un administrador responde manualmente desde el panel. El mensaje
    sale por WhatsApp real, queda guardado con role='admin', y el bot
    se pausa para este número por un rato (para no chocar con el humano).
    """
    ok = await send_text_message(to=phone, message=body.message)
    if not ok:
        raise HTTPException(status_code=502, detail="No se pudo enviar el mensaje por WhatsApp")

    conv = Conversation(
        phone_number=phone,
        user_name=None,
        role="admin",
        message=body.message,
    )
    db.add(conv)

    flag = db.query(ConversationFlag).filter(ConversationFlag.phone_number == phone).first()
    if not flag:
        flag = ConversationFlag(phone_number=phone)
        db.add(flag)
    flag.needs_human = False  # un humano ya está atendiendo
    flag.bot_paused_until = datetime.now(timezone.utc) + timedelta(minutes=body.pause_minutes)

    db.commit()
    print(f"  🧑‍💼  Respuesta manual enviada a {phone} — bot pausado {body.pause_minutes} min")
    return {"ok": True}


@router.post("/conversations/{phone}/resume-bot")
def resume_bot(phone: str, db: Session = Depends(get_db)):
    """El admin termina de atender manualmente y le devuelve el control al bot."""
    flag = db.query(ConversationFlag).filter(ConversationFlag.phone_number == phone).first()
    if flag:
        flag.bot_paused_until = None
        flag.needs_human = False
        db.commit()
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════
# STORES  (ahora en base de datos — persiste entre redeploys)
# ══════════════════════════════════════════════════════════════════

@router.get("/stores")
def list_stores(db: Session = Depends(get_db)):
    stores = db.query(Store).order_by(Store.name).all()
    return [s.to_dict() for s in stores]


@router.post("/stores", status_code=201)
def create_store(store: StoreIn, db: Session = Depends(get_db)):
    new_store = Store(**store.model_dump())
    db.add(new_store)
    db.commit()
    db.refresh(new_store)
    _reindex(db)
    print(f"  ✅  Tienda agregada: {new_store.name} (id={new_store.id})")
    return {"ok": True, "store": new_store.to_dict()}


@router.put("/stores/{store_id}")
def update_store(store_id: int, store: StoreIn, db: Session = Depends(get_db)):
    existing = db.query(Store).filter(Store.id == store_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Tienda no encontrada")
    for field, value in store.model_dump().items():
        setattr(existing, field, value)
    db.commit()
    db.refresh(existing)
    _reindex(db)
    print(f"  ✅  Tienda actualizada: {existing.name} (id={existing.id})")
    return {"ok": True, "store": existing.to_dict()}


@router.delete("/stores/{store_id}")
def delete_store(store_id: int, db: Session = Depends(get_db)):
    existing = db.query(Store).filter(Store.id == store_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Tienda no encontrada")
    name = existing.name
    db.delete(existing)
    db.commit()
    _reindex(db)
    print(f"  🗑️   Tienda eliminada: {name}")
    return {"ok": True, "removed": name}


@router.get("/stores/export")
def export_stores(db: Session = Depends(get_db)):
    stores = db.query(Store).order_by(Store.name).all()
    fieldnames = ["name", "local_number", "floor", "category", "description", "schedule", "phone", "location_hint", "tags", "photo_url", "extra_info"]
    rows = [{k: (getattr(s, k) or "") for k in fieldnames} for s in stores]
    return _csv_response(rows, fieldnames, "locales.csv")


@router.post("/stores/import")
async def import_stores(file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = await file.read()
    raw_rows = _read_csv_upload(content)

    created, updated, skipped, errors = 0, 0, 0, []

    for i, raw in enumerate(raw_rows, start=2):  # fila 2 = primera fila de datos (1 es el header)
        mapped = _map_row(raw, "store")
        if not mapped.get("name"):
            skipped += 1
            errors.append(f"Fila {i}: sin nombre, se saltó")
            continue

        existing = (
            db.query(Store)
            .filter(Store.name == mapped["name"], Store.local_number == mapped.get("local_number"))
            .first()
        )
        if existing:
            for field in ["floor", "category", "description", "schedule", "phone", "location_hint", "tags", "photo_url", "extra_info"]:
                if mapped.get(field):
                    setattr(existing, field, mapped[field])
            updated += 1
        else:
            db.add(Store(
                name=mapped["name"],
                local_number=mapped.get("local_number"),
                floor=mapped.get("floor", "Por confirmar"),
                category=mapped.get("category", "Por confirmar con el CC"),
                description=mapped.get("description", ""),
                schedule=mapped.get("schedule", ""),
                phone=mapped.get("phone", ""),
                location_hint=mapped.get("location_hint", ""),
                tags=mapped.get("tags", ""),
                photo_url=mapped.get("photo_url", ""),
                extra_info=mapped.get("extra_info", ""),
                active=True,
            ))
            created += 1

    db.commit()
    _reindex(db)
    print(f"  📥  Import locales: {created} nuevos, {updated} actualizados, {skipped} saltados")
    return {"ok": True, "created": created, "updated": updated, "skipped": skipped, "errors": errors[:20]}


# ══════════════════════════════════════════════════════════════════
# EVENTS  (ahora en base de datos — persiste entre redeploys)
# ══════════════════════════════════════════════════════════════════

@router.get("/events")
def list_events(db: Session = Depends(get_db)):
    events = db.query(Event).order_by(Event.date).all()
    return [e.to_dict() for e in events]


@router.post("/events", status_code=201)
def create_event(event: EventIn, db: Session = Depends(get_db)):
    new_event = Event(**event.model_dump())
    db.add(new_event)
    db.commit()
    db.refresh(new_event)
    _reindex(db)
    print(f"  ✅  Evento agregado: {new_event.name} (id={new_event.id})")
    return {"ok": True, "event": new_event.to_dict()}


@router.put("/events/{event_id}")
def update_event(event_id: int, event: EventIn, db: Session = Depends(get_db)):
    existing = db.query(Event).filter(Event.id == event_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    for field, value in event.model_dump().items():
        setattr(existing, field, value)
    db.commit()
    db.refresh(existing)
    _reindex(db)
    print(f"  ✅  Evento actualizado: {existing.name} (id={existing.id})")
    return {"ok": True, "event": existing.to_dict()}


@router.delete("/events/{event_id}")
def delete_event(event_id: int, db: Session = Depends(get_db)):
    existing = db.query(Event).filter(Event.id == event_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    name = existing.name
    db.delete(existing)
    db.commit()
    _reindex(db)
    print(f"  🗑️   Evento eliminado: {name}")
    return {"ok": True, "removed": name}


@router.get("/events/export")
def export_events(db: Session = Depends(get_db)):
    events = db.query(Event).order_by(Event.date).all()
    fieldnames = ["name", "date", "time", "location", "description", "priority"]
    rows = [{k: (getattr(e, k) if getattr(e, k) is not None else "") for k in fieldnames} for e in events]
    return _csv_response(rows, fieldnames, "eventos.csv")


@router.post("/events/import")
async def import_events(file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = await file.read()
    raw_rows = _read_csv_upload(content)

    created, updated, skipped, errors = 0, 0, 0, []

    for i, raw in enumerate(raw_rows, start=2):
        mapped = _map_row(raw, "event")
        if not mapped.get("name") or not mapped.get("date"):
            skipped += 1
            errors.append(f"Fila {i}: falta nombre o fecha, se saltó")
            continue

        existing = db.query(Event).filter(Event.name == mapped["name"], Event.date == mapped["date"]).first()
        priority = int(mapped["priority"]) if str(mapped.get("priority", "")).isdigit() else 3
        priority = max(1, min(5, priority))

        if existing:
            existing.time = mapped.get("time", existing.time)
            existing.location = mapped.get("location", existing.location)
            existing.description = mapped.get("description", existing.description)
            existing.priority = priority
            updated += 1
        else:
            db.add(Event(
                name=mapped["name"],
                date=mapped["date"],
                time=mapped.get("time", ""),
                location=mapped.get("location", ""),
                description=mapped.get("description", ""),
                priority=priority,
            ))
            created += 1

    db.commit()
    _reindex(db)
    print(f"  📥  Import eventos: {created} nuevos, {updated} actualizados, {skipped} saltados")
    return {"ok": True, "created": created, "updated": updated, "skipped": skipped, "errors": errors[:20]}


# ══════════════════════════════════════════════════════════════════
# BASE DE CONOCIMIENTO LIBRE
# ══════════════════════════════════════════════════════════════════

@router.get("/knowledge")
def list_knowledge(db: Session = Depends(get_db)):
    entries = db.query(KnowledgeEntry).order_by(KnowledgeEntry.title).all()
    return [e.to_dict() for e in entries]


@router.post("/knowledge", status_code=201)
def create_knowledge(entry: KnowledgeIn, db: Session = Depends(get_db)):
    new_entry = KnowledgeEntry(title=entry.title, content=entry.content, photo_url=entry.photo_url, active=True)
    db.add(new_entry)
    db.commit()
    db.refresh(new_entry)
    _reindex(db)
    print(f"  ✅  Conocimiento agregado: {new_entry.title} (id={new_entry.id})")
    return {"ok": True, "entry": new_entry.to_dict()}


@router.put("/knowledge/{entry_id}")
def update_knowledge(entry_id: int, entry: KnowledgeIn, db: Session = Depends(get_db)):
    existing = db.query(KnowledgeEntry).filter(KnowledgeEntry.id == entry_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Entrada no encontrada")
    existing.title = entry.title
    existing.content = entry.content
    existing.photo_url = entry.photo_url
    db.commit()
    db.refresh(existing)
    _reindex(db)
    print(f"  ✅  Conocimiento actualizado: {existing.title} (id={existing.id})")
    return {"ok": True, "entry": existing.to_dict()}


@router.delete("/knowledge/{entry_id}")
def delete_knowledge(entry_id: int, db: Session = Depends(get_db)):
    existing = db.query(KnowledgeEntry).filter(KnowledgeEntry.id == entry_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Entrada no encontrada")
    title = existing.title
    db.delete(existing)
    db.commit()
    _reindex(db)
    print(f"  🗑️   Conocimiento eliminado: {title}")
    return {"ok": True, "removed": title}


@router.get("/knowledge/export")
def export_knowledge(db: Session = Depends(get_db)):
    entries = db.query(KnowledgeEntry).order_by(KnowledgeEntry.title).all()
    fieldnames = ["title", "content"]
    rows = [{k: (getattr(e, k) or "") for k in fieldnames} for e in entries]
    return _csv_response(rows, fieldnames, "base_de_conocimiento.csv")


@router.post("/knowledge/import")
async def import_knowledge(file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = await file.read()
    raw_rows = _read_csv_upload(content)

    created, updated, skipped, errors = 0, 0, 0, []

    for i, raw in enumerate(raw_rows, start=2):
        mapped = _map_row(raw, "knowledge")
        if not mapped.get("title") or not mapped.get("content"):
            skipped += 1
            errors.append(f"Fila {i}: falta título o contenido, se saltó")
            continue

        existing = db.query(KnowledgeEntry).filter(KnowledgeEntry.title == mapped["title"]).first()
        if existing:
            existing.content = mapped["content"]
            updated += 1
        else:
            db.add(KnowledgeEntry(title=mapped["title"], content=mapped["content"], active=True))
            created += 1

    db.commit()
    _reindex(db)
    print(f"  📥  Import conocimiento: {created} nuevos, {updated} actualizados, {skipped} saltados")
    return {"ok": True, "created": created, "updated": updated, "skipped": skipped, "errors": errors[:20]}


# ══════════════════════════════════════════════════════════════════
# ZONAS — navegación indoor por QR
# ══════════════════════════════════════════════════════════════════

@router.get("/zones")
def list_zones(db: Session = Depends(get_db)):
    from config import get_settings
    settings = get_settings()
    zones = db.query(Zone).order_by(Zone.code).all()
    result = []
    for z in zones:
        d = z.to_dict()
        d["qr_link"] = z.whatsapp_qr_link(settings.WHATSAPP_DISPLAY_NUMBER)
        result.append(d)
    return result


@router.post("/zones", status_code=201)
def create_zone(zone: ZoneIn, db: Session = Depends(get_db)):
    existing = db.query(Zone).filter(Zone.code == zone.code.upper()).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Ya existe una zona con el código {zone.code.upper()}")
    new_zone = Zone(code=zone.code.upper(), floor=zone.floor, description=zone.description, photo_url=zone.photo_url)
    db.add(new_zone)
    db.commit()
    db.refresh(new_zone)
    print(f"  ✅  Zona agregada: {new_zone.code} (id={new_zone.id})")
    return {"ok": True, "zone": new_zone.to_dict()}


@router.put("/zones/{zone_id}")
def update_zone(zone_id: int, zone: ZoneIn, db: Session = Depends(get_db)):
    existing = db.query(Zone).filter(Zone.id == zone_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Zona no encontrada")
    existing.code = zone.code.upper()
    existing.floor = zone.floor
    existing.description = zone.description
    existing.photo_url = zone.photo_url
    db.commit()
    db.refresh(existing)
    print(f"  ✅  Zona actualizada: {existing.code} (id={existing.id})")
    return {"ok": True, "zone": existing.to_dict()}


@router.delete("/zones/{zone_id}")
def delete_zone(zone_id: int, db: Session = Depends(get_db)):
    existing = db.query(Zone).filter(Zone.id == zone_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Zona no encontrada")
    code = existing.code
    db.delete(existing)
    db.commit()
    print(f"  🗑️   Zona eliminada: {code}")
    return {"ok": True, "removed": code}


@router.get("/zones/stats")
def zone_scan_stats(db: Session = Depends(get_db)):
    """Cuántas veces se ha escaneado cada zona — el mapa de calor de tráfico real."""
    rows = (
        db.query(ZoneScan.zone_code, func.count(ZoneScan.id).label("scans"))
        .group_by(ZoneScan.zone_code)
        .order_by(desc("scans"))
        .all()
    )
    return [{"zone_code": r.zone_code, "scans": r.scans} for r in rows]


# ══════════════════════════════════════════════════════════════════
# INFO GENERAL DEL MALL — última pieza migrada a la base de datos
# ══════════════════════════════════════════════════════════════════

@router.get("/mall-info")
def get_mall_info(db: Session = Depends(get_db)):
    info = db.query(MallInfo).filter(MallInfo.id == 1).first()
    if not info:
        # Si todavía no se ha corrido la migración ni creado a mano,
        # devolvemos un objeto vacío en vez de un error 404 — así el
        # formulario del panel se puede llenar desde cero sin drama.
        return {
            "id": None, "name": "Centro Comercial El Puente",
            "address": "", "general_schedule": "", "phone": "",
            "parking": "", "wifi": "",
        }
    return info.to_dict()


@router.put("/mall-info")
def update_mall_info(data: MallInfoIn, db: Session = Depends(get_db)):
    info = db.query(MallInfo).filter(MallInfo.id == 1).first()
    if not info:
        info = MallInfo(id=1)
        db.add(info)
    info.name = data.name
    info.address = data.address
    info.general_schedule = data.general_schedule
    info.phone = data.phone
    info.parking = data.parking
    info.wifi = data.wifi
    info.latitude = data.latitude
    info.longitude = data.longitude
    db.commit()
    db.refresh(info)
    _reindex(db)
    print(f"  ✅  Info general del mall actualizada")
    return {"ok": True, "mall_info": info.to_dict()}


@router.get("/info-points")
def list_info_points(db: Session = Depends(get_db)):
    points = db.query(InfoPoint).order_by(InfoPoint.name).all()
    return [p.to_dict() for p in points]


@router.post("/info-points", status_code=201)
def create_info_point(point: InfoPointIn, db: Session = Depends(get_db)):
    new_point = InfoPoint(**point.model_dump())
    db.add(new_point)
    db.commit()
    db.refresh(new_point)
    _reindex(db)
    print(f"  ✅  Punto de interés agregado: {new_point.name}")
    return {"ok": True, "point": new_point.to_dict()}


@router.put("/info-points/{point_id}")
def update_info_point(point_id: int, point: InfoPointIn, db: Session = Depends(get_db)):
    existing = db.query(InfoPoint).filter(InfoPoint.id == point_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Punto de interés no encontrado")
    for field, value in point.model_dump().items():
        setattr(existing, field, value)
    db.commit()
    db.refresh(existing)
    _reindex(db)
    print(f"  ✅  Punto de interés actualizado: {existing.name}")
    return {"ok": True, "point": existing.to_dict()}


@router.delete("/info-points/{point_id}")
def delete_info_point(point_id: int, db: Session = Depends(get_db)):
    existing = db.query(InfoPoint).filter(InfoPoint.id == point_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Punto de interés no encontrado")
    name = existing.name
    db.delete(existing)
    db.commit()
    _reindex(db)
    print(f"  🗑️   Punto de interés eliminado: {name}")
    return {"ok": True, "removed": name}


# ══════════════════════════════════════════════════════════════════
# TRANSFERENCIAS DE DOMICILIO
# ══════════════════════════════════════════════════════════════════
# Ya no gestionamos el pedido completo — el bot transfiere al cliente
# directo al WhatsApp de la tienda. Esto reemplaza a /orders/stats
# como la fuente real de "cuántos domicilios se están generando".

@router.get("/delivery-transfers/stats")
def delivery_transfer_stats(db: Session = Depends(get_db)):
    today = datetime.now(timezone.utc).date()
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)

    total_today = db.query(DeliveryTransfer).filter(
        func.date(DeliveryTransfer.timestamp) == today
    ).count()

    total_week = db.query(DeliveryTransfer).filter(
        DeliveryTransfer.timestamp >= week_ago
    ).count()

    top_stores = (
        db.query(DeliveryTransfer.store_name, func.count(DeliveryTransfer.id).label("total"))
        .filter(DeliveryTransfer.timestamp >= week_ago)
        .group_by(DeliveryTransfer.store_name)
        .order_by(desc("total"))
        .limit(10)
        .all()
    )

    return {
        "total_today": total_today,
        "total_this_week": total_week,
        "top_stores": [{"store": s, "total": t} for s, t in top_stores],
    }


@router.get("/delivery-transfers")
def list_delivery_transfers(db: Session = Depends(get_db)):
    rows = (
        db.query(DeliveryTransfer)
        .order_by(DeliveryTransfer.timestamp.desc())
        .limit(100)
        .all()
    )
    return [r.to_dict() for r in rows]


# ══════════════════════════════════════════════════════════════════
# SORTEOS Y CAMPAÑAS — distinto de Eventos (tienen premio, requisitos)
# ══════════════════════════════════════════════════════════════════

@router.get("/raffles")
def list_raffles(db: Session = Depends(get_db)):
    raffles = db.query(Raffle).order_by(Raffle.created_at.desc()).all()
    return [r.to_dict() for r in raffles]


@router.post("/raffles", status_code=201)
def create_raffle(raffle: RaffleIn, db: Session = Depends(get_db)):
    new_raffle = Raffle(**raffle.model_dump(), active=True)
    db.add(new_raffle)
    db.commit()
    db.refresh(new_raffle)
    _reindex(db)
    print(f"  ✅  Sorteo agregado: {new_raffle.name} (id={new_raffle.id})")
    return {"ok": True, "raffle": new_raffle.to_dict()}


@router.put("/raffles/{raffle_id}")
def update_raffle(raffle_id: int, raffle: RaffleIn, db: Session = Depends(get_db)):
    existing = db.query(Raffle).filter(Raffle.id == raffle_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Sorteo no encontrado")
    for field, value in raffle.model_dump().items():
        setattr(existing, field, value)
    db.commit()
    db.refresh(existing)
    _reindex(db)
    print(f"  ✅  Sorteo actualizado: {existing.name} (id={existing.id})")
    return {"ok": True, "raffle": existing.to_dict()}


@router.patch("/raffles/{raffle_id}/toggle")
def toggle_raffle(raffle_id: int, db: Session = Depends(get_db)):
    """Activa/desactiva un sorteo sin borrarlo — para 'apagarlo' cuando ya venció."""
    existing = db.query(Raffle).filter(Raffle.id == raffle_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Sorteo no encontrado")
    existing.active = not existing.active
    db.commit()
    db.refresh(existing)
    _reindex(db)
    return {"ok": True, "raffle": existing.to_dict()}


@router.delete("/raffles/{raffle_id}")
def delete_raffle(raffle_id: int, db: Session = Depends(get_db)):
    existing = db.query(Raffle).filter(Raffle.id == raffle_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Sorteo no encontrado")
    name = existing.name
    db.delete(existing)
    db.commit()
    _reindex(db)
    print(f"  🗑️   Sorteo eliminado: {name}")
    return {"ok": True, "removed": name}