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
from groq import AsyncGroq
from config import get_settings
from services.rag import search_stores

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
        "domicilio", "delivery", "a casa", "pedir", "quiero pedir",
        "hacer un pedido", "ordenar", "quiero ordenar", "hacer pedido",
        "llevar a", "enviar a", "mandar a domicilio",
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
- Si la pregunta es amplia o ambigua (ej. "zapatos deportivos" puede ser de vestir o para practicar deporte), primero haz UNA pregunta corta para entender mejor qué busca, antes de dar nombres de tiendas
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

    rag_docs = search_stores(user_message, n_results=8)

    system_content = PROMPTS.get(intent, PROMPTS["general"])

    # Inyectar contexto del pedido activo cuando la pregunta es sobre estado
    if active_order_context:
        system_content += f"\n\n--- PEDIDO ACTIVO DEL CLIENTE ---\n{active_order_context}\n---"

    if rag_docs:
        context = "\n\n".join(f"📌 {doc}" for doc in rag_docs)
        system_content += f"\n\n--- INFORMACIÓN DEL MALL ---\n{context}\n---"

    if user_profile:
        system_content += f"\n\nPERFIL DEL USUARIO: {user_profile}"

    # ── Promoción por prioridad + recomendaciones personalizadas ────
    # Se agregan como contenido DISPONIBLE, no como orden — el prompt le
    # deja al modelo la decisión de si encaja mencionarlo o no, para
    # que nunca se sienta forzado ni repetitivo.
    if db is not None:
        promo_block = _build_promotions_block(db, user_profile)
        if promo_block:
            system_content += promo_block

    messages = [{"role": "system", "content": system_content}]

    for turn in conversation_history[-12:]:
        messages.append({"role": turn["role"], "content": turn["content"]})

    messages.append({"role": "user", "content": f"[Usuario: {user_name}] {user_message}"})

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
        return _strip_thinking_tags(raw)

    except Exception as e:
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