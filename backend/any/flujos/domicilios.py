"""
Flujo domicilios (con estado): armar un pedido para un local y entregarle al cliente un link de
WhatsApp con el pedido ya escrito. Any NO gestiona el pedido después: el local lo atiende.

Pasos (estado en any_estado, caduca solo a las 4 horas de inactividad — en el sistema viejo nunca vencía):
  1. local    → ¿a qué local? (si no lo dijo)
  2. datos    → nombre, celular (por defecto el mismo WhatsApp), dirección, pedido, forma de pago
                (efectivo o transferencia). Se extraen con IA de lo que escriba, en uno o varios mensajes.
  3. confirmar→ resumen exacto armado en código + "¿Confirmas? SÍ / NO".
  4. listo    → link wa.me al local con el pedido escrito. Queda en delivery_managements y
                delivery_transfers (panel de domicilios).
"Cancelar" en cualquier momento cierra el pedido. Si el cliente pregunta otra cosa a mitad del
pedido, se le responde y se le recuerda que el pedido sigue abierto.
"""
from __future__ import annotations

import re
import urllib.parse
from datetime import timezone

from ..config import cfg
from ..conocimiento.buscador import buscar_locales, encontrar_local
from ..conocimiento.catalogo import local_por_id
from ..conocimiento.texto import alguna_frase, normalizar, solo_digitos
from ..llm import completar
from ..nucleo.tipos import Adjunto, Contexto, Respuesta
from .base import Datos, Flujo, leer_prompt

CAMPOS = {"nombre": "tu nombre", "celular": "un celular de contacto", "direccion": "la dirección de entrega",
          "pedido": "qué quieres pedir", "pago": "si pagas en efectivo o por transferencia"}
FRASES_CANCELAR = ["cancelar", "cancela", "cancelar pedido", "ya no quiero", "ya no", "olvidalo", "dejalo asi",
                   "no quiero pedir"]
FRASES_SI = ["si", "sí", "si confirmo", "confirmo", "dale", "listo", "de una", "correcto", "ok", "okay", "si señor",
             "si señora", "perfecto"]
FRASES_NO = ["no", "no gracias", "corregir", "cambiar", "esta mal", "no es asi"]


def _es(frases: list[str], texto: str) -> bool:
    t = normalizar(texto).strip(" .!¡?¿")
    return t in {normalizar(f) for f in frases} or bool(alguna_frase(frases, t) and len(t.split()) <= 4)


_PAGO = [("Transferencia", r"\b(nequi|daviplata|transferencia|transfiero|transferir|transferencias|consignacion|consigno|"
                            r"consignar|bancolombia|pse|llave|bre-?b)\b"),
         ("Efectivo", r"\b(efectivo|cash|contraentrega|contra entrega|al recibir|billete|billetes)\b"),
         ("Tarjeta", r"\b(tarjeta|datafono|debito|credito)\b")]


def pago_en_texto(texto: str) -> str | None:
    """Forma de pago leída en código (no depende de la IA): Nequi y Daviplata cuentan como transferencia."""
    t = normalizar(texto)
    for valor, patron in _PAGO:
        if re.search(patron, t):
            return valor
    return None


def celular_en_texto(texto: str) -> str | None:
    m = re.search(r"(?<!\d)(?:\+?57[\s-]?)?(3\d{2})[\s.-]?(\d{3})[\s.-]?(\d{4})(?!\d)", texto or "")
    return f"{m.group(1)} {m.group(2)} {m.group(3)}" if m else None


_RELLENO_PEDIDO = {"quiero", "pedir", "un", "una", "domicilio", "domicilios", "de", "del", "a", "al", "en", "hacer",
                   "pedido", "me", "gestionas", "gestionar", "hola", "por", "favor", "el", "la", "para"}


def _no_es_pedido(pedido: str, local: str) -> bool:
    """"domicilio de 12B Burger" no es un pedido: solo nombra el local."""
    resto = set(normalizar(pedido).replace(",", " ").split()) - _RELLENO_PEDIDO - set(normalizar(local).split())
    return not resto


def link_pedido(loc, campos: dict) -> str | None:
    if not loc or not loc.whatsapp:
        return None
    texto = (f"Hola, soy {campos['nombre']} 👋 Vengo del asistente del Centro Comercial El Puente.\n\n"
             f"Quiero hacer un pedido a domicilio:\n"
             f"🛍️ {campos['pedido']}\n"
             f"📍 Dirección: {campos['direccion']}\n"
             f"📞 Contacto: {campos['celular']}\n"
             f"💳 Pago: {campos['pago']}\n\n¡Gracias!")
    return f"{loc.whatsapp}?text={urllib.parse.quote(texto)}"


def resumen(loc, campos: dict) -> str:
    return (f"*Tu pedido a {loc.nombre}:*\n"
            f"• Pedido: {campos['pedido']}\n"
            f"• Entregar en: {campos['direccion']}\n"
            f"• A nombre de: {campos['nombre']} · {campos['celular']}\n"
            f"• Pago: {campos['pago']}\n\n"
            f"¿Lo confirmas? Responde *SÍ* para enviarlo o *NO* para corregir algo.")


class Domicilios(Flujo):
    nombre = "domicilios"
    descripcion = "pedir un domicilio o hacer un pedido a un local (incluye seguir un pedido que está a medias)"
    con_estado = True
    temperatura = 0.4
    max_tokens = 350

    # El router consulta esto cuando hay un pedido a medias
    def sigue_en_flujo(self, ctx: Contexto) -> bool:
        paso = ctx.estado.datos.get("paso")
        if _es(FRASES_CANCELAR, ctx.mensaje):
            return True
        if paso == "confirmar" and (_es(FRASES_SI, ctx.mensaje) or _es(FRASES_NO, ctx.mensaje)):
            return True
        return False   # lo demás lo decide el router (sabe que hay un pedido abierto)

    async def ejecutar(self, ctx: Contexto) -> Respuesta:
        e = ctx.estado
        d = e.datos if e.flujo_activo == self.nombre else {}
        if not d:
            d = {"paso": "local", "campos": {}}
        if d and _es(FRASES_CANCELAR, ctx.mensaje) and e.flujo_activo == self.nombre:
            self._cerrar_gestion(ctx, d, "cancelled")
            e.terminar_flujo()
            return await self._redactar(ctx, {"situacion": "el cliente canceló el pedido; confírmalo en una línea "
                                                           "y ofrece ayuda con otra cosa"})

        loc = local_por_id(ctx.db, d["local_id"]) if d.get("local_id") else None
        if not loc:
            loc = self._local_del_mensaje(ctx)
            if not loc:
                e.activar(self.nombre, {**d, "paso": "local"})
                return await self._redactar(ctx, {"situacion": "el cliente quiere un domicilio pero no ha dicho de "
                                                               "qué local; pregúntale de cuál (restaurante o tienda)"})
            if not loc.whatsapp:
                e.terminar_flujo()
                return await self._redactar(ctx, {"situacion": f"{loc.nombre} no tiene WhatsApp registrado, así que "
                                                               "no se le puede enviar el pedido; dilo con honestidad y "
                                                               "ofrece buscar otro local parecido",
                                                  "local": loc.ficha()})
            d = {"paso": "datos", "local_id": loc.id, "local": loc.nombre, "campos": {}}
            d["campos"]["celular"] = self._celular_por_defecto(ctx)
            d["gestion_id"] = self._abrir_gestion(ctx, loc)
            await self._extraer(ctx, d)       # el primer mensaje puede traer ya el pedido
            e.activar(self.nombre, d)
            return await self._pedir_faltantes(ctx, loc, d, primera_vez=True)

        if d.get("paso") == "confirmar":
            if _es(FRASES_SI, ctx.mensaje):
                return await self._finalizar(ctx, loc, d)
            if _es(FRASES_NO, ctx.mensaje):
                d["paso"] = "datos"
                e.activar(self.nombre, d)
                return await self._redactar(ctx, {"situacion": "el cliente quiere corregir el pedido; pregúntale qué "
                                                               "quiere cambiar", "pedido_actual": d["campos"]})
        await self._extraer(ctx, d)
        e.activar(self.nombre, d)
        return await self._pedir_faltantes(ctx, loc, d)

    # ── Pasos ─────────────────────────────────────────────────────

    def _local_del_mensaje(self, ctx: Contexto):
        dec = ctx.decision
        if dec and dec.entidades.get("local"):
            loc = encontrar_local(ctx.db, str(dec.entidades["local"]), incluir_torre=False)
            if loc:
                return loc
        exactos = [r for r in buscar_locales(ctx.db, ctx.mensaje) if r.nombre_exacto]
        if len(exactos) == 1:
            return exactos[0].local
        recordado = ctx.estado.ultimas_entidades.get("local")
        if recordado and dec and dec.es_seguimiento:
            return encontrar_local(ctx.db, recordado, incluir_torre=False)
        return None

    def _celular_por_defecto(self, ctx: Contexto) -> str | None:
        d = solo_digitos(ctx.telefono)
        if len(d) == 12 and d.startswith("57"):
            return f"{d[2:5]} {d[5:8]} {d[8:]}"
        return None

    async def _extraer(self, ctx: Contexto, d: dict):
        """La IA extrae los datos que vengan en el mensaje (solo los que el cliente escribió)."""
        import json
        sistema = leer_prompt("flujos/domicilios_extraer.md")
        usuario = (f"DATOS QUE YA TENGO: {json.dumps(d['campos'], ensure_ascii=False)}\n"
                   f"MENSAJE DEL CLIENTE: {ctx.mensaje}")
        j: dict = {}
        for intento in range(2):      # un segundo intento si el modelo devuelve algo que no es JSON
            try:
                r = await completar(cfg().modelo_de_flujo(self.nombre), [{"role": "system", "content": sistema},
                                                                          {"role": "user", "content": usuario}],
                                    json_salida=True, temperatura=0, max_tokens=900, razonamiento="low")
                ctx.traza.llm("domicilio_extraer", r)
                j = r.json() or {}
                if isinstance(j, dict):
                    break
                j = {}
            except Exception as ex:
                ctx.traza.alerta(f"no se pudieron extraer los datos del pedido (intento {intento + 1}): {ex}")
        if not isinstance(j, dict):
            j = {}
        # lo que el código lee solo (forma de pago y celular) no depende de la IA
        if not (isinstance(j.get("pago"), str) and j["pago"].strip()):
            j["pago"] = pago_en_texto(ctx.mensaje)
        if not (isinstance(j.get("celular"), str) and j["celular"].strip()):
            j["celular"] = celular_en_texto(ctx.mensaje)
        ped = j.get("pedido")
        if isinstance(ped, str) and _no_es_pedido(ped, d.get("local", "")):
            j["pedido"] = None
        for k in CAMPOS:
            v = j.get(k)
            if isinstance(v, str) and v.strip() and v.strip().lower() not in {"null", "none", "-"}:
                d["campos"][k] = v.strip()[:400]
        if d["campos"].get("pago"):
            d["campos"]["pago"] = pago_en_texto(d["campos"]["pago"]) or d["campos"]["pago"]
        ctx.traza.paso("domicilio_datos", d["campos"])

    async def _pedir_faltantes(self, ctx: Contexto, loc, d: dict, primera_vez: bool = False) -> Respuesta:
        faltan = [CAMPOS[k] for k in CAMPOS if not d["campos"].get(k)]
        if not faltan:
            d["paso"] = "confirmar"
            ctx.estado.activar(self.nombre, d)
            return Respuesta(resumen(loc, d["campos"]), self.nombre, entidades={"local": loc.nombre},
                             meta={"domicilio": "confirmar", "telefonos_validos": [loc.telefono, d["campos"]["celular"]]})
        hechos = {"situacion": ("empieza el pedido a domicilio: confirma el local en una frase y pide lo que falta, "
                                "todo en un solo mensaje" if primera_vez else "sigue el pedido: pide solo lo que falta"),
                  "local": loc.ficha(completa=False) | {"horario": loc.horario},
                  "ya_tengo": d["campos"], "me_falta": faltan,
                  "formas_de_pago": "efectivo o transferencia"}
        if d["campos"].get("celular") and primera_vez:
            hechos["nota_celular"] = "dile que usaré este mismo WhatsApp como contacto, salvo que prefiera otro número"
        adjuntos = []
        if primera_vez:
            carta = loc.fotos.get("carta")
            if carta:
                es_pdf = carta.lower().split("?")[0].endswith(".pdf")
                adjuntos.append(Adjunto(tipo="documento" if es_pdf else "imagen", url=carta,
                                        nombre_archivo=f"Carta {loc.nombre}.pdf" if es_pdf else None,
                                        leyenda=f"Carta de {loc.nombre}"))
            elif loc.carta_link:
                hechos["carta_link"] = loc.carta_link
        r = await self._redactar(ctx, hechos, adjuntos)
        r.entidades = {"local": loc.nombre}
        return r

    async def _finalizar(self, ctx: Contexto, loc, d: dict) -> Respuesta:
        link = link_pedido(loc, d["campos"])
        self._cerrar_gestion(ctx, d, "completed", link)
        try:
            from models.delivery_transfer import DeliveryTransfer
            ctx.db.add(DeliveryTransfer(phone_number=ctx.telefono[:20], store_name=loc.nombre[:150]))
            ctx.db.commit()
        except Exception:
            ctx.db.rollback()
        ctx.estado.terminar_flujo()
        r = await self._redactar(ctx, {"situacion": "el pedido quedó listo: dile que toque el link para enviárselo al "
                                                    "local (ya va escrito) y que el local le confirma valor y tiempo de "
                                                    "entrega. NO escribas el link: el sistema lo pone al final.",
                                       "local": loc.nombre, "nombre_cliente": d["campos"].get("nombre")})
        r.texto = (r.texto.rstrip() + f"\n\n👉 {link}").strip()
        r.meta["domicilio"] = "enviado"
        r.meta["telefonos_validos"] = [loc.telefono, d["campos"].get("celular", "")]
        return r

    async def _redactar(self, ctx: Contexto, hechos: dict, adjuntos=None) -> Respuesta:
        datos = Datos(hechos=hechos, adjuntos=list(adjuntos or []))
        r = await Flujo.ejecutar(_Redactor(self, datos), ctx)
        r.flujo = self.nombre
        return r

    # ── Registro para el panel (delivery_managements) ─────────────

    def _abrir_gestion(self, ctx: Contexto, loc) -> int | None:
        try:
            from models.delivery_management import DeliveryManagement
            g = DeliveryManagement(phone_number=ctx.telefono[:20], store_name=loc.nombre[:150], status="collecting")
            ctx.db.add(g)
            ctx.db.commit()
            return g.id
        except Exception:
            ctx.db.rollback()
            return None

    def _cerrar_gestion(self, ctx: Contexto, d: dict, estado: str, link: str | None = None):
        if not d.get("gestion_id"):
            return
        try:
            from models.delivery_management import DeliveryManagement
            g = ctx.db.get(DeliveryManagement, d["gestion_id"])
            if g:
                c = d.get("campos", {})
                g.status = estado
                g.customer_name, g.customer_phone = c.get("nombre"), (c.get("celular") or "")[:20]
                g.address, g.order_details, g.payment_method = c.get("direccion"), c.get("pedido"), c.get("pago")
                g.generated_link = (link or "")[:1500] or None
                if estado == "completed":
                    g.completed_at = ctx.ahora.astimezone(timezone.utc)
                ctx.db.commit()
        except Exception:
            ctx.db.rollback()


class _Redactor(Flujo):
    """Usa la maquinaria común (persona, guardias, traza) para redactar un paso del pedido."""

    def __init__(self, padre: Domicilios, datos: Datos):
        self.nombre, self._datos = padre.nombre, datos
        self.temperatura, self.max_tokens = padre.temperatura, padre.max_tokens

    async def reunir(self, ctx):
        return self._datos

    def respaldo(self, ctx, datos):
        falta = datos.hechos.get("me_falta")
        if falta:
            return "Para armar tu pedido me falta: " + ", ".join(falta) + "."
        return None


def recordatorio(ctx: Contexto) -> str | None:
    """Línea que se agrega cuando el cliente pregunta otra cosa a mitad de un pedido."""
    d = ctx.estado.datos
    if ctx.estado.flujo_activo != "domicilios" or not d.get("local"):
        return None
    return (f"_Tu pedido a *{d['local']}* sigue abierto: cuando quieras seguimos, o escribe *cancelar* "
            f"para cerrarlo._")