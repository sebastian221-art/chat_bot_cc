# 📄 ARCHIVO: backend/routers/webhook.py
"""
Webhook de WhatsApp + test endpoint.

CAMBIOS DE ESTA VERSIÓN:
  - Domicilios: el bot ya NO gestiona el pedido completo. Detecta la
    tienda mencionada y transfiere al cliente al WhatsApp de esa tienda
    (ver services/store_transfer.py). El flujo viejo de
    services/delivery_flow.py queda sin usarse (no se borró, por si
    se retoma en el futuro).
  - Escalamiento humano: si el mensaje dispara una palabra de alerta
    (ver ai.needs_human_attention), la conversación queda marcada en
    ConversationFlag para que el panel la resalte.
  - Pausa del bot: si un admin respondió manualmente desde el panel,
    el bot deja de responder automático a ese número por un rato
    (ver ConversationFlag.bot_paused_until), para no chocar con el humano.
"""
import logging
import time
from datetime import datetime, timezone
from fastapi import APIRouter, Request, Response, Depends, BackgroundTasks
from sqlalchemy.orm import Session

from config import get_settings
from models.database import get_db, SessionLocal
from models.conversation import Conversation
from models.user_profile import UserProfile
from models.conversation_flag import ConversationFlag
from services.whatsapp import send_text_message, parse_incoming_message
from services.ai import generate_response, is_delivery_intent, needs_human_attention, build_handoff_message
from services.store_transfer import (
    find_store_by_message,
    build_transfer_message,
    build_ask_which_store_message,
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
):
    data = await request.json()
    msg  = parse_incoming_message(data)
    if msg is None:
        return {"status": "ok"}
    # OJO: NO le pasamos la sesión de esta petición web a la tarea en
    # segundo plano — esa sesión puede quedar cerrada por FastAPI antes
    # de que la tarea corra, causando lecturas inconsistentes (ej. la
    # pausa del bot no se respetaba). process_message crea su propia
    # sesión nueva, fresca, independiente del ciclo de vida de esta
    # petición HTTP.
    background_tasks.add_task(
        process_message,
        phone_number=msg["phone_number"],
        user_name=msg["name"],
        message_text=msg["message_text"],
    )
    return {"status": "ok"}


# ── Núcleo compartido: decide qué responder ────────────────────────

async def _route_message(db: Session, phone_number: str, user_name: str, message_text: str) -> str:
    """
    Decide y genera la respuesta del bot para un mensaje entrante.
    Compartido entre el webhook real y el endpoint /test para que
    ambos se comporten exactamente igual.
    """
    if is_delivery_intent(message_text):
        store = find_store_by_message(db, message_text)
        if store:
            return build_transfer_message(store)
        return build_ask_which_store_message()

    # También intenta resolver tienda si el mensaje anterior fue
    # "¿de qué tienda quieres pedir?" y ahora el cliente solo dice el nombre
    store = find_store_by_message(db, message_text)
    if store and _last_bot_message_was_ask(db, phone_number):
        return build_transfer_message(store)

    records = _get_history(db, phone_number)
    history = [
        {"role": "assistant" if r.role == "admin" else r.role, "content": r.message}
        for r in reversed(records)
    ]
    profile = db.query(UserProfile).filter(UserProfile.phone_number == phone_number).first()
    profile_text = profile.to_context_string() if profile else ""

    return await generate_response(
        user_message=message_text,
        user_name=user_name,
        conversation_history=history,
        user_profile=profile_text,
    )


def _last_bot_message_was_ask(db: Session, phone_number: str) -> bool:
    last = (
        db.query(Conversation)
        .filter(Conversation.phone_number == phone_number, Conversation.role.in_(["assistant", "admin"]))
        .order_by(Conversation.timestamp.desc())
        .first()
    )
    if not last:
        return False
    return "de qué tienda" in last.message.lower() or "qué restaurante" in last.message.lower()


def _is_bot_paused(db: Session, phone_number: str) -> bool:
    flag = db.query(ConversationFlag).filter(ConversationFlag.phone_number == phone_number).first()
    if not flag or not flag.bot_paused_until:
        return False
    now = datetime.now(timezone.utc)
    paused_until = flag.bot_paused_until
    if paused_until.tzinfo is None:
        paused_until = paused_until.replace(tzinfo=timezone.utc)
    result = now < paused_until
    print(f"  🔎  [{phone_number}] Chequeo de pausa — ahora: {now.isoformat()} | pausado hasta: {paused_until.isoformat()} | ¿pausado?: {result}")
    return result


def _flag_if_needs_human(db: Session, phone_number: str, message_text: str) -> bool:
    """Marca la conversación si corresponde. Devuelve True si se activó el escalamiento."""
    escalate, reason = needs_human_attention(message_text)
    if not escalate:
        return False
    flag = db.query(ConversationFlag).filter(ConversationFlag.phone_number == phone_number).first()
    if not flag:
        flag = ConversationFlag(phone_number=phone_number)
        db.add(flag)
    flag.needs_human = True
    flag.reason = reason
    db.commit()
    print(f"  🆘  [{phone_number}] Escalado a humano (\"{reason}\") — se responde con mensaje de transferencia, sin pasar por la IA")
    return True


# ── Procesamiento principal ───────────────────────────────────────

async def process_message(
    phone_number: str,
    user_name: str,
    message_text: str,
):
    start = time.time()
    print(f"\n  📨  [{phone_number}] {user_name}: {message_text[:80]}")

    db = SessionLocal()
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

        # 3. Si el mensaje amerita atención humana, responde con el
        #    mensaje de transferencia directo — SIN pasar por la IA
        #    (para no arriesgarnos a que improvise datos falsos).
        escalated = _flag_if_needs_human(db, phone_number, message_text)

        # 4. Si el bot está en pausa para este número (un admin lo está
        #    atendiendo manualmente), NO respondemos automático.
        if _is_bot_paused(db, phone_number):
            print(f"  ⏸️   [{phone_number}] Bot en pausa — un admin lo está atendiendo, no se autoresponde")
            return

        # 5. Generar respuesta
        if escalated:
            response_text = build_handoff_message(user_name)
        else:
            response_text = await _route_message(db, phone_number, user_name, message_text)

        # 6. Guardar respuesta y enviar
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
    finally:
        db.close()


# ── Helpers ───────────────────────────────────────────────────────

def _get_history(db: Session, phone_number: str):
    return (
        db.query(Conversation)
        .filter(Conversation.phone_number == phone_number)
        .order_by(Conversation.timestamp.desc())
        .limit(12)
        .all()
    )


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

    escalated = _flag_if_needs_human(db, phone_number, message_text)

    paused = _is_bot_paused(db, phone_number)
    if paused:
        return {
            "user": message_text,
            "bot": None,
            "phone": phone_number,
            "note": "Bot en pausa para este número — un admin lo está atendiendo manualmente.",
            "time_seconds": round(time.time() - start, 2),
        }

    if escalated:
        response_text = build_handoff_message(user_name)
    else:
        response_text = await _route_message(db, phone_number, user_name, message_text)

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
        "user":         message_text,
        "bot":          response_text,
        "phone":        phone_number,
        "time_seconds": elapsed,
    }


@router.delete("/history/{phone}")
async def clear_history(phone: str, db: Session = Depends(get_db)):
    db.query(Conversation).filter(Conversation.phone_number == phone).delete()
    flag = db.query(ConversationFlag).filter(ConversationFlag.phone_number == phone).first()
    if flag:
        db.delete(flag)
    db.commit()
    print(f"  🗑️   Historial de {phone} eliminado")
    return {"message": f"Historial de {phone} eliminado"}