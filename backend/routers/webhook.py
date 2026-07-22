# 📄 ARCHIVO: backend/routers/webhook.py
"""
Webhook de WhatsApp + test endpoint.
FIXES:
  - Sesión activa siempre tiene prioridad sobre is_delivery_intent
  - Nueva intención estado_pedido: busca Order activo e inyecta contexto al AI
  - El AI responde con info real del pedido cuando el cliente pregunta su estado
"""
import logging
import time
from fastapi import APIRouter, Request, Response, Depends, BackgroundTasks
from sqlalchemy.orm import Session

from config import get_settings
from models.database import get_db
from models.conversation import Conversation
from models.user_profile import UserProfile
from models.delivery_session import DeliverySession
from models.order import Order, OrderStatus
from services.whatsapp import send_text_message, parse_incoming_message
from services.ai import generate_response, is_delivery_intent, is_order_status_question
from services.delivery_flow import (
    handle_delivery_message,
    get_or_create_session,
)

settings = get_settings()
logger   = logging.getLogger("mall_bot")
router   = APIRouter(prefix="/webhook", tags=["webhook"])

MAX_HISTORY_PER_USER = 50


# ── Verificación Meta ─────────────────────────────────────────────

@router.get("")
async def verify_webhook(request: Request):
    params    = dict(request.query_params)
    mode      = params.get("hub.mode")
    token     = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")
    if mode == "subscribe" and token == settings.VERIFY_TOKEN:
        print("  ✅  Webhook verificado por Meta")
        return Response(content=challenge, media_type="text/plain")
    print(f"  ❌  Verificación fallida. Token: {token}")
    return Response(content="Forbidden", status_code=403)


# ── Recepción WhatsApp ────────────────────────────────────────────

@router.post("")
async def receive_message(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    data = await request.json()
    msg  = parse_incoming_message(data)
    if msg is None:
        return {"status": "ok"}
    background_tasks.add_task(
        process_message,
        phone_number=msg["phone_number"],
        user_name=msg["name"],
        message_text=msg["message_text"],
        db=db,
    )
    return {"status": "ok"}


# ── Procesamiento principal ───────────────────────────────────────

async def process_message(
    phone_number: str,
    user_name: str,
    message_text: str,
    db: Session,
):
    start = time.time()
    print(f"\n  📨  [{phone_number}] {user_name}: {message_text[:80]}")

    try:
        # 1. Guardar mensaje del usuario
        db.add(Conversation(
            phone_number=phone_number,
            user_name=user_name,
            role="user",
            message=message_text,
        ))
        db.commit()

        # 2. Limpiar historial viejo
        _trim_history(db, phone_number)

        # 3. Verificar sesión activa de domicilio
        #    PRIORIDAD: si hay sesión activa, SIEMPRE va al flujo de domicilio
        session = get_or_create_session(db, phone_number)
        in_delivery_flow = session.step != "idle"

        response_text = None

        if in_delivery_flow:
            # Sesión activa → flujo de domicilio siempre
            response_text = await handle_delivery_message(
                db=db,
                phone_number=phone_number,
                user_name=user_name,
                message=message_text,
            )

        elif is_order_status_question(message_text):
            # 4. El cliente pregunta sobre su pedido pero la sesión ya está idle
            #    (puede pasar si el local aceptó y el cliente pregunta después)
            #    Buscamos el último pedido activo o reciente
            active_order = _get_recent_order(db, phone_number)
            active_order_context = _build_order_context(active_order) if active_order else ""

            records = _get_history(db, phone_number)
            history = [{"role": r.role, "content": r.message} for r in reversed(records)]
            profile = db.query(UserProfile).filter(
                UserProfile.phone_number == phone_number
            ).first()
            profile_text = profile.to_context_string() if profile else ""

            response_text = await generate_response(
                user_message=message_text,
                user_name=user_name,
                conversation_history=history,
                user_profile=profile_text,
                active_order_context=active_order_context,
            )

        elif is_delivery_intent(message_text):
            # 5. Quiere iniciar un nuevo pedido
            response_text = await handle_delivery_message(
                db=db,
                phone_number=phone_number,
                user_name=user_name,
                message=message_text,
            )

        else:
            # 6. Flujo normal de IA — consulta general del mall
            records = _get_history(db, phone_number)
            history = [{"role": r.role, "content": r.message} for r in reversed(records)]
            profile = db.query(UserProfile).filter(
                UserProfile.phone_number == phone_number
            ).first()
            profile_text = profile.to_context_string() if profile else ""

            response_text = await generate_response(
                user_message=message_text,
                user_name=user_name,
                conversation_history=history,
                user_profile=profile_text,
            )

        # 7. Guardar respuesta y enviar
        db.add(Conversation(
            phone_number=phone_number,
            user_name=user_name,
            role="assistant",
            message=response_text,
        ))
        db.commit()

        elapsed = round(time.time() - start, 2)
        print(f"  🤖  Bot ({elapsed}s): {response_text[:80]}")

        await send_text_message(to=phone_number, message=response_text)

    except Exception as e:
        logger.error(f"Error procesando mensaje de {phone_number}: {str(e)}", exc_info=True)
        await send_text_message(
            to=phone_number,
            message="Uy, algo salió mal de mi parte 😅 ¿Puedes intentarlo de nuevo?",
        )


# ── Helpers ───────────────────────────────────────────────────────

def _get_history(db: Session, phone_number: str):
    return (
        db.query(Conversation)
        .filter(Conversation.phone_number == phone_number)
        .order_by(Conversation.timestamp.desc())
        .limit(12)
        .all()
    )


def _get_recent_order(db: Session, phone_number: str) -> Order | None:
    """
    Busca el pedido más reciente del cliente que no esté terminado,
    o el último que haya tenido (para responder 'ya fue entregado').
    """
    # Primero intentar pedido activo
    terminal = {OrderStatus.DELIVERED, OrderStatus.CANCELLED}
    active = (
        db.query(Order)
        .filter(
            Order.client_phone == phone_number,
            Order.status.notin_(terminal),
        )
        .order_by(Order.created_at.desc())
        .first()
    )
    if active:
        return active

    # Si no hay activo, buscar el más reciente (para responder sobre entregados)
    return (
        db.query(Order)
        .filter(Order.client_phone == phone_number)
        .order_by(Order.created_at.desc())
        .first()
    )


def _build_order_context(order: Order) -> str:
    """Construye el texto de contexto del pedido para inyectar al AI."""
    status_labels = {
        OrderStatus.PENDING:    "Pendiente — esperando que el local lo acepte",
        OrderStatus.ACCEPTED:   "Aceptado — el local lo confirmó",
        OrderStatus.PREPARING:  "En preparación — lo están haciendo",
        OrderStatus.READY:      "Listo — por salir a domicilio",
        OrderStatus.ON_THE_WAY: "En camino — ya salió a domicilio",
        OrderStatus.DELIVERED:  "Entregado",
        OrderStatus.CANCELLED:  "Cancelado",
    }

    lines = [
        f"Número de pedido: {order.order_number}",
        f"Local: {order.store_name}",
        f"Estado actual: {status_labels.get(order.status, order.status)}",
        f"Dirección: {order.delivery_address}",
        f"Pago: {order.payment_method or 'No especificado'}",
    ]
    if order.delivery_time_minutes:
        lines.append(f"Tiempo estimado: {order.delivery_time_minutes} minutos")
    if order.total and order.total > 5000:
        lines.append(f"Total: ${order.total:,.0f} COP")
    if order.store_message:
        lines.append(f"Mensaje del local: {order.store_message}")

    return "\n".join(lines)


def _trim_history(db: Session, phone_number: str):
    total = db.query(Conversation).filter(
        Conversation.phone_number == phone_number
    ).count()
    if total > MAX_HISTORY_PER_USER:
        excess = total - MAX_HISTORY_PER_USER
        oldest_ids = (
            db.query(Conversation.id)
            .filter(Conversation.phone_number == phone_number)
            .order_by(Conversation.timestamp.asc())
            .limit(excess)
            .all()
        )
        ids_to_delete = [r.id for r in oldest_ids]
        db.query(Conversation).filter(Conversation.id.in_(ids_to_delete)).delete(
            synchronize_session=False
        )
        db.commit()


# ── Endpoint de prueba ────────────────────────────────────────────

@router.post("/test")
async def test_bot(request: Request, db: Session = Depends(get_db)):
    start        = time.time()
    data         = await request.json()
    message_text = data.get("message", "")
    phone_number = data.get("phone", "test_user")
    user_name    = data.get("name", "Tester")

    if not message_text:
        return {"error": "El campo message es requerido"}

    print(f"\n  📨  [{phone_number}] {user_name}: {message_text[:80]}")

    db.add(Conversation(
        phone_number=phone_number,
        user_name=user_name,
        role="user",
        message=message_text,
    ))
    db.commit()
    _trim_history(db, phone_number)

    session = get_or_create_session(db, phone_number)
    in_delivery_flow = session.step != "idle"

    active_order_context = ""

    if in_delivery_flow:
        response_text = await handle_delivery_message(
            db=db,
            phone_number=phone_number,
            user_name=user_name,
            message=message_text,
        )
    elif is_order_status_question(message_text):
        active_order = _get_recent_order(db, phone_number)
        active_order_context = _build_order_context(active_order) if active_order else ""
        records = _get_history(db, phone_number)
        history = [{"role": r.role, "content": r.message} for r in reversed(records)]
        response_text = await generate_response(
            user_message=message_text,
            user_name=user_name,
            conversation_history=history,
            active_order_context=active_order_context,
        )
    elif is_delivery_intent(message_text):
        response_text = await handle_delivery_message(
            db=db,
            phone_number=phone_number,
            user_name=user_name,
            message=message_text,
        )
    else:
        records = _get_history(db, phone_number)
        history = [{"role": r.role, "content": r.message} for r in reversed(records)]
        profile = db.query(UserProfile).filter(
            UserProfile.phone_number == phone_number
        ).first()
        profile_text = profile.to_context_string() if profile else ""
        response_text = await generate_response(
            user_message=message_text,
            user_name=user_name,
            conversation_history=history,
            user_profile=profile_text,
        )

    db.add(Conversation(
        phone_number=phone_number,
        user_name=user_name,
        role="assistant",
        message=response_text,
    ))
    db.commit()

    elapsed = round(time.time() - start, 2)
    print(f"  🤖  Bot ({elapsed}s): {response_text[:80]}")

    return {
        "user":                message_text,
        "bot":                 response_text,
        "phone":               phone_number,
        "delivery_step":       session.step,
        "active_order_ctx":    active_order_context[:100] if active_order_context else None,
        "time_seconds":        elapsed,
    }


@router.delete("/history/{phone}")
async def clear_history(phone: str, db: Session = Depends(get_db)):
    db.query(Conversation).filter(Conversation.phone_number == phone).delete()
    session = db.query(DeliverySession).filter(
        DeliverySession.phone_number == phone
    ).first()
    if session:
        session.reset()
    db.commit()
    print(f"  🗑️   Historial de {phone} eliminado")
    return {"message": f"Historial de {phone} eliminado"}