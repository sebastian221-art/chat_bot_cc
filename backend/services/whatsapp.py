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


async def send_image_message(to: str, image_url: str, caption: str = "") -> bool:
    """
    Manda una imagen por WhatsApp usando un link público (no un archivo
    subido) — así funciona directo con el `photo_url` que el admin pega
    en el panel, sin necesitar guardar archivos en el servidor.
    """
    url = f"{WHATSAPP_API_URL}/{settings.WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "image",
        "image": {"link": image_url, "caption": caption[:1024] if caption else ""},
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            logger.info(f"Imagen enviada a {to}")
            return True
        except httpx.HTTPStatusError as e:
            logger.error(f"Error HTTP enviando imagen a {to}: {e.response.text}")
            return False
        except Exception as e:
            logger.error(f"Error inesperado enviando imagen a {to}: {str(e)}")
            return False


async def send_location_message(to: str, latitude: float, longitude: float, name: str = "", address: str = "") -> bool:
    """
    Manda una ubicación real de WhatsApp — aparece como un pin de mapa
    que el cliente puede tocar para abrir Google Maps/Waze directo con
    la ruta ya armada. Se usa cuando preguntan dónde queda el mall.
    """
    url = f"{WHATSAPP_API_URL}/{settings.WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "location",
        "location": {
            "latitude": latitude,
            "longitude": longitude,
            "name": name,
            "address": address,
        },
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            logger.info(f"Ubicación enviada a {to}")
            return True
        except httpx.HTTPStatusError as e:
            logger.error(f"Error HTTP enviando ubicación a {to}: {e.response.text}")
            return False
        except Exception as e:
            logger.error(f"Error inesperado enviando ubicación a {to}: {str(e)}")
            return False


def parse_incoming_message(data: dict) -> dict | None:
    try:
        entry   = data["entry"][0]
        value   = entry["changes"][0]["value"]

        if "messages" not in value:
            return None

        message = value["messages"][0]
        contacts = value.get("contacts", [{}])
        profile  = contacts[0].get("profile", {}) if contacts else {}

        base = {
            "phone_number": message["from"],
            "name":         profile.get("name", "Usuario"),
            "message_id":   message["id"],
        }

        if message.get("type") == "text":
            return {
                **base,
                "message_type": "text",
                "message_text": message["text"]["body"],
            }

        if message.get("type") == "image":
            image = message.get("image", {})
            return {
                **base,
                "message_type": "image",
                "media_id":     image.get("id"),
                "mime_type":    image.get("mime_type", "image/jpeg"),
                "caption":      image.get("caption", ""),
            }

        # Otros tipos (audio, documento, ubicación, etc.) — no soportados aún
        return None

    except (KeyError, IndexError) as e:
        logger.warning(f"No se pudo parsear mensaje: {str(e)}")
        return None


async def download_media(media_id: str) -> bytes | None:
    """
    Descarga una imagen de WhatsApp. Meta requiere 2 pasos:
    1) Consultar el media_id para obtener una URL temporal firmada
    2) Descargar el binario de esa URL (también requiere el token)
    """
    headers = {"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"}
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            meta_resp = await client.get(f"{WHATSAPP_API_URL}/{media_id}", headers=headers)
            meta_resp.raise_for_status()
            media_url = meta_resp.json().get("url")
            if not media_url:
                logger.error(f"No se encontró URL de descarga para media_id={media_id}")
                return None

            file_resp = await client.get(media_url, headers=headers)
            file_resp.raise_for_status()
            return file_resp.content

        except httpx.HTTPStatusError as e:
            logger.error(f"Error HTTP descargando media {media_id}: {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Error inesperado descargando media {media_id}: {str(e)}")
            return None