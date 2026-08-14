"""
services/store_transfer.py

Reemplaza el flujo de domicilio gestionado por el bot. En vez de tomar
el pedido completo, el bot identifica la tienda/restaurante y transfiere
al cliente directo al WhatsApp de ese local para que gestionen el
pedido entre ellos.

No usa IA generativa — es más rápido y no hay riesgo de que invente
un número de contacto que no existe.
"""
import re
from sqlalchemy.orm import Session
from models.store import Store

STOPWORDS_ES = {"la", "el", "los", "las", "de", "del", "y", "un", "una", "en", "por", "para"}


def _significant_words(name: str) -> list[str]:
    """Palabras 'distintivas' de un nombre — sin artículos ni palabras muy cortas."""
    words = re.findall(r"[a-záéíóúñü']+", name.lower())
    return [w for w in words if len(w) > 2 and w not in STOPWORDS_ES]


def _contains_word(message: str, word: str) -> bool:
    """True si `word` aparece como palabra completa en el mensaje (no como parte de otra palabra)."""
    return re.search(rf"\b{re.escape(word)}\b", message) is not None


def find_store_by_message(db: Session, message: str) -> Store | None:
    """
    Busca si el cliente mencionó el nombre de una tienda/restaurante en
    su mensaje. Reconoce tanto el nombre completo ("Hamburgo 1718") como
    solo la parte distintiva ("Hamburgo", "zirus") — así funciona con
    cómo la gente realmente escribe, no solo con el nombre exacto.
    Si encuentra exactamente una coincidencia, la devuelve. Si hay 0 o
    varias (ambiguo), devuelve None — mejor preguntar que adivinar mal.
    """
    msg = message.lower()
    stores = db.query(Store).filter(Store.active == True).all()

    # 1) Coincidencia por nombre completo — la más confiable, se revisa primero
    exact_matches = [s for s in stores if s.name.lower() in msg]
    if len(exact_matches) == 1:
        return exact_matches[0]
    if len(exact_matches) > 1:
        return None

    # 2) Respaldo: coincidencia por una palabra distintiva del nombre
    #    (ej. "Hamburgo" encuentra "Hamburgo 1718", "zirus" encuentra "Zirus Pizza")
    word_matches = []
    for s in stores:
        sig_words = _significant_words(s.name)
        if any(_contains_word(msg, w) for w in sig_words):
            word_matches.append(s)

    if len(word_matches) == 1:
        return word_matches[0]
    return None


def build_transfer_message(store: Store) -> str:
    """Mensaje de transferencia cuando SÍ se identificó la tienda."""
    link = store.whatsapp_link()
    if link:
        return (
            f"¡Perfecto! Para tu pedido en *{store.name}*, escríbeles directo aquí 👉 {link}\n\n"
            f"Ellos te confirman el pedido, el tiempo de entrega y la forma de pago. 🛍️"
        )
    if store.phone:
        return (
            f"Para tu pedido en *{store.name}*, comunícate al {store.phone} — "
            f"ellos gestionan directamente sus domicilios."
        )
    return (
        f"*{store.name}* no tiene un teléfono registrado en nuestro directorio todavía. "
        f"Te recomiendo acercarte al Punto de Información del mall para que te ayuden a contactarlos."
    )


def build_ask_which_store_message() -> str:
    """Mensaje cuando el cliente quiere domicilio pero no está claro de qué tienda."""
    return (
        "¡Con gusto te ayudo! 🛍️ ¿De qué tienda o restaurante del mall quieres hacer tu pedido? "
        "Dime el nombre y te paso el contacto directo para que gestiones tu domicilio con ellos."
    )


# ── Petición directa del número de una tienda ───────────────────────
# Distinto de "quiero pedir de X" — aquí la persona pregunta puntualmente
# por el número/teléfono, sin necesariamente enmarcarlo como un pedido
# (ej. "me pasas el número de Zirus Pizza"). La respuesta da el número,
# el link directo, y pregunta qué necesita — para no dejarlo a medias.

PHONE_REQUEST_KEYWORDS = [
    "número de", "numero de", "teléfono de", "telefono de",
    "me pasas el número", "me pasas el numero",
    "me pasa el número", "me pasa el numero",
    "me puedes pasar el número", "me puedes pasar el numero",
    "me puedes dar el número", "me puedes dar el numero",
    "cuál es el número", "cual es el numero",
    "cuál es el teléfono", "cual es el telefono",
    "el contacto de",
]


def is_phone_request_intent(message: str) -> bool:
    msg = message.lower()
    return any(k in msg for k in PHONE_REQUEST_KEYWORDS)


def build_phone_info_message(store: Store) -> str:
    """Da el número, el link directo, y pregunta qué necesita — respuesta completa, no solo el dato suelto."""
    if not store.phone:
        return (
            f"*{store.name}* no tiene un teléfono registrado en nuestro directorio todavía. "
            f"Te recomiendo acercarte al Punto de Información del mall para que te ayuden a contactarlos."
        )

    lines = [f"📞 El número de *{store.name}* es {store.phone}."]
    link = store.whatsapp_link()
    if link:
        lines.append(f"\nTambién puedes escribirles directo por aquí 👉 {link}")
    lines.append("\n¿Qué te gustaría preguntarles o pedirles? Cuéntame y te ayudo con lo que necesites. 😊")
    return "\n".join(lines)