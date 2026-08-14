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
from models.delivery_transfer import DeliveryTransfer
from models.delivery_management import DeliveryManagement
from models.mall_info import MallInfo
from services.whatsapp import send_text_message, send_image_message, send_location_message, parse_incoming_message, download_media
from services.ai import generate_response, is_delivery_intent, is_delivery_management_intent, needs_human_attention, build_handoff_message, classify_intent
from services.vision_search import handle_image_message
from services.content_matching import find_event_by_message, find_raffle_by_message
from services.delivery_management import get_active_session, start_management, continue_management
from services.navigation import (
    parse_zone_code,
    find_zone,
    log_zone_scan,
    get_last_scanned_zone,
    build_zone_not_found_message,
    build_zone_confirmation_message,
    build_navigation_response,
)
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
    background_tasks.add_task(process_message, msg=msg)
    return {"status": "ok"}


# ── Núcleo compartido: decide qué responder ────────────────────────

CARTA_KEYWORDS = ["carta", "menú", "menu", "qué tienen", "que tienen", "qué venden", "que venden"]
PREMIO_KEYWORDS = ["premio", "qué me gano", "que me gano", "qué es el premio", "que es el premio"]


def _pick_store_photo(store, message_text: str) -> str | None:
    """Decide cuál foto de la galería de una tienda mandar: carta si preguntan por el menú, portada en cualquier otro caso."""
    if not store:
        return None
    msg = message_text.lower()
    if any(k in msg for k in CARTA_KEYWORDS):
        return store.get_photo_by_label("carta")
    return store.get_photo_by_label("portada")


def _pick_entity_photo(db, entity_type: str, entity_id: int, message_text: str) -> str | None:
    """Igual que _pick_store_photo, pero para eventos/sorteos/zonas usando la tabla genérica."""
    from models.entity_photo import get_entity_photo
    msg = message_text.lower()
    if entity_type == "raffle" and any(k in msg for k in PREMIO_KEYWORDS):
        return get_entity_photo(db, "raffle", entity_id, "premio")
    default_label = "afiche" if entity_type in ("event", "raffle") else "principal"
    return get_entity_photo(db, entity_type, entity_id, default_label)


def _find_recently_discussed_store(db, phone_number: str, current_store):
    """
    Si el mensaje actual no menciona ninguna tienda por nombre (ej. un
    seguimiento como "¿tienes una foto?" sin repetir de cuál tienda),
    busca en los últimos mensajes cuál se estaba discutiendo — así la
    foto que se manda sigue coincidiendo con el tema real de la
    conversación, igual que ya hace el texto de la IA (que sí ve el
    historial completo).
    """
    if current_store:
        return current_store
    recent = (
        db.query(Conversation)
        .filter(Conversation.phone_number == phone_number)
        .order_by(Conversation.timestamp.desc())
        .limit(6)
        .all()
    )
    for r in recent:
        s = find_store_by_message(db, r.message)
        if s:
            return s
    return None


async def _route_message(db: Session, phone_number: str, user_name: str, message_text: str) -> dict:
    """
    Decide y genera la respuesta del bot para un mensaje entrante.
    Compartido entre el webhook real y el endpoint /test para que
    ambos se comporten exactamente igual.

    Devuelve {"text": ..., "image_url": ..., "location": ...} — según
    el caso, además del texto puede venir una foto (tienda/zona/evento/
    sorteo con foto cargada) o un pin de ubicación real (cuando
    preguntan dónde queda el mall en sí, no una tienda puntual).
    """
    # ── Navegación QR indoor ────────────────────────────────────────
    # Prioridad más alta: si el mensaje trae un código de zona (viene
    # de un QR físico escaneado), lo atendemos primero que cualquier
    # otra cosa — es la señal más específica que puede traer un mensaje.
    zone_code = parse_zone_code(message_text)
    if zone_code:
        log_zone_scan(db, phone_number, zone_code)  # se registra SIEMPRE, exista o no la zona
        zone = find_zone(db, zone_code)
        if not zone:
            return {"text": build_zone_not_found_message(), "image_url": None, "location": None}

        store = find_store_by_message(db, message_text)
        zone_photo = _pick_entity_photo(db, "zone", zone.id, message_text)
        if store:
            text = await build_navigation_response(zone, store, user_name)
            return {"text": text, "image_url": _pick_store_photo(store, message_text) or zone_photo, "location": None}
        return {"text": build_zone_confirmation_message(zone), "image_url": zone_photo, "location": None}

    # Si el mensaje anterior fue "¿a qué tienda quieres llegar?" (después
    # de escanear un QR), usamos la última zona escaneada por este número
    # + el nombre de tienda que acaba de mandar ahora.
    store = find_store_by_message(db, message_text)
    if store and _last_bot_message_was_zone_ask(db, phone_number):
        last_zone = get_last_scanned_zone(db, phone_number)
        if last_zone:
            text = await build_navigation_response(last_zone, store, user_name)
            zone_photo = _pick_entity_photo(db, "zone", last_zone.id, message_text)
            return {"text": text, "image_url": _pick_store_photo(store, message_text) or zone_photo, "location": None}

    # ── Gestión completa de domicilio ────────────────────────────────
    # Prioridad alta: si ya hay una gestión en curso para este número,
    # este mensaje trae (parte de) los datos que faltaban — se procesa
    # como continuación, sin importar qué otra cosa parezca el mensaje.
    active_session = get_active_session(db, phone_number)
    if active_session:
        text = await continue_management(db, active_session, message_text, store, user_name)
        img = _pick_store_photo(store, message_text)
        return {"text": text, "image_url": img, "location": None}

    # Si no hay sesión activa pero el cliente pide EXPLÍCITAMENTE que se
    # le ayude a gestionar el pedido (no solo lo menciona de pasada),
    # arrancamos el flujo completo — carta + validación de horario + datos.
    if is_delivery_management_intent(message_text):
        if store:
            text = await start_management(db, phone_number, store)
            # Aquí forzamos la etiqueta "carta" — es exactamente el
            # momento en que se le muestra el menú al cliente.
            photo = store.get_photo_by_label("carta")
            return {"text": text, "image_url": photo, "location": None}
        return {"text": build_ask_which_store_message(), "image_url": None, "location": None}

    if is_delivery_intent(message_text):
        if store:
            _log_delivery_transfer(db, phone_number, store.name)
            return {"text": build_transfer_message(store), "image_url": _pick_store_photo(store, message_text), "location": None}
        return {"text": build_ask_which_store_message(), "image_url": None, "location": None}

    # También intenta resolver tienda si el mensaje anterior fue
    # "¿de qué tienda quieres pedir?" y ahora el cliente solo dice el nombre
    if store and _last_bot_message_was_ask(db, phone_number):
        _log_delivery_transfer(db, phone_number, store.name)
        return {"text": build_transfer_message(store), "image_url": _pick_store_photo(store, message_text), "location": None}

    # ── Ubicación del mall en sí (no de una tienda puntual) ──────────
    # Si preguntan "dónde queda" sin mencionar una tienda específica,
    # asumimos que preguntan por el mall — mandamos texto + pin real.
    location_data = None
    if classify_intent(message_text) == "ubicacion" and not store:
        mall_info = db.query(MallInfo).filter(MallInfo.id == 1).first()
        if mall_info and mall_info.latitude and mall_info.longitude:
            try:
                location_data = {
                    "latitude": float(mall_info.latitude),
                    "longitude": float(mall_info.longitude),
                    "name": mall_info.name,
                    "address": mall_info.address or "",
                }
            except ValueError:
                location_data = None

    records = _get_history(db, phone_number)
    history = [
        {"role": "assistant" if r.role == "admin" else r.role, "content": r.message}
        for r in reversed(records)
    ]
    profile = db.query(UserProfile).filter(UserProfile.phone_number == phone_number).first()
    profile_text = profile.to_context_string() if profile else ""

    text = await generate_response(
        user_message=message_text,
        user_name=user_name,
        conversation_history=history,
        user_profile=profile_text,
        db=db,
    )

    # Si el cliente mencionó una tienda, evento o sorteo específico y
    # tiene foto cargada en el panel, la mandamos junto con la respuesta
    # — usando la etiqueta correcta según lo que haya preguntado
    # (ej. "premio" si pregunta qué se gana en un sorteo). Si el mensaje
    # actual no menciona ninguna tienda (ej. "¿tienes una foto?" como
    # seguimiento), buscamos en los últimos mensajes cuál se discutía.
    image_url = None
    photo_store = _find_recently_discussed_store(db, phone_number, store)
    if photo_store:
        image_url = _pick_store_photo(photo_store, message_text)
    if not image_url:
        event = find_event_by_message(db, message_text)
        if event:
            image_url = _pick_entity_photo(db, "event", event.id, message_text)
        else:
            raffle = find_raffle_by_message(db, message_text)
            if raffle:
                image_url = _pick_entity_photo(db, "raffle", raffle.id, message_text)

    return {"text": text, "image_url": image_url, "location": location_data}


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


def _last_bot_message_was_zone_ask(db: Session, phone_number: str) -> bool:
    last = (
        db.query(Conversation)
        .filter(Conversation.phone_number == phone_number, Conversation.role.in_(["assistant", "admin"]))
        .order_by(Conversation.timestamp.desc())
        .first()
    )
    if not last:
        return False
    return "a qué tienda o local quieres llegar" in last.message.lower()


def _log_delivery_transfer(db: Session, phone_number: str, store_name: str):
    """
    Registra cada vez que transferimos exitosamente a un cliente al
    WhatsApp de una tienda para su domicilio. Como ya no gestionamos
    el pedido completo, esto es lo que alimenta el panel de
    "Domicilios" y los reportes — no sabemos si se concretó la venta,
    pero sí sabemos que la conexión se hizo.
    """
    db.add(DeliveryTransfer(phone_number=phone_number, store_name=store_name))
    db.commit()


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

async def process_message(msg: dict):
    phone_number = msg["phone_number"]
    user_name    = msg["name"]
    message_type = msg.get("message_type", "text")

    start = time.time()

    db = SessionLocal()
    try:
        if message_type == "image":
            await _process_image_message(db, phone_number, user_name, msg, start)
        else:
            await _process_text_message(db, phone_number, user_name, msg["message_text"], start)

    except Exception as e:
        logger.error(f"Error procesando mensaje de {phone_number}: {str(e)}", exc_info=True)
        await send_text_message(
            to=phone_number,
            message="Uy, algo salió mal de mi parte 😅 ¿Puedes intentarlo de nuevo?",
        )
    finally:
        db.close()


async def _process_text_message(db: Session, phone_number: str, user_name: str, message_text: str, start: float):
    print(f"\n  📨  [{phone_number}] {user_name}: {message_text[:80]}")

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
    image_url = None
    location_data = None
    if escalated:
        response_text = build_handoff_message(user_name)
    else:
        result = await _route_message(db, phone_number, user_name, message_text)
        response_text = result["text"]
        image_url = result["image_url"]
        location_data = result["location"]

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
    if image_url:
        await send_image_message(to=phone_number, image_url=image_url)
        print(f"  🖼️   Foto enviada: {image_url}")
    if location_data:
        await send_location_message(to=phone_number, **location_data)
        print(f"  📍  Ubicación enviada: {location_data['name']}")


async def _process_image_message(db: Session, phone_number: str, user_name: str, msg: dict, start: float):
    caption = msg.get("caption", "")
    print(f"\n  📸  [{phone_number}] {user_name}: [foto]{f' con texto: {caption}' if caption else ''}")

    # 1. Guardar un registro del mensaje (no tenemos el texto, guardamos una nota)
    placeholder = f"[Foto enviada]{f' — {caption}' if caption else ''}"
    db.add(Conversation(
        phone_number=phone_number,
        user_name=user_name,
        role="user",
        message=placeholder,
    ))
    db.commit()
    _trim_history(db, phone_number)

    # 2. Si el bot está pausado (admin atendiendo), no respondemos
    if _is_bot_paused(db, phone_number):
        print(f"  ⏸️   [{phone_number}] Bot en pausa — no se autoresponde a la foto")
        return

    # 3. Descargar la imagen desde Meta
    image_bytes = await download_media(msg["media_id"])
    if not image_bytes:
        response_text = (
            "No pude descargar tu foto 😅 ¿Puedes intentar mandarla de nuevo? "
            "Si sigue sin funcionar, cuéntame con palabras qué buscas."
        )
    else:
        records = _get_history(db, phone_number)
        history = [
            {"role": "assistant" if r.role == "admin" else r.role, "content": r.message}
            for r in reversed(records)
        ]
        response_text = await handle_image_message(
            user_name=user_name,
            image_bytes=image_bytes,
            mime_type=msg.get("mime_type", "image/jpeg"),
            caption=caption,
            conversation_history=history,
        )

    # 4. Guardar respuesta y enviar
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

    image_url = None
    location_data = None
    if escalated:
        response_text = build_handoff_message(user_name)
    else:
        result = await _route_message(db, phone_number, user_name, message_text)
        response_text = result["text"]
        image_url = result["image_url"]
        location_data = result["location"]

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
        "image_url":    image_url,
        "location":     location_data,
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