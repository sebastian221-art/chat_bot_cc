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
from models.delivery_management import DeliveryManagement
from models.raffle import Raffle
from models.marketing import Marketing
from models.cine_funcion import CineFuncion
from models.store_photo import StorePhoto, VALID_LABELS as STORE_PHOTO_LABELS
from models.entity_photo import EntityPhoto, VALID_ENTITY_TYPES, ENTITY_LABELS, get_entity_photo
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

class MarketingIn(BaseModel):
    title: str
    description: Optional[str] = ""
    store_id: Optional[int] = None
    priority: Optional[int] = 3
    valid_until: Optional[str] = ""
    active: Optional[bool] = True
    photo_url: Optional[str] = ""

class CineFuncionIn(BaseModel):
    store_id: int
    title: str
    showtimes: Optional[str] = ""
    description: Optional[str] = ""
    is_premiere: Optional[bool] = False
    active: Optional[bool] = True

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

class StorePhotoIn(BaseModel):
    photo_url: str
    label: str = "portada"

class EntityPhotoIn(BaseModel):
    photo_url: str
    label: str


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


def _attach_photos(db: Session, entity_type: str, items: list, id_field: str = "id") -> list:
    """
    Agrega el arreglo "photos" a cada item de una lista (eventos,
    sorteos, conocimiento, zonas) — con UNA sola consulta a la base de
    datos para todos, en vez de una consulta por cada item.
    """
    if not items:
        return []
    ids = [getattr(i, id_field) for i in items]
    photos = (
        db.query(EntityPhoto)
        .filter(EntityPhoto.entity_type == entity_type, EntityPhoto.entity_id.in_(ids))
        .all()
    )
    by_id = {}
    for p in photos:
        by_id.setdefault(p.entity_id, []).append(p.to_dict())

    result = []
    for item in items:
        d = item.to_dict()
        d["photos"] = by_id.get(getattr(item, id_field), [])
        result.append(d)
    return result


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

    # Traemos TODAS las tiendas existentes de una sola vez, en vez de
    # consultar la base de datos una vez por cada fila del CSV — con
    # archivos grandes (ej. 138 locales), 138 idas y vueltas separadas
    # a la base de datos era otra causa real de que la importación
    # tardara tanto que Railway cortaba la conexión.
    existing_stores = {
        (s.name, s.local_number): s
        for s in db.query(Store).all()
    }

    for i, raw in enumerate(raw_rows, start=2):  # fila 2 = primera fila de datos (1 es el header)
        mapped = _map_row(raw, "store")
        if not mapped.get("name"):
            skipped += 1
            errors.append(f"Fila {i}: sin nombre, se saltó")
            continue

        existing = existing_stores.get((mapped["name"], mapped.get("local_number")))
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

    # Envolvemos el commit en un try/except explícito: si algún dato del
    # CSV viola una restricción de la base de datos (ej. un texto más
    # largo de lo que acepta una columna — exactamente lo que pasó acá
    # con un local_number de 25 caracteres en una columna de 20), esto
    # se convierte en un error CLARO con el mensaje real, en vez de un
    # 500 sin manejar. Un 500 sin manejar no lleva los encabezados de
    # CORS, y el navegador lo reporta como "bloqueado por CORS" — un
    # síntoma engañoso que no tiene nada que ver con CORS de verdad.
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Error al importar locales: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"No se pudo guardar en la base de datos — probablemente algún dato del CSV es demasiado largo o inválido. Detalle técnico: {str(e)[:300]}",
        )

    _reindex(db)
    print(f"  📥  Import locales: {created} nuevos, {updated} actualizados, {skipped} saltados")
    return {"ok": True, "created": created, "updated": updated, "skipped": skipped, "errors": errors[:20]}


# ══════════════════════════════════════════════════════════════════
# EVENTS  (ahora en base de datos — persiste entre redeploys)
# ══════════════════════════════════════════════════════════════════

@router.get("/events")
def list_events(db: Session = Depends(get_db)):
    events = db.query(Event).order_by(Event.date).all()
    return _attach_photos(db, "event", events)


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
    existing_events = {(e.name, e.date): e for e in db.query(Event).all()}

    for i, raw in enumerate(raw_rows, start=2):
        mapped = _map_row(raw, "event")
        if not mapped.get("name") or not mapped.get("date"):
            skipped += 1
            errors.append(f"Fila {i}: falta nombre o fecha, se saltó")
            continue

        existing = existing_events.get((mapped["name"], mapped["date"]))
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
# MARKETING  (promociones de tiendas, del cine, o generales del mall)
# ══════════════════════════════════════════════════════════════════

@router.get("/marketing")
def list_marketing(db: Session = Depends(get_db)):
    promos = db.query(Marketing).order_by(Marketing.priority.desc(), Marketing.created_at.desc()).all()
    return _attach_photos(db, "marketing", promos)


@router.post("/marketing", status_code=201)
def create_marketing(promo: MarketingIn, db: Session = Depends(get_db)):
    new_promo = Marketing(**promo.model_dump())
    db.add(new_promo)
    db.commit()
    db.refresh(new_promo)
    _reindex(db)
    print(f"  ✅  Promoción de marketing agregada: {new_promo.title} (id={new_promo.id})")
    return {"ok": True, "marketing": new_promo.to_dict()}


@router.put("/marketing/{marketing_id}")
def update_marketing(marketing_id: int, promo: MarketingIn, db: Session = Depends(get_db)):
    existing = db.query(Marketing).filter(Marketing.id == marketing_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Promoción no encontrada")
    for field, value in promo.model_dump().items():
        setattr(existing, field, value)
    db.commit()
    db.refresh(existing)
    _reindex(db)
    print(f"  ✅  Promoción de marketing actualizada: {existing.title} (id={existing.id})")
    return {"ok": True, "marketing": existing.to_dict()}


@router.delete("/marketing/{marketing_id}")
def delete_marketing(marketing_id: int, db: Session = Depends(get_db)):
    existing = db.query(Marketing).filter(Marketing.id == marketing_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Promoción no encontrada")
    title = existing.title
    db.delete(existing)
    db.commit()
    _reindex(db)
    print(f"  🗑️   Promoción de marketing eliminada: {title}")
    return {"ok": True, "removed": title}


# ══════════════════════════════════════════════════════════════════
# CARTELERA DE CINE  (funciones/estrenos — ligadas a la tienda del Cine)
# ══════════════════════════════════════════════════════════════════

@router.get("/cine-funciones")
def list_cine_funciones(store_id: int, db: Session = Depends(get_db)):
    """Siempre filtrado por store_id — la cartelera se administra desde el local del Cine específico."""
    funciones = (
        db.query(CineFuncion)
        .filter(CineFuncion.store_id == store_id)
        .order_by(CineFuncion.is_premiere.desc(), CineFuncion.title)
        .all()
    )
    return [f.to_dict() for f in funciones]


@router.post("/cine-funciones", status_code=201)
def create_cine_funcion(funcion: CineFuncionIn, db: Session = Depends(get_db)):
    new_funcion = CineFuncion(**funcion.model_dump())
    db.add(new_funcion)
    db.commit()
    db.refresh(new_funcion)
    _reindex(db)
    print(f"  🎬  Función de cine agregada: {new_funcion.title} (id={new_funcion.id})")
    return {"ok": True, "funcion": new_funcion.to_dict()}


@router.put("/cine-funciones/{funcion_id}")
def update_cine_funcion(funcion_id: int, funcion: CineFuncionIn, db: Session = Depends(get_db)):
    existing = db.query(CineFuncion).filter(CineFuncion.id == funcion_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Función no encontrada")
    for field, value in funcion.model_dump().items():
        setattr(existing, field, value)
    db.commit()
    db.refresh(existing)
    _reindex(db)
    print(f"  🎬  Función de cine actualizada: {existing.title} (id={existing.id})")
    return {"ok": True, "funcion": existing.to_dict()}


@router.delete("/cine-funciones/{funcion_id}")
def delete_cine_funcion(funcion_id: int, db: Session = Depends(get_db)):
    existing = db.query(CineFuncion).filter(CineFuncion.id == funcion_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Función no encontrada")
    title = existing.title
    db.delete(existing)
    db.commit()
    _reindex(db)
    print(f"  🗑️   Función de cine eliminada: {title}")
    return {"ok": True, "removed": title}


# ══════════════════════════════════════════════════════════════════
# BASE DE CONOCIMIENTO LIBRE
# ══════════════════════════════════════════════════════════════════

@router.get("/knowledge")
def list_knowledge(db: Session = Depends(get_db)):
    entries = db.query(KnowledgeEntry).order_by(KnowledgeEntry.title).all()
    return _attach_photos(db, "knowledge", entries)


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
    existing_knowledge = {k.title: k for k in db.query(KnowledgeEntry).all()}

    for i, raw in enumerate(raw_rows, start=2):
        mapped = _map_row(raw, "knowledge")
        if not mapped.get("title") or not mapped.get("content"):
            skipped += 1
            errors.append(f"Fila {i}: falta título o contenido, se saltó")
            continue

        existing = existing_knowledge.get(mapped["title"])
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
    photos = _attach_photos(db, "zone", zones)
    result = []
    for z, d in zip(zones, photos):
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
    return _attach_photos(db, "raffle", raffles)


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


# ══════════════════════════════════════════════════════════════════
# GESTIONES DE DOMICILIO — flujo completo (carta + datos + link)
# Distinto de /delivery-transfers, que es la simple mención sin datos.
# ══════════════════════════════════════════════════════════════════

@router.get("/delivery-managements/stats")
def delivery_management_stats(db: Session = Depends(get_db)):
    today = datetime.now(timezone.utc).date()
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)

    base_query = db.query(DeliveryManagement).filter(DeliveryManagement.created_at >= week_ago)

    total_week = base_query.count()
    completed_week = base_query.filter(DeliveryManagement.status == "completed").count()
    closed_week = base_query.filter(DeliveryManagement.status == "closed").count()
    abandoned_week = base_query.filter(DeliveryManagement.status == "collecting").count()

    total_today = db.query(DeliveryManagement).filter(func.date(DeliveryManagement.created_at) == today).count()

    top_stores = (
        db.query(DeliveryManagement.store_name, func.count(DeliveryManagement.id).label("total"))
        .filter(DeliveryManagement.created_at >= week_ago, DeliveryManagement.status == "completed")
        .group_by(DeliveryManagement.store_name)
        .order_by(desc("total"))
        .limit(10)
        .all()
    )

    return {
        "total_today": total_today,
        "total_this_week": total_week,
        "completed_this_week": completed_week,
        "closed_this_week": closed_week,
        "abandoned_this_week": abandoned_week,
        "top_stores": [{"store": s, "total": t} for s, t in top_stores],
    }


@router.get("/delivery-managements")
def list_delivery_managements(db: Session = Depends(get_db)):
    rows = (
        db.query(DeliveryManagement)
        .order_by(DeliveryManagement.created_at.desc())
        .limit(100)
        .all()
    )
    return [r.to_dict() for r in rows]


# ══════════════════════════════════════════════════════════════════
# GALERÍA DE FOTOS — TIENDAS (tabla dedicada, portada/carta/otra)
# ══════════════════════════════════════════════════════════════════

@router.get("/stores/{store_id}/photos")
def list_store_photos(store_id: int, db: Session = Depends(get_db)):
    photos = (
        db.query(StorePhoto)
        .filter(StorePhoto.store_id == store_id)
        .order_by(StorePhoto.created_at.asc())
        .all()
    )
    return [p.to_dict() for p in photos]


@router.post("/stores/{store_id}/photos", status_code=201)
def add_store_photo(store_id: int, photo: StorePhotoIn, db: Session = Depends(get_db)):
    store = db.query(Store).filter(Store.id == store_id).first()
    if not store:
        raise HTTPException(status_code=404, detail="Tienda no encontrada")
    if photo.label not in STORE_PHOTO_LABELS:
        raise HTTPException(status_code=400, detail=f"Etiqueta inválida — debe ser una de: {STORE_PHOTO_LABELS}")

    new_photo = StorePhoto(store_id=store_id, photo_url=photo.photo_url, label=photo.label)
    db.add(new_photo)
    db.commit()
    db.refresh(new_photo)
    _reindex(db)
    print(f"  ✅  Foto agregada a {store.name} ({photo.label})")
    return {"ok": True, "photo": new_photo.to_dict()}


@router.delete("/stores/{store_id}/photos/{photo_id}")
def delete_store_photo(store_id: int, photo_id: int, db: Session = Depends(get_db)):
    photo = db.query(StorePhoto).filter(StorePhoto.id == photo_id, StorePhoto.store_id == store_id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="Foto no encontrada")
    db.delete(photo)
    db.commit()
    _reindex(db)
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════
# GALERÍA DE FOTOS GENÉRICA — Eventos, Sorteos, Conocimiento, Zonas
# Una sola tabla y 3 endpoints sirven para los 4 tipos de contenido,
# en vez de repetir la misma tabla y lógica 4 veces.
# ══════════════════════════════════════════════════════════════════

@router.get("/photos/{entity_type}/{entity_id}")
def list_entity_photos(entity_type: str, entity_id: int, db: Session = Depends(get_db)):
    if entity_type not in VALID_ENTITY_TYPES:
        raise HTTPException(status_code=400, detail=f"Tipo inválido — debe ser uno de: {VALID_ENTITY_TYPES}")
    photos = (
        db.query(EntityPhoto)
        .filter(EntityPhoto.entity_type == entity_type, EntityPhoto.entity_id == entity_id)
        .order_by(EntityPhoto.created_at.asc())
        .all()
    )
    return [p.to_dict() for p in photos]


@router.post("/photos/{entity_type}/{entity_id}", status_code=201)
def add_entity_photo(entity_type: str, entity_id: int, photo: EntityPhotoIn, db: Session = Depends(get_db)):
    if entity_type not in VALID_ENTITY_TYPES:
        raise HTTPException(status_code=400, detail=f"Tipo inválido — debe ser uno de: {VALID_ENTITY_TYPES}")
    valid_labels = ENTITY_LABELS.get(entity_type, [])
    if photo.label not in valid_labels:
        raise HTTPException(status_code=400, detail=f"Etiqueta inválida para {entity_type} — debe ser una de: {valid_labels}")

    new_photo = EntityPhoto(entity_type=entity_type, entity_id=entity_id, photo_url=photo.photo_url, label=photo.label)
    db.add(new_photo)
    db.commit()
    db.refresh(new_photo)
    _reindex(db)
    print(f"  ✅  Foto agregada a {entity_type} #{entity_id} ({photo.label})")
    return {"ok": True, "photo": new_photo.to_dict()}


@router.delete("/photos/{entity_type}/{entity_id}/{photo_id}")
def delete_entity_photo(entity_type: str, entity_id: int, photo_id: int, db: Session = Depends(get_db)):
    photo = (
        db.query(EntityPhoto)
        .filter(EntityPhoto.id == photo_id, EntityPhoto.entity_type == entity_type, EntityPhoto.entity_id == entity_id)
        .first()
    )
    if not photo:
        raise HTTPException(status_code=404, detail="Foto no encontrada")
    db.delete(photo)
    db.commit()
    _reindex(db)
    return {"ok": True}

# ══════════════════════════════════════════════════════════════════
# FLUJO DEL BOT  (solo lectura — para el panel de visualización)
# ══════════════════════════════════════════════════════════════════

@router.get("/flujo-bot")
def get_flujo_bot(db: Session = Depends(get_db)):
    """
    Expone (SOLO LECTURA) toda la estructura real de cómo responde el
    bot: los prompts, las intenciones y sus palabras clave, las
    categorías de búsqueda justa, y un conteo de la información que
    alimenta al bot. Sirve para el panel 'Flujo del Bot' — no modifica
    nada, solo hace visible lo que ya existe en el código.
    """
    from services.ai import BASE_PERSONA, PROMPTS, INTENT_RULES
    from services.category_search import CATEGORIAS_BUSQUEDA, INTENCION_BUSQUEDA
    from models.store import Store
    from models.knowledge import KnowledgeEntry
    from models.event import Event
    from models.raffle import Raffle
    from models.marketing import Marketing

    # Los prompts, sin repetir BASE_PERSONA en cada uno (se muestra aparte)
    prompts_limpios = {}
    for intent, texto in PROMPTS.items():
        especifico = texto.replace(BASE_PERSONA, "").strip()
        prompts_limpios[intent] = especifico

    # Descripción legible de qué hace cada intención
    descripcion_intents = {
        "saludo": "Cuando el cliente saluda. Distingue si es conversación nueva o continuación (ventana de 4 horas).",
        "horario": "Preguntas sobre horarios de apertura/cierre del mall o locales.",
        "ubicacion": "Ubicación del CENTRO COMERCIAL en sí (manda el pin real). No se activa si preguntan por dónde comprar algo.",
        "estado_pedido": "Preguntas sobre el estado de un pedido ya hecho (redirige al local).",
        "domicilio": "Prompt sin uso actual — el sistema de domicilios lo maneja store_transfer.py.",
        "categoria": "Prompt de respaldo para listas por categoría (la búsqueda justa por categoría lo cubre antes).",
        "general": "Todo lo demás: consultas sobre tiendas, productos, servicios. Aquí vive el comportamiento propositivo.",
    }

    # Conteo de la información que alimenta al bot
    conteo_datos = {
        "tiendas": db.query(Store).count(),
        "base_conocimiento": db.query(KnowledgeEntry).count(),
        "eventos": db.query(Event).count(),
        "sorteos": db.query(Raffle).count(),
        "promociones": db.query(Marketing).count(),
    }

    # Rutas directas — respuestas que NO usan la IA ni los prompts, sino
    # que se arman en el código. Describen la parte "mecánica" del bot.
    rutas_directas = [
        {
            "nombre": "Número de una tienda",
            "cuando": "El cliente pide el teléfono/contacto de un local (ej. \"pásame el número de Zirus Pizza\").",
            "archivo": "services/store_transfer.py",
            "que_hace": "Responde con el número, el link directo de WhatsApp y una pregunta de seguimiento — texto armado en el código, sin IA.",
        },
        {
            "nombre": "Cartelera de cine",
            "cuando": "Preguntan por películas, cartelera, funciones o estrenos.",
            "archivo": "services/cine.py",
            "que_hace": "Busca la tienda del cine y lista sus películas activas con horarios, directamente desde la base de datos. Si nombran una película puntual, da solo esa con su póster.",
        },
        {
            "nombre": "Gestión de domicilio",
            "cuando": "El cliente pide ayuda para hacer un pedido a domicilio, o ya está en medio de una gestión.",
            "archivo": "services/store_transfer.py + delivery_management.py",
            "que_hace": "Valida horario, muestra la carta, recolecta los datos (nombre, celular, dirección, pedido, pago), detecta cancelaciones y arma el pedido final — un flujo paso a paso sin prompts conversacionales.",
        },
        {
            "nombre": "Búsqueda justa por categoría",
            "cuando": "Preguntan por un TIPO de producto (ej. \"hamburguesas\", \"zapatos formales\") sin nombrar una tienda.",
            "archivo": "services/category_search.py + rag.py",
            "que_hace": "Lista TODOS los locales de esa categoría en orden alfabético neutral, sin destacar a ninguno — equidad comercial garantizada, sin IA.",
        },
        {
            "nombre": "Ubicación del mall",
            "cuando": "Preguntan dónde queda el centro comercial en sí (no una tienda).",
            "archivo": "routers/webhook.py",
            "que_hace": "Adjunta el pin de ubicación real (GPS) del mall junto con la respuesta.",
        },
        {
            "nombre": "Navegación por QR",
            "cuando": "El cliente escanea un código QR de una zona del mall.",
            "archivo": "services/navigation.py",
            "que_hace": "Reconoce la zona escaneada y orienta al cliente desde ese punto.",
        },
    ]

    return {
        "persona_base": BASE_PERSONA,
        "intenciones": [
            {
                "nombre": intent,
                "descripcion": descripcion_intents.get(intent, ""),
                "palabras_clave": INTENT_RULES.get(intent, []),
                "prompt_especifico": prompts_limpios.get(intent, ""),
            }
            for intent in ["saludo", "horario", "ubicacion", "estado_pedido", "domicilio", "categoria", "general"]
        ],
        "rutas_directas": rutas_directas,
        "busqueda_categoria": {
            "palabras_intencion": INTENCION_BUSQUEDA,
            "categorias": [
                {"nombre": nombre, "terminos": terminos}
                for nombre, terminos in CATEGORIAS_BUSQUEDA.items()
            ],
        },
        "conteo_datos": conteo_datos,
    }

# ══════════════════════════════════════════════════════════════════
# ORQUESTADOR  (mapa de herramientas, trazas, y control del switch)
# ══════════════════════════════════════════════════════════════════

@router.get("/orquestador/mapa")
def get_orquestador_mapa(db: Session = Depends(get_db)):
    """Expone el registro de herramientas + el estado del switch — para la vista 'mapa' del panel."""
    from services.orchestrator_tools import HERRAMIENTAS
    from services.orchestrator_switch import get_config
    return {
        "herramientas": HERRAMIENTAS,
        "switch": get_config(db),
    }


@router.get("/orquestador/trazas")
def get_orquestador_trazas(limit: int = 50, modo: str = None, fecha: str = None, db: Session = Depends(get_db)):
    """
    Trazas del orquestador — para la vista 'trazas en vivo'.
    - modo: filtra 'prueba' o 'produccion'
    - fecha: filtra por día (formato YYYY-MM-DD). Si no se da, trae las más recientes.
    """
    from models.orchestrator_trace import OrchestratorTrace
    from sqlalchemy import func as sqlfunc
    q = db.query(OrchestratorTrace)
    if modo:
        q = q.filter(OrchestratorTrace.modo == modo)
    if fecha:
        # Filtrar por el día indicado (comparando solo la parte de fecha)
        try:
            q = q.filter(sqlfunc.date(OrchestratorTrace.created_at) == fecha)
        except Exception:
            pass
    trazas = q.order_by(OrchestratorTrace.created_at.desc()).limit(min(limit, 200)).all()
    return [t.to_dict() for t in trazas]


@router.get("/orquestador/trazas/fechas")
def get_orquestador_trazas_fechas(modo: str = None, db: Session = Depends(get_db)):
    """Devuelve las fechas (días) que tienen trazas, para el selector de fecha del panel."""
    from models.orchestrator_trace import OrchestratorTrace
    from sqlalchemy import func as sqlfunc
    q = db.query(sqlfunc.date(OrchestratorTrace.created_at).label("dia"))
    if modo:
        q = q.filter(OrchestratorTrace.modo == modo)
    fechas = q.distinct().order_by(sqlfunc.date(OrchestratorTrace.created_at).desc()).all()
    return [str(f.dia) for f in fechas if f.dia]


@router.delete("/orquestador/trazas")
def limpiar_orquestador_trazas(fecha: str = None, todo: bool = False, db: Session = Depends(get_db)):
    """
    Limpia trazas para liberar memoria.
    - Si 'todo=true': borra TODAS las trazas.
    - Si 'fecha=YYYY-MM-DD': borra solo las de ESE día.
    - Si no se da nada: borra las de días ANTERIORES a hoy (deja solo hoy).
    """
    from models.orchestrator_trace import OrchestratorTrace
    from sqlalchemy import func as sqlfunc
    from datetime import date
    q = db.query(OrchestratorTrace)
    if todo:
        borradas = q.delete(synchronize_session=False)
    elif fecha:
        borradas = q.filter(sqlfunc.date(OrchestratorTrace.created_at) == fecha).delete(synchronize_session=False)
    else:
        # Borra todo lo anterior a hoy (deja solo el día actual)
        hoy = str(date.today())
        borradas = q.filter(sqlfunc.date(OrchestratorTrace.created_at) < hoy).delete(synchronize_session=False)
    db.commit()
    print(f"  🧹  Trazas limpiadas: {borradas}")
    return {"ok": True, "borradas": borradas}


class SwitchIn(BaseModel):
    modo: str
    telefonos_prueba: Optional[str] = None


@router.post("/orquestador/switch")
def set_orquestador_switch(body: SwitchIn, db: Session = Depends(get_db)):
    """Cambia el modo del switch (off / solo_yo / produccion)."""
    from services.orchestrator_switch import set_modo
    try:
        cfg = set_modo(db, body.modo, body.telefonos_prueba)
        print(f"  🔀  Switch del orquestador → {cfg['modo']}")
        return {"ok": True, "switch": cfg}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))