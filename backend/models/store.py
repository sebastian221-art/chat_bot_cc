from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, func
from models.database import Base


class Store(Base):
    __tablename__ = "stores"

    id            = Column(Integer, primary_key=True, index=True)
    name          = Column(String(150), nullable=False, index=True)
    floor         = Column(String(20), nullable=False)
    category      = Column(String(80), nullable=False)
    description   = Column(Text, nullable=True)
    schedule      = Column(String(200), nullable=True)
    phone         = Column(String(20), nullable=True)
    location_hint = Column(String(200), nullable=True)
    tags          = Column(String(300), nullable=True)
    active        = Column(Boolean, default=True)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())
    updated_at    = Column(DateTime(timezone=True), onupdate=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "floor": self.floor,
            "category": self.category,
            "description": self.description,
            "schedule": self.schedule,
            "phone": self.phone,
            "location_hint": self.location_hint,
            "tags": self.tags,
            "active": self.active,
        }

    def to_rag_text(self) -> str:
        parts = [
            f"Tienda: {self.name}",
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
        return " | ".join(parts)