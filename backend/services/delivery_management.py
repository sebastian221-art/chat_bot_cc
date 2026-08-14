"""
services/delivery_management.py

Orquesta el flujo completo de "gestión de domicilio" (distinto de la
simple transferencia): valida horario del local, muestra la carta,
recolecta los datos del cliente en 1 o varios mensajes, y arma el
link personalizado de WhatsApp con el pedido ya escrito.
"""
import logging
import urllib.parse
from sqlalchemy.orm import Session
from models.delivery_management import DeliveryManagement
from models.store import Store
from services.ai import check_store_open, extract_order_data

logger = logging.getLogger("mall_bot")


def get_active_session(db: Session, phone_number: str) -> DeliveryManagement | None:
    """Busca si este número ya tiene una gestión en curso (recolectando datos)."""
    return (
        db.query(DeliveryManagement)
        .filter(DeliveryManagement.phone_number == phone_number, DeliveryManagement.status == "collecting")
        .order_by(DeliveryManagement.created_at.desc())
        .first()
    )


def build_carta_message(store: Store) -> str:
    lines = [f"📋 Esto es lo que tenemos registrado de *{store.name}*:"]
    if store.extra_info:
        lines.append(f"\n{store.extra_info}")
        lines.append("\n_Ten en cuenta que esta información puede no estar 100% actualizada — para confirmar precios o disponibilidad exacta, coméntaselo directo al local en el siguiente paso._")
    else:
        lines.append("\nNo tengo la carta cargada de este local todavía — no hay problema, igual podemos continuar y puedes preguntarle los detalles directo al local.")
    return "\n".join(lines)


def build_data_request_message() -> str:
    return (
        "Para armar tu pedido necesito estos datos — puedes mandármelos todos juntos en un solo mensaje:\n\n"
        "👤 Tu nombre\n"
        "📞 Tu número de celular de contacto\n"
        "📍 Dirección de entrega\n"
        "🛍️ Qué quieres pedir\n"
        "💳 Si pagas en efectivo o por transferencia"
    )


def build_missing_fields_message(session: DeliveryManagement) -> str:
    missing = session.missing_fields()
    if len(missing) == 1:
        return f"¡Ya casi! Solo me falta: {missing[0]}."
    lista = ", ".join(missing[:-1]) + f" y {missing[-1]}"
    return f"¡Vamos bien! Todavía me falta: {lista}."


def build_personalized_link(store: Store, session: DeliveryManagement) -> str | None:
    """Arma el link wa.me hacia el local, con el pedido completo ya escrito en el mensaje."""
    if not store.phone:
        return None
    digits = "".join(c for c in store.phone if c.isdigit())
    if not digits:
        return None
    if not digits.startswith("57") and len(digits) == 10:
        digits = "57" + digits

    texto = (
        f"Hola, soy {session.customer_name} 👋 Vengo del asistente del Centro Comercial El Puente.\n\n"
        f"Quiero hacer un pedido:\n"
        f"🛍️ {session.order_details}\n"
        f"📍 Dirección: {session.address}\n"
        f"📞 Contacto: {session.customer_phone}\n"
        f"💳 Forma de pago: {session.payment_method}\n\n"
        f"¡Gracias!"
    )
    encoded = urllib.parse.quote(texto)
    return f"https://wa.me/{digits}?text={encoded}"


async def start_management(db: Session, phone_number: str, store: Store) -> str:
    """
    Primer paso: el cliente pidió explícitamente gestión de domicilio
    para un local identificado. Valida horario, muestra carta, pide datos.
    """
    is_open, closed_message = await check_store_open(store.schedule)
    if not is_open:
        session = DeliveryManagement(phone_number=phone_number, store_name=store.name, status="closed")
        db.add(session)
        db.commit()
        aviso = closed_message or "el local está cerrado en este momento"
        return f"😕 {store.name} está cerrado ahora mismo — {aviso}. ¿Quieres que te ayude con otra cosa mientras tanto?"

    session = DeliveryManagement(phone_number=phone_number, store_name=store.name, status="collecting")
    db.add(session)
    db.commit()

    carta = build_carta_message(store)
    pedido_datos = build_data_request_message()
    return f"{carta}\n\n{pedido_datos}"


async def continue_management(db: Session, session: DeliveryManagement, message: str, store: Store | None, user_name: str = "") -> str:
    """
    El cliente ya tenía una gestión en curso. Este mensaje puede ser:
    1) Datos (parte o todos) del pedido → los extrae y actualiza
    2) Una cancelación explícita ("ya no quiero") → cierra la gestión
       limpiamente, sin dejar al cliente atrapado
    3) Algo totalmente distinto (ej. "¿se permiten mascotas?") → responde
       la pregunta real usando el motor normal de IA, y recuerda que el
       pedido sigue en curso — así el cliente nunca siente que el bot
       "no entiende" o lo ignora solo porque está a mitad de un domicilio
    """
    existing = {
        "nombre": session.customer_name,
        "celular": session.customer_phone,
        "direccion": session.address,
        "pedido": session.order_details,
        "forma_pago": session.payment_method,
    }
    extracted = await extract_order_data(message, existing)

    # 1) Cancelación explícita — cerramos la gestión, sin dejar al
    #    cliente atrapado pidiéndole datos que ya no quiere dar.
    if extracted.get("cancela"):
        session.status = "cancelled"
        db.commit()
        return "Listo, cancelé la gestión de ese domicilio 👍 ¿En qué más te ayudo?"

    # 2) Mensaje sin relación con el pedido — respondemos la pregunta
    #    real (con el motor normal de IA, con acceso a todo el contexto
    #    del mall) y recordamos que el pedido sigue pendiente, en vez de
    #    ignorar la pregunta o insistir con los datos que faltan.
    if not extracted.get("relacionado", True):
        from services.ai import generate_response
        respuesta_real = await generate_response(
            user_message=message,
            user_name=user_name,
            conversation_history=[],
            db=db,
        )
        recordatorio = (
            f"\n\n_Por cierto, tu pedido a **{session.store_name}** sigue en curso — "
            f"cuando quieras seguir, mándame los datos que falten 😊_"
        )
        return respuesta_real + recordatorio

    # 3) Es sobre el pedido — actualizamos con lo nuevo que haya llegado
    session.customer_name = extracted["customer_name"]
    session.customer_phone = extracted["customer_phone"]
    session.address = extracted["address"]
    session.order_details = extracted["order_details"]
    session.payment_method = extracted["payment_method"]
    db.commit()

    if not session.is_complete():
        db.commit()
        return build_missing_fields_message(session)

    # Completo — armamos el link. Necesitamos la tienda para el teléfono.
    if store is None:
        from models.store import Store as StoreModel
        store = db.query(StoreModel).filter(StoreModel.name == session.store_name).first()

    if not store:
        return "Se me perdió el dato de a qué local le estabas pidiendo 😅 ¿me confirmas el nombre de la tienda o restaurante otra vez?"

    link = build_personalized_link(store, session)
    if not link:
        return f"Ya tengo todos tus datos, pero {store.name} no tiene un número de WhatsApp registrado — pásate por el Punto de Información (Piso 1) para que te ayuden a contactarlos."

    session.status = "completed"
    session.generated_link = link
    from sqlalchemy import func
    session.completed_at = func.now()
    db.commit()

    return (
        f"¡Listo, {session.customer_name}! 🎉 Ya tengo todo tu pedido armado.\n\n"
        f"Toca este link para mandárselo directo a *{store.name}* — ya viene escrito con todos tus datos, solo confirma el envío:\n\n"
        f"{link}"
    )