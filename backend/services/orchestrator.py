# 📄 ARCHIVO: backend/services/orchestrator.py
"""
ORQUESTADOR CENTRAL — el cerebro único del flujo nuevo.

Recibe cada mensaje en UN solo punto, decide qué herramienta usar
(híbrido: reglas para lo obvio, IA para lo ambiguo), la ejecuta, y
GUARDA UNA TRAZA completa de todo lo que pensó — para que el flujo sea
totalmente visible desde el panel.

Este es el ESQUELETO (paso 1): la estructura completa funciona de punta
a punta, con 2 herramientas conectadas de verdad (emergencia y
conversación general) para poder ver el sistema andando. Las demás
herramientas se irán conectando una a una, reutilizando la lógica que
YA existe (no se reescribe nada).

Convive con el flujo viejo mediante un switch (ver orchestrator_switch).
Mientras el switch no lo active, este código no toca a ningún cliente.
"""
import json
import re
import time
import logging
import contextvars

from sqlalchemy.orm import Session

from models.orchestrator_trace import OrchestratorTrace
from services.orchestrator_tools import HERRAMIENTAS, herramienta_por_nombre

logger = logging.getLogger("mall_bot")


# Nombre del cliente del mensaje en curso (perfil de WhatsApp). Se guarda
# aquí para que TODAS las herramientas lo tengan sin cambiar sus firmas.
# Antes el orquestador llamaba a _route_message con nombre "" y por eso Any
# nunca llamaba al cliente por su nombre en modo orquestador.
_usuario_actual: contextvars.ContextVar[str] = contextvars.ContextVar("usuario_actual", default="")


def nombre_cliente() -> str:
    """Nombre del cliente (o '' si WhatsApp no lo trae / es genérico)."""
    n = (_usuario_actual.get() or "").strip()
    if not n or n.lower() in ("usuario", "cliente", "tester", "none", "null"):
        return ""
    return n.split()[0].capitalize() if n.isupper() or n.islower() else n.split()[0]


class Traza:
    """Acumula los pasos del razonamiento para guardarlos al final."""
    def __init__(self, phone_number: str, mensaje: str, modo: str = "prueba"):
        self.phone_number = phone_number
        self.mensaje = mensaje
        self.modo = modo
        self.pasos = []
        self.inicio = time.time()
        self.herramienta_elegida = None
        self.metodo_decision = None
        self.razon_decision = None
        self.respuesta = None
        self.fotos = 0
        self.fotos_urls = []       # links de las fotos enviadas (para verlas en el panel)
        self.contenido_extra = []  # qué evento/promo/sorteo/tienda se agregó
        self.ubicacion = "no"
        self.uso_general = False   # True si la respuesta la terminó dando la conversación general (IA)

    def paso(self, nombre: str, detalle: str):
        ms = round((time.time() - self.inicio) * 1000, 1)
        self.pasos.append({"paso": nombre, "detalle": detalle, "ms": ms})

    def guardar(self, db: Session):
        trace = OrchestratorTrace(
            phone_number=self.phone_number,
            mensaje_usuario=self.mensaje,
            herramienta_elegida=self.herramienta_elegida,
            metodo_decision=self.metodo_decision,
            razon_decision=self.razon_decision,
            respuesta_bot=self.respuesta,
            fotos_enviadas=self.fotos,
            fotos_urls=json.dumps(self.fotos_urls, ensure_ascii=False),
            contenido_extra=json.dumps(self.contenido_extra, ensure_ascii=False),
            ubicacion_enviada=self.ubicacion,
            pasos=json.dumps(self.pasos, ensure_ascii=False),
            tiempo_total_ms=round((time.time() - self.inicio) * 1000, 1),
            modo=self.modo,
        )
        db.add(trace)
        db.commit()
        return trace


# ══════════════════════════════════════════════════════════════════
# DECISIÓN — qué herramienta usar (híbrido: reglas primero, IA después)
# ══════════════════════════════════════════════════════════════════

def _decidir_por_reglas(mensaje: str, traza: Traza) -> str | None:
    """
    Decisión RÁPIDA por palabras clave — para lo obvio, sin gastar IA.
    Recorre las herramientas EN ORDEN (las urgentes/específicas primero)
    y devuelve la primera que coincida. Si ninguna coincide con reglas
    claras, devuelve None y se pasa a la decisión por IA.
    """
    msg = mensaje.lower()
    for h in HERRAMIENTAS:
        palabras = h.get("palabras_clave", [])
        if not palabras:
            continue  # herramientas sin palabras clave se deciden por IA/lógica especial
        for palabra in palabras:
            if _coincide_palabra(palabra, msg):
                traza.paso("decision_reglas", f"La palabra '{palabra}' coincide con la herramienta '{h['nombre']}'")
                return h["nombre"]
    return None


def _coincide_palabra(palabra: str, msg: str) -> bool:
    """
    Coincidencia por PALABRA COMPLETA (acepta plural -s/-es), no por
    subcadena. Antes "tarifas de parqueadero" disparaba 'sorteos' porque
    "ta-RIFA-s" contiene "rifa". Las frases con espacios siguen igual.
    """
    pal = palabra.lower().strip()
    if " " in pal:
        return pal in msg
    return re.search(rf"(?<![a-záéíóúñü]){re.escape(pal)}(?:s|es)?(?![a-záéíóúñü])", msg) is not None


async def _decidir_por_ia(mensaje: str, traza: Traza) -> str:
    """
    Decisión FLEXIBLE por IA — para lo ambiguo o nuevo. Le da a la IA la
    lista de herramientas con sus descripciones y le pide que elija la
    más adecuada. Esto es lo que permite "pilotear" lo inesperado.

    Si la IA falla o elige algo inválido, cae a 'conversacion_general'
    (el fallback seguro).
    """
    from services.ai import _get_groq_client, settings, _strip_thinking_tags
    client = _get_groq_client()

    lista_tools = "\n".join(
        f"- {h['nombre']}: {h['descripcion']}"
        for h in HERRAMIENTAS
    )
    prompt = f"""Eres el enrutador de un asistente de centro comercial (Centro Comercial El Puente). Tu ÚNICA tarea es elegir qué herramienta debe manejar el mensaje del cliente. NO respondas al cliente, solo clasifica.

Herramientas disponibles:
{lista_tools}

Mensaje del cliente: "{mensaje}"

Reglas de decisión:
- Si el cliente busca/pregunta por un producto, comida, tienda o servicio → la herramienta de información que corresponda.
- Si es un saludo, charla casual, agradecimiento, o algo que NO es del centro comercial (preguntas generales, trivia, temas personales) → conversacion_general.
- Si expresa molestia, reclamo o inconformidad → queja.
- Si es una situación de peligro o urgencia → emergencia.

Responde SOLO con el nombre exacto de una herramienta de la lista (una palabra). Nada más."""

    try:
        completion = await client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,   # antes 20 — muy poco: el modelo razona internamente y no alcanzaba a escribir el nombre
            temperature=0.0,
        )
        raw = completion.choices[0].message.content or ""
        limpio = _strip_thinking_tags(raw).strip().lower()
        # El modelo a veces devuelve el nombre dentro de una frase — buscamos
        # cuál de las herramientas reales aparece en su respuesta.
        eleccion = None
        nombres = [h["nombre"] for h in HERRAMIENTAS]
        if limpio.strip(" .'\"`") in nombres:
            eleccion = limpio.strip(" .'\"`")
        else:
            # Fase 0: antes ganaba el primero de la LISTA que apareciera en la
            # frase ("no es emergencia → conversacion_general" elegía emergencia).
            # Ahora gana el que la IA nombró de último, que es su conclusión.
            pos = [(limpio.rfind(n), n) for n in nombres if n in limpio]
            if pos:
                eleccion = max(pos)[1]
        if eleccion:
            traza.paso("decision_ia", f"La IA eligió la herramienta '{eleccion}' (respuesta cruda: '{limpio[:40]}')")
            return eleccion
        traza.paso("decision_ia", f"La IA no dio una herramienta clara ('{limpio[:40]}') → se usa conversacion_general")
        return "conversacion_general"
    except Exception as e:
        traza.paso("decision_ia_error", f"Error al consultar la IA: {str(e)} → se usa conversacion_general")
        return "conversacion_general"


async def decidir_herramienta(mensaje: str, traza: Traza) -> tuple[str, str]:
    """
    Decisión HÍBRIDA. Devuelve (nombre_herramienta, metodo).
    1. Intenta por reglas (rápido, barato, para lo obvio).
    2. Si no hay match claro, decide por IA (flexible, para lo ambiguo).
    """
    por_reglas = _decidir_por_reglas(mensaje, traza)
    if por_reglas:
        traza.metodo_decision = "reglas"
        traza.razon_decision = f"Decisión por reglas (palabra clave) → {por_reglas}"
        return por_reglas, "reglas"

    traza.paso("decision", "Ninguna regla clara coincidió → se consulta a la IA para decidir")
    por_ia = await _decidir_por_ia(mensaje, traza)
    traza.metodo_decision = "ia"
    traza.razon_decision = f"Decisión por IA → {por_ia}"
    return por_ia, "ia"


# ══════════════════════════════════════════════════════════════════
# EJECUCIÓN — correr la herramienta elegida
# ══════════════════════════════════════════════════════════════════

# Contacto del mall para emergencias y quejas (del Info General)
CONTACTO_MALL = "317 432 0138"


async def _ejecutar_emergencia(db, phone_number, mensaje, traza) -> dict:
    """
    Herramienta de EMERGENCIA — respuesta inmediata, calmada y con la
    ruta correcta. NO usa IA (para que sea instantánea). Tiene 3
    variantes que rotan para que no suene idéntica cada vez, pero TODAS
    dan siempre la misma información crítica: Punto de Información +
    seguridad + contacto del mall. Consistente en lo importante, con un
    toque humano en la forma.
    """
    import random
    traza.paso("ejecucion", "Ejecutando herramienta de emergencia — respuesta directa con contacto de seguridad")
    variantes = [
        (
            "🚨 Entiendo que es una situación urgente. Por favor, dirígete de inmediato al *Punto de "
            "Información* (Pasillo Barichara) o busca al personal de *seguridad* más cercano — ellos pueden actuar "
            "al instante.\n\n"
            f"También puedes llamar directamente a la administración del centro comercial al *{CONTACTO_MALL}*.\n\n"
            "Estamos para ayudarte."
        ),
        (
            "🚨 Lo primero es mantener la calma — estamos aquí para ayudarte. Acércate lo más rápido "
            "posible al *Punto de Información* (Pasillo Barichara) o busca al *personal de seguridad*, que está "
            "capacitado para atender este tipo de situaciones de inmediato.\n\n"
            f"Si lo prefieres, llama directo a la administración al *{CONTACTO_MALL}*. No estás solo en esto."
        ),
        (
            "🚨 Entiendo la urgencia y vamos a ayudarte. Dirígete ya al *Punto de Información* (Pasillo Barichara) "
            "o al *personal de seguridad* más cercano — ellos pueden actuar en el momento.\n\n"
            f"También tienes la línea directa de la administración: *{CONTACTO_MALL}*. Cuenta con nosotros."
        ),
    ]
    return {"text": random.choice(variantes), "image_urls": [], "location": None}


async def _ejecutar_conversacion_general(db, phone_number, mensaje, traza) -> dict:
    """
    Herramienta GENERAL / piloteo. Delega en _route_message (el flujo
    viejo probado) porque este NO solo genera el texto — también adjunta
    automáticamente las FOTOS de la tienda/evento/sorteo/marketing que
    se haya mencionado (toda esa lógica ya existe y funciona ahí). Si
    llamáramos a generate_response directo, perderíamos las fotos.

    Mantiene las 2 redes de seguridad: si _route_message devuelve texto
    vacío, se reintenta; si sigue vacío, respaldo amable.
    """
    traza.paso("ejecucion", "Conversación general → delega en _route_message (incluye fotos de tienda/evento/sorteo)")
    from routers.webhook import _route_message

    traza.uso_general = True

    async def _intentar():
        r = await _route_message(db, phone_number, nombre_cliente(), mensaje)
        return r

    resultado = None
    try:
        resultado = await _intentar()
    except Exception as e:
        traza.paso("error", f"_route_message falló: {str(e)}")

    # Red 1: reintento si vino vacío o ridículamente corto ("Juan, no")
    if not resultado or len((resultado.get("text") or "").strip()) < 12:
        traza.paso("reintento", "_route_message devolvió vacío → se reintenta una vez")
        try:
            resultado = await _intentar()
        except Exception as e:
            traza.paso("reintento_error", f"El reintento falló: {str(e)}")

    # Red 2: respaldo amable si sigue vacío
    if not resultado or not (resultado.get("text") or "").strip():
        traza.paso("respaldo", "Sigue vacío → mensaje de respaldo")
        return {
            "text": (
                "¡Hola! Soy Any 🛍️, tu asistente del Centro Comercial El Puente. "
                "¿En qué te puedo ayudar? Puedo orientarte con tiendas, comida, horarios, "
                "servicios o cualquier cosa del centro comercial 😊"
            ),
            "image_urls": [], "location": None,
        }

    fotos = len(resultado.get("image_urls") or [])
    traza.paso("resultado_ia", f"Respuesta final: {len((resultado.get('text') or ''))} caracteres, {fotos} foto(s)")
    return {
        "text": resultado.get("text", ""),
        "image_urls": resultado.get("image_urls", []),
        "location": resultado.get("location"),
        "mentioned_store_id": resultado.get("mentioned_store_id"),  # memoria de contexto
    }


# ══════════════════════════════════════════════════════════════════
# HERRAMIENTAS conectadas a la lógica que YA existe (no se reescribe)
# ══════════════════════════════════════════════════════════════════

async def _ejecutar_queja(db, phone_number, mensaje, traza) -> dict:
    """
    Herramienta de QUEJA — recoge la inconformidad con empatía y la
    escala al contacto del mall. NO usa IA. Tiene 3 variantes que rotan
    para sonar más humana, pero todas mantienen la empatía y el canal
    correcto (administración + Punto de Información).
    """
    import random
    traza.paso("ejecucion", "Ejecutando herramienta de queja — respuesta empática con canal de escalamiento")
    variantes = [
        (
            "Lamento mucho lo que pasó, y gracias por tomarte el tiempo de contarnos — "
            "tu comentario es importante para el centro comercial. 🙏\n\n"
            "Para que tu queja quede registrada formalmente y le den seguimiento, te recomiendo "
            f"comunicarte con la administración al *{CONTACTO_MALL}*, o acercarte al *Punto de "
            "Información* (Pasillo Barichara). Ahí podrán ayudarte de manera directa.\n\n"
            "¿Hay algo más en lo que te pueda apoyar mientras tanto?"
        ),
        (
            "Siento mucho que hayas vivido esa experiencia, y de verdad agradezco que nos lo cuentes — "
            "así el centro comercial puede mejorar. 🙏\n\n"
            "Para que tu caso quede registrado y le hagan seguimiento, lo mejor es que te comuniques con "
            f"la administración al *{CONTACTO_MALL}* o pases por el *Punto de Información* (Pasillo Barichara), donde "
            "te atenderán directamente.\n\n"
            "¿Puedo ayudarte con algo más mientras tanto?"
        ),
        (
            "Lamento lo sucedido y te agradezco la confianza de contárnoslo. Tu opinión nos ayuda a "
            "mejorar la experiencia en el centro comercial. 🙏\n\n"
            f"Para darle trámite formal a tu queja, comunícate con la administración al *{CONTACTO_MALL}* "
            "o acércate al *Punto de Información* (Pasillo Barichara); ellos podrán gestionarla como corresponde.\n\n"
            "Quedo atenta por si necesitas algo más."
        ),
    ]
    texto = random.choice(variantes)
    return {"text": texto, "image_urls": [], "location": None}


def _telefono_administracion(db) -> str:
    """Teléfono de la Administración si está cargada como 'local' de servicios; si no, el del mall."""
    try:
        from models.store import Store
        adm = db.query(Store).filter(Store.name.ilike("%administraci%")).first()
        if adm and adm.phone:
            return adm.phone
    except Exception:
        pass
    return CONTACTO_MALL


def _link_wa(numero: str) -> str:
    tel = re.sub(r"\D", "", numero or "")
    if tel.startswith("3") and len(tel) == 10:
        tel = "57" + tel
    return f"https://wa.me/{tel}" if tel else ""


async def _ejecutar_administracion_mall(db, phone_number, mensaje, traza) -> dict:
    """
    Temas que resuelve la ADMINISTRACIÓN del centro comercial, no Any:
    alquiler de salón/local/espacio/stand, publicidad, proveedores,
    empleo/hojas de vida, convenios. Respuesta corta y directa con el
    contacto, sin inventar precios ni disponibilidad.
    """
    nom = nombre_cliente()
    tel_adm = _telefono_administracion(db)
    msg = _sin_tildes_simple(mensaje)
    if any(k in msg for k in ("salon", "alquil", "arrend", "arriendo", "espacio", "stand", "local disponible", "locales disponibles", "fiesta", "evento privado")):
        tema = "el alquiler de salones, locales o espacios"
    elif any(k in msg for k in ("publicidad", "pautar", "pauta", "patrocin", "convenio")):
        tema = "publicidad, pauta y convenios"
    elif any(k in msg for k in ("hoja de vida", "hojas de vida", "empleo", "vacante", "trabajar", "trabajo")):
        tema = "empleo y hojas de vida"
    elif any(k in msg for k in ("proveedor", "vender mis productos", "ofrecer mis servicios")):
        tema = "proveedores"
    else:
        tema = "ese tema"
    traza.paso("ejecucion", f"Administración del mall → {tema} (se da el contacto, sin inventar condiciones)")
    saludo = f"{nom}, eso" if nom else "Eso"
    texto = (f"{saludo} lo maneja directamente la *Administración del Centro Comercial El Puente* ({tema}).\n"
             f"📞 {tel_adm}" + (f" 👉 {_link_wa(tel_adm)}" if _link_wa(tel_adm) else ""))
    if tel_adm != CONTACTO_MALL:
        texto += f"\n📱 Línea del centro comercial: {CONTACTO_MALL} 👉 {_link_wa(CONTACTO_MALL)}"
    texto += "\nEllos te confirman disponibilidad, condiciones y costos. 😊"
    return {"text": texto, "image_urls": [], "location": None}


async def _ejecutar_numero_tienda(db, phone_number, mensaje, traza) -> dict:
    """Reutiliza la lógica del flujo viejo: buscar tienda + armar su info de contacto."""
    from services.store_transfer import find_store_by_message, build_phone_info_message
    from routers.webhook import _pick_store_photo, _wrap

    store = find_store_by_message(db, mensaje)
    if store:
        traza.paso("ejecucion", f"Tienda encontrada: '{store.name}' → se arma su número + link (lógica existente)")
        return {
            "text": build_phone_info_message(store),
            "image_urls": _wrap([_pick_store_photo(store, mensaje)]),
            "location": None,
            "mentioned_store_id": store.id,
        }
    traza.paso("ejecucion", "No se identificó una tienda puntual → cae a conversación general")
    return await _ejecutar_conversacion_general(db, phone_number, mensaje, traza)


async def _ejecutar_cartelera_cine(db, phone_number, mensaje, traza) -> dict:
    """
    Todo lo del CINE, según lo que pregunten:
      - tarifas/boleta/precio        → bloque de TARIFAS (de la info extra del cine)
      - confitería/combos/crispetas  → bloque de CONFITERÍA
      - dónde queda / ubicación      → datos del local del cine
      - una película puntual         → esa película (horarios + sinopsis)
      - lo demás                     → cartelera completa (corta: título, horarios, ficha)
    La info extra (tarifas/confitería) la carga 'Sincronizar web' o la
    plantilla de cine; si no existe, se dice con honestidad y se da el contacto.
    """
    from services.cine import (find_cine_store, find_cine_funcion_by_message, build_cartelera_message,
                               build_funcion_especifica_message, bloque_info_extra, resumir_tarifas, URL_COMPRA_CINE)
    from routers.webhook import _wrap

    cine_store = find_cine_store(db)
    if not cine_store:
        traza.paso("ejecucion", "No hay tienda de cine registrada")
        return {"text": build_cartelera_message(None), "image_urls": [], "location": None}

    msg = _sin_tildes_simple(mensaje)
    nom = nombre_cliente()

    def _intro(frase: str) -> str:
        # "Sebastián, estas son…" / "Estas son…"
        return f"{nom}, {frase}" if nom else frase[0].upper() + frase[1:]

    def _contacto() -> str:
        tel = re.sub(r"\D", "", cine_store.phone or "")
        return f" Puedes confirmar directo con el cine al {cine_store.phone}." if tel else " Puedes confirmar en la taquilla del cine."

    # ── Comprar / reservar boletas → link de compra (sin inventar pasos) ──
    if any(k in msg for k in ("comprar", "compro", "reservar", "reserva", "adquirir", "en linea", "online", "por internet", "pagina del cine", "como hago para")):
        bloque = bloque_info_extra(cine_store, "tarifa")
        resumen = resumir_tarifas(bloque) if bloque else ""
        traza.paso("ejecucion", "Cine → compra/reserva de boletas: link de Cinelandia + resumen de tarifas")
        texto = (f"🎟️ {_intro('las boletas de *' + cine_store.name + '* se compran en taquilla o en línea aquí 👉 ' + URL_COMPRA_CINE)}\n"
                 "Ahí eliges la película, el horario y la silla.")
        if resumen:
            texto += "\n\n" + resumen
        return {"text": texto, "image_urls": [], "location": None, "mentioned_store_id": cine_store.id}

    # ── Tarifas / precios ──
    if any(k in msg for k in ("tarifa", "precio", "cuanto vale", "cuanto cuesta", "cuanto esta", "boleta", "boleteria", "entrada", "cuanto sale", "valor de")) and not any(k in msg for k in ("combo", "crispeta", "confiteria", "palomita")):
        bloque = bloque_info_extra(cine_store, "tarifa")
        traza.paso("ejecucion", f"Cine → tarifas ({'encontradas' if bloque else 'sin datos cargados'})")
        if bloque:
            texto = resumir_tarifas(bloque) or bloque
            return {"text": f"🎟️ {_intro(f'estas son las tarifas de *{cine_store.name}*:')}\n\n{texto}\n\nCompra en línea 👉 {URL_COMPRA_CINE}", "image_urls": [], "location": None, "mentioned_store_id": cine_store.id}
        return {"text": f"Aún no tengo las tarifas de *{cine_store.name}* cargadas.{_contacto()}", "image_urls": [], "location": None, "mentioned_store_id": cine_store.id}

    # ── Confitería / combos ──
    if any(k in msg for k in ("combo", "crispeta", "confiteria", "palomita", "gaseosa", "perro caliente", "nachos")):
        bloque = bloque_info_extra(cine_store, "confiter")
        traza.paso("ejecucion", f"Cine → confitería ({'encontrada' if bloque else 'sin datos cargados'})")
        if bloque:
            return {"text": f"🍿 {_intro(f'esto tiene la confitería de *{cine_store.name}*:')}\n\n{bloque}", "image_urls": [], "location": None, "mentioned_store_id": cine_store.id}
        return {"text": f"Aún no tengo los combos de confitería de *{cine_store.name}* cargados.{_contacto()}", "image_urls": [], "location": None, "mentioned_store_id": cine_store.id}

    # ── Ubicación / horario del cine como local ──
    if any(k in msg for k in ("donde queda", "donde esta", "ubicacion", "en que piso", "como llego", "horario del cine", "a que hora abre")) and not any(k in msg for k in ("pelicula", "funcion", "cartelera")):
        partes = [f"🎬 *{cine_store.name}*"]
        from services.category_search import ubicacion_mostrable
        ubic = ubicacion_mostrable(cine_store)
        if ubic:
            partes.append(f"📍 {ubic}")
        if cine_store.schedule:
            partes.append(f"🕒 {cine_store.schedule}")
        if cine_store.phone:
            partes.append(f"📞 {cine_store.phone}")
        traza.paso("ejecucion", "Cine → ubicación/datos del local")
        return {"text": "\n".join(partes), "image_urls": [], "location": None, "mentioned_store_id": cine_store.id}

    # ── Película puntual ──
    funcion = find_cine_funcion_by_message(db, cine_store.id, mensaje)
    if funcion:
        traza.paso("ejecucion", f"Película puntual: '{funcion.title}'")
        from models.entity_photo import get_entity_photo
        poster = get_entity_photo(db, "cine_funcion", funcion.id, "poster")
        return {"text": build_funcion_especifica_message(funcion, cine_store), "image_urls": _wrap([poster]), "location": None, "mentioned_store_id": cine_store.id}

    # ── Cartelera completa ──
    traza.paso("ejecucion", f"Cartelera completa de '{cine_store.name}'")
    from models.entity_photo import get_entity_photo
    posters = []
    for f in cine_store.cine_funciones:
        if f.active and len(posters) < 2:
            p = get_entity_photo(db, "cine_funcion", f.id, "poster")
            if p:
                posters.append(p)
    texto = build_cartelera_message(cine_store)
    # Si preguntaron por una película que NO está en cartelera, se aclara.
    if any(k in msg for k in ("horario", "a que hora", "dan ", "funcion", "de que trata")) and "pelicula" not in msg and "cartelera" not in msg and "cine" not in msg:
        texto = "Esa película no está en la cartelera de esta semana. " + texto
    return {"text": texto, "image_urls": posters, "location": None, "mentioned_store_id": cine_store.id}


async def _ejecutar_busqueda_categoria(db, phone_number, mensaje, traza) -> dict:
    """
    Búsqueda JUSTA por categoría: SIEMPRE se listan TODOS los locales que
    coinciden, sin importar cuántos sean (ropa=27, zapatos=16…). Es una
    exigencia del Centro Comercial: si se muestran solo algunos o se
    "pregunta para acotar", los demás locales sienten que hay preferencia.
    Las listas largas ya no son problema porque WhatsApp parte los
    mensajes largos automáticamente (ver services/whatsapp.py).
    Con 0 locales, cae a conversación general.
    """
    from services.category_search import detectar_categoria, construir_lista_locales
    from services.rag import find_all_stores_by_category

    # La IA (o las reglas) YA decidieron que es una búsqueda por categoría:
    # no exigimos verbo ("dónde", "quiero"). "tiendas de ropa", "droguerías",
    # "juguetería" deben listar TODOS los locales, no caer a la IA.
    cat = detectar_categoria(mensaje, exigir_intencion=False)
    if cat:
        nombre_cat, terminos = cat
        locales = find_all_stores_by_category(db, terminos)
        traza.paso("ejecucion", f"Categoría '{nombre_cat}' → {len(locales)} locales (búsqueda justa, se listan TODOS)")

        if len(locales) >= 1:
            # Aunque sea UN solo local, se muestra — antes se exigía 2+ y
            # un local real (ej. Juguetería Cocoa Kids) quedaba oculto y el
            # bot decía "no hay juguetería" siendo falso.
            return {"text": construir_lista_locales(locales, nombre_cat), "image_urls": [], "location": None}

    traza.paso("ejecucion", "No se detectó categoría con locales → cae a conversación general")
    return await _ejecutar_conversacion_general(db, phone_number, mensaje, traza)


async def _ejecutar_ubicacion_mall(db, phone_number, mensaje, traza) -> dict:
    """Manda el pin real del mall — misma lógica del flujo viejo."""
    from models.mall_info import MallInfo

    mall_info = db.query(MallInfo).filter(MallInfo.id == 1).first()
    if mall_info and mall_info.latitude and mall_info.longitude:
        try:
            location = {
                "latitude": float(mall_info.latitude),
                "longitude": float(mall_info.longitude),
                "name": mall_info.name,
                "address": mall_info.address or "",
            }
            traza.paso("ejecucion", f"Ubicación del mall → pin real ({location['latitude']}, {location['longitude']})")
            texto = f"📍 {mall_info.name} está ubicado en {mall_info.address or 'el centro de la ciudad'}. Te comparto la ubicación exacta 😊"
            return {"text": texto, "image_urls": [], "location": location}
        except ValueError:
            pass
    traza.paso("ejecucion", "Sin coordenadas del mall → cae a conversación general")
    return await _ejecutar_conversacion_general(db, phone_number, mensaje, traza)


async def _ejecutar_gestion_domicilio(db, phone_number, mensaje, traza) -> dict:
    """
    La gestión de domicilio del flujo viejo tiene varios pasos
    entrelazados (identificar la tienda, validar horario, recolectar
    datos, detectar cancelaciones). En vez de reimplementar eso —donde
    es fácil introducir bugs— delegamos en _route_message del flujo
    viejo, que ya orquesta todo el domicilio correctamente. Reutilización
    pura: el orquestador decide "esto es domicilio", y deja que la
    maquinaria probada lo maneje.
    """
    traza.paso("ejecucion", "Gestión de domicilio → delega en el flujo probado (_route_message) para no romper el paso a paso")
    from routers.webhook import _route_message
    resultado = await _route_message(db, phone_number, nombre_cliente(), mensaje)
    return {
        "text": resultado.get("text", ""),
        "image_urls": resultado.get("image_urls", []),
        "location": resultado.get("location"),
        "mentioned_store_id": resultado.get("mentioned_store_id"),
    }


async def _ejecutar_torre_medica(db, phone_number, mensaje, traza) -> dict:
    """
    Torre médica / servicios de salud. Busca en la base de conocimiento
    (donde se cargará la info de la torre médica). Si encuentra algo
    relevante, responde con eso. Si NO hay datos cargados, da una
    respuesta HONESTA y CONSISTENTE — sin inventar ubicaciones, y SIN
    adjuntar fotos ni el pin del mall de relleno (que era justo el bug:
    mandaba la foto de la última hamburguesa y el mapa sin venir al
    caso). Cuando cargues los datos de la torre médica, responderá con
    el consultorio exacto.
    """
    from services.rag import search_knowledge_and_events
    from services.store_transfer import find_store_by_message
    from models.store import Store as _Store

    traza.paso("ejecucion", "Consulta de servicios médicos → primero busca en los locales (torre médica)")

    # ── 0) ¿Nombró un consultorio/servicio puntual? (Sanitas, ISEM, FOSCAL…)
    #    Los consultorios se cargan como locales con zona 'Torre Médica',
    #    así que la misma búsqueda de tiendas los encuentra.
    store = find_store_by_message(db, mensaje)
    # Fase 0: antes decía "X se encuentra en la Torre Médica" para CUALQUIER
    # local nombrado (ej. una droguería del centro comercial).
    if store and "torre" not in (store.location_hint or "").lower():
        store = None
    if store:
        traza.paso("ejecucion", f"Servicio médico puntual encontrado en locales: '{store.name}'")
        partes = [f"🏥 *{store.name}* se encuentra en la *Torre Médica* del Centro Comercial El Puente."]
        piso = (store.floor or "").strip()
        if piso and piso.lower() != "por confirmar":
            partes.append(f"📍 {piso}")
        if store.schedule:
            partes.append(f"🕒 {store.schedule}")
        link = store.whatsapp_link()
        if store.phone and link:
            partes.append(f"📞 {store.phone} 👉 {link}")
        elif store.phone:
            partes.append(f"📞 {store.phone}")
        partes.append("Si necesitas llegar, el *Punto de Información* (Pasillo Barichara) también puede orientarte. 😊")
        return {"text": "\n".join(partes), "image_urls": [], "location": None}

    # ── 1) ¿Pregunta general por la torre médica? → listar los consultorios cargados
    medicos = db.query(_Store).filter(
        _Store.active == True, _Store.location_hint.ilike("%torre%")
    ).all()
    # Limpieza defensiva (fase 0): la sincronización de la web creó filas
    # basura llamadas "Teléfono:" y hay consultorios duplicados (uno vacío).
    vistos = {}
    for m in medicos:
        nm = (m.name or "").strip()
        if not nm or nm.endswith(":"):
            continue
        k = nm.lower()
        if k not in vistos or (m.description and not vistos[k].description):
            vistos[k] = m
    medicos = sorted(vistos.values(), key=lambda m: m.name.lower())

    def _linea_consultorio(m):
        det = f"• *{m.name}*"
        piso = (m.floor or "").strip()
        if piso.lower().startswith("piso"):
            det += f" — {piso}"  # en la Torre sí se dice el piso (única excepción)
        if m.phone:
            det += f" — 📞 {m.phone}"
        return det

    # ── 1a) ¿Lo que pide coincide con la especialidad de algún consultorio?
    #    Antes solo se miraba la Torre si el mensaje decía "médico",
    #    "consultorio"…; "¿tienen vacunación?" respondía "no tengo datos"
    #    teniendo 29 consultorios cargados (traza #7, 23/10).
    from services.rag import _palabras, _coincide_palabra
    genericas = {"tienes", "tienen", "tiene", "hay", "servicio", "servicios", "quiero", "necesito", "donde",
                 "queda", "algun", "alguna", "cita", "sacar", "medico", "medica", "doctor", "doctora",
                 "consultorio", "consultorios", "torre", "salud", "para", "como", "puedo", "busco"}
    claves = [w for w in _palabras(mensaje) if len(w) >= 4 and w not in genericas]
    if medicos and claves:
        hallados = [m for m in medicos if any(
            _coincide_palabra(c, _palabras(f"{m.name} {m.tags or ''} {m.description or ''}")) for c in claves)]
        if hallados:
            traza.paso("ejecucion", f"Torre médica → {len(hallados)} consultorio(s) coinciden con {claves}")
            lineas = ["🏥 Para eso, en la *Torre Médica* del Centro Comercial El Puente encuentras:\n"]
            lineas += [_linea_consultorio(m) for m in hallados]
            lineas.append("\nTe recomiendo llamar antes para confirmar disponibilidad. 😊")
            return {"text": "\n".join(lineas), "image_urls": [], "location": None}

    pide_lista = any(p in mensaje.lower() for p in (
        "torre", "medic", "médic", "consultorio", "salud", "doctor", "especialista", "cita"
    ))
    if medicos:
        # Si eligieron la Torre pero no hubo coincidencia puntual, se muestran
        # los consultorios cargados en vez de "no tengo datos".
        traza.paso("ejecucion", f"Torre médica → se listan {len(medicos)} consultorios/servicios cargados")
        if pide_lista:
            lineas = ["🏥 En la *Torre Médica* del Centro Comercial El Puente encuentras:\n"]
        else:
            lineas = ["No encontré ese servicio exacto entre los consultorios registrados. "
                      "Estos son los de la *Torre Médica*, por si alguno te sirve:\n"]
        lineas += [_linea_consultorio(m) for m in medicos]
        lineas.append("\n¿Buscas alguno en particular? Dime el nombre y te paso sus datos. 😊")
        return {"text": "\n".join(lineas), "image_urls": [], "location": None}

    # Buscar en la base de conocimiento algo sobre torre médica/servicios
    try:
        docs = search_knowledge_and_events(mensaje, n_results=3)
    except Exception:
        docs = []

    # Filtrar a lo que de verdad hable de salud/torre médica
    relevantes = [d for d in docs if any(
        k in d.lower() for k in ("médic", "medic", "salud", "torre", "consultorio", "clínic", "clinic", "radiograf", "laboratorio")
    )]

    if relevantes:
        traza.paso("resultado", f"Encontró {len(relevantes)} entrada(s) relevante(s) en la base de conocimiento")
        from services.ai import generate_response
        # Usamos la IA solo para redactar con base en lo encontrado, pero
        # SIN la maquinaria de fotos del flujo viejo.
        contexto = "\n".join(relevantes[:2])
        texto, *_ = await generate_response(
            user_message=mensaje,
            user_name="",
            conversation_history=[{"role": "system", "content": f"Información disponible sobre servicios médicos del centro comercial:\n{contexto}"}],
            db=db,
            phone_number=phone_number,
        )
        if (texto or "").strip():
            return {"text": texto.strip(), "image_urls": [], "location": None}

    # Sin datos → respuesta honesta, consistente, sin fotos ni pin de relleno
    traza.paso("respaldo_honesto", "Sin datos de torre médica cargados → respuesta honesta y consistente (sin foto ni ubicación de relleno)")
    texto = (
        "El Centro Comercial El Puente cuenta con una *Torre Médica y Empresarial* donde hay varios "
        "consultorios y servicios de salud. Para orientarte al consultorio exacto que necesitas, te "
        "recomiendo acercarte al *Punto de Información* (Pasillo Barichara) o llamar a la administración al "
        f"*{CONTACTO_MALL}* — con gusto te indican dónde dirigirte. 😊"
    )
    return {"text": texto, "image_urls": [], "location": None}


# ══════════════════════════════════════════════════════════════════
# HERRAMIENTAS DEDICADAS: EVENTOS, SORTEOS, PROMOCIONES
# Cada una trae SU información específica y manda SU foto directamente
# (sin depender de que la IA adivine el ID). Así nunca se mezclan ni
# mandan fotos equivocadas.
# ══════════════════════════════════════════════════════════════════

def _foto_de_entidad(db, tipo, entidad):
    """Busca la foto de un evento/sorteo/promo: primero en entity_photo,
    y si no, en el campo photo_url del propio modelo. Devuelve None si no
    hay ninguna — nunca una foto de algo diferente."""
    from models.entity_photo import get_entity_photo
    # 1) tabla entity_photo (galería con etiquetas)
    url = get_entity_photo(db, tipo, entidad.id, "portada")
    if url:
        return url
    # 2) campo directo del modelo (donde a veces se carga la foto)
    return getattr(entidad, "photo_url", None) or None


async def _redactar_creativo(datos_fijos: str, tipo_contenido: str, traza) -> str | None:
    """
    Toma los datos EXACTOS (fechas, premios, requisitos, etc.) y le pide
    a la IA que redacte una invitación cálida y atractiva alrededor de
    ellos — SIN cambiar ni inventar ningún dato. Es la "creatividad
    seria": decora la plantilla, no altera la información.

    Devuelve el texto redactado, o None si algo falla (en cuyo caso el
    llamador usa su plantilla fija como respaldo — nunca se queda sin
    respuesta).
    """
    from services.ai import _get_groq_client, settings, _strip_thinking_tags
    prompt = f"""Eres Any, la asistente cálida del Centro Comercial El Puente. Escribe un mensaje corto, alegre y natural para invitar a un cliente a este {tipo_contenido}, usando EXACTAMENTE estos datos (no cambies fechas, nombres, premios ni requisitos, no inventes nada que no esté aquí):

{datos_fijos}

Reglas:
- Tono cálido, entusiasta y cercano (colombiano natural), sin exagerar ni sonar falso.
- Usa máximo 2 emojis, donde aporten.
- Menciona TODOS los datos dados (fecha, lugar, premio, cómo participar, etc.) pero de forma fluida, no como una lista de campos rígida.
- Extensión: entre 3 y 6 líneas. Ni muy corto (no vale un saludo de una línea), ni muy largo.
- NO inventes precios, requisitos ni fechas que no estén arriba.
- No agregues despedidas largas ni "pasa por el Punto de Información".
Responde SOLO con el mensaje para el cliente, nada más."""
    try:
        client = _get_groq_client()
        completion = await client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.85,  # alto para creatividad; los datos van fijos en el prompt
        )
        texto = _strip_thinking_tags(completion.choices[0].message.content or "").strip()
        if texto and len(texto) > 60:  # mínimo real, para que no salga un saludo corto sin datos
            traza.paso("creatividad", f"Texto redactado con IA (creatividad seria) para {tipo_contenido}")
            return texto
    except Exception as e:
        traza.paso("creatividad_error", f"No se pudo redactar creativo ({e}) → se usa plantilla fija")
    return None


PALABRAS_INSCRIPCION = ("inscrib", "inscripcion", "anotar", "anotarme", "registrarme", "registrar a", "participar en",
                        "como participo", "cupo", "cupos", "matricular", "apuntar")


def _respuesta_inscripcion_evento(db, mensaje: str, traza) -> dict | None:
    """
    "Quiero inscribir a mis hijos en Run Run Kids" → datos EXACTOS del evento
    + contacto del mall para la inscripción. Nunca se inventa el procedimiento
    (antes la IA decía "lleva la cédula, paga en efectivo…" sin base).
    """
    msg = _sin_tildes_simple(mensaje)
    if not any(k in msg for k in PALABRAS_INSCRIPCION):
        return None
    try:
        from services.content_matching import find_event_by_message
        ev = find_event_by_message(db, mensaje)
    except Exception:
        ev = None
    if not ev:
        return None
    nom = nombre_cliente()
    lineas = [f"{'¡Claro, ' + nom + '!' if nom else '¡Claro!'} Esto es lo que tengo del *{ev.name}*:"]
    if ev.date:
        lineas.append(f"📅 {ev.date}" + (f" · {ev.time}" if ev.time else ""))
    if ev.location:
        lineas.append(f"📍 {ev.location}")
    if ev.description:
        lineas.append(ev.description.strip())
    lineas.append(f"\nPara inscribirte y confirmar requisitos, escribe al centro comercial: {CONTACTO_MALL} 👉 {_link_wa(CONTACTO_MALL)}"
                  " o acércate al *Punto de Información*. Ellos te guían con el pago y la inscripción. 😊")
    traza.paso("inscripcion", f"Inscripción al evento '{ev.name}' → datos exactos + contacto del mall (sin inventar procedimiento)")
    return {"text": "\n".join(lineas), "image_urls": [], "location": None, "evento_id": ev.id}


async def _ejecutar_eventos(db, phone_number, mensaje, traza) -> dict:
    """Lista los eventos activos. Si hay pocos sorteos, los menciona
    también (para promocionar sin saturar). Manda la foto del evento de
    mayor prioridad."""
    from models.event import Event
    from models.raffle import Raffle

    insc = _respuesta_inscripcion_evento(db, mensaje, traza)
    if insc:
        ev = db.query(Event).filter(Event.id == insc.pop("evento_id")).first()
        foto = _foto_de_entidad(db, "event", ev) if ev else None
        insc["image_urls"] = [foto] if foto else []
        return insc

    eventos_todos = [e for e in db.query(Event).order_by(Event.priority.desc()).all() if e.esta_vigente()]
    if not eventos_todos:
        traza.paso("ejecucion", "No hay eventos cargados → respuesta honesta")
        return {"text": "Por ahora no tenemos eventos programados, pero te invito a estar pendiente 😊. "
                        "¿Te ayudo con algo más del centro comercial?", "image_urls": [], "location": None}

    # ROTACIÓN: si hay varios eventos, se elige uno como "principal" (el
    # que da la foto y encabeza) de forma ponderada por prioridad — los
    # más importantes salen de primeros más seguido, pero rotan. Así la
    # foto no es siempre la del mismo evento. Los demás igual se listan.
    import random as _rnd
    if len(eventos_todos) > 1:
        pesos = [max(1, e.priority) ** 2 for e in eventos_todos]
        principal = _rnd.choices(eventos_todos, weights=pesos, k=1)[0]
        eventos = [principal] + [e for e in eventos_todos if e.id != principal.id]
    else:
        eventos = eventos_todos

    # Datos EXACTOS de los eventos (para la redacción creativa)
    datos = []
    for e in eventos[:4]:
        d = f"Evento: {e.name}"
        if e.date: d += f". Fecha: {e.date}" + (f" a las {e.time}" if e.time else "")
        if e.location: d += f". Lugar: {e.location}"
        if e.description: d += f". Descripción: {e.description}"
        datos.append(d)
    sorteos = [r for r in db.query(Raffle).filter(Raffle.active == True).order_by(Raffle.priority.desc()).all() if r.esta_vigente()]
    if sorteos and len(sorteos) <= 2:
        datos.append("Además, menciona brevemente que también hay un sorteo activo (" +
                     ", ".join(s.name for s in sorteos) + ") por si quiere preguntar por él.")

    # CREATIVIDAD SERIA: la IA redacta la invitación con esos datos exactos
    texto = await _redactar_creativo("\n".join(datos), "evento", traza)

    # Respaldo: plantilla fija si la IA falló (nunca quedar sin respuesta)
    if not texto:
        import random as _rnd
        _intro_ev = _rnd.choice([
            "¡Estos son los eventos del Centro Comercial El Puente! 🎉\n",
            "¡Tenemos planes que no te puedes perder! 🎉 Estos son los eventos del centro comercial:\n",
            "¡Prepárate, porque vienen cosas buenas! 🎉 Estos son nuestros eventos:\n",
        ])
        lineas = [_intro_ev]
        for e in eventos[:4]:
            linea = f"*{e.name}*"
            if e.date:
                linea += f"\n📅 {e.date}" + (f" · {e.time}" if e.time else "")
            if e.location:
                linea += f"\n📍 {e.location}"
            if e.description:
                linea += f"\n{e.description}"
            lineas.append(linea)
        if sorteos and len(sorteos) <= 2:
            nombres = ", ".join(f"*{s.name}*" for s in sorteos)
            lineas.append(f"\nY no te pierdas nuestro sorteo: {nombres} 🎁 — pregúntame por él si quieres los detalles.")
        texto = "\n\n".join(lineas)

    # Foto del evento principal (mayor prioridad)
    foto = _foto_de_entidad(db, "event", eventos[0])
    fotos = [foto] if foto else []
    if foto:
        traza.paso("foto", f"Foto del evento '{eventos[0].name}' adjuntada")
    else:
        traza.paso("foto", f"El evento '{eventos[0].name}' no tiene foto cargada → no se manda ninguna (nunca de relleno)")

    return {"text": texto, "image_urls": fotos, "location": None}


async def _ejecutar_sorteos(db, phone_number, mensaje, traza) -> dict:
    """Lista los sorteos activos. Si hay pocos eventos, los menciona
    también. Manda la foto del sorteo principal."""
    from models.raffle import Raffle
    from models.event import Event

    sorteos_todos = [r for r in db.query(Raffle).filter(Raffle.active == True).order_by(Raffle.priority.desc()).all() if r.esta_vigente()]
    if not sorteos_todos:
        traza.paso("ejecucion", "No hay sorteos activos → respuesta honesta")
        return {"text": "Por ahora no tenemos sorteos activos, pero mantente atento porque siempre hay novedades 😊. "
                        "¿Te ayudo con algo más?", "image_urls": [], "location": None}

    # ROTACIÓN ponderada por prioridad para el sorteo principal (la foto)
    import random as _rnd
    if len(sorteos_todos) > 1:
        pesos = [max(1, s.priority) ** 2 for s in sorteos_todos]
        principal = _rnd.choices(sorteos_todos, weights=pesos, k=1)[0]
        sorteos = [principal] + [s for s in sorteos_todos if s.id != principal.id]
    else:
        sorteos = sorteos_todos

    traza.paso("ejecucion", f"Sorteos activos: {len(sorteos)} → se listan y se manda la foto del principal")

    # Datos EXACTOS de los sorteos
    datos = []
    for s in sorteos[:4]:
        d = f"Sorteo: {s.name}"
        if s.prize: d += f". Premio: {s.prize}"
        if s.requirements: d += f". Cómo participar: {s.requirements}"
        if s.end_date: d += f". Fecha límite: {s.end_date}"
        if s.location: d += f". Lugar: {s.location}"
        datos.append(d)
    eventos = [e for e in db.query(Event).order_by(Event.priority.desc()).all() if e.esta_vigente()]
    if eventos and len(eventos) <= 2:
        datos.append("Además, menciona brevemente que también hay un evento (" +
                     ", ".join(e.name for e in eventos) + ") por si quiere saber más.")

    texto = await _redactar_creativo("\n".join(datos), "sorteo", traza)

    if not texto:
        import random as _rnd
        _intro_so = _rnd.choice([
            "¡Participa en nuestros sorteos! 🎁\n",
            "¡Tenemos premios esperándote! 🎁 Estos son los sorteos activos:\n",
            "¡Anímate a participar y llévate algo increíble! 🎁\n",
        ])
        lineas = [_intro_so]
        for s in sorteos[:4]:
            linea = f"*{s.name}*"
            if s.prize:
                linea += f"\n🏆 Premio: {s.prize}"
            if s.requirements:
                linea += f"\n📋 Cómo participar: {s.requirements}"
            if s.end_date:
                linea += f"\n📅 Hasta: {s.end_date}"
            if s.location:
                linea += f"\n📍 {s.location}"
            lineas.append(linea)
        if eventos and len(eventos) <= 2:
            nombres = ", ".join(f"*{e.name}*" for e in eventos)
            lineas.append(f"\nAdemás tenemos el evento {nombres} 🎉 — pregúntame si quieres saber más.")
        texto = "\n\n".join(lineas)

    foto = _foto_de_entidad(db, "raffle", sorteos[0])
    fotos = [foto] if foto else []
    if foto:
        traza.paso("foto", f"Foto del sorteo '{sorteos[0].name}' adjuntada")
    else:
        traza.paso("foto", f"El sorteo '{sorteos[0].name}' no tiene foto → no se manda ninguna")

    # Fase 0: antes devolvía "\n\n".join(lineas), que no existe cuando la IA
    # redactó bien el texto → NameError y el cliente se quedaba sin respuesta.
    return {"text": texto, "image_urls": fotos, "location": None}


async def _ejecutar_promociones(db, phone_number, mensaje, traza) -> dict:
    """Lista las promociones de marketing activas. Manda la foto de la
    promo principal. Si no hay promos puras, menciona eventos/sorteos
    como actividades, con honestidad."""
    from models.marketing import Marketing
    from models.event import Event
    from models.raffle import Raffle

    promos_todos = db.query(Marketing).filter(Marketing.active == True).order_by(Marketing.priority.desc()).all()
    # No mostrar promociones vencidas (quedan guardadas, pero Any no las
    # ofrece como vigentes).
    promos_todos = [m for m in promos_todos if m.esta_vigente()]

    # ROTACIÓN ponderada por prioridad para la promo principal (la foto)
    import random as _rnd
    if len(promos_todos) > 1:
        pesos = [max(1, m.priority) ** 2 for m in promos_todos]
        principal = _rnd.choices(promos_todos, weights=pesos, k=1)[0]
        promos = [principal] + [m for m in promos_todos if m.id != principal.id]
    else:
        promos = promos_todos

    if promos:
        traza.paso("ejecucion", f"Promociones activas: {len(promos)} → se listan y se manda la foto de la principal")

        # Datos EXACTOS de las promos
        datos = []
        for p in promos[:4]:
            d = f"Promoción: {p.title}"
            if p.description: d += f". Detalle: {p.description}"
            if p.valid_until: d += f". Válida hasta: {p.valid_until}"
            datos.append(d)

        texto = await _redactar_creativo("\n".join(datos), "promoción", traza)

        if not texto:
            import random as _rnd
            _intro_pr = _rnd.choice([
                "¡Estas son nuestras promociones! 🛍️\n",
                "¡Aprovecha estas promociones del centro comercial! 🛍️\n",
                "¡Tenemos ofertas que te van a encantar! 🛍️\n",
            ])
            lineas = [_intro_pr]
            for p in promos[:4]:
                linea = f"*{p.title}*"
                if p.description:
                    linea += f"\n{p.description}"
                if p.valid_until:
                    linea += f"\n📅 Válida hasta: {p.valid_until}"
                lineas.append(linea)
            texto = "\n\n".join(lineas)

        foto = _foto_de_entidad(db, "marketing", promos[0])
        fotos = [foto] if foto else []
        if foto:
            traza.paso("foto", f"Foto de la promo '{promos[0].title}' adjuntada")
        return {"text": texto, "image_urls": fotos, "location": None}

    # Sin promos puras → mencionar honestamente eventos/sorteos como actividades
    traza.paso("ejecucion", "No hay promociones de marketing puras → se mencionan eventos/sorteos como actividades")
    eventos = [e for e in db.query(Event).order_by(Event.priority.desc()).all() if e.esta_vigente()]
    sorteos = db.query(Raffle).filter(Raffle.active == True).order_by(Raffle.priority.desc()).all()
    partes = ["En este momento no tengo una promoción comercial puntual, pero sí tenemos estas actividades: 😊\n"]
    if eventos:
        partes.append(f"🎉 Evento: *{eventos[0].name}*" + (f" — {eventos[0].date}" if eventos[0].date else ""))
    if sorteos:
        partes.append(f"🎁 Sorteo: *{sorteos[0].name}*" + (f" — hasta {sorteos[0].end_date}" if sorteos[0].end_date else ""))
    partes.append("\nPara ofertas puntuales de las tiendas, te recomiendo pasar por el Punto de Información (Pasillo Barichara). 😊")
    return {"text": "\n".join(partes), "image_urls": [], "location": None}


# Mapa de nombre de herramienta → función que la ejecuta.
# Ahora TODAS las herramientas están conectadas, reutilizando la lógica
# que ya funcionaba en el flujo viejo (no se reescribió nada).
EJECUTORES = {
    "emergencia": _ejecutar_emergencia,
    "queja": _ejecutar_queja,
    "administracion_mall": _ejecutar_administracion_mall,
    "numero_tienda": _ejecutar_numero_tienda,
    "cartelera_cine": _ejecutar_cartelera_cine,
    "busqueda_categoria": _ejecutar_busqueda_categoria,
    "ubicacion_mall": _ejecutar_ubicacion_mall,
    "gestion_domicilio": _ejecutar_gestion_domicilio,
    "torre_medica": _ejecutar_torre_medica,
    "eventos": _ejecutar_eventos,
    "sorteos": _ejecutar_sorteos,
    "promociones": _ejecutar_promociones,
    "conversacion_general": _ejecutar_conversacion_general,
}


# ══════════════════════════════════════════════════════════════════
# PUNTO DE ENTRADA — lo que llama el webhook cuando el switch está ON
# ══════════════════════════════════════════════════════════════════

def _menciona_pelicula_en_cartelera(db, mensaje: str) -> str | None:
    """
    ¿El mensaje nombra una película que está en cartelera ahora? Devuelve
    el título si sí, None si no. Sirve para que preguntas como "¿a qué
    horas dan Tadeo?" o "¿de qué trata Vértigo 2?" vayan SIEMPRE a cine,
    aunque no digan la palabra 'película' (antes se iban a 'eventos').

    Es conservador: solo cuenta palabras distintivas del título (4+ letras)
    y excluye palabras genéricas que podrían chocar con otras consultas
    del mall (ej. 'punto' de 'Punto de Información').
    """
    try:
        from services.store_transfer import _sin_tildes
        from services.cine import palabras_clave_titulo
        from models.cine_funcion import CineFuncion
        import re as _re
        msg = _sin_tildes(mensaje)
        funciones = db.query(CineFuncion).filter(CineFuncion.active == True).all()
        for f in funciones:
            for w in palabras_clave_titulo(f.title):
                if _re.search(rf"\b{_re.escape(w)}\b", msg):
                    return f.title
    except Exception:
        pass
    return None


SERVICIOS_NO_CINE = ("parqueadero", "centro comercial", "el mall", "banco", "cajero", "administracion", "punto de informacion",
                     "misa", "bano", "atencion", "jumbo", "torre", "consultorio", "medico", "gimnasio", "casino", "registro")


def _parece_pregunta_de_funcion(db, mensaje: str) -> bool:
    """'horarios de X', 'a qué hora dan X', 'de qué trata X', 'funciones de X' — y X no es tienda ni servicio."""
    try:
        msg = _sin_tildes_simple(mensaje)
        es_compra = re.search(r"\b(reservar|reserva|comprar|compro|adquirir)\b", msg) and re.search(r"\b(en linea|online|boleta|boletas|entrada|entradas|funcion|silla|sillas|por internet)\b", msg)
        if not es_compra and not re.search(r"\b(horarios? de|a que horas? (dan|pasan|es)|de que trata|funcion(es)? de|dan la pelicula|pasan)\b", msg):
            return False
        if any(k in msg for k in SERVICIOS_NO_CINE):
            return False
        # Preguntas por el horario del CENTRO COMERCIAL (escrito de cualquier
        # forma: "centro ccial", "el cc", "el mall", "horario de funcionamiento")
        # no son de cine. Antes "horario de funcionamiento del centro ccial"
        # se mandaba a la cartelera porque "ccial" no estaba en la lista (traza #9, 23/10).
        if re.search(r"\b(centro|cc|ccial|comercial|mall|puente|funcionamiento|atencion|abren|cierran|local|tienda)\b", msg):
            return False
        from services.store_transfer import find_store_by_message
        if find_store_by_message(db, mensaje):
            return False
        from models.cine_funcion import CineFuncion
        return db.query(CineFuncion).filter(CineFuncion.active == True).count() > 0
    except Exception:
        return False


def _sin_tildes_simple(t: str) -> str:
    from services.store_transfer import _sin_tildes
    return _sin_tildes(t or "")


PALABRAS_CARTA = ("carta", "menú", "menu", "catálogo", "catalogo", "qué venden", "que venden", "qué tienen", "que tienen", "productos de",
                  "instagram", "redes", "red social", "página", "pagina", "link", "enlace", "perfil")
PALABRAS_REDES = ("instagram", "redes", "red social", "perfil", "pagina", "página")


def _atajo_carta_link(db, mensaje: str, traza) -> dict | None:
    """Si piden la carta/menú/catálogo de un local que la tiene como ENLACE, responde directo."""
    try:
        msg = mensaje.lower()
        if not any(p in msg for p in PALABRAS_CARTA):
            return None
        from services.store_transfer import find_store_by_message
        st = find_store_by_message(db, mensaje)
        pide_redes = any(p in msg for p in PALABRAS_REDES)
        nom = nombre_cliente()
        if not st:
            # "¿de qué locales tienes instagram?" → no se pueden listar 100 links
            if pide_redes and not any(p in msg for p in ("carta", "menu", "menú", "catalogo", "catálogo")):
                from models.store import Store
                n = db.query(Store).filter(Store.active == True, Store.catalogo_link.ilike("%instagram%")).count()
                if n:
                    traza.paso("atajo_redes", f"Pregunta general por Instagram → hay {n} locales con link")
                    return {"text": (f"{nom + ', t' if nom else 'T'}engo el Instagram de {n} locales del centro comercial. "
                                     "Dime cuál te interesa y te paso el suyo de una 😊"), "image_urls": [], "location": None}
            return None
        link = st.carta_como_link() if hasattr(st, "carta_como_link") else None
        if not link:
            if pide_redes and not getattr(st, "catalogo_link", None):
                # Piden el Instagram y el local no lo tiene → honesto + WhatsApp
                texto = f"{nom + ', por' if nom else 'Por'} ahora no tengo el Instagram de *{st.name}*."
                if st.phone:
                    texto += f" Puedes escribirles directo 👉 {_link_wa(st.phone)}"
                traza.paso("atajo_redes", f"'{st.name}' no tiene Instagram cargado → respuesta honesta")
                return {"text": texto, "image_urls": [], "location": None, "mentioned_store_id": st.id}
            return None
        saludo = f"¡Claro, {nom}! " if nom else "¡Claro! "
        es_ig = "instagram" in link.lower()
        que = "el Instagram" if (es_ig and pide_redes) else "la carta/catálogo"
        texto = f"{saludo}Aquí tienes {que} de *{st.name}* 👉 {link}"
        if st.phone:
            tel = re.sub(r"\D", "", st.phone)
            if tel:
                if tel.startswith("3") and len(tel) == 10:
                    tel = "57" + tel
                texto += f"\nSi quieres pedir o preguntar algo, escríbeles directo: https://wa.me/{tel}"
        traza.paso("atajo_carta", f"'{st.name}' tiene la carta como enlace → se entrega directo sin IA")
        return {"text": texto, "image_urls": [], "location": None, "mentioned_store_id": st.id}
    except Exception as e:
        traza.paso("atajo_carta_error", str(e)[:80])
        return None


async def procesar_con_orquestador(db: Session, phone_number: str, mensaje: str, modo: str = "prueba", user_name: str = "") -> dict:
    """
    Punto de entrada único del orquestador. Recibe el mensaje, decide,
    ejecuta, guarda la traza, y devuelve la respuesta en el MISMO
    formato que el flujo viejo (text, image_urls, location) — para que
    el switch pueda intercambiarlos sin que el resto del código note la
    diferencia.
    """
    traza = Traza(phone_number, mensaje, modo)
    _usuario_actual.set(user_name or "")
    traza.paso("inicio", f"Mensaje recibido: '{mensaje}'" + (f" (cliente: {nombre_cliente()})" if nombre_cliente() else ""))

    # ATAJO CARTA/CATÁLOGO POR LINK: "carta de Gari Sushi", "menú de X",
    # "catálogo de Y" → si el local tiene su carta como ENLACE (Instagram,
    # web, WhatsApp), se entrega directo, sin IA (antes la IA decía
    # "te comparto lo que tengo de su carta 👇" y no mandaba nada).
    insc = _respuesta_inscripcion_evento(db, mensaje, traza)
    if insc:
        from models.event import Event as _Ev
        ev = db.query(_Ev).filter(_Ev.id == insc.pop("evento_id")).first()
        foto = _foto_de_entidad(db, "event", ev) if ev else None
        insc["image_urls"] = [foto] if foto else []
        traza.herramienta_elegida = "eventos"
        traza.metodo_decision = "reglas"
        traza.razon_decision = f"Inscripción a evento '{ev.name if ev else ''}' (respuesta directa con contacto del mall)"
        traza.respuesta = insc["text"]; traza.fotos = len(insc["image_urls"]); traza.fotos_urls = insc["image_urls"]
        traza.paso("fin", f"Respuesta lista ({len(traza.respuesta)} caracteres, {traza.fotos} fotos)")
        traza.guardar(db)
        return insc

    atajo = _atajo_carta_link(db, mensaje, traza)
    if atajo:
        traza.herramienta_elegida = "conversacion_general"
        traza.metodo_decision = "reglas"
        traza.razon_decision = "Carta/catálogo por enlace del local (respuesta directa)"
        traza.respuesta = atajo["text"]
        traza.paso("fin", f"Respuesta lista ({len(traza.respuesta)} caracteres, 0 fotos)")
        traza.guardar(db)
        return atajo

    # 1. Decidir qué herramienta usar (híbrido)
    nombre_tool, metodo = await decidir_herramienta(mensaje, traza)

    # Corrección de cine: si el mensaje nombra una película en cartelera
    # y NO quedó en cine, lo reencaminamos (ej. "¿a qué horas dan Tadeo?"
    # se iba a 'eventos'). No pisa emergencia/queja/domicilio.
    if nombre_tool not in ("cartelera_cine", "emergencia", "queja", "gestion_domicilio"):
        peli = _menciona_pelicula_en_cartelera(db, mensaje)
        if peli:
            traza.paso("correccion_cine", f"El mensaje nombra la película '{peli}' → se reencamina a cartelera_cine (venía como '{nombre_tool}')")
            nombre_tool = "cartelera_cine"
            metodo = "reglas"

    # Pregunta de CINE sin nombrar película conocida ("horarios de Vértigo 2"
    # cuando ya salió de cartelera, "a qué hora dan X"): si no es una tienda
    # ni un servicio del mall, va a cine, que responde "no está en cartelera"
    # y muestra la cartelera actual (antes la IA contestaba "Juan, no").
    if nombre_tool == "conversacion_general" and _parece_pregunta_de_funcion(db, mensaje):
        traza.paso("correccion_cine", "Pregunta por horarios/función de algo que no es tienda ni servicio → cartelera_cine")
        nombre_tool = "cartelera_cine"
        metodo = "reglas"

    traza.herramienta_elegida = nombre_tool

    # 2. Ejecutar la herramienta (si no está conectada aún, cae al general)
    ejecutor = EJECUTORES.get(nombre_tool)
    if not ejecutor:
        traza.paso("ejecucion", f"La herramienta '{nombre_tool}' aún no está conectada en el esqueleto → se usa conversacion_general")
        ejecutor = EJECUTORES["conversacion_general"]

    resultado = await ejecutor(db, phone_number, mensaje, traza)

    # Red de seguridad GLOBAL: si CUALQUIER herramienta devolvió texto
    # vacío (por el motivo que sea), nunca lo mandamos así al cliente —
    # ponemos un respaldo amable. Es la última barrera antes del cliente.
    if not (resultado.get("text") or "").strip():
        traza.paso("respaldo_global", "La herramienta devolvió texto vacío → respaldo global (el cliente nunca recibe vacío)")
        resultado["text"] = (
            "¡Hola! Soy Any 🛍️, tu asistente del Centro Comercial El Puente. "
            "Cuéntame en qué te puedo ayudar — tiendas, comida, horarios, servicios o lo que necesites 😊"
        )

    # PROMOCIÓN AL FINAL (casi siempre): las herramientas dedicadas
    # (búsqueda por categoría, número de tienda, cine, etc.) NO pasan por
    # generate_response, así que la promoción del final nunca les llegaba.
    # Aquí se la agregamos a esas respuestas, para que el mall tenga la
    # visibilidad que pidió. NO se agrega en: emergencias, quejas,
    # promociones/eventos/sorteos (que ya SON la promo), ni cuando la
    # respuesta ya trae una promo. La conversación general la sigue
    # manejando internamente (no la duplicamos).
    HERRAMIENTAS_SIN_PROMO = {
        "emergencia", "queja", "eventos", "sorteos", "promociones",
        "conversacion_general", "gestion_domicilio", "administracion_mall", "ubicacion_mall",
    }
    # Tampoco se pega promo a respuestas cortas (aclaraciones): queda más
    # largo el anuncio que la respuesta y cansa al cliente.
    if len((resultado.get("text") or "")) < 120:
        traza.uso_general = traza.uso_general or True
    # Si la herramienta terminó delegando en la conversación general, la IA
    # YA puso su promoción → no se agrega otra (antes salían dos seguidas).
    if traza.herramienta_elegida not in HERRAMIENTAS_SIN_PROMO and not traza.uso_general:
        try:
            from services.ai import _texto_promo_para_pegar
            promo = _texto_promo_para_pegar(db, phone_number)
            if promo:
                resultado["text"] = resultado["text"].rstrip() + "\n\n" + promo["texto"]
                # Si la promo tiene foto y la respuesta no traía ninguna, la adjuntamos
                if promo.get("foto") and not resultado.get("image_urls"):
                    resultado.setdefault("image_urls", []).append(promo["foto"])
                traza.paso("promo_agregada", f"Promoción agregada al final: {promo.get('nombre', '')}")
        except Exception as e:
            traza.paso("promo_error", f"No se pudo agregar promo: {e}")

    # MEMORIA DE CONTEXTO: el webhook guarda `mentioned_store_id` en la
    # conversación para que los seguimientos ("¿tienen carta?", "¿a qué
    # hora abre?") sepan de qué tienda se venía hablando. Si la
    # herramienta no lo marcó pero el mensaje nombra una tienda, lo
    # ponemos aquí. Sin esto, en modo orquestador el bot "olvidaba" la
    # tienda entre mensajes — causa raíz de la foto de la carta que no
    # llegaba.
    if not resultado.get("mentioned_store_id"):
        try:
            from services.store_transfer import find_store_by_message
            from services.category_search import detectar_categoria
            # Solo guardar tienda de contexto si el mensaje la NOMBRA y NO
            # es una búsqueda por categoría (para no arrastrar una tienda
            # a preguntas de "zapatos", "ropa", "comida", etc.)
            st = find_store_by_message(db, mensaje)
            if st and (not detectar_categoria(mensaje) or _sin_tildes_simple(st.name) in _sin_tildes_simple(mensaje)):
                resultado["mentioned_store_id"] = st.id
        except Exception:
            pass
    if resultado.get("mentioned_store_id"):
        traza.paso("contexto", f"Tienda en contexto guardada para seguimientos (ID {resultado['mentioned_store_id']})")

    # 3. Registrar el resultado en la traza
    traza.respuesta = resultado.get("text", "")
    fotos_list = resultado.get("image_urls", []) or []
    traza.fotos = len(fotos_list)
    traza.fotos_urls = fotos_list  # guardar los LINKS de las fotos para verlos en el panel
    loc = resultado.get("location")
    traza.ubicacion = "si" if loc else "no"
    # Registrar detalle de la ubicación en contenido_extra si la hay
    if loc:
        traza.contenido_extra.append({"tipo": "ubicacion", "detalle": loc.get("name", "ubicación del mall")})
    # Registrar cada foto como contenido agregado (para la vista detallada)
    for url in fotos_list:
        traza.contenido_extra.append({"tipo": "foto", "detalle": url})
    traza.paso("fin", f"Respuesta lista ({len(traza.respuesta)} caracteres, {traza.fotos} fotos)")

    # 4. Guardar la traza (esto es lo que hace todo visible en el panel)
    traza.guardar(db)

    return resultado