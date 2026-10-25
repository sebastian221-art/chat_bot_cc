"""Lee los mensajes fijos y listas de frases de datos/mensajes.yaml (editable sin tocar código)."""
from __future__ import annotations

import os

import yaml

_RUTA = os.path.join(os.path.dirname(__file__), "..", "datos", "mensajes.yaml")
_cache: dict | None = None


def _datos() -> dict:
    global _cache
    if _cache is None:
        with open(_RUTA, encoding="utf-8") as f:
            _cache = yaml.safe_load(f) or {}
    return _cache


def recargar():
    global _cache
    _cache = None


def valor(clave: str, defecto=None):
    return _datos().get(clave, defecto)


def texto(clave: str, **variables) -> str:
    d = _datos()
    t = d.get(clave, "")
    if isinstance(t, dict):
        t = t.get("texto", "")
    base = {"correo": d.get("correo_datos", ""), "linea": d.get("linea_mall", ""),
            "linea_link": d.get("linea_mall_link", ""), "punto": d.get("punto_informacion", "")}
    base.update(variables)
    try:
        return t.format(**base).strip()
    except (KeyError, IndexError):
        return t.strip()


def frases(clave: str) -> list[str]:
    return list(_datos().get(clave) or [])
