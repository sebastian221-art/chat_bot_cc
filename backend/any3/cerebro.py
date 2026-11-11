"""
El cerebro: lee el directorio COMPLETO + la conversación y decide qué responde la pregunta (por IDs).
No escribe la respuesta; solo elige. El código valida que cada ID exista (no puede inventar locales).
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from any.llm import ErrorLLM

from . import llm
from .directorio import Directorio

ACCIONES = {"locales", "info", "eventos", "sorteos_promos", "cine", "domicilios", "emergencia_queja",
            "administracion", "conversacion", "aclarar", "no_hay"}
PIDE = {"general", "telefono", "ubicacion", "horario", "carta", "instagram", "foto", "precios"}
_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def _prompt(nombre: str) -> str:
    with open(os.path.join(os.path.dirname(__file__), "prompts", nombre), encoding="utf-8") as f:
        return f.read().strip()


@dataclass
class Eleccion:
    accion: str
    ids: list = field(default_factory=list)
    info_ids: list = field(default_factory=list)
    ids_eventos: list = field(default_factory=list)
    ids_promos: list = field(default_factory=list)
    es_local_concreto: bool = False
    pide: str = "general"
    busqueda: str = ""
    consulta: str = ""
    certeza: str = "alta"
    aclaracion: str = ""
    razon: str = ""
    descartados: list = field(default_factory=list)   # IDs que la IA dio y no existen (para la traza)

    def dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v not in (None, "", [], False)}


def _conversacion(ctx, maximo: int = 8) -> str:
    lineas = []
    for t in ctx.historial[-maximo:]:
        texto = t.texto
        if t.rol != "user":   # sin la novedad del día ni el aviso legal: no son el tema
            texto = "\n".join(l for l in texto.split("\n") if not re.search(r"(?i)de paso|ley 1581", l)).strip()
            texto = re.sub(r"https?://\S+", "[link]", texto)
            if len(texto) > 500:
                texto = texto[:500] + "…"
        lineas.append(("Cliente: " if t.rol == "user" else "Any: ") + texto)
    return "\n".join(lineas) or "(es el primer mensaje)"


def _ultimo(ctx, d: Directorio) -> str:
    e = ctx.estado.ultimas_entidades or {}
    partes = []
    ids = e.get("any3_ids") or []
    if ids:
        partes.append("locales mostrados: " + ", ".join(f"{i} {d.nombre(i)}" for i in ids[:12] if i in d.locales))
    for k in ("local", "categoria", "evento", "pelicula", "promo", "sorteo", "servicio"):
        if e.get(k):
            partes.append(f"{k}: {e[k]}")
    if ctx.estado.ultimo_flujo:
        partes.append(f"tema: {ctx.estado.ultimo_flujo}")
    return "; ".join(partes) or "(nada)"


def mensajes(ctx, d: Directorio) -> list[dict]:
    a = ctx.ahora
    fijo = _prompt("cerebro.md") + "\n\n# DIRECTORIO COMPLETO DEL CENTRO COMERCIAL\n" + d.texto
    variable = (f"Hoy es {_DIAS[a.weekday()]} {a.day:02d}/{a.month:02d}/{a.year}, "
                f"{a.strftime('%I:%M %p').lstrip('0').lower()} (hora de Colombia).")
    usuario = (f"CONVERSACIÓN RECIENTE:\n{_conversacion(ctx)}\n\n"
               f"Lo último que se habló: {_ultimo(ctx, d)}\n\n"
               f"MENSAJE NUEVO DEL CLIENTE: {ctx.mensaje}")
    return [{"role": "system", "content": fijo}, {"role": "system", "content": variable},
            {"role": "user", "content": usuario}]


def validar(j: dict, d: Directorio) -> Eleccion:
    accion = str(j.get("accion") or "").strip().lower()
    if accion not in ACCIONES:
        raise ErrorLLM(f"acción desconocida del cerebro: {accion!r}")
    descartados = []

    def ids_de(clave: str, validos: dict) -> list:
        out = []
        for x in j.get(clave) or []:
            x = str(x).strip().upper()
            if x in validos and x not in out:
                out.append(x)
            elif x not in validos:
                descartados.append(x)
        return out
    pide = str(j.get("pide") or "general").strip().lower()
    e = Eleccion(accion=accion, ids=ids_de("ids", d.locales), info_ids=ids_de("info_ids", d.info),
                 ids_eventos=ids_de("ids_eventos", d.eventos),
                 ids_promos=ids_de("ids_promos", {**d.sorteos, **d.promos}),
                 es_local_concreto=bool(j.get("es_local_concreto")), pide=pide if pide in PIDE else "general",
                 busqueda=str(j.get("busqueda") or "").strip()[:80], consulta=str(j.get("consulta") or "").strip()[:300],
                 certeza=str(j.get("certeza") or "alta").strip().lower(), aclaracion=str(j.get("aclaracion") or "").strip(),
                 razon=str(j.get("razon") or "").strip()[:300], descartados=descartados)
    if e.accion == "locales" and not e.ids:
        e.accion = "info" if e.info_ids else "no_hay"
    if e.accion == "info" and not e.info_ids and e.ids:
        e.accion = "locales"
    if e.accion == "aclarar" and not e.aclaracion:
        e.accion = "conversacion"
    return e


async def elegir(ctx, d: Directorio) -> Eleccion:
    import asyncio
    r = await asyncio.wait_for(llm.completar(mensajes(ctx, d), json_salida=True, temperatura=0, max_tokens=2500,
                                             razonamiento="medium", timeout_s=20), timeout=45)
    ctx.traza.llm("cerebro", r)
    return validar(r.json(), d)
