from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, func
from models.database import Base


class Raffle(Base):
    """
    Un sorteo/campaña del mall (ej. "sorteo de un carro") — distinto de
    un Evento porque tiene premio, requisitos de participación y fecha
    límite, no una fecha/hora puntual de algo que "sucede".
    """
    __tablename__ = "raffles"

    id           = Column(Integer, primary_key=True, index=True)
    name         = Column(String(150), nullable=False, index=True)  # ej: "Sorteo de un carro"
    prize        = Column(String(250), nullable=False)              # ej: "Un Renault Kwid 0km"
    requirements = Column(Text, nullable=True)                      # cómo participar
    end_date     = Column(String(30), nullable=True)                # fecha límite / fecha del sorteo
    location     = Column(String(150), nullable=True)               # dónde registrarse
    description  = Column(Text, nullable=True)
    # 1 = baja, 3 = normal, 5 = máxima — igual que en Eventos, qué tanto
    # lo promociona Any proactivamente en las conversaciones.
    priority     = Column(Integer, nullable=False, default=3)
    photo_url    = Column(String(500), nullable=True)  # foto/afiche del sorteo
    active       = Column(Boolean, default=True)  # para "apagar" un sorteo vencido sin borrar el historial
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    updated_at   = Column(DateTime(timezone=True), onupdate=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "prize": self.prize,
            "requirements": self.requirements,
            "end_date": self.end_date,
            "location": self.location,
            "description": self.description,
            "priority": self.priority,
            "photo_url": self.photo_url,
            "active": self.active,
        }

    def to_rag_text(self) -> str:
        urgencia = {1: "baja", 2: "baja", 3: "normal", 4: "alta", 5: "máxima"}.get(self.priority, "normal")
        parts = [
            f"Sorteo/Campaña: {self.name}",
            f"Premio: {self.prize}",
            f"Prioridad de promoción: {urgencia}",
        ]
        if self.requirements:
            parts.append(f"Cómo participar: {self.requirements}")
        if self.end_date:
            parts.append(f"Fecha límite: {self.end_date}")
        if self.location:
            parts.append(f"Dónde registrarse: {self.location}")
        if self.description:
            parts.append(f"Descripción: {self.description}")
        return " | ".join(parts)