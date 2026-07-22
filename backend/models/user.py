# 📄 ARCHIVO: backend/models/user.py  ← NUEVO
"""
Modelo de usuarios del panel admin.
Roles: admin | local | supervisor | parqueadero
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, func
from models.database import Base


class UserRole:
    ADMIN       = "admin"
    LOCAL       = "local"        # dueño de un local específico
    SUPERVISOR  = "supervisor"   # empleado del CC
    PARQUEADERO = "parqueadero"  # operador de parqueadero


ROLE_LABELS = {
    UserRole.ADMIN:       "Administrador",
    UserRole.LOCAL:       "Dueño de local",
    UserRole.SUPERVISOR:  "Supervisor CC",
    UserRole.PARQUEADERO: "Parqueadero",
}

STORE_TYPES = ["restaurante", "tienda", "farmacia", "cine", "entretenimiento"]


class User(Base):
    __tablename__ = "users"

    id              = Column(Integer, primary_key=True, index=True)
    username        = Column(String(50),  unique=True, nullable=False, index=True)
    full_name       = Column(String(100), nullable=True)
    hashed_password = Column(String(200), nullable=False)
    role            = Column(String(20),  nullable=False, default=UserRole.LOCAL)

    # Solo para rol LOCAL — qué panel puede ver
    store_name = Column(String(150), nullable=True)  # ej: "El Corral"
    store_type = Column(String(30),  nullable=True)  # ej: "restaurante"
    store_id   = Column(String(50),  nullable=True)  # ej: "el-corral" (el [id] de la URL)

    is_active  = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def to_dict(self):
        return {
            "id":         self.id,
            "username":   self.username,
            "full_name":  self.full_name,
            "role":       self.role,
            "role_label": ROLE_LABELS.get(self.role, self.role),
            "store_name": self.store_name,
            "store_type": self.store_type,
            "store_id":   self.store_id,
            "is_active":  self.is_active,
            "created_at": str(self.created_at) if self.created_at else None,
        }

    def to_token_payload(self):
        """Datos mínimos para el JWT — sin contraseña."""
        return {
            "id":         self.id,
            "username":   self.username,
            "full_name":  self.full_name or self.username,
            "role":       self.role,
            "store_name": self.store_name,
            "store_type": self.store_type,
            "store_id":   self.store_id,
        }