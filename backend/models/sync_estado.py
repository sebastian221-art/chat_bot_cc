from sqlalchemy import Column, String, Text, DateTime, func
from sqlalchemy.orm import Session
from models.database import Base


class SyncEstado(Base):
    """
    Pequeña tabla clave→valor para el SINCRONIZADOR automático (el que lee
    la web del mall y de Cinelandia). Guarda cosas como el hash del afiche
    de campañas (para saber si cambió) y el resumen de la última corrida.
    Se crea sola con create_tables() al arrancar — no necesita migración.
    """
    __tablename__ = "sync_estado"

    clave       = Column(String(80), primary_key=True)
    valor       = Column(Text, nullable=True)
    actualizado = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


def sync_get(db: Session, clave: str, default: str | None = None) -> str | None:
    row = db.query(SyncEstado).filter(SyncEstado.clave == clave).first()
    return row.valor if row else default


def sync_set(db: Session, clave: str, valor: str) -> None:
    row = db.query(SyncEstado).filter(SyncEstado.clave == clave).first()
    if row:
        row.valor = valor
    else:
        db.add(SyncEstado(clave=clave, valor=valor))
    db.commit()