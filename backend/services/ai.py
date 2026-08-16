# 📄 ARCHIVO: backend/services/ai.py
"""
Servicio de IA — Groq + LLaMA.
FIXES:
  - Nueva intención 'estado_pedido' para preguntas sobre el pedido activo
  - Prompt dedicado que responde con elegancia sobre el estado
  - is_delivery_intent ya no clasifica preguntas de estado como nuevos pedidos
"""
import logging
import base64
import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from groq import AsyncGroq
from config import get_settings
from services.rag import search_stores, search_knowledge_and_events

settings = get_settings()
logger   = logging.getLogger("mall_bot")

_groq_client = None


def _get_groq_client() -> AsyncGroq:
    global _groq_client
    if _groq_client is None:
        _groq_client = AsyncGroq(api_key=settings.GROQ_API_KEY)
    return _groq_client


# ── Clasificador de intención ─────────────────────────────────────

INTENT_RULES = {
    "saludo":        ["hola", "buenas", "buenos días", "buenas tardes", "buenas noches", "hey", "qué más", "quiubo"],
    "horario":       ["horario", "a qué hora", "qué hora", "abre", "cierra", "cuándo abren", "hasta qué hora"],
    "ubicacion":     ["dónde", "donde", "piso", "ubicación", "cómo llego", "queda", "está ubicado"],
    "estado_pedido": [
        "cuánto se demora", "cuanto se demora", "cuánto tarda", "cuanto tarda",
        "ya está listo", "ya esta listo", "ya llegó", "ya llego",
        "mi pedido", "el pedido", "dónde está mi pedido", "donde esta mi pedido",
        "cuándo llega", "cuando llega", "en camino", "lo aceptaron",
        "ya viene", "cuánto falta", "cuanto falta", "ya lo entregaron",
        "estado del pedido", "cómo va mi pedido", "como va mi pedido",
    ],
    "domicilio": [
        "domicilio", "delivery", "pedir a domicilio", "quiero pedir",
        "hacer un pedido", "ordenar", "quiero ordenar", "hacer pedido",
        "enviar a mi casa", "mandar a domicilio", "que me lo traigan",
        "que me lo lleven",
    ],
    "categoria": ["restaurantes", "comida", "ropa", "tecnología", "cine", "gym", "farmacias", "cafeterías"],
}


def classify_intent(message: str) -> str:
    msg = message.lower()
    # estado_pedido va primero para que no confunda "mi pedido" con nuevo domicilio
    for intent in ["estado_pedido", "saludo", "horario", "ubicacion", "domicilio", "categoria"]:
        keywords = INTENT_RULES.get(intent, [])
        if any(k in msg for k in keywords):
            return intent
    return "general"


# ── Persona base ──────────────────────────────────────────────────

BASE_PERSONA = """Eres Any 🛍️, el asistente virtual del Centro Comercial El Puente en San Gil, Santander.
Eres amigable, cálido y directo — como un buen guía del mall que conoce todo de memoria.

REGLAS SIEMPRE:
- Responde en español
- Preséntate como "Any" cuando corresponda (nunca como "Puente Bot" ni ningún otro nombre)
- NUNCA inventes datos — si un dato puntual (número de local exacto, categoría, teléfono, disponibilidad) NO aparece literalmente en la información que se te dio abajo, dilo con claridad ("no tengo ese dato exacto") en vez de completarlo con algo que suene creíble
- Si no sabes algo, dilo con amabilidad y sugiere el Punto de Información (Piso 1)
- Usa máximo 1-2 emojis por mensaje, solo cuando aporten
- NUNCA uses tablas (con | o guiones de separación entre columnas) — WhatsApp no las muestra bien. Usa listas simples con guion o texto corrido
- Si el cliente saluda pero ya venías hablando con él en esta conversación, NO reinicies el saludo como si fuera la primera vez — sigue el hilo de lo que se hablaba"""

# ── Prompts por intención ─────────────────────────────────────────

PROMPTS = {
    "saludo": BASE_PERSONA + """

TIPO DE RESPUESTA: Saludo
- Si NO hay conversación previa (es el primer mensaje del chat): saluda cálido y breve, invita a preguntar. Ejemplo: "¡Hola! Soy Any 👋 ¿En qué te puedo ayudar hoy?"
- Si YA hay conversación previa (el historial de abajo tiene mensajes anteriores): NO te presentes de nuevo ni reinicies el saludo — responde algo breve tipo "¡Hola de nuevo! ¿en qué más te ayudo?" y queda atento a seguir el hilo de lo último que se hablaba
- 1-2 líneas máximo
""",

    "horario": BASE_PERSONA + """

TIPO DE RESPUESTA: Horario / Información puntual
- Máximo 2-3 líneas
- Da el dato exacto primero, luego contexto si aplica
""",

    "ubicacion": BASE_PERSONA + """

TIPO DE RESPUESTA: Ubicación
- Máximo 2-3 líneas
- Menciona el piso y una referencia visual concreta
""",

    # NOTA: ya no gestionamos pedidos ni su estado — redirige al local,
    # igual que el flujo de domicilio.
    "estado_pedido": BASE_PERSONA + """

TIPO DE RESPUESTA: Preguntan por el estado de un pedido
- Ya no gestionamos el estado de pedidos directamente por este chat
- Explica con amabilidad que para el estado de su pedido deben escribirle directo a la tienda o restaurante donde lo hicieron
- Si en el mensaje o el historial se menciona qué tienda, dilo explícitamente
- Máximo 3 líneas, tono cálido y resolutivo
""",

    # NOTA: esta intención ya NO usa este prompt para responder — ver
    # services/store_transfer.py, que SÍ funciona para cualquier tipo de
    # local (no solo restaurantes) siempre que tenga teléfono registrado.
    # Este bloque se deja solo por si se quiere revertir al flujo antiguo.
    "domicilio": BASE_PERSONA + """

TIPO DE RESPUESTA: Domicilio (prompt sin uso actualmente)
- El sistema de domicilios funciona para cualquier tipo de local del mall, no solo restaurantes
- Pregunta al usuario: ¿de qué tienda o restaurante quiere pedir?
- Máximo 4-5 líneas
""",

    "categoria": BASE_PERSONA + """

TIPO DE RESPUESTA: Lista de opciones por categoría
- NUNCA listes todas las opciones que existan de una — máximo 2-3 por respuesta, aunque haya más en los datos
- OBLIGATORIO: si la categoría que preguntan puede referirse a más de un tipo de producto (ej. "zapatos deportivos" → ¿de vestir o para practicar deporte?, "ropa" → ¿de hombre, mujer o niño?, "restaurantes" → ¿comida rápida o algo más específico?), SIEMPRE pregunta primero para aclarar — nunca des nombres de tiendas directamente en esos casos, sin excepción
- Cuando ya des opciones, formato simple por línea: "📍 Nombre — Piso X — qué vende, en pocas palabras"
- Cierra invitando a seguir preguntando, sin sonar repetitivo de un mensaje a otro
- Si el cliente pide explícitamente "todas" o "todos los que haya", ahí sí puedes dar la lista completa
""",

    "general": BASE_PERSONA + """

TIPO DE RESPUESTA: Consulta general sobre una tienda o servicio
- Da solo lo que preguntaron — si preguntan "¿dónde queda X?" no agregues horario y teléfono si no lo pidieron; si preguntan "cuéntame todo de X" ahí sí da nombre, piso, horario, teléfono, qué vende
- Si es una pregunta de sí/no: responde directo primero, el resto es opcional
- Si tu respuesta necesitaría listar más de 2-3 tiendas para responder bien, mejor pregunta qué tipo específico busca en vez de listarlas todas
- Nunca cortes información a la mitad — si algo no cabe en pocas líneas, resume lo esencial y ofrece dar más detalle si lo piden
""",
}


# ── Función principal ─────────────────────────────────────────────

def _build_mall_info_block(db) -> str:
    """
    Trae dirección, horario general, teléfono y parqueadero directo de
    la tabla mall_info — sin pasar por el buscador semántico, que con
    muchas tiendas cargadas puede no priorizar esta info general.
    """
    from models.mall_info import MallInfo
    try:
        info = db.query(MallInfo).filter(MallInfo.id == 1).first()
        if not info:
            return ""
        lines = []
        if info.address:
            lines.append(f"Dirección del mall: {info.address}")
        if info.general_schedule:
            lines.append(f"Horario general del mall: {info.general_schedule}")
        if info.phone:
            lines.append(f"Teléfono de contacto del mall: {info.phone}")
        if info.parking:
            lines.append(f"Parqueadero: {info.parking}")
        if info.wifi:
            lines.append(f"WiFi: {info.wifi}")
        if not lines:
            return ""
        return "\n\n--- INFORMACIÓN GENERAL DEL MALL (usa esto para preguntas sobre horario, ubicación, teléfono o parqueadero del CENTRO COMERCIAL en sí, no de una tienda puntual) ---\n" + "\n".join(lines) + "\n---"
    except Exception as e:
        logger.error(f"Error cargando info general del mall: {str(e)}")
        return ""


def _build_promotions_block(db, user_profile: str) -> str:
    """
    Arma el bloque de promociones disponibles para esta respuesta:
    1) Eventos/sorteos de prioridad alta (4-5) — se cargan SIEMPRE,
       para que el mall pueda garantizar visibilidad real, sin
       depender de que el tema de la conversación coincida por azar.
    2) Recomendaciones personalizadas — busca, entre la info de las
       tiendas, lo que más encaje con el perfil de intereses de este
       cliente específico (si existe un perfil).
    En ambos casos, la decisión de MENCIONARLO o no queda en manos del
    modelo — esto es contenido disponible, no una orden.
    """
    from models.event import Event
    from models.raffle import Raffle

    parts = []

    try:
        high_priority_events = db.query(Event).filter(Event.priority >= 4).all()
        high_priority_raffles = db.query(Raffle).filter(Raffle.priority >= 4, Raffle.active == True).all()
        promo_texts = [e.to_rag_text() for e in high_priority_events] + [r.to_rag_text() for r in high_priority_raffles]
        if promo_texts:
            parts.append(
                "PROMOCIONES DE ALTA PRIORIDAD (el mall quiere que esto tenga visibilidad real — "
                "busca un momento natural en tu respuesta para mencionarlo, variando cómo lo dices "
                "cada vez, sin sonar forzado ni repetitivo. Adapta el ESTILO y el TONO de cómo lo "
                "mencionas al tipo de cosa que es — un sorteo de un carro se menciona con emoción y "
                "urgencia ('¡no te lo pierdas!'), una promoción de ropa con un tono más de moda y "
                "estilo, un evento familiar con calidez. No uses siempre la misma fórmula):\n" +
                "\n".join(f"🎯 {t}" for t in promo_texts)
            )
    except Exception as e:
        logger.error(f"Error cargando promociones de prioridad: {str(e)}")

    if user_profile:
        try:
            personalized = search_stores(user_profile, n_results=3)
            if personalized:
                parts.append(
                    "POSIBLES RECOMENDACIONES SEGÚN EL PERFIL DE ESTE CLIENTE (solo menciónalas si "
                    "de verdad encajan con lo que está preguntando o con sus gustos conocidos — "
                    "si no calzan bien, ignóralas por completo. Si las mencionas, hazlo con un toque "
                    "personal que muestre que conoces sus gustos, ej. 'ya que te gusta la tecnología, "
                    "tal vez te interese...' — y adapta el estilo del mensaje a la categoría de lo que "
                    "recomiendas, igual que con las promociones de arriba):\n" +
                    "\n".join(f"💡 {t}" for t in personalized)
                )
        except Exception as e:
            logger.error(f"Error buscando recomendaciones personalizadas: {str(e)}")

    if not parts:
        return ""
    return "\n\n--- CONTENIDO PROMOCIONAL DISPONIBLE ---\n" + "\n\n".join(parts) + "\n---"


async def generate_response(
    user_message: str,
    user_name: str,
    conversation_history: list[dict],
    user_profile: str = "",
    active_order_context: str = "",   # ← NUEVO: contexto del pedido activo si existe
    db=None,                          # ← NUEVO: para promociones por prioridad + personalizadas
) -> str:
    client = _get_groq_client()
    intent = classify_intent(user_message)
    print(f"    🔍 TRAZA IA — intención clasificada: '{intent}' → usando prompt '{intent if intent in PROMPTS else 'general'}'")

    rag_docs = search_stores(user_message, n_results=8)
    print(f"    🔍 TRAZA IA — búsqueda RAG general (tiendas/mall): {len(rag_docs)} documento(s) encontrado(s)")
    for i, doc in enumerate(rag_docs[:8], 1):
        print(f"       {i}. {doc[:120]}{'...' if len(doc) > 120 else ''}")

    system_content = PROMPTS.get(intent, PROMPTS["general"])

    # Inyectar contexto del pedido activo cuando la pregunta es sobre estado
    if active_order_context:
        system_content += f"\n\n--- PEDIDO ACTIVO DEL CLIENTE ---\n{active_order_context}\n---"

    if rag_docs:
        context = "\n\n".join(f"📌 {doc}" for doc in rag_docs)
        system_content += f"\n\n--- INFORMACIÓN DEL MALL ---\n{context}\n---"

    # ── Base de Conocimiento, Eventos y Sorteos — búsqueda APARTE ────
    # Igual que con la info general del mall: con 138+ tiendas cargadas,
    # una entrada real de la Base de Conocimiento (ej. política de
    # mascotas) puede perder la competencia semántica contra puras
    # tiendas y nunca llegar a los 8 resultados de arriba. Esta segunda
    # búsqueda, filtrada para que las tiendas no puedan participar,
    # garantiza que esta información SIEMPRE tenga su propio espacio.
    kb_docs = search_knowledge_and_events(user_message, n_results=4)
    print(f"    🔍 TRAZA IA — búsqueda filtrada (conocimiento/eventos/sorteos): {len(kb_docs)} documento(s) encontrado(s)")
    for i, doc in enumerate(kb_docs, 1):
        print(f"       {i}. {doc[:120]}{'...' if len(doc) > 120 else ''}")
    if kb_docs:
        kb_context = "\n\n".join(f"📖 {doc}" for doc in kb_docs)
        system_content += f"\n\n--- BASE DE CONOCIMIENTO / EVENTOS / SORTEOS RELEVANTES ---\n{kb_context}\n---"

    # ── Info general del mall — SIEMPRE disponible, sin depender de RAG ──
    # Con 138+ tiendas cargadas, una pregunta genérica como "¿cuál es el
    # horario?" o "¿dónde queda el mall?" puede perder la competencia
    # semántica contra el horario de tiendas individuales, y esa info
    # general nunca llega a aparecer en los 8 resultados de arriba.
    # Por eso la inyectamos siempre, aparte, para preguntas de horario,
    # ubicación o parqueadero — igual que ya hacemos con las promociones.
    if db is not None and intent in ("horario", "ubicacion", "general", "categoria"):
        mall_block = _build_mall_info_block(db)
        print(f"    🔍 TRAZA IA — info general del mall inyectada: {'SÍ' if mall_block else 'NO (mall_info vacío o intención no aplica)'}")
        if mall_block:
            system_content += mall_block
    else:
        print(f"    🔍 TRAZA IA — info general del mall inyectada: NO (intención '{intent}' no la necesita)")

    if user_profile:
        system_content += f"\n\nPERFIL DEL USUARIO: {user_profile}"
    print(f"    🔍 TRAZA IA — perfil de usuario inyectado: {'SÍ' if user_profile else 'NO'}")

    # ── Promoción por prioridad + recomendaciones personalizadas ────
    # Se agregan como contenido DISPONIBLE, no como orden — el prompt le
    # deja al modelo la decisión de si encaja mencionarlo o no, para
    # que nunca se sienta forzado ni repetitivo.
    if db is not None:
        promo_block = _build_promotions_block(db, user_profile)
        print(f"    🔍 TRAZA IA — promociones de prioridad alta inyectadas: {'SÍ' if promo_block else 'NO'}")
        if promo_block:
            system_content += promo_block

    print(f"    🔍 TRAZA IA — tamaño total del prompt del sistema: {len(system_content)} caracteres | historial incluido: {min(len(conversation_history), 12)} mensajes | modelo: {settings.GROQ_MODEL}")

    messages = [{"role": "system", "content": system_content}]

    for turn in conversation_history[-12:]:
        messages.append({"role": turn["role"], "content": turn["content"]})

    messages.append({"role": "user", "content": f"[Usuario: {user_name}] {user_message}"})

    print(f"    🔍 TRAZA IA — llamando a la API de Groq (modelo: {settings.GROQ_MODEL}, {len(messages)} mensajes en el contexto)...")

    try:
        completion = await client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=messages,
            max_tokens=600,  # antes 500 — un poco más de margen de seguridad,
                             # aunque la segmentación de respuestas (2-3 opciones
                             # máximo) ya debería evitar que se corten
            temperature=0.7,
            top_p=0.9,
            # NOTA: NO usamos reasoning_effort/reasoning_format aquí — la
            # version de groq instalada (0.11.0) no los reconoce y el
            # SDK lanza un TypeError antes de llegar a Groq. La limpieza
            # del <think> se hace después, con _strip_thinking_tags().
        )
        raw = completion.choices[0].message.content or ""
        limpio = _strip_thinking_tags(raw)
        print(f"    🔍 TRAZA IA — respuesta recibida de Groq: {len(raw)} caracteres crudos → {len(limpio)} después de limpiar")
        return limpio

    except Exception as e:
        print(f"    🔍 TRAZA IA — ❌ ERROR llamando a Groq: {str(e)}")
        logger.error(f"Error Groq API: {str(e)}")
        return "Uy, tuve un problema técnico 😅 ¿Puedes intentarlo de nuevo en un momento?"


# ── Helpers para webhook ──────────────────────────────────────────

def is_order_status_question(message: str) -> bool:
    """Retorna True si el cliente está preguntando por el estado de su pedido."""
    return classify_intent(message) == "estado_pedido"


def is_delivery_intent(message: str) -> bool:
    """
    Retorna True solo si el mensaje quiere INICIAR un nuevo pedido.
    Las preguntas de estado ('cuánto se demora', 'ya llegó') ya NO disparan esto.
    """
    return classify_intent(message) == "domicilio"


# ── Gestión completa de domicilios (carta + datos + link personalizado) ────

MANAGEMENT_KEYWORDS = [
    "ayúdame a gestionar", "ayudame a gestionar", "gestiona mi pedido",
    "gestionar mi domicilio", "gestionar mi pedido", "ayúdame con mi pedido",
    "ayudame con mi pedido", "quiero que gestiones", "haz mi pedido",
    "tramitar mi pedido", "gestionar el domicilio",
    # Formas más naturales de pedir lo mismo — la gente rara vez dice
    # "gestionar" literalmente, así que hay que cubrir cómo hablan de verdad
    "ayúdame a hacer el domicilio", "ayudame a hacer el domicilio",
    "ayúdame a hacer mi pedido", "ayudame a hacer mi pedido",
    "que tu me ayudes a hacer el domicilio", "que tu me ayudes con el domicilio",
    "que me ayudes a hacer el domicilio", "que me ayudes con el domicilio",
    "me ayudas a hacer el domicilio", "me ayudas con el domicilio",
    "me ayudas a hacer mi pedido", "me ayudas con mi pedido",
    "hazme el domicilio", "hazme el pedido", "encárgate de mi pedido",
    "encargate de mi pedido", "encárgate del domicilio", "encargate del domicilio",
]


def is_delivery_management_intent(message: str) -> bool:
    """
    Distingue una MENCIÓN simple ('quiero pedir de Zirus') de una
    GESTIÓN explícita ('ayúdame a gestionar mi pedido a Zirus') — solo
    la segunda dispara el flujo completo de recolección de datos.
    """
    msg = message.lower()
    if any(k in msg for k in MANAGEMENT_KEYWORDS):
        return True
    # Respaldo más flexible: cualquier mensaje que combine la raíz
    # "gestion" (gestionar/gestiona/gestiones/gestión) con pedido o
    # domicilio, sin importar el orden exacto de las palabras — para
    # no depender de una lista infinita de frases exactas (ej. "quiero
    # que TÚ ME gestiones el pedido" no calzaba con ninguna frase fija).
    return "gestion" in msg and any(k in msg for k in ("pedido", "domicilio", "orden"))


def _safe_json_parse(raw: str) -> dict | None:
    """Intenta parsear JSON aunque el modelo agregue texto extra alrededor."""
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
    return None


async def extract_order_data(message: str, existing: dict) -> dict:
    """
    Usa la IA para extraer nombre, celular, dirección, pedido y forma de
    pago del mensaje del cliente, combinando con lo que ya se había
    recolectado antes (para no perder datos entre mensajes).

    Además, en la MISMA llamada (sin gastar una llamada extra a la IA),
    detecta 2 cosas clave para que el bot no se quede "atrapado" pidiendo
    datos sin parar:
    - cancela: el cliente ya no quiere seguir con el domicilio
    - relacionado: si el mensaje tiene algo que ver con el pedido, o es
      una pregunta/comentario totalmente distinto (ej. "¿se permiten
      mascotas?") que hay que responder de verdad, no ignorar
    """
    client = _get_groq_client()
    prompt = f"""Estás ayudando a un cliente a completar los datos de un pedido a domicilio, mensaje por mensaje.

Datos ya recolectados en mensajes anteriores (puede haber campos vacíos):
{json.dumps(existing, ensure_ascii=False)}

Mensaje nuevo del cliente: "{message}"

Devuelve SOLO un objeto JSON con estas claves exactas: nombre, celular, direccion, pedido, forma_pago, cancela, relacionado.
Reglas para los datos del pedido:
- Si un dato aparece en el mensaje nuevo, úsalo (actualiza el campo).
- Si no aparece en el mensaje nuevo pero ya estaba recolectado antes, mantén el valor anterior.
- Si nunca ha aparecido en ningún mensaje, pon null.
- forma_pago debe ser "efectivo" o "transferencia" si se puede inferir con claridad, si no null.
- No inventes ningún dato que no esté explícito.

Reglas para "cancela" (true/false):
- true SOLO si el cliente dice explícitamente que ya no quiere seguir con el pedido/domicilio (ej. "ya no quiero", "olvídalo", "cancela", "déjalo así", "no gracias")
- false en cualquier otro caso, incluyendo cuando solo está dando datos

Reglas para "relacionado" (true/false):
- true si el mensaje tiene que ver con dar algún dato del pedido (nombre, celular, dirección, qué quiere pedir, forma de pago), aunque sea parcial o esté mezclado con otra cosa
- false si el mensaje es una pregunta o comentario que NO tiene nada que ver con completar el pedido (ej. "¿se permiten mascotas?", "¿cuál es el horario?") — en ese caso el cliente simplemente se desvió a preguntar otra cosa, no está cancelando ni dando datos

No agregues texto antes ni después del JSON."""

    try:
        completion = await client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=350,
            temperature=0.1,
        )
        raw = completion.choices[0].message.content or ""
        raw = _strip_thinking_tags(raw)
        parsed = _safe_json_parse(raw)
        if parsed:
            return {
                "customer_name": parsed.get("nombre") or existing.get("nombre"),
                "customer_phone": parsed.get("celular") or existing.get("celular"),
                "address": parsed.get("direccion") or existing.get("direccion"),
                "order_details": parsed.get("pedido") or existing.get("pedido"),
                "payment_method": parsed.get("forma_pago") or existing.get("forma_pago"),
                "cancela": bool(parsed.get("cancela", False)),
                "relacionado": bool(parsed.get("relacionado", True)),
            }
    except Exception as e:
        logger.error(f"Error extrayendo datos de pedido: {str(e)}")

    return {
        "customer_name": existing.get("nombre"),
        "customer_phone": existing.get("celular"),
        "address": existing.get("direccion"),
        "order_details": existing.get("pedido"),
        "payment_method": existing.get("forma_pago"),
        "cancela": False,
        "relacionado": True,
    }


DIAS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


async def check_store_open(schedule: str | None) -> tuple[bool, str | None]:
    """
    Usa la IA para interpretar el horario en texto libre del local y
    decidir si está abierto ahora mismo (hora Colombia). Si el local no
    tiene horario registrado, se asume que sí puede intentar el pedido.
    """
    if not schedule:
        return True, None

    now = datetime.now(ZoneInfo("America/Bogota"))
    dia = DIAS_ES[now.weekday()]
    hora = now.strftime("%H:%M")

    client = _get_groq_client()
    prompt = f"""Horario de atención de un local: "{schedule}"
Ahora mismo es {dia}, {hora} (hora de Colombia).

¿Está el local abierto en este momento? Responde SOLO con un JSON:
{{"abierto": true o false, "mensaje": "si está cerrado, una frase breve y natural en español diciendo cuándo abre; si está abierto, null"}}"""

    try:
        completion = await client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0.1,
        )
        raw = _strip_thinking_tags(completion.choices[0].message.content or "")
        parsed = _safe_json_parse(raw)
        if parsed is not None:
            return bool(parsed.get("abierto", True)), parsed.get("mensaje")
    except Exception as e:
        logger.error(f"Error validando horario: {str(e)}")

    return True, None


# ── Escalamiento a humano ──────────────────────────────────────────

ESCALATION_KEYWORDS = [
    # Pide explícitamente una persona
    "hablar con una persona", "hablar con alguien", "persona real",
    "atención al cliente", "un humano", "hablar con un humano",
    "quiero hablar con alguien de verdad",
    # Queja / reclamo serio
    "queja", "reclamo", "denuncia", "pésimo servicio", "muy mal servicio",
    "terrible servicio", "esto es una estafa", "es un fraude", "me robaron",
    "no funciona nada", "esto no sirve",
    # Urgencia
    "es urgente", "emergencia", "urgente por favor",
    # Frustración explícita con el bot
    "no me estás ayudando", "no me entiendes", "esto es inútil",
    "quiero cancelar mi cuenta",
]


def needs_human_attention(message: str) -> tuple[bool, str]:
    """
    Detecta si el mensaje amerita que un administrador revise la
    conversación. No bloquea la respuesta del bot — el bot igual
    responde su mejor intento, pero la conversación queda marcada
    para que un humano le haga seguimiento desde el panel.

    Devuelve (True/False, razón_detectada_o_vacío).
    """
    msg = message.lower()
    for keyword in ESCALATION_KEYWORDS:
        if keyword in msg:
            return True, keyword
    return False, ""


def build_handoff_message(user_name: str = "") -> str:
    """
    Mensaje que ve el cliente cuando se detecta que necesita un humano.
    No pasa por la IA generativa a propósito — así nunca improvisa
    datos falsos (como números de teléfono inventados) en un momento
    delicado.
    """
    saludo = f"¡Entendido, {user_name}!" if user_name else "¡Entendido!"
    return (
        f"{saludo} Ya le avisé a nuestro equipo del Centro Comercial El Puente "
        f"para que te atienda personalmente 🙋 En un momento alguien continúa "
        f"esta conversación contigo por aquí mismo.\n\n"
        f"Mientras tanto, si hay algo más en lo que te pueda ayudar, dime."
    )


# ── Visión (bot que ve fotos) ──────────────────────────────────────

async def analyze_product_image(image_bytes: bytes, mime_type: str, caption: str = "") -> str:
    """
    Usa el modelo de visión de Groq para describir en pocas palabras
    qué producto aparece en una foto que manda el cliente — pensado
    para buscar algo parecido en el directorio del mall.

    Puede mencionar un diseño/estilo muy icónico y reconocible (ej. las
    3 franjas de Adidas, el swoosh de Nike) para que el cliente entienda
    qué tipo de producto es — pero no debe afirmar que esa marca está
    disponible en el mall si no aparece en el directorio real.
    """
    client = _get_groq_client()
    b64_image = base64.b64encode(image_bytes).decode("utf-8")

    prompt = (
        "Un cliente de un centro comercial mandó esta foto de un producto que "
        "le interesa. Describe en 1-2 líneas QUÉ es (tipo de prenda, calzado, "
        "accesorio, comida, tecnología, etc.), su categoría general, color "
        "principal y estilo. Sé breve y concreto, en español.\n\n"
        "Si el diseño tiene un detalle MUY icónico y reconocible de una marca "
        "conocida (ej. las 3 franjas de Adidas, el swoosh de Nike, las suelas "
        "rojas de Louboutin), puedes mencionarlo como referencia de estilo "
        "(ej. \"estilo con 3 franjas laterales, similar a Adidas\") — pero deja "
        "claro que es una referencia visual, no una confirmación de marca. "
        "Si no hay nada así de obvio, no adivines ninguna marca.\n\n"
        "Responde directo, sin mostrar tu razonamiento paso a paso. /no_think"
    )
    if caption:
        prompt += f'\n\nEl cliente escribió junto a la foto: "{caption}"'

    try:
        completion = await client.chat.completions.create(
            model=settings.GROQ_VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64_image}"}},
                    ],
                }
            ],
            max_tokens=700,  # antes 250 — muy poco, el modelo se cortaba a mitad
                             # de su razonamiento interno sin llegar a cerrar el
                             # bloque <think>, y eso se colaba entero en la respuesta
            temperature=0.4,
            # NOTA: NO usamos reasoning_format/reasoning_effort aquí — la
            # version de groq instalada (0.11.0) no los reconoce y el
            # SDK lanza un TypeError antes de llegar a Groq. Por eso
            # intentamos apagar el "pensar" directo en el prompt (/no_think,
            # convención nativa de los modelos Qwen3) y además limpiamos
            # cualquier <think> que se cuele, con _strip_thinking_tags().
        )
        raw = (completion.choices[0].message.content or "").strip()
        return _strip_thinking_tags(raw)
    except Exception as e:
        logger.error(f"Error Groq Vision: {str(e)}")
        return ""


def _strip_thinking_tags(text: str) -> str:
    """
    Red de seguridad de 2 niveles contra el "pensamiento" interno del
    modelo colándose en la respuesta del cliente:

    1. Caso normal: bloque <think>...</think> completo y bien cerrado
       — se remueve entero.
    2. Caso de respaldo: el modelo abrió <think> pero se quedó sin
       tokens antes de cerrarlo (pasó una vez con max_tokens muy bajo).
       Buscamos el signo "¡" como pista de dónde empieza la respuesta
       real en español (casi no existe en texto en inglés). Si ni eso
       aparece, preferimos devolver vacío — mejor un mensaje genérico
       de respaldo que arriesgarnos a mandar razonamiento interno.
    """
    import re
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()

    if "<think" in cleaned.lower():
        match = re.search(r"¡", cleaned)
        cleaned = cleaned[match.start():].strip() if match else ""

    return cleaned