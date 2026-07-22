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

BASE_PERSONA = """Eres Puente Bot 🛍️, el asistente virtual del Centro Comercial El Puente en Bucaramanga.
Eres amigable, cálido y directo — como un buen guía del mall que conoce todo de memoria.

REGLAS SIEMPRE:
- Responde en español
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
- Ejemplo tono: "¡Hola! Soy Puente Bot 👋 ¿En qué te puedo ayudar hoy?"
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

    "estado_pedido": BASE_PERSONA + """

TIPO DE RESPUESTA: Estado del pedido activo
- El cliente ya tiene un pedido en curso y pregunta cómo va
- USA SIEMPRE la info del pedido que se te provee abajo
- Sé cálido, tranquilizador y específico
- Si hay tiempo estimado, menciónalo
- Si el pedido ya fue aceptado, díselo con entusiasmo
- Si aún está pendiente, dile que en cuanto el local confirme se le notifica
- Máximo 3-4 líneas, tono conversacional
- NUNCA digas "no tengo información" si te dan datos del pedido
- Si no hay datos del pedido, di que el sistema está verificando y que ya viene la confirmación
""",

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