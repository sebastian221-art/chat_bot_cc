from sqlalchemy import Column, String, Boolean, DateTime, func
from models.database import Base


class ConversationFlag(Base):
    """
    Una fila por número de teléfono. Guarda:
      - needs_human: la IA detectó algo que un humano debería revisar/atender
      - bot_paused_until: mientras esta fecha no haya pasado, el bot NO
        responde automáticamente a este número (el admin lo está atendiendo
        manualmente desde el panel)
    """
    __tablename__ = "conversation_flags"

    phone_number     = Column(String(20), primary_key=True)
    needs_human      = Column(Boolean, default=False)
    reason           = Column(String(300), nullable=True)
    bot_paused_until = Column(DateTime(timezone=True), nullable=True)
    updated_at       = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        return {
            "phone_number": self.phone_number,
            "needs_human": self.needs_human,
            "reason": self.reason,
            "bot_paused_until": str(self.bot_paused_until) if self.bot_paused_until else None,
        }