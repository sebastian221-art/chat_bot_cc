from sqlalchemy import Column, Integer, String, Text, DateTime, func
from models.database import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id           = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(20), index=True, nullable=False)
    user_name    = Column(String(100), nullable=True)
    role         = Column(String(10), nullable=False)  # "user" o "assistant"
    message      = Column(Text, nullable=False)
    timestamp    = Column(DateTime(timezone=True), server_default=func.now())
    session_id   = Column(String(50), nullable=True)
    # De qué tienda trató la respuesta del bot (si trató de alguna) —
    # se llena con el ID que la propia IA identificó (marca [TIENDA:]),
    # no adivinando por palabras. Permite que un mensaje de seguimiento
    # como "¿tienes foto?" sepa con certeza de qué tienda se hablaba,
    # sin tener que re-analizar el texto viejo (frágil).
    mentioned_store_id = Column(Integer, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "phone_number": self.phone_number,
            "user_name": self.user_name,
            "role": self.role,
            "message": self.message,
            "timestamp": str(self.timestamp),
        }