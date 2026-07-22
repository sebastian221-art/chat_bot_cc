"""
services/profiling.py  ← NUEVO archivo
Job que se ejecuta cada 7 días para resumir conversaciones
y construir el perfil de cada usuario usando Groq.
Se llama desde main.py en el startup y puede schedularse con un cron.
"""
import logging
from datetime import datetime, timedelta
from groq import AsyncGroq
from sqlalchemy.orm import Session
from models.conversation import Conversation
from models.user_profile import UserProfile
from config import get_settings
from services.analytics import KNOWN_STORES, CATEGORY_KEYWORDS

settings = get_settings()
logger   = logging.getLogger("mall_bot")

_groq_client = None

def _get_client() -> AsyncGroq:
    global _groq_client
    if _groq_client is None:
        _groq_client = AsyncGroq(api_key=settings.GROQ_API_KEY)
    return _groq_client


PROFILE_PROMPT = """Eres un analista de datos de un centro comercial.
Analiza esta conversación de un cliente con el chatbot del mall y genera un perfil conciso.

Responde SOLO con este JSON (sin markdown, sin explicaciones):
{
  "summary": "1-2 frases describiendo al usuario y sus intereses principales",
  "interests": "lista separada por comas de sus intereses (máx 5)",
  "fav_stores": "tiendas que mencionó o consultó, separadas por comas (máx 3)",
  "visit_freq": "ocasional | regular | frecuente"
}

CONVERSACIÓN:
"""


async def profile_user(
    db: Session,
    phone_number: str,
    force: bool = False,
) -> UserProfile | None:
    """
    Genera o actualiza el perfil de un usuario.
    Solo se ejecuta si no fue perfilado en los últimos 7 días (a menos que force=True).
    """
    import json

    # Buscar perfil existente
    profile = db.query(UserProfile).filter(
        UserProfile.phone_number == phone_number
    ).first()

    # Verificar si necesita actualización
    if profile and not force:
        if profile.last_profiled:
            days_since = (datetime.utcnow() - profile.last_profiled).days
            if days_since < 7:
                return profile

    # Cargar últimas 60 conversaciones del usuario
    records = (
        db.query(Conversation)
        .filter(Conversation.phone_number == phone_number)
        .order_by(Conversation.timestamp.desc())
        .limit(60)
        .all()
    )

    if len(records) < 3:
        return None  # No hay suficiente historial

    # Formatear conversación
    conv_text = "\n".join(
        f"{'Usuario' if r.role == 'user' else 'Bot'}: {r.message}"
        for r in reversed(records)
    )

    try:
        client = _get_client()
        completion = await client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[
                {"role": "system", "content": PROFILE_PROMPT + conv_text},
                {"role": "user", "content": "Genera el perfil JSON."},
            ],
            max_tokens=200,
            temperature=0.3,
        )

        raw = completion.choices[0].message.content.strip()
        # Limpiar posibles backticks
        raw = raw.replace("```json", "").replace("```", "").strip()
        data = json.loads(raw)

        # Crear o actualizar perfil
        if not profile:
            profile = UserProfile(
                phone_number=phone_number,
                user_name=records[-1].user_name if records else None,
            )
            db.add(profile)

        profile.summary      = data.get("summary", "")
        profile.interests    = data.get("interests", "")
        profile.fav_stores   = data.get("fav_stores", "")
        profile.visit_freq   = data.get("visit_freq", "ocasional")
        profile.total_msgs   = len(records)
        profile.last_profiled = datetime.utcnow()

        db.commit()
        db.refresh(profile)
        print(f"  🧠  Perfil actualizado: {phone_number} — {profile.summary[:60]}")
        return profile

    except Exception as e:
        logger.error(f"Error generando perfil para {phone_number}: {str(e)}")
        return None


async def run_profiling_job(db: Session) -> int:
    """
    Perfila todos los usuarios que llevan 7+ días sin actualizar.
    Se llama desde un endpoint o cron job.
    """
    week_ago = datetime.utcnow() - timedelta(days=7)

    # Usuarios con actividad reciente que no han sido perfilados
    phones = (
        db.query(Conversation.phone_number)
        .filter(Conversation.timestamp >= week_ago)
        .distinct()
        .all()
    )

    count = 0
    for (phone,) in phones:
        result = await profile_user(db, phone)
        if result:
            count += 1

    print(f"  🧠  Job de perfilado completado: {count} usuarios actualizados")
    return count