from sqlalchemy import Column, Integer, String, Text, DateTime, func
from models.database import Base


class Event(Base):
    __tablename__ = "events"

    id          = Column(Integer, primary_key=True, index=True)
    name        = Column(String(150), nullable=False, index=True)
    date        = Column(String(30), nullable=False)
    time        = Column(String(30), nullable=True)
    location    = Column(String(150), nullable=False)
    description = Column(Text, nullable=True)
    # 1 = baja, 3 = normal, 5 = máxima. El bot lo usa para decidir
    # qué tanto promociona el evento proactivamente en conversaciones.
    priority    = Column(Integer, nullable=False, default=3)
    photo_url   = Column(String(500), nullable=True)  # foto/afiche del evento
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "date": self.date,
            "time": self.time,
            "location": self.location,
            "description": self.description,
            "priority": self.priority,
            "photo_url": self.photo_url,
        }

    def to_rag_text(self) -> str:
        urgencia = {1: "baja", 2: "baja", 3: "normal", 4: "alta", 5: "máxima"}.get(self.priority, "normal")
        parts = [
            f"Evento: {self.name}",
            f"Fecha: {self.date}",
            f"Lugar: {self.location}",
            f"Prioridad de promoción: {urgencia}",
        ]
        if self.time:
            parts.append(f"Hora: {self.time}")
        if self.description:
            parts.append(f"Descripción: {self.description}")
        return " | ".join(parts)