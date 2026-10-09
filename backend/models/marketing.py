from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, func
from sqlalchemy.orm import relationship
from models.database import Base


class Marketing(Base):
    """
    Promociones/ofertas puntuales — de una tienda específica (ej. "2x1
    en pizzas en Zirus Pizza") o generales del mall/cine sin tienda
    asociada. Distinto de Eventos (algo que pasa en una fecha/lugar) y
    de Sorteos (con premio y requisitos de participación) — esto es
    específicamente contenido publicitario/comercial.
    """
    __tablename__ = "marketing"

    id          = Column(Integer, primary_key=True, index=True)
    title       = Column(String(150), nullable=False, index=True)
    description = Column(Text, nullable=True)
    store_id    = Column(Integer, ForeignKey("stores.id"), nullable=True)
    priority    = Column(Integer, nullable=False, default=3)
    valid_until = Column(String(30), nullable=True)
    active      = Column(Boolean, nullable=False, default=True)
    photo_url   = Column(String(500), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())

    store = relationship("Store", backref="marketing_promos")

    def esta_vigente(self) -> bool:
        """
        True si la promoción NO está vencida. Se basa en valid_until, que
        suele venir como "DD/MM/AAAA". Si la fecha ya pasó, devuelve False
        (así Any no promociona ofertas vencidas, aunque sigan guardadas en
        la base). Si no hay fecha o no se puede interpretar, se asume
        vigente (no escondemos algo por una fecha rara)."""
        import datetime, re
        v = (self.valid_until or "").strip()
        if not v:
            return True
        m = re.search(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})", v)
        if not m:
            return True
        d, mes, a = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if a < 100:
            a += 2000
        try:
            fin = datetime.date(a, mes, d)
        except ValueError:
            return True
        return fin >= datetime.date.today()

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "store_id": self.store_id,
            "store_name": self.store.name if self.store else None,
            "priority": self.priority,
            "valid_until": self.valid_until,
            "active": self.active,
            "photo_url": self.photo_url,
        }

    def to_rag_text(self) -> str:
        urgencia = {1: "baja", 2: "baja", 3: "normal", 4: "alta", 5: "máxima"}.get(self.priority, "normal")
        parts = [
            f"ID: {self.id}",
            f"Promoción: {self.title}",
            f"Prioridad de promoción: {urgencia}",
        ]
        if self.store:
            parts.append(f"Tienda: {self.store.name}")
        else:
            parts.append("Tienda: general del mall (no aplica a una tienda puntual)")
        if self.description:
            parts.append(f"Detalle: {self.description}")
        if self.valid_until:
            parts.append(f"Válido hasta: {self.valid_until}")
        return " | ".join(parts)