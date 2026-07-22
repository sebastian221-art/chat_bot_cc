"""
routers/api.py
Endpoints que usa el panel de administración:
  GET/POST/PUT/DELETE /stores
  GET/POST/PUT/DELETE /events
  GET                 /stats
  GET                 /conversations
"""
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from pydantic import BaseModel

from models.database import get_db
from models.conversation import Conversation
from models.store import Store
from services.rag import load_stores_to_rag

logger = logging.getLogger("mall_bot")
router = APIRouter(tags=["panel"])

DATA_PATH = Path(__file__).parent.parent / "data" / "tiendas.json"

# ── Pydantic schemas ──────────────────────────────────────────────

class StoreIn(BaseModel):
    name: str
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


# ── Helpers para leer/escribir tiendas.json ───────────────────────

def _read_json():
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def _write_json(data: dict):
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    # Reindexar RAG automáticamente al guardar
    try:
        load_stores_to_rag()
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

    # Tiendas activas
    data = _read_json()
    total_stores = len(data.get("stores", []))
    total_events = len(data.get("events", []))

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
# STORES
# ══════════════════════════════════════════════════════════════════

@router.get("/stores")
def list_stores():
    data = _read_json()
    return data.get("stores", [])


@router.post("/stores", status_code=201)
def create_store(store: StoreIn):
    data = _read_json()
    stores = data.get("stores", [])
    new_store = store.model_dump()
    stores.append(new_store)
    data["stores"] = stores
    _write_json(data)
    print(f"  ✅  Tienda agregada: {store.name}")
    return {"ok": True, "store": new_store}


@router.put("/stores/{index}")
def update_store(index: int, store: StoreIn):
    data = _read_json()
    stores = data.get("stores", [])
    if index < 0 or index >= len(stores):
        raise HTTPException(status_code=404, detail="Tienda no encontrada")
    stores[index] = store.model_dump()
    data["stores"] = stores
    _write_json(data)
    print(f"  ✅  Tienda actualizada: {store.name}")
    return {"ok": True, "store": stores[index]}


@router.delete("/stores/{index}")
def delete_store(index: int):
    data = _read_json()
    stores = data.get("stores", [])
    if index < 0 or index >= len(stores):
        raise HTTPException(status_code=404, detail="Tienda no encontrada")
    removed = stores.pop(index)
    data["stores"] = stores
    _write_json(data)
    print(f"  🗑️   Tienda eliminada: {removed['name']}")
    return {"ok": True, "removed": removed["name"]}


# ══════════════════════════════════════════════════════════════════
# EVENTS
# ══════════════════════════════════════════════════════════════════

@router.get("/events")
def list_events():
    data = _read_json()
    return data.get("events", [])


@router.post("/events", status_code=201)
def create_event(event: EventIn):
    data = _read_json()
    events = data.get("events", [])
    new_event = event.model_dump()
    events.append(new_event)
    data["events"] = events
    _write_json(data)
    print(f"  ✅  Evento agregado: {event.name}")
    return {"ok": True, "event": new_event}


@router.put("/events/{index}")
def update_event(index: int, event: EventIn):
    data = _read_json()
    events = data.get("events", [])
    if index < 0 or index >= len(events):
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    events[index] = event.model_dump()
    data["events"] = events
    _write_json(data)
    print(f"  ✅  Evento actualizado: {event.name}")
    return {"ok": True, "event": events[index]}


@router.delete("/events/{index}")
def delete_event(index: int):
    data = _read_json()
    events = data.get("events", [])
    if index < 0 or index >= len(events):
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    removed = events.pop(index)
    data["events"] = events
    _write_json(data)
    print(f"  🗑️   Evento eliminado: {removed['name']}")
    return {"ok": True, "removed": removed["name"]}