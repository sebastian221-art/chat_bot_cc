"""«¿Qué hay este mes en el centro comercial?» (27/11): eventos, sorteos y promociones juntos.

En el texto van TODOS (eventos con su fecha, sorteos y promociones agrupadas por local) y en foto UNA sola: la más
actual (ver la_mas_actual). Si después preguntan por uno en especial, ese flujo manda su información y su foto.
"""
from __future__ import annotations

import re

from ..conocimiento.texto import normalizar
from .base import Datos

_PREGUNTA = re.compile(r"\b(que hay|que tienen|que tiene el|que planes?|planes|novedad\w*|que hay de nuevo|"
                       r"que se puede hacer|que podemos hacer|que puedo hacer|que esta pasando|que pasa)\b")
_PERIODO = re.compile(r"\b(mall|centro comercial|el puente|este mes|esta semana|hoy|manana|fin de semana|finde|"
                      r"diciembre|enero|navidad|vacaciones|temporada)\b")
_CATEGORIA = re.compile(r"\b(evento\w*|promo\w*|descuento\w*|oferta\w*|sorteo\w*|rifa\w*|premio\w*|cine|pelicula\w*|"
                        r"comer|comida|restaurante\w*|tienda\w*|local\w*|ropa|black)\b")


def es_pregunta_general(mensaje: str) -> bool:
    t = normalizar(mensaje)
    return bool(_PREGUNTA.search(t) and _PERIODO.search(t) and not _CATEGORIA.search(t))


async def reunir(ctx) -> Datos:
    from . import la_mas_actual
    from .eventos import Eventos, eventos_vigentes
    from .sorteos_promos import SorteosPromos, dias_de_promo, promos_vigentes, sorteos_vigentes
    from ..conocimiento.catalogo import local_por_id
    hoy = ctx.ahora.date()
    datos = await Eventos().reunir(ctx)
    sp = await SorteosPromos().reunir(ctx)
    evs, sorteos, promos = eventos_vigentes(ctx.db, hoy), sorteos_vigentes(ctx.db, hoy), promos_vigentes(ctx.db, hoy)
    datos.meta.pop("afiches", None)          # la foto la decide la más actual, no el primer evento que se nombre
    for k in ("eventos_con_afiche", "afiches"):
        datos.hechos.pop(k, None)
    datos.hechos["sorteos_vigentes"] = sp.hechos.get("sorteos_vigentes") or "no hay sorteos vigentes"
    datos.hechos["registro_de_facturas"] = sp.hechos.get("registro_de_facturas")
    por_local: dict[str, list] = {}
    for m in promos:
        loc = local_por_id(ctx.db, m.store_id) if m.store_id else None
        rec = dias_de_promo(m)
        dia_en_titulo = re.search(r"\b(lunes|martes|miercoles|jueves|viernes|sabado|domingo)s?\b", normalizar(m.title))
        linea = m.title + (f" ({rec[0]})" if rec and not dia_en_titulo else "")
        por_local.setdefault(loc.nombre if loc else "Centro Comercial El Puente", []).append(linea)
    datos.hechos["promociones_por_local"] = por_local or "no hay promociones vigentes"
    datos.hechos["como_responder"] = (
        "El cliente pregunta qué hay en el centro comercial (en general o en un periodo). Responde en tres bloques "
        "cortos, cada uno con su título en negrita: *Eventos* (todos los que faltan en el periodo que pide, una línea "
        "cada uno con su fecha), *Sorteos* (una línea cada uno, con el registro de facturas) y *Promociones* (UNA "
        "línea por local con lo principal; si un local tiene promociones por día de la semana, resúmelas en esa "
        "línea). No omitas ninguno. Al final, una línea: si quiere más de alguno, que te diga cuál.")
    datos.meta["sin_promo"] = True
    la_mas_actual.poner(datos, la_mas_actual.elegir(ctx.db, hoy, eventos=evs, sorteos=sorteos, promos=promos),
                        len(evs) + len(sorteos) + len(promos))
    datos.hechos.pop("como_ofrecer_mas", None)   # ya va en como_responder
    datos.entidades = {}
    return datos
