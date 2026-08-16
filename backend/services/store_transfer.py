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

    # 2) Respaldo: coincidencia por palabras distintivas del nombre
    #    (ej. "Hamburgo" encuentra "Hamburgo 1718", "zirus" encuentra "Zirus Pizza")
    #    IMPORTANTE: contamos CUÁNTAS palabras coinciden por tienda, y
    #    preferimos la que más comparte — antes, con que 2 tiendas
    #    compartieran aunque fuera 1 sola palabra cualquiera, se rendía
    #    y no encontraba nada (ej. "12B Burguer" no encontraba "12B
    #    Burguer Angus" por una ambigüedad menor con otra tienda).
    candidates = []
    for s in stores:
        sig_words = _significant_words(s.name)
        matched = [w for w in sig_words if _contains_word(msg, w)]
        if matched:
            candidates.append((s, len(matched)))

    if not candidates:
        return None

    max_score = max(score for _, score in candidates)
    best = [s for s, score in candidates if score == max_score]

    if len(best) == 1:
        return best[0]
    return None  # empate real en la coincidencia más fuerte — ahí sí es ambiguo de verdad


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


def build_ask_which_store_management_message() -> str:
    """
    Igual que build_ask_which_store_message, pero para cuando el cliente
    pidió EXPLÍCITAMENTE gestión completa (no solo el contacto) — el
    texto es distinto a propósito, para poder reconocer después (cuando
    el cliente solo responda el nombre de la tienda) que debe continuar
    con el flujo completo de carta + datos, no con la transferencia simple.
    """
    return (
        "¡Con gusto te ayudo a gestionar tu pedido! 🛍️ ¿De qué tienda o restaurante quieres pedir? "
        "Dime el nombre y arrancamos con todo el proceso — te pido los datos y armamos tu pedido juntos."
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