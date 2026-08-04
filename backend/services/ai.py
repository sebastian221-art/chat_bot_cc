# 📄 ARCHIVO: backend/services/ai.py
"""
Servicio de IA — Groq + LLaMA.
FIXES:
  - Nueva intención 'estado_pedido' para preguntas sobre el pedido activo
  - Prompt dedicado que responde con elegancia sobre el estado
  - is_delivery_intent ya no clasifica preguntas de estado como nuevos pedidos
"""
import logging
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
- NUNCA inventes datos — solo usa la info que te dan abajo
- Si no sabes algo, dilo con amabilidad y sugiere el Punto de Información (Piso 1)
- Usa máximo 1-2 emojis por mensaje, solo cuando aporten
- Si el usuario saluda, salúdalo de vuelta y pregunta en qué le ayudas"""

# ── Prompts por intención ─────────────────────────────────────────

PROMPTS = {
    "saludo": BASE_PERSONA + """

TIPO DE RESPUESTA: Saludo
- 1-2 líneas máximo
- Cálido, breve, invita a preguntar
- Ejemplo tono: "¡Hola! Soy Any 👋 ¿En qué te puedo ayudar hoy?"
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
    # services/store_transfer.py. Se deja aquí solo por si se quiere
    # revertir al flujo antiguo en el futuro.
    "domicilio": BASE_PERSONA + """

TIPO DE RESPUESTA: Domicilio
- El sistema de domicilios está disponible para restaurantes del mall
- Pregunta al usuario: ¿de qué restaurante quiere pedir?
- Lista los restaurantes disponibles con nombre y piso (solo los que estén en los datos)
- Máximo 4-5 líneas
""",

    "categoria": BASE_PERSONA + """

TIPO DE RESPUESTA: Lista de opciones por categoría
- Lista TODAS las opciones de esa categoría que estén en los datos
- Formato por opción: "📍 Nombre — Piso X — descripción de 1 línea"
- Sin párrafos. Lista limpia y escaneable
- Al final: una línea cálida invitando a preguntar por más detalles
""",

    "general": BASE_PERSONA + """

TIPO DE RESPUESTA: Consulta general sobre una tienda o servicio
- Si preguntan por UNA tienda específica: nombre, piso, horario, teléfono, qué vende — en 4-6 líneas
- Si es una pregunta de sí/no: responde directo y añade el dato relevante
- Nunca cortes información útil, pero tampoco rellenes con palabras vacías
""",
}


# ── Función principal ─────────────────────────────────────────────

async def generate_response(
    user_message: str,
    user_name: str,
    conversation_history: list[dict],
    user_profile: str = "",
    active_order_context: str = "",   # ← NUEVO: contexto del pedido activo si existe
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

    messages = [{"role": "system", "content": system_content}]

    for turn in conversation_history[-12:]:
        messages.append({"role": turn["role"], "content": turn["content"]})

    messages.append({"role": "user", "content": f"[Usuario: {user_name}] {user_message}"})

    try:
        completion = await client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=messages,
            max_tokens=500,
            temperature=0.7,
            top_p=0.9,
        )
        return completion.choices[0].message.content

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