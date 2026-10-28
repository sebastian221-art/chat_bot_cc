"""Directorio de áreas del centro comercial (any/datos/areas.yaml): a qué área va cada tema y su contacto."""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from .texto import normalizar

RUTA = Path(__file__).resolve().parent.parent / "datos" / "areas.yaml"


@lru_cache(maxsize=1)
def areas() -> list[dict]:
    try:
        import yaml
        return yaml.safe_load(RUTA.read_text(encoding="utf-8")) or []
    except Exception:
        return []


def ficha_area(a: dict) -> dict:
    from .texto import link_whatsapp
    tel = str(a.get("telefono") or "")
    d = {"area": a.get("area"), "responsable": a.get("responsable"), "telefono": tel,
         "whatsapp": link_whatsapp(tel.split("·")[0]) if tel else None,
         "correo": a.get("correo"), "ubicacion": a.get("ubicacion"), "horario": a.get("horario")}
    return {k: v for k, v in d.items() if v}


def area_para(texto: str) -> dict | None:
    """El área de la que habla el mensaje («queja a la gerencia» → Gerencia). La más específica gana."""
    n = normalizar(texto or "")
    mejor, largo = None, 0
    for a in areas():
        for t in [a.get("area", "")] + list(a.get("temas") or []):
            tn = normalizar(str(t))
            if tn and re.search(rf"\b{re.escape(tn)}\b", n) and len(tn) > largo:
                mejor, largo = a, len(tn)
    return mejor


def directorio() -> list[dict]:
    return [ficha_area(a) for a in areas()]