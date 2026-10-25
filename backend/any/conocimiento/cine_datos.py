"""
Datos del cine (Cinelandia Múltiplex), leídos de la base:
  - cartelera: tabla cine_funciones (la llena el sincronizador o el panel);
  - tarifas y confitería: bloques "💵 TARIFAS…" y "🍿 CONFITERÍA…" en extra_info del local del cine.
Las tarifas se interpretan línea por línea para poder dar las del día que pregunta el cliente.
Del extra_info solo se leen esos dos bloques (el resto puede tener datos internos).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from .catalogo import locales
from .texto import normalizar, palabras

DIAS = ["LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES", "SABADO", "DOMINGO"]
_TARIFA = re.compile(
    r"(2D|3D)\s+([A-ZÁÉÍÓÚ]+)\s*⏰?\s*DESDE\s+([\d:]+\s*[AP]M)(?:\s+HASTA\s+([\d:]+\s*[AP]M))?\s*\|"
    r"\s*\$?\s*([\d.,]+)\s*\|\s*\$?\s*([\d.,]+)\s*💳?\s*\|\s*\$?\s*([\d.,]+)\s*\|\s*\$?\s*([\d.,]+)", re.I)


@dataclass
class Tarifa:
    formato: str
    dia: str
    desde: str
    hasta: str
    general: str
    general_tarjeta: str
    vip: str
    vip_tarjeta: str

    def dict(self) -> dict:
        return {"formato": self.formato, "dia": self.dia.capitalize(), "franja": f"{self.desde} a {self.hasta}".strip(),
                "general": self.general, "general_con_tarjeta_cinelandia": self.general_tarjeta,
                "vip": self.vip, "vip_con_tarjeta_cinelandia": self.vip_tarjeta}


def local_cine(db: Session):
    return next((l for l in locales(db) if l.es_cine), None)


def _extra_info_cine(db: Session) -> str:
    from models.store import Store
    loc = local_cine(db)
    if not loc:
        return ""
    s = db.get(Store, loc.id)
    return (s.extra_info or "") if s else ""


def bloque(db: Session, clave: str) -> str:
    """Bloque de extra_info cuya primera línea contiene la clave ("tarifa", "confiter")."""
    for b in re.split(r"\n\s*\n", _extra_info_cine(db)):
        if clave in normalizar(b.strip().split("\n", 1)[0]):
            return b.strip()
    return ""


def _precio(x: str) -> str:
    return "$" + x.replace(",", ".").strip()


def tarifas(db: Session) -> list[Tarifa]:
    out = []
    for linea in bloque(db, "tarifa").split("\n"):
        m = _TARIFA.search(linea)
        if m:
            fmt, dia, desde, hasta, g, gt, v, vt = m.groups()
            out.append(Tarifa(fmt.upper(), normalizar(dia).upper(), desde.strip().lower(), (hasta or "").strip().lower(),
                              _precio(g), _precio(gt), _precio(v), _precio(vt)))
    return out


def tarifas_del_dia(db: Session, cuando: datetime) -> list[dict]:
    dia = DIAS[cuando.weekday()]
    return [t.dict() for t in tarifas(db) if t.dia == dia]


def confiteria(db: Session) -> list[str]:
    b = bloque(db, "confiter")
    return [l.strip(" •\t") for l in b.split("\n")[1:] if l.strip(" •\t")]


def cartelera(db: Session) -> list:
    from models.cine_funcion import CineFuncion
    loc = local_cine(db)
    if not loc:
        return []
    return (db.query(CineFuncion).filter(CineFuncion.store_id == loc.id, CineFuncion.active.is_(True))
            .order_by(CineFuncion.title).all())


def pelicula_mencionada(funciones: list, texto: str):
    """La película que nombró el cliente (por palabras distintivas del título)."""
    pal = set(palabras(texto))
    mejor, puntaje = None, 0
    for f in funciones:
        claves = [p for p in palabras(f.title) if len(p) >= 4]
        if not claves:
            continue
        acierto = sum(1 for p in claves if p in pal)
        if acierto and acierto / len(claves) > puntaje:
            mejor, puntaje = f, acierto / len(claves)
    return mejor if puntaje >= 0.5 or (mejor and len([p for p in palabras(mejor.title) if len(p) >= 4]) > 2 and puntaje > 0) else None