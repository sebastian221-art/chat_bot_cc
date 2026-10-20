from sqlalchemy import Column, Integer, String, Text, DateTime, func
from models.database import Base


def _fecha_final_vigente(texto: str) -> bool:
    import datetime, re
    fechas = re.findall(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})", texto or "")
    if not fechas:
        return True
    d, m, a = (int(x) for x in fechas[-1])
    if a < 100:
        a += 2000
    try:
        return datetime.date(a, m, d) >= datetime.date.today()
    except ValueError:
        return True


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

    def esta_vigente(self) -> bool:
        """
        True si el evento NO ha pasado. Lee la ÚLTIMA fecha DD/MM/AAAA que
        aparezca en `date` ("18/10/2026" o "23/10/2026 al 25/10/2026"); si
        esa fecha ya pasó, False. Sin fecha interpretable (ej. "Todos los
        domingos") se asume vigente. Así Any deja de anunciar eventos viejos.
        """
        return _fecha_final_vigente(self.date)

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
            f"ID: {self.id}",
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