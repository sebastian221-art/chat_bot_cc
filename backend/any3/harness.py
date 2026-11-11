"""
Any 3.0: el mismo orden de Any 2.0, pero la parte que fallaba (entender la pregunta y encontrar los datos) la
hace un agente que lee TODO, y una segunda IA vigila cada respuesta antes de enviarla.

    contexto → (casos especiales → Any 2.0 tal cual)
             → CEREBRO: elige del directorio completo qué responde la pregunta (IDs que el código valida)
             → DATOS: el código arma los datos verificados de esos IDs (las mismas fichas y listas de Any 2.0)
             → REDACTOR: escribe con los prompts de Any 2.0 (ya pulidos), solo con esos datos
             → VIGILANTE: revisa la respuesta contra los datos → quita locales que no son / reescribe una vez /
               usa la respuesta armada por código
             → guardias de salida de Any 2.0 → guardar → traza

Lo que Any 3.0 no maneja distinto (fotos que manda el cliente, un domicilio a medias, cine, quejas y
emergencias, administración, bot en pausa, privacidad) lo responde Any 2.0 exactamente igual que hoy.
Si algo de Any 3.0 falla, también responde Any 2.0: el cliente nunca se queda sin respuesta.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime

from any.config import ZONA_HORARIA
from any.conocimiento.texto import normalizar
from any.flujos import FLUJOS
from any.flujos.base import Datos
from any.llm import ErrorLLM
from any.nucleo import estado as est
from any.nucleo import guardias, mensajes, promociones
from any.nucleo.harness import _cargar_modelos
from any.nucleo.harness import procesar as procesar_any2
from any.nucleo.tipos import Contexto, Decision, Respuesta
from any.nucleo.trazas import Traza

from . import cerebro, llm, vigilante
from .directorio import construir

log = logging.getLogger("any3")

# Temas que Any 2.0 ya maneja bien con su propia lógica (estado, acciones, cartelera): se le pasan tal cual
DELEGADOS = {"cine", "domicilios", "emergencia_queja", "administracion"}
FLUJO_DE = {"locales": "locales", "no_hay": "locales", "info": "servicios_mall", "eventos": "eventos",
            "sorteos_promos": "sorteos_promos", "conversacion": "conversacion", "aclarar": "conversacion"}
_PIDE = {"general": None, "precios": "carta", "telefono": "telefono", "ubicacion": "ubicacion", "horario": "horario",
         "carta": "carta", "instagram": "instagram", "foto": "foto"}
LINEA_MALL = "317 432 0138"


# Contadores desde que arrancó el servidor (se ven en /any3/estado): cuántos respondió Any 3.0, cuántos pasó a
# Any 2.0 por tema (normal) y cuántos por ERROR (lo que hay que vigilar al ponerla de principal).
import collections as _col
CONTADOR: _col.Counter = _col.Counter()
SEGUNDOS: _col.deque = _col.deque(maxlen=300)
_ERRORES_A_ANY2 = ("cerebro falló", "error")      # «tema de Any 2.0: …» es normal (cine, domicilios, QR…)


async def _any2(db, telefono, nombre, mensaje, ahora, modo, imagen, es_audio, motivo: str) -> Respuesta:
    if modo == "produccion":
        es_error = motivo.startswith(_ERRORES_A_ANY2)
        CONTADOR["pasó a Any 2.0 por error" if es_error else "pasó a Any 2.0 (tema de Any 2.0)"] += 1
        if es_error:
            try:
                from services.bandeja import registrar_problema
                registrar_problema("Any 3.0 falló y respondió Any 2.0", telefono, motivo)
            except Exception:
                pass
    r = await procesar_any2(db, telefono, nombre, mensaje, ahora=ahora, modo=modo, imagen=imagen, es_audio=es_audio)
    r.meta["any3"] = {"respondio": "any2", "motivo": motivo}
    return r


async def procesar(db, telefono: str, nombre: str, mensaje: str, ahora: datetime | None = None,
                   modo: str = "prueba", imagen: bytes | None = None, es_audio: bool = False) -> Respuesta:
    ahora = ahora or datetime.now(ZONA_HORARIA)
    if ahora.tzinfo is None:
        ahora = ahora.replace(tzinfo=ZONA_HORARIA)
    mensaje = (mensaje or "").strip()
    args = (db, telefono, nombre, mensaje, ahora, modo, imagen, es_audio)
    try:
        _cargar_modelos()
        est.asegurar_tablas(db)
        if imagen or not mensaje:
            return await _any2(*args, motivo="foto o mensaje vacío")
        estado = est.cargar_estado(db, telefono, ahora)
        if estado.flujo_activo:                      # un domicilio a medias: lo termina Any 2.0
            return await _any2(*args, motivo=f"flujo activo: {estado.flujo_activo}")
        if guardias.bot_en_pausa(db, telefono, ahora):
            return await _any2(*args, motivo="bot en pausa (asesor humano)")
        historial, sesion_nueva = est.cargar_historial(db, telefono, ahora)
        traza = Traza(telefono, mensaje, modo)
        t0 = time.monotonic()
        ctx = Contexto(db=db, telefono=telefono, nombre=nombre, mensaje=mensaje, ahora=ahora, historial=historial,
                       sesion_nueva=sesion_nueva, estado=estado, traza=traza, modo=modo)
        ctx._any3_t0 = t0
        if guardias.privacidad(ctx) is not None:      # pedir borrar datos, etc.: lo maneja Any 2.0
            return await _any2(*args, motivo="privacidad")
        regla = _regla_fija_de_any2(db, mensaje)
        if regla:                                     # emergencia, QR de zona, «?», salón de eventos: reglas exactas
            return await _any2(*args, motivo=f"tema de Any 2.0: {regla}")
        traza.paso("contexto", {"motor": "any3", "turnos_historial": len(historial), "sesion_nueva": sesion_nueva,
                                "recordado": estado.ultimas_entidades})
    except Exception as e:
        log.exception("Any 3.0 falló preparando el contexto")
        try:
            db.rollback()
        except Exception:
            pass
        return await _any2(*args, motivo=f"error preparando: {e!r}"[:200])

    # ── Cerebro ──
    try:
        directorio = construir(db, ahora.date())
        el = await cerebro.elegir(ctx, directorio)
    except Exception as e:
        log.warning("Any 3.0: el cerebro falló, responde Any 2.0: %r", e)
        try:
            db.rollback()
        except Exception:
            pass
        return await _any2(*args, motivo=f"cerebro falló: {e!r}"[:200])
    traza.paso("cerebro", {**el.dict(), "nombres": [directorio.nombre(i) for i in el.ids + el.info_ids]})
    if el.accion in DELEGADOS:
        return await _any2(*args, motivo=f"tema de Any 2.0: {el.accion}")

    try:
        r = await _responder(ctx, el, directorio)
    except Exception as e:
        log.exception("Any 3.0 falló respondiendo")
        try:
            db.rollback()
        except Exception:
            pass
        return await _any2(*args, motivo=f"error respondiendo: {e!r}"[:200])
    r = _salida(ctx, r, es_audio)
    if modo == "produccion":
        CONTADOR["respondió Any 3.0"] += 1
        SEGUNDOS.append(time.monotonic() - ctx._any3_t0)
    return r


def _regla_fija_de_any2(db, mensaje: str) -> str | None:
    """Las reglas exactas que Any 2.0 aplica ANTES de pensar (no dependen de la IA): se respetan igual.
    Así Any 3.0 hace todo lo que hace Any 2.0: una emergencia nunca pasa por el modelo, el QR de una zona se
    registra, un «?» suelto pide aclarar y el alquiler de salones va con los números de reservas."""
    from any.nucleo.router import regla_emergencia, regla_salon_eventos
    from any.flujos.navegacion_qr import codigo_qr
    if regla_emergencia(mensaje):
        return "emergencia"
    if codigo_qr(db, mensaje):
        return "QR de zona"
    if not re.search(r"[0-9A-Za-zÁÉÍÓÚáéíóúÑñÜü]", mensaje or ""):
        return "mensaje sin palabras"
    if regla_salon_eventos(mensaje):
        return "salón de eventos"
    return None


# ── Datos verificados a partir de lo que eligió el cerebro ─────────

def _datos(ctx, el, d) -> tuple[str, Datos | None]:
    """(nombre del flujo cuyo redactor se usa, datos). Datos None = se usan los del propio flujo de Any 2.0."""
    from any.flujos.locales import Locales
    from any.conocimiento.areas import ficha_area
    flujo = FLUJO_DE[el.accion]
    pide = _PIDE.get(el.pide)
    locs = [d.locales[i] for i in el.ids]
    info = []
    for k in el.info_ids:
        f = d.info[k]
        info.append(ficha_area(f["area"]) if f.get("fuente") == "areas" else
                    {"titulo": f["titulo"], "contenido": f["contenido"]})

    if el.accion == "locales":
        if len(locs) == 1:
            datos = Locales()._ficha(locs[0], pide)
            if not el.es_local_concreto:
                datos.hechos["nota"] = (f"Es el ÚNICO local que encontré para «{el.busqueda or ctx.mensaje}»: "
                                        f"dilo así, con naturalidad, y da sus datos.")
        else:
            if pide == "carta":     # «¿qué restaurantes tienen carta?»: solo los que la tienen (como Any 2.0)
                from any.flujos.locales import carta_de
                con_carta = [l for l in locs if any(carta_de(l))]
                if con_carta:
                    locs = con_carta
                else:
                    pide = None
            datos = Locales()._datos_lista(locs, el.busqueda or el.consulta or ctx.mensaje, pide)
            if pide in ("telefono", "instagram"):
                datos.hechos["nota"] = "Los contactos de cada local van en la lista que pone el sistema."
        if pide == "horario" or re.search(r"horario|abiert|abren|cierran|a esta hora", normalizar(ctx.mensaje)):
            from any.conocimiento.servicios import info_mall
            hg = info_mall(ctx.db).get("horario_general")
            if hg:
                datos.hechos["horario_general_del_centro_comercial"] = hg
        if info:
            datos.hechos["info_oficial_relacionada"] = info
        if el.certeza == "probable":
            datos.hechos["certeza"] = ("Estos locales PROBABLEMENTE lo tienen (no lo declaran exactamente): dilo así, "
                                       "«puedes encontrarlo en…», y sugiere confirmar por WhatsApp antes de ir.")
        datos.entidades["any3_ids"] = el.ids[:20]
        return flujo, datos

    if el.accion == "no_hay":
        hechos = {"modo": "info_relacionada" if info else "sin_resultados", "busqueda": el.busqueda or ctx.mensaje,
                  "linea_del_centro_comercial": LINEA_MALL}
        if info:
            hechos["info_oficial_relacionada"] = info
        return flujo, Datos(hechos=hechos, entidades={"categoria": el.busqueda} if el.busqueda else {})

    if el.accion == "info":
        return flujo, None        # se usan los datos de Any 2.0 + lo que eligió el cerebro (ver _responder)
    return flujo, None


async def _datos_de_flujo(ctx, el, d, flujo_obj) -> Datos:
    """Temas cuyo flujo de Any 2.0 arma bien sus datos (eventos, sorteos, conversación, servicios): se usan, y se
    les suma lo que eligió el cerebro."""
    from any.conocimiento.areas import ficha_area
    datos = await flujo_obj.reunir(ctx)
    if el.accion == "info":
        elegidos = []
        for k in el.info_ids:
            f = d.info[k]
            elegidos.append(ficha_area(f["area"]) if f.get("fuente") == "areas" else
                            {"titulo": f["titulo"], "contenido": f["contenido"]})
        previos = datos.hechos.get("fragmentos_relevantes") or []
        titulos = {normalizar(str(x.get("titulo") or x.get("area") or "")) for x in elegidos}
        datos.hechos["fragmentos_relevantes"] = elegidos + [p for p in previos
                                                             if normalizar(str(p.get("titulo") or "")) not in titulos][:3]
        if el.ids:
            locs = [d.locales[i] for i in el.ids][:8]
            datos.hechos["locales_relacionados"] = [l.ficha() for l in locs]
            datos.meta.setdefault("telefonos_validos", []).extend(l.telefono for l in locs if l.telefono)
            datos.entidades["any3_ids"] = el.ids[:20]
    return datos


# ── Redactar, vigilar, corregir ───────────────────────────────────

async def _redactar(flujo_obj, ctx, datos: Datos, correccion: str = "") -> tuple[str, str]:
    """(texto crudo del modelo, texto compuesto). Mismos mensajes que Any 2.0 (persona + instrucciones del flujo +
    datos verificados + historial) con el modelo de Any 3.0."""
    msgs = flujo_obj._mensajes(ctx, datos)
    if correccion:
        msgs.insert(-1, {"role": "system", "content": (
            "REVISIÓN DE CALIDAD: tu respuesta anterior fue RECHAZADA por esto: " + correccion +
            "\nEscríbela de nuevo corrigiendo eso. Usa SOLO los datos verificados; si un dato no está, no lo pongas.")})
    try:
        r = await asyncio.wait_for(llm.completar(msgs, temperatura=min(flujo_obj.temperatura, 0.4),
                                                 max_tokens=max(flujo_obj.max_tokens, 600), razonamiento="low",
                                                 timeout_s=20), timeout=30)
        ctx.traza.llm(f"redactor_{flujo_obj.nombre}" + ("_correccion" if correccion else ""), r)
        crudo = r.texto or ""
    except (ErrorLLM, asyncio.TimeoutError) as e:
        ctx.traza.alerta(f"el redactor falló: {e}")
        crudo = ""
    if not crudo.strip():
        datos.meta["respaldo"] = True
        return "", flujo_obj.componer(ctx, datos, flujo_obj.respaldo(ctx, datos) or "")
    return crudo, flujo_obj.componer(ctx, datos, crudo)


def _para_vigilar(ctx, datos: Datos) -> dict:
    h = dict(datos.hechos)
    if datos.meta.get("lista"):
        h["lista_que_puso_el_sistema"] = datos.meta["lista"]
    if datos.adjuntos:
        h["se_adjunta"] = [a.dict() for a in datos.adjuntos]
    if ctx.promo:
        h["novedad_de_pasada"] = ctx.promo["datos"]
    return h


def _quitar_de_lista(ctx, datos: Datos, quitar: list[str], busqueda: str) -> Datos | None:
    """El vigilante dijo que estos locales no corresponden: se rearma la lista sin ellos (máximo la mitad)."""
    from any.conocimiento.catalogo import locales
    from any.flujos.locales import Locales
    nombres = datos.meta.get("lista_equidad") or []
    fuera = {normalizar(q) for q in quitar}
    quedan = [n for n in nombres if normalizar(n) not in fuera]
    if not nombres or len(quedan) == len(nombres) or len(quedan) < len(nombres) / 2 or not quedan:
        return None
    por_nombre = {l.nombre: l for l in locales(ctx.db)}
    sel = [por_nombre[n] for n in quedan if n in por_nombre]
    nuevo = Locales()._datos_lista(sel, busqueda, datos.hechos.get("lo_que_pide"))
    for k in ("horario_general_del_centro_comercial", "info_oficial_relacionada", "certeza", "nota", "filtro"):
        if k in datos.hechos:
            nuevo.hechos[k] = datos.hechos[k]
    nuevo.entidades = {**datos.entidades, **nuevo.entidades}
    nuevo.entidades["any3_ids"] = [f"L{l.id}" for l in sel]
    return nuevo


async def _responder(ctx, el, d) -> Respuesta:
    if el.accion == "aclarar":
        saludo = "¡Hola! Soy Any, la asistente del Centro Comercial El Puente 😊\n\n" if ctx.sesion_nueva else ""
        ctx.decision = Decision("conversacion", {}, False, el.consulta, el.razon, "any3")
        ctx.traza.paso("datos_reunidos", {"flujo": "conversacion", "hechos": {"aclaracion": el.aclaracion}})
        return Respuesta(saludo + el.aclaracion, "conversacion", meta={"any3": {"accion": "aclarar"}})

    nombre_flujo, datos = _datos(ctx, el, d)
    flujo_obj = FLUJOS[nombre_flujo]
    entidades = {}
    if el.accion == "locales" and len(el.ids) == 1:
        entidades["local"] = d.locales[el.ids[0]].nombre
    elif el.accion in ("locales", "no_hay") and el.busqueda:
        entidades["categoria"] = el.busqueda
    if el.ids_eventos:
        entidades["evento"] = d.nombre(el.ids_eventos[0])
    ctx.decision = Decision(nombre_flujo, entidades, False, el.consulta, el.razon, "any3")
    try:
        ctx.promo = promociones.elegir(ctx, nombre_flujo)
        if ctx.promo:
            ctx.traza.paso("promocion_elegida", ctx.promo)
    except Exception as e:
        ctx.traza.alerta(f"regla de promociones falló: {e}")
        ctx.db.rollback()
    if datos is None:
        datos = await _datos_de_flujo(ctx, el, d, flujo_obj)
    ctx.traza.paso("datos_reunidos", {"flujo": nombre_flujo, "hechos": datos.hechos,
                                      "adjuntos": [a.dict() for a in datos.adjuntos]})

    if datos.respuesta_directa:
        texto, crudo = flujo_obj.componer(ctx, datos, datos.respuesta_directa), ""
    else:
        crudo, texto = await _redactar(flujo_obj, ctx, datos)

    # ── Vigilante ──
    revision = {"intentos": []}
    # Presupuesto de tiempo: el cliente no puede esperar de más. Si ya se fue mucho tiempo, no se vigila
    # (las guardias de código de Any 2.0 siguen aplicando igual).
    gastado = time.monotonic() - ctx._any3_t0
    if gastado > 40:
        ctx.traza.alerta(f"sin vigilante: ya iban {gastado:.0f} s")
    elif not datos.meta.get("respaldo") and not datos.respuesta_directa:
        v = await vigilante.revisar(ctx, _para_vigilar(ctx, datos), texto, el.consulta)
        revision["intentos"].append(v.dict())
        ctx.traza.paso("vigilante", v.dict())
        if not v.ok and v.quitar and datos.meta.get("lista_equidad"):
            nuevo = _quitar_de_lista(ctx, datos, v.quitar, el.busqueda or el.consulta or ctx.mensaje)
            if nuevo is not None:
                ctx.traza.alerta(f"vigilante: se quitaron de la lista {v.quitar}")
                datos = nuevo
                ctx.traza.paso("datos_reunidos", {"flujo": nombre_flujo, "hechos": datos.hechos, "ajuste": "vigilante"})
                texto = flujo_obj.componer(ctx, datos, crudo) if crudo else texto
            elif v.gravedad != "grave":
                ctx.traza.alerta(f"vigilante quería quitar {v.quitar}, pero era demasiado: se deja la lista")
        if v.gravedad == "grave" and time.monotonic() - ctx._any3_t0 > 55:
            ctx.traza.alerta("el vigilante encontró un problema grave pero ya no hay tiempo de reescribir: "
                             "se usa la respuesta armada por código")
            plan_b = flujo_obj.respaldo(ctx, datos)
            if plan_b:
                texto = flujo_obj.componer(ctx, datos, plan_b)
                revision["final"] = "codigo_por_tiempo"
        elif v.gravedad == "grave":
            correccion = "; ".join(v.problemas) + (". " + v.correccion if v.correccion else "")
            crudo2, texto2 = await _redactar(flujo_obj, ctx, datos, correccion=correccion)
            v2 = await vigilante.revisar(ctx, _para_vigilar(ctx, datos), texto2, el.consulta) if crudo2 else \
                vigilante.Veredicto(ok=False, gravedad="grave", problemas=["el redactor no respondió"])
            revision["intentos"].append(v2.dict())
            ctx.traza.paso("vigilante_2", v2.dict())
            if v2.gravedad != "grave":
                texto = texto2
            else:
                plan_b = flujo_obj.respaldo(ctx, datos)
                if plan_b:
                    ctx.traza.alerta("vigilante rechazó dos veces: se usa la respuesta armada por código")
                    texto = flujo_obj.componer(ctx, datos, plan_b)
                    revision["final"] = "codigo"
                else:
                    ctx.traza.alerta("vigilante rechazó dos veces y no hay respuesta por código: se envía la corregida")
                    texto = texto2 or texto
                    revision["final"] = "corregida_sin_aprobar"
    meta = dict(datos.meta)
    meta["any3"] = {"accion": el.accion, "ids": el.ids, "info_ids": el.info_ids, "revision": revision}
    return Respuesta(texto, nombre_flujo, datos.adjuntos, entidades={**entidades, **datos.entidades}, meta=meta)


# ── Salida (igual que Any 2.0) ────────────────────────────────────

_VACIO = re.compile(r"[ \t]*(?:[•·\-–]\s*)?(?:📸|📞|💬|👉|📲)?\s*\*?(?:instagram|whatsapp|tel[eé]fono|horario)\*?\s*:?\s*\*?\s*"
                    r"\(?(?:no disponible|no registrad[oa]|sin dato|n/?a)\)?\*?\.?[ \t]*", re.I)


def _sin_datos_vacios(t: str) -> str:
    """«📸 Instagram: (no disponible)» en una ficha: si el cliente no lo pidió, el dato que falta no se escribe
    (regla de la persona; el examen del 11/11 mostró que el modelo a veces la rompe)."""
    nuevo = _VACIO.sub("", t)
    return re.sub(r"\n{3,}", "\n\n", nuevo).strip() if nuevo != t else t



def _salida(ctx, r: Respuesta, es_audio: bool) -> Respuesta:
    db, estado, traza = ctx.db, ctx.estado, ctx.traza
    r = guardias.revisar_salida(ctx, r)
    if ctx.promo and r.texto and r.responder and not r.meta.get("error"):
        try:
            r.texto, agregada = promociones.asegurar(ctx, ctx.promo, r.texto)
            r.meta["promo"] = {**ctx.promo["datos"], "agregada_por_codigo": agregada}
            traza.paso("promocion_mostrada", r.meta["promo"])
        except Exception as e:
            traza.alerta(f"no se pudo registrar la promoción: {e}")
            db.rollback()
    if r.texto:
        r.texto = guardias.corregir_lugares(guardias.nombres_en_mayuscula(ctx, r.texto))
        r.texto = _sin_datos_vacios(r.texto)
    guardias.aviso_privacidad(ctx, r)
    if r.entidades:
        from any.nucleo.router import limpiar_entidades
        estado.ultimas_entidades = limpiar_entidades({**estado.ultimas_entidades, **r.entidades})
        if "any3_ids" not in r.entidades:
            estado.ultimas_entidades.pop("any3_ids", None)
    estado.ultimo_flujo = r.flujo
    try:
        est.guardar_turno(db, ctx.telefono, ctx.nombre, "user", ("🎤 " + ctx.mensaje) if es_audio else ctx.mensaje,
                          ctx.ahora)
        for previo in r.previos:
            est.guardar_turno(db, ctx.telefono, ctx.nombre, "assistant", previo, ctx.ahora)
        if r.texto:
            est.guardar_turno(db, ctx.telefono, ctx.nombre, "assistant", r.texto, ctx.ahora)
        est.guardar_estado(db, estado, ctx.ahora)
    except Exception as e:
        log.error("Any 3.0: no se pudo guardar el turno: %s", e)
        db.rollback()
    traza.paso("salida", {"motor": "any3", "flujo": r.flujo, "caracteres": len(r.texto), "adjuntos": len(r.adjuntos)})
    r.meta["traza_id"] = traza.guardar(db, ctx.decision, r)
    r.meta["traza"] = traza.resumen()
    return r
