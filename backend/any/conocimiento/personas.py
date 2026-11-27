"""Profesionales por nombre (27/11: «Quiero una cita con la dra. Juliana Pinto» → «no está registrada», y en la
pregunta siguiente Any la listó entre los especialistas de Mediwork).

Los nombres de médicos, odontólogos y asesores vienen dentro de la descripción del local («nutricionista Juliana
Pinto; psicología clínica Dra. Zaidy García…»). El directorio del cerebro corta la descripción, así que el nombre no
se ve. Aquí se busca por código: dos palabras seguidas del mensaje que en la descripción de un local aparecen juntas
y con mayúscula (un nombre propio)."""
from __future__ import annotations

import re

from .texto import normalizar

_PISTA = re.compile(r"\b(dr|dra|doctor\w*|doc|cita|especialista\w*|medic\w*|nutricionista|psicolog\w*|odontolog\w*|"
                    r"ortodoncista|dermatolog\w*|ginecolog\w*|pediatra|cardiolog\w*|internista|urolog\w*|asesor\w*|"
                    r"licenciad\w*|profesional|terapeuta|fisioterapeuta|optometra|abogad\w*)\b")
_NO_NOMBRE = {"torre", "medica", "medico", "centro", "comercial", "puente", "plazoleta", "pasillo", "paseo", "local",
              "oficina", "consultorio", "piso", "nivel", "zona", "san", "gil", "santander", "colombia", "lunes",
              "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"}
_PALABRA = re.compile(r"[A-Za-zÁÉÍÓÚÑÜáéíóúñü]+")


def _pares_con_mayuscula(texto: str) -> set[tuple[str, str]]:
    pal = [m.group(0) for m in _PALABRA.finditer(texto or "")]
    out = set()
    for a, b in zip(pal, pal[1:]):
        if a[:1].isupper() and b[:1].isupper() and len(a) > 2 and len(b) > 2:
            na, nb = normalizar(a), normalizar(b)
            if na not in _NO_NOMBRE and nb not in _NO_NOMBRE:
                out.add((na, nb))
    return out


def locales_por_persona(mensaje: str, locales) -> list:
    """Locales en cuya descripción aparece el nombre que trae el mensaje. Solo si el mensaje habla de un profesional
    (doctora, cita, especialista, asesor…), para no confundir nombres de lugares."""
    t = normalizar(mensaje)
    if not _PISTA.search(t):
        return []
    palabras = [w for w in re.findall(r"[a-zñ]+", t) if len(w) > 2]
    pares = set(zip(palabras, palabras[1:]))
    if not pares:
        return []
    return [l for l in locales if pares & _pares_con_mayuscula(f"{l.nombre} {l.descripcion}")]
