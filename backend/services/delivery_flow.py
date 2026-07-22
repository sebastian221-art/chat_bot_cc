# 📄 ARCHIVO: backend/services/delivery_flow.py
"""
Flujo de domicilios v4 — detección inteligente + mensajes con personalidad.
FIXES:
  - _handle_waiting_local: consulta estado real del Order en DB
  - is_delivery_intent: no dispara si hay pedido activo para ese teléfono
  - Respuestas amables y contextuales mientras el cliente espera su pedido
"""
import json
import re
import logging
import unicodedata
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from models.delivery_session import DeliverySession
from models.order import Order, OrderStatus
from services.orders import create_order, format_menu_for_bot, get_store_menu

logger = logging.getLogger("mall_bot")

DELIVERY_CATEGORIES = {
    "Comida Rápida", "Restaurante", "Cafetería",
    "Farmacia y Salud", "Salud y Óptica",
}

CONFIRM_WORDS = {
    "sí", "si", "yes", "confirmo", "confirmar", "correcto",
    "claro", "dale", "ok", "listo", "va", "acepto", "afirmativo",
    "exacto", "correcto", "así es", "de una", "va que va",
}
CANCEL_WORDS = {
    "no", "cancelar", "cancel", "no quiero", "déjalo", "dejalo",
    "mejor no", "no gracias", "olvidalo", "olvídalo", "no más",
}
CALL_WORDS = {
    "llamar", "llamo", "teléfono", "telefono", "número", "numero",
    "prefiero llamar", "quiero llamar", "dame el número",
}
DELIVERY_WORDS = {
    "domicilio", "delivery", "pedir", "pedido", "a casa", "enviar",
    "llevar", "quiero pedir", "hacer un pedido", "ordenar",
    "quiero ordenar", "hacer pedido", "un pedido",
}

# Palabras que indican consulta sobre pedido activo — NO deben reiniciar el flujo
ORDER_STATUS_WORDS = {
    "demora", "tarda", "tardará", "tardara", "cuánto", "cuanto",
    "listo", "llegó", "llego", "llegará", "llegara", "entregaron",
    "dónde está", "donde esta", "mi pedido", "el pedido", "estado",
    "confirmaron", "aceptaron", "rechazaron", "ya viene", "en camino",
    "preparando", "está listo", "esta listo",
}


# ── Normalización ─────────────────────────────────────────────────

def _norm(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text.lower().strip())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", _norm(text)) if len(w) > 2}


def is_delivery_intent(message: str, db: Session = None, phone_number: str = None) -> bool:
    """
    Retorna True solo si el mensaje quiere INICIAR un pedido y NO hay
    ya un pedido activo para este teléfono.
    """
    msg_norm = _norm(message)

    # Si el mensaje parece una consulta sobre pedido existente → NO es nuevo flujo
    if any(k in msg_norm for k in ORDER_STATUS_WORDS):
        return False

    has_delivery_word = any(k in msg_norm for k in DELIVERY_WORDS)
    if not has_delivery_word:
        return False

    # Si hay un Order activo (no terminado) para este teléfono → no reiniciar
    if db is not None and phone_number:
        active = _get_active_order(db, phone_number)
        if active:
            return False

    return True


def _get_active_order(db: Session, phone_number: str) -> Order | None:
    """Retorna el pedido más reciente activo (no finalizado) del cliente."""
    terminal = {OrderStatus.DELIVERED, OrderStatus.CANCELLED}
    return (
        db.query(Order)
        .filter(
            Order.client_phone == phone_number,
            Order.status.notin_(terminal),
        )
        .order_by(Order.created_at.desc())
        .first()
    )


def _is_confirm(msg: str) -> bool:
    m = _norm(msg)
    return any(m == k or m.startswith(k + " ") for k in CONFIRM_WORDS)


def _is_cancel(msg: str) -> bool:
    return any(k in _norm(msg) for k in CANCEL_WORDS)


def _wants_to_call(msg: str) -> bool:
    return any(k in _norm(msg) for k in CALL_WORDS)


# ── DB helpers ────────────────────────────────────────────────────

def get_or_create_session(db: Session, phone: str) -> DeliverySession:
    s = db.query(DeliverySession).filter(
        DeliverySession.phone_number == phone
    ).first()
    if not s:
        s = DeliverySession(phone_number=phone, step="idle")
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


def _save(db: Session, s: DeliverySession):
    s.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(s)


# ── Tiendas ───────────────────────────────────────────────────────

def get_delivery_stores(db: Session) -> list[dict]:
    import os
    path = os.path.join(os.path.dirname(__file__), "..", "data", "tiendas.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [s for s in data.get("stores", [])
                if s.get("category", "") in DELIVERY_CATEGORIES]
    except Exception as e:
        logger.error(f"Error leyendo tiendas.json: {e}")
        return []


def find_store_in_text(db: Session, text: str) -> dict | None:
    stores    = get_delivery_stores(db)
    msg_words = _words(text)

    for s in stores:
        if _norm(s.get("name", "")) in _norm(text):
            return s

    for s in stores:
        store_words = _words(s.get("name", ""))
        if store_words & msg_words:
            return s

    return None


# ── Parser IA ────────────────────────────────────────────────────

async def _parse_order_data(message: str, store_name: str) -> dict | None:
    from groq import AsyncGroq
    from config import get_settings
    settings = get_settings()
    client   = AsyncGroq(api_key=settings.GROQ_API_KEY)

    prompt = (
        f"Extrae información de este pedido de domicilio del local '{store_name}'.\n"
        f"Mensaje del cliente: \"{message}\"\n\n"
        "Responde ÚNICAMENTE con JSON válido, sin texto adicional ni backticks:\n"
        "{\n"
        "  \"nombre\": \"nombre completo de quien recibe\",\n"
        "  \"direccion\": \"dirección exacta de entrega\",\n"
        "  \"pago\": \"efectivo o transferencia\",\n"
        "  \"productos\": \"descripción exacta de lo que pide con cantidades\",\n"
        "  \"ok\": true\n"
        "}\n\n"
        "Reglas:\n"
        "- ok: false si falta nombre, dirección O productos\n"
        "- pago por defecto: 'efectivo' si no se menciona\n"
        "- No inventes datos, usa solo lo que hay en el mensaje"
    )

    try:
        resp = await client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=250,
            temperature=0.0,
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r"```[a-z]*", "", raw).replace("```", "").strip()
        return json.loads(raw)
    except Exception as e:
        logger.error(f"Error parseando pedido: {e}")
        return None


# ── Mensajes con personalidad ─────────────────────────────────────

def _msg_store_list(stores: list[dict]) -> str:
    lines = ["🛵 *¡Con gusto te ayudo con tu domicilio!*\n"]
    lines.append("¿De cuál de estos locales quieres pedir?\n")
    emojis = ["🍔", "🥞", "🥗", "🌮", "☕", "💊", "👓", "🏪"]
    for i, s in enumerate(stores):
        e = emojis[i % len(emojis)]
        lines.append(f"{e} *{s['name']}* — {s.get('floor', '')}")
    lines.append(
        "\nEscribe el nombre del local para continuar.\n"
        "_(¿Prefieres llamar? Escribe *llamar* y te doy el número 📞)_"
    )
    return "\n".join(lines)


def _msg_show_store(store: dict, menu_text: str) -> str:
    name  = store["name"]
    floor = store.get("floor", "")
    phone = store.get("phone", "")

    header = f"🍽️ *{name}*  ·  {floor}"
    if phone:
        header += f"\n📞 {phone} _(si prefieres llamar)_"

    return (
        f"{header}\n\n"
        f"*Carta disponible:*\n"
        f"{menu_text}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📝 Para hacer el pedido, envíame *todo en un mensaje*:\n\n"
        f"  • 👤 Nombre de quien recibe\n"
        f"  • 📍 Dirección exacta (barrio, referencias)\n"
        f"  • 💳 Forma de pago (efectivo o Nequi/Daviplata)\n"
        f"  • 🛒 Qué quieres pedir con cantidades\n\n"
        f"_Ej: Juan Pérez / Cra 27 #45-12, Cabecera, frente al parque "
        f"/ Nequi / 2 hamburguesas clásicas y 1 jugo_"
    )


def _msg_summary(s: DeliverySession) -> str:
    pago_icon = "📱" if any(k in _norm(s.payment_method or "") for k in ["transfer", "nequi", "daviplata"]) else "💵"
    return (
        f"✨ *Perfecto, revisa tu pedido antes de confirmar:*\n\n"
        f"🏪 *Local:*      {s.store_name}\n"
        f"👤 *Recibe:*     {s.client_name}\n"
        f"📍 *Dirección:*  {s.delivery_address}\n"
        f"{pago_icon} *Pago:*       {s.payment_method}\n"
        f"🛒 *Pedido:*     {s.products_text}\n\n"
        f"¿Todo correcto? Responde *SÍ* para enviarlo al local "
        f"o *NO* si quieres cambiar algo 😊"
    )


def _msg_confirmed(order_number: str, store_name: str) -> str:
    return (
        f"🎉 *¡Pedido enviado!*\n\n"
        f"📋 *#{order_number}*  ·  {store_name}\n\n"
        f"El local ya lo recibió ✅ En cuanto confirmen te cuento:\n"
        f"   ⏱️ Tiempo estimado\n"
        f"   💰 Total a pagar\n\n"
        f"🔔 Te notifico aquí mismo, no tienes que hacer nada más.\n\n"
        f"——————————————\n"
        f"_¿Arrepentiste? Escribe_ *cancelar* _y lo detenemos._"
    )


def _msg_cancelled() -> str:
    return (
        "❌ *Pedido cancelado.*\n\n"
        "Sin problema 😊 Cuando quieras intentarlo de nuevo, "
        "aquí estaré."
    )


def _msg_order_status(order: Order) -> str:
    """Respuesta elegante sobre el estado actual del pedido activo."""
    status = order.status

    if status == OrderStatus.PENDING:
        return (
            f"⏳ *Tu pedido #{order.order_number} está siendo revisado* por *{order.store_name}*.\n\n"
            f"En cuanto lo acepten te notifico aquí mismo 🔔\n\n"
            f"——————————————\n"
            f"_¿Ya no lo quieres? Escribe_ *cancelar*_._"
        )

    if status == OrderStatus.ACCEPTED:
        lines = [
            f"✅ *¡Tu pedido #{order.order_number} fue aceptado!* 🎉\n",
            f"🏪 Local: *{order.store_name}*",
        ]
        if order.delivery_time_minutes:
            lines.append(f"⏱️ Tiempo estimado: *{order.delivery_time_minutes} minutos*")
        else:
            lines.append("⏱️ El local está preparando tu pedido ahora mismo")
        if order.total and order.total > 0:
            lines.append(f"💰 Total: *${order.total:,.0f} COP*")
        if order.store_message:
            lines.append(f"💬 {order.store_message}")
        lines.append("\n🛵 Te aviso cuando salga a domicilio.")
        return "\n".join(lines)

    if status == OrderStatus.PREPARING:
        return (
            f"👨‍🍳 *¡Están preparando tu pedido!* #{order.order_number}\n\n"
            f"Tu pedido de *{order.store_name}* ya está en cocina 🔥\n"
            + (f"⏱️ Tiempo estimado: *{order.delivery_time_minutes} min*\n" if order.delivery_time_minutes else "")
            + "\nTe aviso cuando salga a domicilio 🛵"
        )

    if status == OrderStatus.READY:
        return (
            f"✅ *¡Tu pedido está listo!* #{order.order_number}\n\n"
            f"Ya terminaron de preparar tu pedido de *{order.store_name}*.\n"
            f"Está por salir a domicilio ahora mismo 🛵"
        )

    if status == OrderStatus.ON_THE_WAY:
        return (
            f"🛵 *¡Tu pedido va en camino!* #{order.order_number}\n\n"
            f"Ya salió de *{order.store_name}* hacia tu dirección.\n"
            f"¡Pronto llega! 🏠"
        )

    # Estado desconocido — respuesta genérica pero amable
    return (
        f"📋 Tu pedido *#{order.order_number}* de *{order.store_name}* "
        f"está siendo procesado. Te notificamos a medida que avance 🔔"
    )


def _msg_waiting_fallback() -> str:
    return (
        "⏳ *Aún esperamos respuesta del local.*\n\n"
        "En cuanto confirmen te aviso aquí 🔔\n\n"
        "——————————————\n"
        "_¿Ya no lo quieres? Escribe_ *cancelar*_._"
    )


def _msg_call_number(store: dict) -> str:
    return (
        f"📞 *Número de {store['name']}:*\n\n"
        f"*{store.get('phone', 'No disponible')}*\n\n"
        f"Llama directamente para hacer tu pedido.\n"
        f"¡Que lo disfrutes! 🍔"
    )


def _msg_call_list(stores: list[dict]) -> str:
    lines = ["📞 *Números de los locales con domicilio:*\n"]
    emojis = ["🍔", "🥞", "🥗", "🌮", "☕", "💊"]
    for i, s in enumerate(stores):
        if s.get("phone"):
            e = emojis[i % len(emojis)]
            lines.append(f"{e} *{s['name']}*\n    {s['phone']}")
    lines.append("\n¡Que disfrutes tu domicilio! 😊")
    return "\n".join(lines)


def _msg_not_found_store(stores: list[dict]) -> str:
    names = "\n".join(f"• {s['name']}" for s in stores[:6])
    return (
        f"Mmm, no encontré ese local 🤔\n\n"
        f"Los disponibles son:\n{names}\n\n"
        f"¿Cuál de esos te interesa?"
    )


def _msg_missing_fields(missing: list[str]) -> str:
    items = "\n".join(f"  • {m}" for m in missing)
    return (
        f"¡Casi listo! Solo me falta un poco más de info 😊\n\n"
        f"{items}\n\n"
        f"Envíame los datos que faltan y enseguida lo tramito 👌"
    )


# ── Handlers ─────────────────────────────────────────────────────

def _handle_cancel(db: Session, s: DeliverySession) -> str:
    if s.order_id:
        order = db.query(Order).filter(Order.id == s.order_id).first()
        if order and order.status == OrderStatus.PENDING:
            order.status = OrderStatus.CANCELLED
            db.commit()
    s.reset()
    _save(db, s)
    return _msg_cancelled()


def _offer_call(db: Session, s: DeliverySession, text: str) -> str:
    stores = get_delivery_stores(db)
    store  = find_store_in_text(db, text) or (
        next((st for st in stores if _norm(st["name"]) == _norm(s.store_name or "")), None)
        if s.store_name else None
    )
    s.reset()
    _save(db, s)
    if store and store.get("phone"):
        return _msg_call_number(store)
    return _msg_call_list(stores)


def _go_to_store(db: Session, s: DeliverySession, store: dict) -> str:
    s.store_name    = store["name"]
    s.step          = "collecting_all"
    s.step_attempts = 0
    _save(db, s)

    products  = get_store_menu(db, store["name"])
    menu_text = format_menu_for_bot(products)
    return _msg_show_store(store, menu_text)


def _handle_idle(db: Session, s: DeliverySession, message: str) -> str:
    store = find_store_in_text(db, message)
    if store:
        return _go_to_store(db, s, store)

    stores = get_delivery_stores(db)
    if not stores:
        return (
            "🛵 Me encantaría ayudarte con un domicilio, pero aún no hay "
            "locales registrados con ese servicio.\n"
            "Visita el *Punto de Información* en el Piso 1 para más ayuda 😊"
        )

    s.step          = "asking_store"
    s.step_attempts = 0
    _save(db, s)
    return _msg_store_list(stores)


def _handle_asking_store(db: Session, s: DeliverySession, message: str) -> str:
    if _wants_to_call(message):
        return _offer_call(db, s, message)

    store = find_store_in_text(db, message)
    if not store:
        s.step_attempts += 1
        _save(db, s)
        if s.step_attempts >= 3:
            s.reset(); _save(db, s)
            return (
                "No pude identificar el local después de varios intentos 😅\n"
                "Escribe *domicilio* cuando quieras intentarlo de nuevo."
            )
        return _msg_not_found_store(get_delivery_stores(db))

    return _go_to_store(db, s, store)


async def _handle_collecting_all(
    db: Session, s: DeliverySession, message: str, user_name: str
) -> str:
    parsed = await _parse_order_data(message, s.store_name or "")

    if not parsed or not parsed.get("ok"):
        s.step_attempts += 1
        _save(db, s)

        missing = []
        if parsed:
            if not parsed.get("nombre"):    missing.append("👤 *Nombre* de quien recibe")
            if not parsed.get("direccion"): missing.append("📍 *Dirección* exacta")
            if not parsed.get("productos"): missing.append("🛒 *Qué quieres pedir*")
        else:
            missing = ["👤 *Nombre*", "📍 *Dirección*", "🛒 *Qué quieres pedir*"]

        if s.step_attempts >= 3:
            s.reset(); _save(db, s)
            return (
                "Tuve problemas entendiendo los datos 😅\n"
                "Escribe *domicilio* para empezar de nuevo cuando quieras."
            )
        return _msg_missing_fields(missing)

    pago_raw = _norm(parsed.get("pago", ""))
    if any(k in pago_raw for k in ["nequi", "daviplata", "transfer", "digital", "bancolombia"]):
        payment = "Transferencia / Nequi 📱"
    else:
        payment = "Efectivo 💵"

    s.client_name      = parsed.get("nombre", user_name).strip().title()
    s.delivery_address = parsed.get("direccion", "").strip()
    s.payment_method   = payment
    s.products_text    = parsed.get("productos", "").strip()
    s.step             = "confirming"
    s.step_attempts    = 0
    _save(db, s)

    return _msg_summary(s)


def _handle_confirming(
    db: Session, s: DeliverySession, message: str, user_name: str
) -> str:
    if _is_cancel(message):
        return _handle_cancel(db, s)
    if not _is_confirm(message):
        return (
            "Solo responde *SÍ* para confirmar y enviar el pedido al local, "
            "o *NO* para cancelar 😊"
        )

    order = create_order(
        db=db,
        client_phone=s.phone_number,
        client_name=s.client_name or user_name,
        store_name=s.store_name or "",
        items=[{
            "product_name": s.products_text,
            "quantity":     1,
            "unit_price":   0,
            "notes":        "",
        }],
        delivery_address=s.delivery_address or "",
        notes=f"Pago: {s.payment_method}",
    )

    s.order_id       = order.id
    s.local_notified = True
    s.step           = "waiting_local"
    _save(db, s)

    return _msg_confirmed(order.order_number, s.store_name or "")


def _handle_waiting_local(db: Session, s: DeliverySession, message: str) -> str:
    """
    El cliente manda un mensaje mientras espera al local.
    Consultamos el Order real en DB para responder con info actualizada.
    """
    if _is_cancel(message):
        return _handle_cancel(db, s)

    # Buscar el Order real
    order = None
    if s.order_id:
        order = db.query(Order).filter(Order.id == s.order_id).first()

    # Si el pedido ya fue entregado o cancelado externamente, limpiar sesión
    if order and order.status in (OrderStatus.DELIVERED, OrderStatus.CANCELLED):
        s.reset()
        _save(db, s)
        if order.status == OrderStatus.DELIVERED:
            return "🏠 *¡Tu pedido ya fue entregado!* ¿Cómo estuvo la experiencia? Cuéntame del *1 al 5* ⭐"
        return "El pedido fue cancelado. Si quieres hacer uno nuevo, escribe *domicilio* 😊"

    # Si encontramos el order, responder con su estado real
    if order:
        return _msg_order_status(order)

    # Fallback si por alguna razón no encontramos el order
    return _msg_waiting_fallback()


# ══════════════════════════════════════════════════════════════════
# PUNTO DE ENTRADA
# ══════════════════════════════════════════════════════════════════

async def handle_delivery_message(
    db: Session,
    phone_number: str,
    user_name: str,
    message: str,
) -> str:
    s = get_or_create_session(db, phone_number)
    logger.info(f"  🛵  [{phone_number}] step={s.step} | {message[:60]}")

    if s.step != "idle" and _is_cancel(message):
        return _handle_cancel(db, s)

    if _wants_to_call(message) and s.step in ("idle", "asking_store", "collecting_all"):
        return _offer_call(db, s, message)

    if s.step == "idle":
        return _handle_idle(db, s, message)
    if s.step == "asking_store":
        return _handle_asking_store(db, s, message)
    if s.step == "collecting_all":
        return await _handle_collecting_all(db, s, message, user_name)
    if s.step == "confirming":
        return _handle_confirming(db, s, message, user_name)
    if s.step == "waiting_local":
        return _handle_waiting_local(db, s, message)

    s.reset(); _save(db, s)
    return "Algo se enredó por aquí 😅 Escribe *domicilio* para empezar de nuevo."