from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, func
from models.database import Base


class KnowledgeEntry(Base):
    """
    Base de Conocimiento libre. El admin agrega un título + texto suelto
    (políticas del mall, preguntas frecuentes, lo que sea) y el bot lo
    usa como contexto adicional al responder — igual que hace con
    tiendas y eventos, pero sin estructura fija.
    """
    __tablename__ = "knowledge_entries"

    id         = Column(Integer, primary_key=True, index=True)
    title      = Column(String(150), nullable=False)
    content    = Column(Text, nullable=False)
    photo_url  = Column(String(500), nullable=True)  # foto opcional relacionada con esta entrada
    active     = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "photo_url": self.photo_url,
            "active": self.active,
        }

    def to_rag_text(self) -> str:
        return f"{self.title}: {self.content}"