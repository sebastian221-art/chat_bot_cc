from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from models.database import Base


class PromotionShown(Base):
    """
    Registro de qué promociones (eventos, sorteos, marketing) ya se le
    mostraron a cada número de teléfono, dentro de la sesión de
    conversación actual — para no pasarse del límite de 2 promociones
    distintas por sesión, y para no repetir la misma una y otra vez
    dentro del mismo hilo.

    Una "sesión" se define por inactividad: si pasan más de
    SESSION_GAP_HOURS (ver services/ai.py) sin que ese número escriba,
    la siguiente vez que escriba cuenta como sesión nueva — y con eso,
    2 promociones nuevas disponibles otra vez.
    """
    __tablename__ = "promotions_shown"

    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(20), nullable=False, index=True)
    entity_type = Column(String(20), nullable=False)  # "event" | "raffle" | "marketing"
    entity_id = Column(Integer, nullable=False)
    shown_at = Column(DateTime(timezone=True), server_default=func.now())