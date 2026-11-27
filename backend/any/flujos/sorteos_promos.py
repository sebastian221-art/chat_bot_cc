"""
Flujo sorteos y promociones: sorteos vigentes (tabla raffles), promociones y descuentos
vigentes (tabla marketing) y cómo registrar facturas (link oficial + Punto de Información
+ reglas de la base de conocimiento). Nada de esto se inventa: si un dato no está, se dice.
"""
from __future__ import annotations

import re

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


_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
# Preguntas por promociones de un local (26/11, Jumbo: «cuando pregunten por ofertas, promociones o descuentos,
# se envían estas imágenes»)
PIDE_PROMOS = re.compile(r"\b(promo\w*|descuento\w*|dcto|dto|oferta\w*|rebaja\w*|black|friday|weekend|2x1|"
                         r"liquidacion\w*|en promocion|que te resuelven)\b|%")
MAX_IMAGENES_PROMOS = 8


def dias_de_promo(m):
    """Promociones que se repiten («Todos los jueves en Jumbo…») → ("todos los jueves", {3}); si no, None."""
    from ..conocimiento.vigencia import recurrencia
    return recurrencia(m.title, m.description)


def aplica_hoy(m, hoy) -> bool:
    rec = dias_de_promo(m)
    return rec is None or hoy.weekday() in rec[1]


def ficha_promo(db, m, hoy=None) -> dict:
    d = {"titulo": m.title, "descripcion": m.description, "vigente_hasta": m.valid_until or None}
    rec = dias_de_promo(m)
    if rec:
        d["dias"] = rec[0]
        if hoy:
            d["aplica_hoy"] = "sí" if hoy.weekday() in rec[1] else f"no (hoy es {_DIAS[hoy.weekday()]})"
    if m.store_id:
        loc = local_por_id(db, m.store_id)
        if loc:
            d["local"] = loc.nombre
            d["zona"] = loc.zona
    return {k: v for k, v in d.items() if v}


def promos_de_locales(db, hoy, store_ids) -> list:
    ids = {int(i) for i in store_ids if i}
    return [m for m in promos_vigentes(db, hoy) if m.store_id in ids] if ids else []


def mostrar_promos(ctx, datos: Datos, promos: list, clave: str = "promociones") -> None:
    """Pone en los datos las promociones elegidas (las que aplican HOY primero) y adjunta la imagen de cada una."""
    hoy = ctx.ahora.date()
    promos = sorted(promos, key=lambda m: (not aplica_hoy(m, hoy), -(m.priority or 3)))
    datos.hechos[clave] = [ficha_promo(ctx.db, m, hoy) for m in promos]
    imagenes = 0
    for m in promos[:MAX_IMAGENES_PROMOS]:
        foto = foto_principal(ctx.db, "marketing", m.id, respaldo=getattr(m, "photo_url", None))
        if foto and not any(a.url == foto for a in datos.adjuntos):
            datos.adjuntos.append(Adjunto(tipo="imagen", url=foto, leyenda=m.title))
            imagenes += 1
    if imagenes:
        datos.hechos["imagenes"] = (f"van adjuntas {imagenes} imágenes de estas promociones (las piezas oficiales): no "
                                    "las describas ni digas que no tienes imágenes.")
    if any(dias_de_promo(m) for m in promos):
        datos.hechos["como_responder_dias"] = (
            f"Hoy es {_DIAS[hoy.weekday()]}. Algunas promociones son de un día de la semana («dias»): di primero las "
            "que aplican hoy y luego las de los otros días, con su día. Si el cliente pregunta por un día o un "
            "producto (carne, frutas, aseo…), da solo la que corresponde.")


def sumar_promos_del_local(ctx, nombre_local: str, datos: Datos) -> None:
    """A la ficha de un local le suma sus promociones vigentes. Si preguntan por promociones/descuentos/ofertas,
    van todas con su imagen; si no, se mencionan en una línea."""
    try:
        from ..conocimiento.catalogo import locales
        from ..conocimiento.texto import normalizar
        hoy = ctx.ahora.date()
        nombre = normalizar(nombre_local or "")
        ids = [l.id for l in locales(ctx.db) if normalizar(l.nombre) == nombre]
        promos = promos_de_locales(ctx.db, hoy, ids)
        if not promos:
            return
        if PIDE_PROMOS.search(normalizar(ctx.mensaje)):
            datos.adjuntos = [a for a in datos.adjuntos if a.tipo != "imagen"]
            mostrar_promos(ctx, datos, promos, "promociones_vigentes_de_este_local")
            datos.hechos["como_responder"] = (
                "El cliente pregunta por las promociones de este local: responde con TODAS las de "
                "«promociones_vigentes_de_este_local», una línea por promoción con lo que dice (porcentaje, en qué "
                "aplica, condición y hasta cuándo). De la ficha del local da solo la ubicación y el contacto en una línea.")
        else:
            hoy_ = [m for m in promos if aplica_hoy(m, hoy)]
            if hoy_:
                datos.hechos["promociones_vigentes_de_este_local"] = [
                    {k: v for k, v in ficha_promo(ctx.db, m, hoy).items() if k in ("titulo", "vigente_hasta", "dias")}
                    for m in hoy_]
                datos.hechos["como_usar_promociones"] = ("Este local tiene promociones vigentes hoy: menciónalas en "
                                                         "UNA línea al final (solo el título).")
    except Exception as e:
        if hasattr(ctx, "traza"):
            ctx.traza.alerta(f"promociones del local: {e}")
        try:
            ctx.db.rollback()
        except Exception:
            pass


def enfocar(ctx, datos: Datos, promos: list, sorteos: list, locales_ids: list) -> None:
    """Any 3.0: el cerebro eligió promociones (P…) o locales concretos → solo esas, con su imagen."""
    hoy = ctx.ahora.date()
    if not promos and locales_ids:
        promos = promos_de_locales(ctx.db, hoy, locales_ids)
        if not promos and not sorteos:
            from ..conocimiento.catalogo import local_por_id
            nombres = [l.nombre for l in (local_por_id(ctx.db, i) for i in locales_ids) if l]
            for k in ("promociones_vigentes", "como_responder_lista"):
                datos.hechos.pop(k, None)
            datos.hechos["nota"] = (f"{', '.join(nombres)} no tiene promociones registradas en el centro comercial. "
                                    "Dilo así, sin inventar, y sugiere preguntarle al local por su WhatsApp. Los "
                                    "sorteos del centro comercial sí aplican a sus facturas.")
            return
    if not (promos or sorteos):
        return
    for k in ("sorteos_vigentes", "promociones_vigentes", "imagen", "como_responder_lista"):
        datos.hechos.pop(k, None)
    datos.adjuntos = []
    if sorteos:
        datos.hechos["sorteos"] = [ficha_sorteo(s) for s in sorteos]
        for s in sorteos[:1]:
            foto = foto_principal(ctx.db, "raffle", s.id, respaldo=s.photo_url, orden=("afiche", "premio", "otra"))
            if foto:
                datos.adjuntos.append(Adjunto(tipo="imagen", url=foto, leyenda=s.name))
    if promos:
        mostrar_promos(ctx, datos, promos)
        if len(promos) == 1:
            datos.entidades["promo"] = promos[0].title


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
            hechos["promocion"] = ficha_promo(db, p, hoy)
            datos.entidades["promo"] = p.title
            foto = foto_principal(db, "marketing", p.id, respaldo=getattr(p, "photo_url", None))
            if foto:
                datos.adjuntos.append(Adjunto(tipo="imagen", url=foto, leyenda=p.title))
        elif self._del_local(ctx, promos):
            mostrar_promos(ctx, datos, self._del_local(ctx, promos))
        else:
            hechos["sorteos_vigentes"] = [ficha_sorteo(x) for x in sorteos] or "no hay sorteos vigentes"
            hechos["promociones_vigentes"] = [ficha_promo(db, x, hoy) for x in promos] or "no hay promociones vigentes"
            if len(promos) > 6:
                hechos["como_responder_lista"] = (
                    "Son muchas promociones: agrúpalas por local, una línea por local con lo principal (porcentaje y "
                    "hasta cuándo). Las de un día de la semana («dias») van con su día.")
            # Lista general: UNA imagen de referencia (el sorteo principal), no una por cada uno (pedido 11/11)
            for x in sorteos:
                foto = foto_principal(db, "raffle", x.id, respaldo=x.photo_url, orden=("afiche", "premio", "otra"))
                if foto:
                    datos.adjuntos.append(Adjunto(tipo="imagen", url=foto, leyenda=x.name))
                    hechos["imagen"] = (f"se adjunta UNA imagen de referencia: la de «{x.name}». No digas que envías "
                                        f"imágenes de los demás.")
                    break
            if len(promos) == 1:
                datos.entidades["promo"] = promos[0].title
        return datos

    @staticmethod
    def _del_local(ctx, promos: list) -> list:
        """«¿Jumbo tiene promociones?» por Any 2.0: el router reconoció el local."""
        nombre = ((ctx.decision.entidades or {}).get("local") if ctx.decision else None) or ""
        if not nombre:
            return []
        from ..conocimiento.catalogo import locales
        from ..conocimiento.texto import normalizar
        ids = {l.id for l in locales(ctx.db) if normalizar(l.nombre) == normalizar(nombre)}
        return [m for m in promos if m.store_id in ids]