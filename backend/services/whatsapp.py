import httpx
import logging
from config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

WHATSAPP_API_URL = "https://graph.facebook.com/v19.0"


async def send_text_message(to: str, message: str) -> bool:
    url = f"{WHATSAPP_API_URL}/{settings.WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"preview_url": False, "body": message},
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            logger.info(f"Mensaje enviado a {to}")
            return True
        except httpx.HTTPStatusError as e:
            logger.error(f"Error HTTP enviando a {to}: {e.response.text}")
            return False
        except Exception as e:
            logger.error(f"Error inesperado enviando a {to}: {str(e)}")
            return False


def parse_incoming_message(data: dict) -> dict | None:
    try:
        entry   = data["entry"][0]
        value   = entry["changes"][0]["value"]

        if "messages" not in value:
            return None

        message = value["messages"][0]

        # Fase 1: solo texto. Fase 2 se agrega imágenes
        if message.get("type") != "text":
            return None

        contacts = value.get("contacts", [{}])
        profile  = contacts[0].get("profile", {}) if contacts else {}

        return {
            "phone_number": message["from"],
            "name":         profile.get("name", "Usuario"),
            "message_text": message["text"]["body"],
            "message_id":   message["id"],
        }
    except (KeyError, IndexError) as e:
        logger.warning(f"No se pudo parsear mensaje: {str(e)}")
        return None