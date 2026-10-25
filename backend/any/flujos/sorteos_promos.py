"""
Flujo sorteos y promociones: sorteos vigentes (tabla raffles), promociones y descuentos
vigentes (tabla marketing) y cómo registrar facturas (link oficial + Punto de Información
+ reglas de la base de conocimiento). Nada de esto se inventa: si un dato no está, se dice.
"""
from __future__ import annotations

from ..conocimiento.buscador import buscar_conocimiento
from ..conocimiento.catalogo import local_por_id
from ..conocimiento.fotos import foto_principal
from ..conocimiento.texto import palabras
from ..conocimiento.vigencia import vigente
from ..nucleo import mensajes
from ..nucleo.tipos import Adjunto, Contexto
from .base import Datos, Flujo


def sorteos_vigentes(db, hoy) -> list:
    from models.raffle import Raffle
    return [r for r in db.query(Raffle).filter(Raffle.active.is_(True)).order_by(Raffle.priority.desc()).all()
            if vigente(r.end_date, hoy)]


def promos_vigentes(db, hoy) -> list:
    from models.marketing import Marketing
    return [m for m in db.query(Marketing).filter(Marketing.active.is_(True)).order_by(Marketing.priority.desc()).all()
            if vigente(m.valid_until, hoy)]


def _mencion(items: list, texto: str, campo: str):
    pal = set(palabras(texto))
    mejor, puntaje = None, 0.0
    for it in items:
        claves = [p for p in palabras(getattr(it, campo) or "") if len(p) >= 3]
        if claves:
            p = sum(1 for c in claves if c in pal) / len(claves)
            if p > puntaje:
                mejor, puntaje = it, p
    return mejor if puntaje >= 0.5 else None


def ficha_sorteo(r) -> dict:
    d = {"nombre": r.name, "premio": r.prize, "como_participar": r.requirements, "hasta": r.end_date,
         "donde_registrar": r.location, "descripcion": r.description}
    return {k: v for k, v in d.items() if v}


def ficha_promo(db, m) -> dict:
    d = {"titulo": m.title, "descripcion": m.description, "vigente_hasta": m.valid_until or None}
    if m.store_id:
        loc = local_por_id(db, m.store_id)
        if loc:
            d["local"] = loc.nombre
            d["zona"] = loc.zona
    return {k: v for k, v in d.items() if v}


class SorteosPromos(Flujo):
    nombre = "sorteos_promos"
    descripcion = "sorteos, registro de facturas, premios, promociones y descuentos vigentes"
    temperatura = 0.5
    max_tokens = 600

    async def reunir(self, ctx: Contexto) -> Datos:
        db, hoy = ctx.db, ctx.ahora.date()
        d = ctx.decision
        texto = f"{ctx.mensaje} {(d.consulta if d else '')}"
        sorteos, promos = sorteos_vigentes(db, hoy), promos_vigentes(db, hoy)
        hechos: dict = {
            "registro_de_facturas": {
                "en_linea": mensajes.valor("registro_facturas_url"),
                "presencial": "Punto de Información, Pasillo Barichara",
                "reglas": [f.contenido for f in buscar_conocimiento(db, "registro de facturas sorteos", k=2)],
            },
        }
        datos = Datos(hechos=hechos, meta={"sin_promo": True}, entidades={"tema": "sorteos_promos"})
        s = _mencion(sorteos, texto, "name")
        p = _mencion(promos, texto, "title") or _mencion(promos, texto, "description")
        recordado = ctx.estado.ultimas_entidades.get("promo")
        if not (s or p) and recordado and d and d.es_seguimiento:   # "¿ese descuento en qué es?"
            p = next((x for x in promos if x.title == recordado), None)
        if s:
            hechos["sorteo"] = ficha_sorteo(s)
            datos.entidades["sorteo"] = s.name
            foto = foto_principal(db, "raffle", s.id, respaldo=s.photo_url, orden=("afiche", "premio", "otra"))
            if foto:
                datos.adjuntos.append(Adjunto(tipo="imagen", url=foto, leyenda=s.name))
        elif p:
            hechos["promocion"] = ficha_promo(db, p)
            datos.entidades["promo"] = p.title
        else:
            hechos["sorteos_vigentes"] = [ficha_sorteo(x) for x in sorteos] or "no hay sorteos vigentes"
            hechos["promociones_vigentes"] = [ficha_promo(db, x) for x in promos] or "no hay promociones vigentes"
            if len(promos) == 1:
                datos.entidades["promo"] = promos[0].title
        return datos