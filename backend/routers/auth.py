# 📄 ARCHIVO: backend/routers/auth.py  ← NUEVO
"""
Endpoints de autenticación y gestión de usuarios.
  POST /auth/login     → retorna JWT
  GET  /auth/me        → usuario actual (requiere token)
  GET  /auth/users     → listar usuarios (solo admin)
  POST /auth/users     → crear usuario (solo admin)
  PUT  /auth/users/:id → editar usuario (solo admin)
  DELETE /auth/users/:id → eliminar usuario (solo admin)
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from models.database import get_db
from models.user import User, UserRole
from services.auth import (
    authenticate_user,
    create_token,
    get_user_from_token,
    hash_password,
)

logger = logging.getLogger("mall_bot")
router = APIRouter(prefix="/auth", tags=["auth"])


# ── Schemas ───────────────────────────────────────────────────────

class LoginIn(BaseModel):
    username: str
    password: str


class UserIn(BaseModel):
    username:   str
    full_name:  Optional[str] = ""
    password:   str
    role:       str
    store_name: Optional[str] = None
    store_type: Optional[str] = None
    store_id:   Optional[str] = None
    is_active:  Optional[bool] = True


class UserUpdate(BaseModel):
    full_name:  Optional[str] = None
    password:   Optional[str] = None
    role:       Optional[str] = None
    store_name: Optional[str] = None
    store_type: Optional[str] = None
    store_id:   Optional[str] = None
    is_active:  Optional[bool] = None


# ── Dependencia: usuario autenticado ─────────────────────────────

def get_current_user(
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
) -> User:
    token = ""
    if authorization.startswith("Bearer "):
        token = authorization[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Token requerido")
    user = get_user_from_token(db, token)
    if not user:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Solo admins pueden hacer esto")
    return current_user


# ── Endpoints ─────────────────────────────────────────────────────

@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = authenticate_user(db, body.username, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")

    token = create_token(user)
    print(f"  🔑  Login: {user.username} ({user.role})")

    return {
        "token":      token,
        "user":       user.to_dict(),
        "redirect_to": _get_redirect(user),
    }


def _get_redirect(user: User) -> str:
    """Ruta a la que debe ir cada rol tras hacer login."""
    if user.role == UserRole.ADMIN:
        return "/dashboard"
    if user.role == UserRole.SUPERVISOR:
        return "/dashboard"
    if user.role == UserRole.PARQUEADERO:
        return "/panel/parqueadero"
    if user.role == UserRole.LOCAL:
        if user.store_type and user.store_id:
            return f"/panel/{user.store_type}/{user.store_id}"
        return "/locales"
    return "/dashboard"


@router.get("/me")
def me(current_user: User = Depends(get_current_user)):
    return current_user.to_dict()


@router.get("/users")
def list_users(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    users = db.query(User).order_by(User.created_at.desc()).all()
    return [u.to_dict() for u in users]


@router.post("/users", status_code=201)
def create_user(
    body: UserIn,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    existing = db.query(User).filter(User.username == body.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="El nombre de usuario ya existe")

    user = User(
        username        = body.username,
        full_name       = body.full_name,
        hashed_password = hash_password(body.password),
        role            = body.role,
        store_name      = body.store_name,
        store_type      = body.store_type,
        store_id        = body.store_id,
        is_active       = body.is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"ok": True, "user": user.to_dict()}


@router.put("/users/{user_id}")
def update_user(
    user_id: int,
    body: UserUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if body.full_name  is not None: user.full_name  = body.full_name
    if body.role       is not None: user.role       = body.role
    if body.store_name is not None: user.store_name = body.store_name
    if body.store_type is not None: user.store_type = body.store_type
    if body.store_id   is not None: user.store_id   = body.store_id
    if body.is_active  is not None: user.is_active  = body.is_active
    if body.password:
        user.hashed_password = hash_password(body.password)

    db.commit()
    db.refresh(user)
    return {"ok": True, "user": user.to_dict()}


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    current: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if user_id == current.id:
        raise HTTPException(status_code=400, detail="No puedes eliminarte a ti mismo")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    db.delete(user)
    db.commit()
    return {"ok": True, "removed": user.username}