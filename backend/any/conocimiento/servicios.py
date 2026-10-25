"""Datos generales del centro comercial (tabla mall_info, editable desde el panel)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from .texto import normalizar


def _float(v) -> float | None:
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def info_mall(db: Session) -> dict:
    from models.mall_info import MallInfo
    mi = db.query(MallInfo).first()
    if not mi:
        return {}
    d = {"nombre": mi.name, "direccion": mi.address, "horario_general": mi.general_schedule,
         "telefono": mi.phone, "parqueadero": mi.parking, "wifi": mi.wifi,
         "latitud": _float(mi.latitude), "longitud": _float(mi.longitude)}
    return {k: v for k, v in d.items() if v not in (None, "")}


def local_de_servicio(db: Session, nombre: str):
    """Locales internos del mall (Administración, Punto de Información, Parqueaderos)."""
    from .catalogo import locales
    n = normalizar(nombre)
    for l in locales(db):
        if l.es_servicio and normalizar(l.nombre) == n:
            return l
    return None
