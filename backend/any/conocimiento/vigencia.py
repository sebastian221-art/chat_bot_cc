"""
Fechas de eventos, sorteos y promociones, que en la base son texto libre:
  "31/10/2026" · "23/10/2026 al 25/10/2026" · "Todos los domingos" · "" · "2026-11-08"
Se compara siempre contra la fecha del contexto (ctx.ahora), no contra date.today():
así el banco de pruebas puede simular otro día.
"""
from __future__ import annotations

import re
from datetime import date

_DMY = re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})\b")
_YMD = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")


def fechas(texto: str | None) -> list[date]:
    out = []
    t = texto or ""
    for a, m, d in _YMD.findall(t):
        try:
            out.append(date(int(a), int(m), int(d)))
        except ValueError:
            pass
    for d, m, a in _DMY.findall(_YMD.sub(" ", t)):
        a = int(a) + (2000 if len(a) == 2 else 0)
        try:
            out.append(date(a, int(m), int(d)))
        except ValueError:
            pass
    return out


def fecha_inicio(texto: str | None) -> date | None:
    f = fechas(texto)
    return min(f) if f else None


def fecha_final(texto: str | None) -> date | None:
    f = fechas(texto)
    return max(f) if f else None


def vigente(texto: str | None, hoy: date) -> bool:
    """Sin fecha interpretable ("Todos los domingos", vacío) se considera vigente."""
    fin = fecha_final(texto)
    return fin is None or fin >= hoy


def dias_para(texto: str | None, hoy: date) -> int | None:
    ini = fecha_inicio(texto)
    return (ini - hoy).days if ini else None