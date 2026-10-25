"""Fotos de eventos, sorteos, promociones y películas (tabla entity_photos, galería del panel)."""
from __future__ import annotations

from sqlalchemy.orm import Session


def fotos_de(db: Session, tipo: str, entidad_id: int) -> dict:
    """{etiqueta: url} — tipo: event | raffle | marketing | cine_funcion | knowledge | zone."""
    try:
        from models.entity_photo import EntityPhoto
        filas = (db.query(EntityPhoto).filter(EntityPhoto.entity_type == tipo, EntityPhoto.entity_id == entidad_id)
                 .order_by(EntityPhoto.id).all())
    except Exception:
        db.rollback()
        return {}
    out: dict = {}
    for f in filas:
        out.setdefault(f.label or "otra", f.photo_url)
    return out


def foto_principal(db: Session, tipo: str, entidad_id: int, respaldo: str | None = None,
                   orden=("afiche", "poster", "principal", "premio", "otra")) -> str | None:
    fotos = fotos_de(db, tipo, entidad_id)
    for etiqueta in orden:
        if fotos.get(etiqueta):
            return fotos[etiqueta]
    return respaldo or None