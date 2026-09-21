# 📄 ARCHIVO: backend/services/auth.py  ← NUEVO
"""
Servicio de autenticación.
- Hash/verificación de contraseñas con bcrypt
- Generación y decodificación de JWT
- Creación del admin por defecto al iniciar
"""
import os
import logging
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from sqlalchemy.orm import Session

from models.user import User, UserRole

logger = logging.getLogger("mall_bot")

# El secreto para firmar los tokens. DEBE configurarse como variable de
# entorno JWT_SECRET en Railway con un valor largo y aleatorio. Si se usa
# el valor por defecto (que está en el código público), cualquiera podría
# falsificar tokens — por eso se advierte fuerte en los logs.
_SECRET_DEFECTO = "cc-el-puente-super-secret-2024-change-in-prod"
SECRET_KEY = os.getenv("JWT_SECRET", _SECRET_DEFECTO)
if SECRET_KEY == _SECRET_DEFECTO:
    logger.warning("⚠️ SEGURIDAD: se está usando el JWT_SECRET por defecto. "
                   "Configura la variable de entorno JWT_SECRET en Railway con un "
                   "valor largo y aleatorio para proteger las sesiones del panel.")
ALGORITHM         = "HS256"
TOKEN_EXPIRE_DAYS = 7


# ── Contraseñas ───────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ── JWT ───────────────────────────────────────────────────────────

def create_token(user: User) -> str:
    payload = {
        **user.to_token_payload(),
        "exp": datetime.now(timezone.utc) + timedelta(days=TOKEN_EXPIRE_DAYS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        logger.warning("Token expirado")
        return None
    except Exception:
        return None


# ── Autenticación ─────────────────────────────────────────────────

def authenticate_user(db: Session, username: str, password: str) -> User | None:
    user = db.query(User).filter(
        User.username == username,
        User.is_active == True,
    ).first()
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def get_user_from_token(db: Session, token: str) -> User | None:
    payload = decode_token(token)
    if not payload:
        return None
    user_id = payload.get("id")
    if not user_id:
        return None
    return db.query(User).filter(
        User.id == int(user_id),
        User.is_active == True,
    ).first()


# ── Admin por defecto ─────────────────────────────────────────────

def create_default_admin(db: Session):
    """
    Crea el usuario admin inicial si no existe ningún admin.
    Se llama al arrancar el servidor.
    """
    existing = db.query(User).filter(User.role == UserRole.ADMIN).first()
    if existing:
        return

    admin = User(
        username        = "admin",
        full_name       = "Administrador CC El Puente",
        hashed_password = hash_password("admin123"),
        role            = UserRole.ADMIN,
    )
    db.add(admin)
    db.commit()
    print("  👑  Admin creado  →  usuario: admin  |  contraseña: admin123")
    print("  ⚠️   CAMBIA LA CONTRASEÑA ANTES DE PONER EN PRODUCCIÓN")