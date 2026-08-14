from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, func
from models.database import Base


class Store(Base):
    __tablename__ = "stores"

    id            = Column(Integer, primary_key=True, index=True)
    name          = Column(String(150), nullable=False, index=True)
    local_number  = Column(String(60), nullable=True)   # ej: "104", "S/N" — ampliado de 20 a 60 (lección aprendida: un valor de 25 caracteres causó un error 500 real en una importación)
    floor         = Column(String(20), nullable=False)
    category      = Column(String(80), nullable=False)
    description   = Column(Text, nullable=True)
    schedule      = Column(String(200), nullable=True)
    phone         = Column(String(20), nullable=True)
    location_hint = Column(String(200), nullable=True)
    tags          = Column(String(300), nullable=True)
    photo_url     = Column(String(500), nullable=True)  # link a una foto del local (externo — ver nota en el panel)
    extra_info    = Column(Text, nullable=True)  # campo libre: carta, cartelera, o cualquier info adicional del local
    active        = Column(Boolean, default=True)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())
    updated_at    = Column(DateTime(timezone=True), onupdate=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "local_number": self.local_number,
            "floor": self.floor,
            "category": self.category,
            "description": self.description,
            "schedule": self.schedule,
            "phone": self.phone,
            "location_hint": self.location_hint,
            "tags": self.tags,
            "photo_url": self.photo_url,
            "extra_info": self.extra_info,
            "active": self.active,
        }

    def whatsapp_link(self) -> str | None:
        """Genera el link wa.me a partir del teléfono, para transferencias de domicilio."""
        if not self.phone:
            return None
        digits = "".join(c for c in self.phone if c.isdigit())
        if not digits:
            return None
        if not digits.startswith("57") and len(digits) == 10:
            digits = "57" + digits
        return f"https://wa.me/{digits}"

    def to_rag_text(self) -> str:
        parts = [
            f"Tienda: {self.name}",
            f"Local: {self.local_number or 'S/N'}",
            f"Piso: {self.floor}",
            f"Categoría: {self.category}",
        ]
        if self.description:
            parts.append(f"Descripción: {self.description}")
        if self.schedule:
            parts.append(f"Horario: {self.schedule}")
        if self.location_hint:
            parts.append(f"Ubicación: {self.location_hint}")
        if self.tags:
            parts.append(f"Palabras clave: {self.tags}")
        if self.extra_info:
            parts.append(f"Información adicional: {self.extra_info}")
        return " | ".join(parts)