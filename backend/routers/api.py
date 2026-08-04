"""
routers/api.py
Endpoints que usa el panel de administración:
  GET/POST/PUT/DELETE /stores   (base de datos)
  GET/POST/PUT/DELETE /events   (base de datos)
  GET                 /stats
  GET                 /conversations
"""
import logging
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from pydantic import BaseModel

from models.database import get_db
from models.conversation import Conversation
from models.store import Store
from models.event import Event
from services.rag import load_stores_to_rag

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

class EventIn(BaseModel):
    name: str
    date: str
    time: str
    location: str
    description: Optional[str] = ""
    priority: Optional[int] = 3


def _reindex(db: Session):
    try:
        load_stores_to_rag(db)
    except Exception as e:
        logger.warning(f"RAG no se pudo actualizar: {e}")


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
    return [
        {
            "phone": r.phone_number,
            "name":  r.user_name,
            "total": r.total,
            "last_seen": str(r.last_seen),
        }
        for r in rows
    ]


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