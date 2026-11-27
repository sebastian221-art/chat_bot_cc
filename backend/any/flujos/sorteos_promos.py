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
MAX_IMAGENES_PROMOS = 8       # cuando piden promociones concretas


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


def dias_pedidos(mensaje: str, hoy) -> set[int]:
    """Días de la semana que nombra el cliente: «el viernes», «hoy», «mañana», «el fin de semana»."""
    from ..conocimiento.texto import normalizar
    t = normalizar(mensaje)
    dias = {i for i, d in enumerate(["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"])
            if re.search(rf"\b{d}s?\b", t)}
    if re.search(r"\bhoy\b", t):
        dias.add(hoy.weekday())
    if re.search(r"\bmanana\b", t) and not re.search(r"\b(en|por|de) la manana\b", t):
        dias.add((hoy.weekday() + 1) % 7)
    if re.search(r"fin de semana|finde\b", t):
        dias |= {5, 6}
    return dias


def mostrar_promos(ctx, datos: Datos, promos: list, clave: str = "promociones", especificas: bool = False) -> None:
    """Pone en los datos las promociones (las que aplican HOY primero) y sus imágenes (26/11, pedido de Jumbo):
    - pregunta general («¿Jumbo tiene promociones?»): el texto de TODAS (todos los días) y solo las imágenes de las de
      HOY; las demás imágenes se mandan si preguntan por ese día o por esa promoción.
    - un día concreto («¿qué hay el viernes?»): solo las de ese día, con sus imágenes.
    - promociones concretas (el cliente pidió esa, o un producto): esas, con su imagen."""
    hoy = ctx.ahora.date()
    pedidos = dias_pedidos(ctx.mensaje, hoy)
    if pedidos and any(dias_de_promo(m) for m in promos):
        del_dia = [m for m in promos if (dias_de_promo(m) or (None, set()))[1] & pedidos]
        if del_dia:
            promos, especificas = del_dia, True
            nombres = ", ".join(_DIAS[i] for i in sorted(pedidos))
            datos.hechos["dia_pedido"] = f"El cliente pregunta por {nombres}: responde solo con las de ese día, con detalle."
    promos = sorted(promos, key=lambda m: (not aplica_hoy(m, hoy), -(m.priority or 3)))
    por_dia = any(dias_de_promo(m) for m in promos)
    if not especificas and len(promos) > 6 and len({m.store_id for m in promos}) > 2:
        # muchas de varios locales (el Black, «todas las del mall»): una línea por local, armada por código
        datos.hechos["promociones_por_local"] = resumen_por_local(ctx.db, promos, hoy)
        datos.meta["sin_listas_anteriores"] = True
        datos.hechos["como_responder_lista"] = (
            "Nombra TODAS: una línea por local con «•», el nombre del local en negrita y su resumen de "
            "«promociones_por_local» tal cual (puedes acortar las palabras, no quitar promociones). No agregues "
            "detalles que no estén ahí.")
    elif especificas or not por_dia:
        datos.hechos[clave] = [ficha_promo(ctx.db, m, hoy) for m in promos]
    else:
        # General con promociones por día: las de HOY con detalle; las de otros días, solo su título (que ya dice el
        # día y el porcentaje), para que el texto las nombre TODAS sin volverse eterno.
        datos.hechos[clave] = [ficha_promo(ctx.db, m, hoy) if aplica_hoy(m, hoy) else
                               {k: v for k, v in ficha_promo(ctx.db, m, hoy).items() if k in ("titulo", "dias")}
                               for m in promos]
    from . import la_mas_actual
    if especificas:
        # pidió una(s) en especial (o un día): esas, con su imagen
        imagenes = 0
        for m in promos[:MAX_IMAGENES_PROMOS]:
            foto = foto_principal(ctx.db, "marketing", m.id, respaldo=getattr(m, "photo_url", None))
            if foto and not any(a.url == foto for a in datos.adjuntos):
                datos.adjuntos.append(Adjunto(tipo="imagen", url=foto, leyenda=m.title))
                imagenes += 1
        if imagenes:
            datos.hechos["imagenes"] = (f"va(n) adjunta(s) {imagenes} imagen(es) de esta(s) promoción(es): no las "
                                        "describas ni ofrezcas mandarlas.")
    else:
        # 27/11: pregunta general → el texto con TODAS y UNA sola foto: la más actual (la de hoy)
        la_mas_actual.poner(datos, la_mas_actual.elegir(ctx.db, hoy, promos=promos), len(promos))
    if por_dia:
        datos.hechos["como_responder_dias"] = (
            f"Hoy es {_DIAS[hoy.weekday()]}. Son promociones de un día de la semana («dias»). "
            + ("Responde con el detalle de estas." if especificas or datos.hechos.get("dia_pedido") else
               "Nómbralas TODAS: primero las de HOY (una línea cada una, con porcentaje y medio de pago) y después UNA "
               "línea por cada uno de los otros días de la semana, en orden, con lo que trae ese día (ej. «Viernes: "
               "charcutería 15% o 20% y vinos paga 2 lleva 3»). No omitas ningún día.")
            + " Una promoción de otro día SIGUE VIGENTE: nunca digas que «no hay» o que «no está activa»; di qué día "
              "aplica (ej. «el descuento en carne es los miércoles»).")


def resumen_por_local(db, promos: list, hoy) -> dict:
    """27/11: la lista general del centro comercial salió con 35 líneas (8 de Jumbo). Una línea lista por local:
    «Jumbo»: «Lunes de Mercado y Aseo (20% con Tarjeta Cencosud); Martes de …» · «Koaj»: «Black: del 10% al 50% …;
    Jeans desde $79.900». Las del centro comercial (sin local) llevan su descripción corta, porque el título solo
    («Mensualidad de parqueadero») no dice nada."""
    grupos: dict[str, list] = {}
    for m in promos:
        loc = local_por_id(db, m.store_id) if m.store_id else None
        grupos.setdefault(loc.nombre if loc else "", []).append(m)
    out = {}
    for nombre, ms in grupos.items():
        from .la_mas_actual import _cercania_promo
        ms = sorted(ms, key=lambda m: (_cercania_promo(m, hoy), m.id or 0))   # las de hoy y luego por día de la semana
        partes = []
        for m in ms:
            t = m.title.strip()
            if nombre:
                t = re.sub(rf"^(?:{re.escape(nombre)}\s*:\s*)", "", t, flags=re.I)
                t = re.sub(rf"^(Black|Descuentos?)\s+en\s+{re.escape(nombre)}\s*:\s*", r"\1: ", t, flags=re.I)
                t = re.sub(rf"^{re.escape(nombre)}\s*:\s*", "", t, flags=re.I)
            if not nombre or not re.search(r"\d", t):
                # el título solo («Cinelandia», «Mensualidad de parqueadero») no dice nada: va su descripción corta
                corta = (m.description or "").strip().split(". ")[0][:140]
                t = f"{t}: {corta}" if corta and corta.lower() not in t.lower() else t
            if m.valid_until and nombre:
                t += f" (hasta el {m.valid_until})"
            partes.append(t)
        out[nombre or "Centro Comercial El Puente"] = "; ".join(partes)
    return out


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
    for k in ("sorteos_vigentes", "promociones_vigentes", "imagen", "como_responder_lista", "promocion", "promociones",
              "imagenes", "como_ofrecer_mas", "dia_pedido", "como_responder_dias"):
        datos.hechos.pop(k, None)       # lo que haya armado el flujo de Any 2.0 se reemplaza por lo que eligió el cerebro
    datos.adjuntos = []
    if sorteos:
        datos.hechos["sorteos"] = [ficha_sorteo(s) for s in sorteos]
        for s in sorteos[:1]:
            foto = foto_principal(ctx.db, "raffle", s.id, respaldo=s.photo_url, orden=("afiche", "premio", "otra"))
            if foto:
                datos.adjuntos.append(Adjunto(tipo="imagen", url=foto, leyenda=s.name))
    if promos:
        from ..conocimiento.texto import normalizar
        msg = normalizar(ctx.mensaje)
        tiendas = {m.store_id for m in promos if m.store_id}
        todas_del_local = promos_de_locales(ctx.db, hoy, tiendas)
        especificas = len(promos) <= 2      # «la de vinos», «descuento en carne»: esa(s), con su imagen
        if len(tiendas) == 1 and (len(promos) >= 3 or dias_pedidos(ctx.mensaje, hoy)):
            # 27/11: «¿Jumbo tiene promociones?» → el cerebro eligió 10 de 11 y salieron 8 imágenes. Pregunta general
            # = TODAS las del local en el texto y solo las imágenes de hoy; con un día, todas las de ese día.
            promos, especificas = todas_del_local or promos, False
        if re.search(r"\bblack\b", msg):
            # 27/11: «¿qué promociones hay por el Black?» → el cerebro dejó por fuera Koaj, YOYO, Americanino…
            ya = {m.id for m in promos}
            promos = promos + [m for m in promos_vigentes(ctx.db, hoy)
                               if m.id not in ya and re.search(r"\bblack\b", normalizar(f"{m.title} {m.description}"))]
        mostrar_promos(ctx, datos, promos, especificas=especificas)
        if sorteos and not especificas:
            from . import la_mas_actual
            la_mas_actual.poner(datos, la_mas_actual.elegir(ctx.db, hoy, sorteos=sorteos, promos=promos),
                                len(sorteos) + len(promos))
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
            if len(promos) > 6:
                # 27/11: una línea por local, armada por código (antes 35 líneas y 20 s)
                hechos["promociones_por_local"] = resumen_por_local(db, promos, hoy)
                datos.meta["sin_listas_anteriores"] = True
                hechos["como_responder_lista"] = (
                    "Nombra TODAS: una línea por local con «•», el nombre del local en negrita y su resumen de "
                    "«promociones_por_local» tal cual (puedes acortar las palabras, no quitar promociones). Las del "
                    "Centro Comercial El Puente primero. No agregues detalles que no estén ahí. Aunque ya hayas "
                    "respondido esto antes en la conversación, ármala de nuevo con ESTOS datos: no copies la anterior.")
            else:
                hechos["promociones_vigentes"] = ([ficha_promo(db, x, hoy) for x in promos]
                                                  or "no hay promociones vigentes")
            # Lista general: el texto con todos y UNA imagen, la más actual (pedidos 11/11 y 27/11)
            from . import la_mas_actual
            la_mas_actual.poner(datos, la_mas_actual.elegir(db, hoy, sorteos=sorteos, promos=promos),
                                len(sorteos) + len(promos))
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