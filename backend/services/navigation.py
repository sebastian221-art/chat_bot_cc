"""
services/navigation.py

Navegación indoor por QR: cada QR pegado en una zona del mall codifica
un mensaje de WhatsApp pre-llenado con un código de zona (ej. "Zona A5").
Cuando el bot detecta ese código, sabe dónde está el cliente y puede
darle indicaciones hacia la tienda que busca.

Bono: cada escaneo queda registrado (ZoneScan) — con eso se arman
mapas de calor de tráfico real por zona, sin cámaras ni sensores.
"""
import re
import logging
from sqlalchemy.orm import Session
from models.zone import Zone
from models.zone_scan import ZoneScan
from models.store import Store
from services.ai import generate_response

logger = logging.getLogger("mall_bot")

ZONE_PATTERN = re.compile(r"zona\s+([a-z0-9\-]+)", re.IGNORECASE)


def parse_zone_code(message: str) -> str | None:
    """Detecta un código de zona tipo 'Zona A5' en el mensaje. None si no hay."""
    match = ZONE_PATTERN.search(message)
    return match.group(1).upper() if match else None


def find_zone(db: Session, code: str) -> Zone | None:
    return db.query(Zone).filter(Zone.code == code.upper()).first()


def log_zone_scan(db: Session, phone_number: str, zone_code: str):
    """Registra el escaneo SIEMPRE, aunque la zona no esté configurada aún —
    así no perdemos el dato de tráfico mientras se termina de cargar el mapa."""
    db.add(ZoneScan(phone_number=phone_number, zone_code=zone_code.upper()))
    db.commit()


def get_last_scanned_zone(db: Session, phone_number: str) -> Zone | None:
    """Última zona que este número escaneó — para recordar el contexto
    si el cliente responde con el nombre de la tienda en el siguiente mensaje."""
    last_scan = (
        db.query(ZoneScan)
        .filter(ZoneScan.phone_number == phone_number)
        .order_by(ZoneScan.timestamp.desc())
        .first()
    )
    if not last_scan:
        return None
    return find_zone(db, last_scan.zone_code)


def build_zone_not_found_message() -> str:
    return (
        "No reconozco ese código de zona todavía 🤔 (puede que el QR sea nuevo). "
        "Cuéntame igual qué tienda o local buscas y te ayudo con la ubicación general."
    )


def build_zone_confirmation_message(zone: Zone) -> str:
    return (
        f"📍 ¡Perfecto! Veo que estás en *{zone.description}* ({zone.floor}).\n\n"
        f"¿A qué tienda o local quieres llegar? Dime el nombre y te doy las indicaciones "
        f"exactas desde donde estás."
    )


async def build_navigation_response(zone: Zone, store: Store, user_name: str) -> str:
    """
    Le pasa el contexto (dónde está el cliente + dónde está la tienda)
    a la IA para que redacte indicaciones naturales — mismo motor y
    personalidad que cualquier otra respuesta de Any.
    """
    query = (
        f"El cliente escaneó un código QR y está físicamente parado en: "
        f"{zone.description} ({zone.floor}). Quiere llegar a la tienda '{store.name}' "
        f"(Local {store.local_number or 'S/N'}), que está en {store.floor}"
        f"{', ubicación: ' + store.location_hint if store.location_hint else ''}. "
        f"Dale indicaciones claras y breves de cómo llegar desde donde está hasta esa tienda."
    )
    texto, _ = await generate_response(user_message=query, user_name=user_name, conversation_history=[])
    return texto