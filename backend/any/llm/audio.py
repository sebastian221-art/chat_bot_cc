"""
Notas de voz de WhatsApp → texto (Whisper en Groq).

Privacidad: el audio NUNCA se guarda. Se descarga de Meta a la memoria, se manda a transcribir, y la variable
se descarta en cuanto llega el texto. No se escribe en disco, ni en la base de datos, ni en los logs. Lo único
que queda es el TEXTO de lo que dijo el cliente, igual que si lo hubiera escrito (para responderle y para que
aparezca en Conversaciones del panel).
"""
from __future__ import annotations

import logging
import os

import httpx

log = logging.getLogger("any.audio")

URL = "https://api.groq.com/openai/v1/audio/transcriptions"
MODELO = os.environ.get("ANY_MODELO_AUDIO", "whisper-large-v3-turbo")
MAX_BYTES = 8 * 1024 * 1024          # ~8 MB: varios minutos de nota de voz; más largo se pide escribirlo


class AudioMuyLargo(Exception):
    pass


async def transcribir(audio: bytes, mime: str = "audio/ogg") -> str | None:
    """Texto de la nota de voz, o None si no se pudo. El audio solo vive en memoria durante esta llamada."""
    if not audio:
        return None
    if len(audio) > MAX_BYTES:
        raise AudioMuyLargo()
    ext = "ogg" if "ogg" in (mime or "") else ("mp3" if "mpeg" in (mime or "") else ("m4a" if "mp4" in (mime or "") else "ogg"))
    clave = os.environ.get("GROQ_API_KEY", "")
    try:
        async with httpx.AsyncClient(timeout=40.0) as client:
            r = await client.post(URL, headers={"Authorization": f"Bearer {clave}"},
                                  data={"model": MODELO, "language": "es", "response_format": "json", "temperature": "0"},
                                  files={"file": (f"nota_de_voz.{ext}", audio, mime or "audio/ogg")})
            r.raise_for_status()
            texto = (r.json().get("text") or "").strip()
            return texto or None
    except Exception as e:      # el detalle del error, nunca el audio
        log.warning("No se pudo transcribir la nota de voz: %s", str(e)[:200])
        return None
    finally:
        del audio