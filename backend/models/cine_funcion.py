from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, func
from sqlalchemy.orm import relationship
from models.database import Base


class CineFuncion(Base):
    """
    Funciones/estrenos de cine — ligadas a la tienda del Cine
    específicamente (store_id obligatorio, a diferencia de Marketing).
    Se maneja distinto a un local normal porque cambia semana a
    semana: título de la película y horarios de función, no un
    horario fijo de apertura como cualquier otro local.
    """
    __tablename__ = "cine_funciones"

    id          = Column(Integer, primary_key=True, index=True)
    store_id    = Column(Integer, ForeignKey("stores.id"), nullable=False, index=True)
    title       = Column(String(150), nullable=False)
    # Texto libre a propósito — cada cine anuncia sus horarios como
    # texto corrido (ej. "2:00pm, 5:00pm, 8:00pm"), no vale la pena
    # forzar una estructura rígida de horarios individuales.
    showtimes   = Column(String(200), nullable=True)
    description = Column(Text, nullable=True)  # sinopsis breve, género, clasificación
    is_premiere = Column(Boolean, nullable=False, default=False)
    active      = Column(Boolean, nullable=False, default=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())

    store = relationship("Store", backref="cine_funciones")

    def to_dict(self):
        return {
            "id": self.id,
            "store_id": self.store_id,
            "title": self.title,
            "showtimes": self.showtimes,
            "description": self.description,
            "is_premiere": self.is_premiere,
            "active": self.active,
        }

    def to_rag_text(self) -> str:
        parts = [f"🎬 {self.title}"]
        if self.is_premiere:
            parts.append("(ESTRENO)")
        if self.showtimes:
            parts.append(f"— Funciones: {self.showtimes}")
        if self.description:
            parts.append(f"— {self.description}")
        return " ".join(parts)