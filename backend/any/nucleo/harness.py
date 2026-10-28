"""
El núcleo de Any 2.0: el MISMO orden fijo para cada mensaje.

    contexto → entrada (pausa humana, privacidad) → router → flujo → salida → traza

    from any.nucleo.harness import procesar
    r = await procesar(db, "573001112233", "Juan", "¿hay parqueadero?")
    r.mensajes()   # textos a enviar, en orden
    r.adjuntos     # fotos, PDF, pin

No envía nada por WhatsApp (eso lo hace any/entrada.py): así se puede probar
igual en el chat de prueba, en el banco de pruebas y en producción.
"""
from __future__ import annotations

import logging
from datetime import datetime

from ..config import ZONA_HORARIA
from ..flujos import FLUJOS, PENDIENTES, RESPALDO
from ..flujos.base import Datos, Flujo
from . import estado as est
from . import guardias, mensajes, promociones, router
from .tipos import Contexto, Respuesta
from .trazas import Traza

log = logging.getLogger("any.harness")


class FlujoPendiente(Flujo):
    """Para los temas que aún no tienen especialista: responde con honestidad, sin inventar."""

    def __init__(self, nombre: str):
        self.nombre = nombre
        self.descripcion = PENDIENTES.get(nombre, "")

    async def reunir(self, ctx):
        # Sin IA a propósito: con un tema sin datos, el modelo llegó a inventar un local y una zona
        # (banco de pruebas del 24/10). Respuesta fija y honesta hasta que el especialista exista.
        return Datos(respuesta_directa=mensajes.texto("tema_pendiente"),
                     hechos={"tema": self.descripcion, "disponible": False},
                     meta={"pendiente": True, "sin_promo": True})


_MODELOS_CARGADOS = False


def _cargar_modelos():
    """Registra todos los modelos compartidos antes de la primera consulta (relaciones como Marketing→Store
    fallan si se usa uno antes de importar el otro; en el banco de pruebas pasó exactamente eso)."""
    global _MODELOS_CARGADOS
    if _MODELOS_CARGADOS:
        return
    import importlib
    for m in ("store", "store_photo", "cine_funcion", "marketing", "event", "raffle", "entity_photo", "knowledge",
              "mall_info", "info_point", "conversation", "conversation_flag", "promotion_shown", "orchestrator_trace",
              "zone"):
        try:
            importlib.import_module(f"models.{m}")
        except Exception as e:  # un modelo que no exista en esta versión no debe tumbar a Any
            log.warning("No se pudo cargar models.%s: %s", m, e)
    _MODELOS_CARGADOS = True


async def procesar(db, telefono: str, nombre: str, mensaje: str, ahora: datetime | None = None,
                   modo: str = "prueba", imagen: bytes | None = None, es_audio: bool = False) -> Respuesta:
    ahora = (ahora or datetime.now(ZONA_HORARIA))
    if ahora.tzinfo is None:
        ahora = ahora.replace(tzinfo=ZONA_HORARIA)
    mensaje = (mensaje or "").strip()
    traza = Traza(telefono, mensaje, modo)
    _cargar_modelos()
    est.asegurar_tablas(db)

    # ── Contexto ──
    historial, sesion_nueva = est.cargar_historial(db, telefono, ahora)
    estado = est.cargar_estado(db, telefono, ahora)
    ctx = Contexto(db=db, telefono=telefono, nombre=nombre, mensaje=mensaje, ahora=ahora, historial=historial,
                   sesion_nueva=sesion_nueva, estado=estado, traza=traza, modo=modo, imagen=imagen)
    traza.paso("contexto", {"turnos_historial": len(historial), "sesion_nueva": sesion_nueva,
                            "flujo_activo": estado.flujo_activo, "recordado": estado.ultimas_entidades})

    decision = None
    try:
        # ── Entrada ──
        if guardias.bot_en_pausa(db, telefono, ahora):
            traza.paso("pausa_humana", "un asesor tiene la conversación: Any no responde")
            est.guardar_turno(db, telefono, nombre, "user", mensaje, ahora)
            r = Respuesta("", "pausa_humana", responder=False)
            traza.guardar(db, None, r)
            return r

        r = guardias.privacidad(ctx)
        if r is None:
            if not mensaje and not imagen:
                r = Respuesta(mensajes.texto("error_tecnico"), RESPALDO)
            else:
                # ── Router ──
                decision = await router.decidir(ctx)
                ctx.decision = decision
                traza.paso("router", {"flujo": decision.flujo, "metodo": decision.metodo, "razon": decision.razon,
                                      "entidades": decision.entidades, "seguimiento": decision.es_seguimiento,
                                      "consulta": decision.consulta})
                # ── Flujo ──
                flujo = FLUJOS.get(decision.flujo) or FlujoPendiente(decision.flujo)
                if decision.flujo in FLUJOS:
                    try:
                        ctx.promo = promociones.elegir(ctx, decision.flujo)
                    except Exception as e:   # una promo nunca tumba la respuesta
                        traza.alerta(f"regla de promociones falló: {e}")
                        db.rollback()
                    if ctx.promo:
                        traza.paso("promocion_elegida", ctx.promo)
                r = await flujo.ejecutar(ctx)
                if not r.texto and not r.meta.get("respaldo"):
                    r.texto = (flujo.respaldo(ctx, Datos()) or "")
    except Exception as e:  # nada de lo anterior puede dejar al cliente sin respuesta
        log.exception("Error en el núcleo de Any 2.0")
        traza.alerta(f"error inesperado: {type(e).__name__}: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        r = Respuesta(mensajes.texto("error_tecnico"), decision.flujo if decision else RESPALDO,
                      meta={"error": True})

    # ── Salida ──
    r = guardias.revisar_salida(ctx, r)
    if estado.flujo_activo == "domicilios" and r.flujo not in ("domicilios", "emergencia_queja") and r.texto:
        from ..flujos.domicilios import recordatorio
        nota = recordatorio(ctx)
        if nota:
            r.texto = r.texto.rstrip() + "\n\n" + nota
    if ctx.promo and r.texto and r.responder and not r.meta.get("error") and not r.meta.get("pendiente"):
        r.texto, agregada = promociones.asegurar(ctx, ctx.promo, r.texto)
        r.meta["promo"] = {**ctx.promo["datos"], "agregada_por_codigo": agregada}
        traza.paso("promocion_mostrada", r.meta["promo"])
    if r.texto and r.flujo != "privacidad":
        r.texto = guardias.corregir_lugares(guardias.nombres_en_mayuscula(ctx, r.texto))
    borrado = bool(r.meta.get("borrado"))
    if not borrado:
        guardias.aviso_privacidad(ctx, r)
        if r.entidades:
            estado.ultimas_entidades = {**estado.ultimas_entidades, **r.entidades}
        estado.ultimo_flujo = r.flujo
        try:
            est.guardar_turno(db, telefono, nombre, "user",
                              ("🎤 " + mensaje) if es_audio else (mensaje or "[imagen]"), ahora)   # 🎤 = vino por nota de voz
            for previo in r.previos:   # el aviso legal queda en el panel, pero aparte de la respuesta
                est.guardar_turno(db, telefono, nombre, "assistant", previo, ahora)
            if r.texto:
                est.guardar_turno(db, telefono, nombre, "assistant", r.texto, ahora)
            est.guardar_estado(db, estado, ahora)
        except Exception as e:
            log.error("No se pudo guardar el turno: %s", e)
            db.rollback()
    else:
        traza.telefono = "borrado"
        traza.mensaje = "[datos eliminados por solicitud del titular]"
    traza.paso("salida", {"flujo": r.flujo, "caracteres": len(r.texto), "adjuntos": len(r.adjuntos)})
    r.meta["traza_id"] = traza.guardar(db, decision, r)
    r.meta["traza"] = traza.resumen()
    return r