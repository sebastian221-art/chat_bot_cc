"""
services/store_transfer.py

Reemplaza el flujo de domicilio gestionado por el bot. En vez de tomar
el pedido completo, el bot identifica la tienda/restaurante y transfiere
al cliente directo al WhatsApp de ese local para que gestionen el
pedido entre ellos.

No usa IA generativa — es más rápido y no hay riesgo de que invente
un número de contacto que no existe.
"""
from sqlalchemy.orm import Session
from models.store import Store


def find_store_by_message(db: Session, message: str) -> Store | None:
    """
    Busca si el cliente mencionó el nombre de una tienda/restaurante
    específico en su mensaje. Si encuentra exactamente una coincidencia,
    la devuelve. Si hay 0 o varias, devuelve None (hay que preguntar).
    """
    msg = message.lower()
    stores = db.query(Store).filter(Store.active == True).all()
    matches = [s for s in stores if s.name.lower() in msg]
    if len(matches) == 1:
        return matches[0]
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