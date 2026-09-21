# 📄 ARCHIVO: backend/services/proteccion_datos.py
"""
Protección de datos personales (Ley 1581 de 2012 — Habeas Data).

Dos funciones para cumplir con la normativa colombiana de datos:

1. AVISO DE PRIVACIDAD (aviso_si_es_nuevo):
   La PRIMERA vez que un cliente escribe, antes de atenderlo, se le
   muestra un aviso informando que al continuar autoriza el tratamiento
   de sus datos, y cómo ejercer sus derechos. Solo se muestra una vez
   (se recuerda que ya se le mostró). Es la autorización por conducta
   inequívoca que permite la ley.

2. COMANDO "ELIMINAR MIS DATOS" (es_solicitud_eliminar / eliminar_datos):
   Si el cliente pide eliminar sus datos, se le pide confirmación y, al
   confirmar, se borra su historial de conversación y su perfil. Es el
   derecho de supresión que exige la ley.

Contacto para ejercer derechos: info.jelcom@gmail.com
"""
import logging
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, DateTime, func
from models.database import Base

logger = logging.getLogger("mall_bot")

CORREO_DATOS = "info.jelcom@gmail.com"


class AvisoMostrado(Base):
    """Registra a qué teléfonos ya se les mostró el aviso de privacidad,
    para no repetirlo en cada conversación."""
    __tablename__ = "aviso_privacidad_mostrado"
    id           = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(30), nullable=False, unique=True, index=True)
    mostrado_at  = Column(DateTime(timezone=True), server_default=func.now())


# ── Textos ────────────────────────────────────────────────────────
TEXTO_AVISO = (
    "¡Hola! 👋 Soy *Any*, tu asistente virtual del Centro Comercial El Puente.\n\n"
    "Antes de empezar, un aviso rápido: al continuar esta conversación, autorizas "
    "el tratamiento de tus datos personales para poder atenderte y mejorar el "
    "servicio, conforme a la *Ley 1581 de 2012* de protección de datos.\n\n"
    "Tus derechos: puedes consultar, actualizar o eliminar tus datos cuando quieras. "
    f"Si deseas eliminarlos, solo escríbeme *\"eliminar mis datos\"*. Para cualquier "
    f"otra solicitud, puedes escribir a *{CORREO_DATOS}*.\n\n"
    "¿En qué te puedo ayudar hoy? 😊"
)

TEXTO_CONFIRMAR_ELIMINAR = (
    "Entiendo que quieres eliminar tus datos personales. 🔒\n\n"
    "Esto borrará tu historial de conversación y la información que tengo de ti. "
    "La próxima vez que escribas, será como empezar de cero.\n\n"
    "¿Confirmas que deseas eliminar tus datos? Responde *\"sí, eliminar\"* para confirmar, "
    "o cualquier otra cosa para cancelar."
)

TEXTO_ELIMINADO = (
    "✅ Listo. Tus datos personales fueron eliminados de nuestro sistema.\n\n"
    "Gracias por visitarnos. Si vuelves a escribir, con gusto te atenderé de nuevo. 😊"
)


# ── Aviso de privacidad ───────────────────────────────────────────
def ya_vio_aviso(db: Session, phone_number: str) -> bool:
    try:
        return db.query(AvisoMostrado).filter(AvisoMostrado.phone_number == phone_number).first() is not None
    except Exception:
        return True  # si falla, no molestamos con el aviso


def marcar_aviso_mostrado(db: Session, phone_number: str):
    try:
        if not ya_vio_aviso(db, phone_number):
            db.add(AvisoMostrado(phone_number=phone_number))
            db.commit()
    except Exception as e:
        logger.error(f"No se pudo marcar el aviso como mostrado: {e}")


# ── Comando eliminar datos ────────────────────────────────────────
def es_solicitud_eliminar(mensaje: str) -> bool:
    """¿El cliente pidió eliminar sus datos?"""
    m = mensaje.lower().strip()
    frases = [
        "eliminar mis datos", "eliminar mis datos personales", "borra mis datos",
        "borrar mis datos", "elimina mis datos", "quiero eliminar mis datos",
        "eliminar mi informacion", "eliminar mi información", "borrar mi informacion",
        "no guardes mis datos", "eliminar datos",
    ]
    return any(f in m for f in frases)


def es_confirmacion_eliminar(mensaje: str) -> bool:
    """¿El cliente confirmó la eliminación?"""
    m = mensaje.lower().strip()
    return any(f in m for f in ["sí, eliminar", "si, eliminar", "si eliminar", "sí eliminar",
                                 "confirmo", "sí confirmo", "si confirmo", "eliminar"])


def eliminar_datos(db: Session, phone_number: str) -> bool:
    """Borra el historial de conversación y el perfil del cliente."""
    try:
        from models.conversation import Conversation
        from models.user_profile import UserProfile

        db.query(Conversation).filter(Conversation.phone_number == phone_number).delete(synchronize_session=False)
        db.query(UserProfile).filter(UserProfile.phone_number == phone_number).delete(synchronize_session=False)
        # También quitamos el registro del aviso, para que si vuelve se le muestre de nuevo
        db.query(AvisoMostrado).filter(AvisoMostrado.phone_number == phone_number).delete(synchronize_session=False)
        db.commit()
        print(f"  🔒  Datos eliminados a solicitud del titular: {phone_number}")
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Error eliminando datos de {phone_number}: {e}")
        return False