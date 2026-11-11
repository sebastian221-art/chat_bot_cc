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


def candidatos(ctx, d: Directorio, maximo: int = 25) -> list[str]:
    """Pistas del buscador por palabras de Any 2.0 (lo que encuentra por lo que cada local declara vender).
    El cerebro las REVISA una por una y busca más: así no se le escapa un local perdido en un directorio largo
    (pasó en el examen con Groq: popsy y ROAD TRIP venden gomitas y no los vio)."""
    try:
        from any.conocimiento.buscador import buscar_locales, seleccionar_relevantes
        res = buscar_locales(ctx.db, ctx.mensaje, incluir_torre=True)
        primero = seleccionar_relevantes(res)
        resto = sorted((r for r in res if r not in primero), key=lambda r: -r.puntaje)
        ids = []
        for r in list(primero) + resto:
            i = f"L{r.local.id}"
            if i in d.locales and i not in ids:
                ids.append(i)
        return ids[:maximo]
    except Exception as e:
        try:
            ctx.db.rollback()
        except Exception:
            pass
        ctx.traza.alerta(f"el buscador de pistas falló: {e}")
        return []


def mensajes(ctx, d: Directorio) -> list[dict]:
    a = ctx.ahora
    fijo = _prompt("cerebro.md") + "\n\n# DIRECTORIO COMPLETO DEL CENTRO COMERCIAL\n" + d.texto
    variable = (f"Hoy es {_DIAS[a.weekday()]} {a.day:02d}/{a.month:02d}/{a.year}, "
                f"{a.strftime('%I:%M %p').lstrip('0').lower()} (hora de Colombia).")
    pistas = candidatos(ctx, d)
    ctx.traza.paso("pistas_buscador", [f"{i} {d.nombre(i)}" for i in pistas])
    texto_pistas = ("\n".join(f"- {i} {d.nombre(i)}" for i in pistas) if pistas else "(el buscador no encontró nada)")
    usuario = (f"CONVERSACIÓN RECIENTE:\n{_conversacion(ctx)}\n\n"
               f"Lo último que se habló: {_ultimo(ctx, d)}\n\n"
               f"PISTAS DEL BUSCADOR POR PALABRAS (pueden sobrar o faltar: revisa CADA una contra su línea del "
               f"directorio y busca además otros locales que sirvan):\n{texto_pistas}\n\n"
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


_COMPACTO_HASTA = 0.0      # si el proveedor rechazó el directorio completo por tamaño, se usa el corto un rato


def _es_por_tamano(e: Exception) -> bool:
    t = str(e).lower()
    return any(x in t for x in ("413", "too large", "tokens per minute", "rate_limit", "429", "context_length",
                                "maximum context"))


def modo_directorio() -> str:
    import time
    from . import config
    m = config.directorio_modo()
    if m != "auto":
        return m
    return "compacto" if time.monotonic() < _COMPACTO_HASTA else "completo"


async def _llamar(ctx, d: Directorio, modo: str):
    """Si el modelo devuelve vacío (con Groq pasó: gastó el cupo pensando en listas largas de ropa), se repite
    con más cupo y razonamiento corto."""
    import asyncio
    msgs = mensajes(ctx, d)
    r = None
    for intento, (razonamiento, cupo) in enumerate((("medium", 8000), ("low", 8000))):
        r = await asyncio.wait_for(llm.completar(msgs, json_salida=True, temperatura=0, max_tokens=cupo,
                                                 razonamiento=razonamiento, timeout_s=25), timeout=45)
        ctx.traza.llm(f"cerebro_{modo}" + ("_reintento" if intento else ""), r)
        if (r.texto or "").strip():
            return r
        ctx.traza.alerta("el cerebro devolvió una respuesta vacía: se repite")
    return r


async def elegir(ctx, d: Directorio) -> Eleccion:
    """Lee el directorio completo. Si el proveedor lo rechaza por tamaño o por límite de tokens por minuto (Groq),
    repite con el directorio corto y lo sigue usando 10 minutos (configurable con ANY3_DIRECTORIO)."""
    import time
    from .directorio import construir
    global _COMPACTO_HASTA
    modo = modo_directorio()
    if modo == "compacto":
        d = construir(ctx.db, d.hoy, compacto=True)
    try:
        r = await _llamar(ctx, d, modo)
    except Exception as e:
        if modo == "compacto" or not _es_por_tamano(e):
            raise
        ctx.traza.alerta(f"el modelo rechazó el directorio completo por tamaño: se usa el corto ({str(e)[:160]})")
        _COMPACTO_HASTA = time.monotonic() + 600
        modo = "compacto"
        r = await _llamar(ctx, construir(ctx.db, d.hoy, compacto=True), modo)
    ctx.traza.paso("directorio", modo)
    return validar(r.json(), d)
