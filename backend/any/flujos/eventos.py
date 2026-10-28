"""
Flujo eventos: actividades del centro comercial (concursos, carreras, festivales, misa…).
Solo eventos vigentes según la fecha del contexto. La inscripción se explica SOLO con lo que
dice la descripción del evento; si no lo dice, se da la línea del centro comercial.
"""
from __future__ import annotations

from ..conocimiento.fotos import foto_principal
from ..conocimiento.texto import normalizar, palabras
from ..conocimiento.vigencia import dias_para, fecha_inicio, vigente
from ..nucleo.tipos import Adjunto, Contexto
from .base import Datos, Flujo


def eventos_vigentes(db, hoy) -> list:
    from models.event import Event
    evs = [e for e in db.query(Event).all() if vigente(e.date, hoy)]
    # primero los que tienen fecha (por fecha), luego los recurrentes ("todos los domingos")
    return sorted(evs, key=lambda e: (fecha_inicio(e.date) is None, fecha_inicio(e.date) or hoy, e.name))


def evento_mencionado(evs: list, texto: str):
    pal = set(palabras(texto))
    mejor, puntaje = None, 0.0
    for e in evs:
        claves = [p for p in palabras(e.name) if len(p) >= 3 and p not in {"del", "las", "los", "una"}]
        if not claves:
            continue
        p = sum(1 for c in claves if c in pal) / len(claves)
        if p > puntaje:
            mejor, puntaje = e, p
    return mejor if puntaje >= 0.5 else None


def ficha_evento(e, hoy) -> dict:
    d = {"nombre": e.name, "fecha": e.date, "hora": e.time, "lugar": e.location, "descripcion": e.description}
    faltan = dias_para(e.date, hoy)
    if faltan is not None:
        d["dias_para_el_evento"] = faltan
    # el código decide si cae hoy o este fin de semana (el modelo se equivocaba contando días)
    from datetime import timedelta
    sab = hoy + timedelta(days=(5 - hoy.weekday()) % 7) if hoy.weekday() != 6 else hoy - timedelta(days=1)
    dias = _dias_del_evento(e.date, hoy)
    if dias is not None:
        d["es_hoy"] = hoy in dias
        d["es_este_fin_de_semana"] = bool({sab, sab + timedelta(days=1)} & dias)
    else:   # recurrentes: "todos los domingos" (en la fecha o, si la fecha está vacía, en la descripción)
        import re
        from ..conocimiento.vigencia import recurrencia
        rec = recurrencia(e.date, e.description)
        if rec and not e.date:
            d["fecha"] = rec[0][0].upper() + rec[0][1:]
        if rec:      # el modelo calculaba mal el día ("domingo 29/10" cuando era 01/11)
            from datetime import timedelta
            prox = next(hoy + timedelta(days=i) for i in range(8) if (hoy + timedelta(days=i)).weekday() in rec[1])
            dia = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"][prox.weekday()]
            d["proxima_vez"] = "hoy" if prox == hoy else f"{dia} {prox.strftime('%d/%m/%Y')}"
        f = (e.date or (rec[0] if rec else "")).lower()
        nombres = ["lunes", "martes", "miercoles", "miércoles", "jueves", "viernes", "sabado", "sábado", "domingo"]
        dia_hoy = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"][hoy.weekday()]
        if any(n in f for n in nombres):
            d["es_hoy"] = dia_hoy in f or (dia_hoy == "miércoles" and "miercoles" in f) or (dia_hoy == "sábado" and "sabado" in f)
            d["es_este_fin_de_semana"] = bool(re.search(r"s[aá]bado|domingo|fin de semana", f))
    return {k: v for k, v in d.items() if v not in (None, "")}


def _dias_del_evento(fecha_texto, hoy):
    """Días en que ocurre el evento (rango 'del 23/10 al 25/10' o una fecha); None si es recurrente o no se entiende."""
    from datetime import timedelta
    from ..conocimiento.vigencia import fecha_inicio, fecha_final as fecha_fin
    try:
        ini, fin = fecha_inicio(fecha_texto), fecha_fin(fecha_texto)
    except Exception:
        return None
    if not ini:
        return None
    fin = fin or ini
    if (fin - ini).days > 60:
        return None
    return {ini + timedelta(days=i) for i in range((fin - ini).days + 1)}


MAX_AFICHES = 4


class Eventos(Flujo):
    nombre = "eventos"
    descripcion = "eventos y actividades del centro comercial (concursos, carreras, ferias, misa) e inscripciones"
    temperatura = 0.5
    max_tokens = 600

    def componer(self, ctx, datos, texto):
        """Adjunta el afiche de cada evento que la respuesta nombra (máximo 4, en el orden en que aparecen)."""
        from ..conocimiento.texto import normalizar
        afiches = datos.meta.get("afiches") or {}
        if afiches and texto:
            t = normalizar(texto)
            ya = {a.url for a in datos.adjuntos}
            def nucleo(n):   # "Run Run Kids 2026" también vale escrito "Run Run Kids"
                import re
                return re.sub(r"\s*\b\d{4}\b\s*$", "", normalizar(n)).strip()
            nombrados = sorted((t.find(nucleo(n)), n) for n in afiches if nucleo(n) and nucleo(n) in t)
            for _, n in nombrados[:MAX_AFICHES]:
                if afiches[n] not in ya:
                    datos.adjuntos.append(Adjunto(tipo="imagen", url=afiches[n], leyenda=n))
        return texto

    async def reunir(self, ctx: Contexto) -> Datos:
        db, hoy = ctx.db, ctx.ahora.date()
        d = ctx.decision
        texto = f"{ctx.mensaje} {(d.consulta if d else '')} {(d.entidades.get('evento') if d else '') or ''}"
        evs = eventos_vigentes(db, hoy)
        e = evento_mencionado(evs, texto)
        recordado = ctx.estado.ultimas_entidades.get("evento")
        if not e and recordado and d and d.es_seguimiento:
            e = next((x for x in evs if x.name == recordado), None)
        hechos = {"hoy": hoy.strftime("%d/%m/%Y"),
                  "inscripciones_solo_si_el_evento_requiere_inscripcion_y_la_descripcion_no_dice_como":
                      "línea del centro comercial 317 432 0138 · https://wa.me/573174320138"}
        datos = Datos(hechos=hechos, meta={"sin_promo": True})
        if e:
            hechos["evento"] = ficha_evento(e, hoy)
            datos.entidades["evento"] = e.name
            foto = foto_principal(db, "event", e.id, respaldo=e.photo_url)
            if foto:
                datos.adjuntos.append(Adjunto(tipo="imagen", url=foto, leyenda=e.name))
        else:
            hechos["eventos_vigentes"] = [ficha_evento(x, hoy) for x in evs] or "no hay eventos programados por ahora"
            # Afiches: se envían solo los de los eventos que la respuesta termine nombrando (ver componer)
            afiches = {}
            for x in evs:
                f = foto_principal(db, "event", x.id, respaldo=x.photo_url)
                if f:
                    afiches[x.name] = f
            datos.meta["afiches"] = afiches
            if afiches:
                hechos["afiches"] = "los afiches de los eventos que menciones se envían aparte, como imágenes"
            nombre = d.entidades.get("evento") if d else None
            if nombre:
                hechos["evento_pedido_no_encontrado"] = nombre
        return datos