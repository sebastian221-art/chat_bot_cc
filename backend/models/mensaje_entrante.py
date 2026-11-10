from sqlalchemy import Column, Integer, String, Text, DateTime, func
from models.database import Base


class MensajeEntrante(Base):
    """
    Bandeja de entrada a prueba de reinicios.

    Antes: Meta nos mandaba el mensaje, respondíamos «200 OK» al instante y lo procesábamos en memoria.
    Si el servidor se reiniciaba o se caía en ese momento (Railway reinicia contenedores), el mensaje se
    perdía: Meta ya tenía su «OK» y no lo reenviaba, y el cliente se quedaba sin respuesta (10/11/2026).

    Ahora cada mensaje se guarda aquí ANTES de responder «OK». Al arrancar, y cada minuto, se revisa si
    quedó alguno sin responder y se responde. También evita contestar dos veces si Meta reenvía el mismo
    mensaje (mismo `wamid`). Se crea sola con create_tables() — no necesita migración.
    """
    __tablename__ = "mensajes_entrantes"

    id          = Column(Integer, primary_key=True, index=True)
    wamid       = Column(String(200), unique=True, index=True, nullable=False)   # id del mensaje en WhatsApp
    telefono    = Column(String(40), index=True, nullable=False)
    datos       = Column(Text, nullable=False)                                    # el mensaje ya parseado (JSON)
    estado      = Column(String(20), index=True, nullable=False, default="pendiente")  # pendiente | procesando | hecho | error | vencido
    intentos    = Column(Integer, nullable=False, default=0)
    recibido    = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    actualizado = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
