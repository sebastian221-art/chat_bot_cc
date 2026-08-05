from sqlalchemy import Column, Integer, String, Text, DateTime, func
from models.database import Base


class MallInfo(Base):
    """
    Información general del Centro Comercial — es una tabla "singleton":
    solo existe UNA fila (id=1) porque solo hay un mall. Se edita desde
    el panel como un formulario simple, no como una lista.
    """
    __tablename__ = "mall_info"

    id               = Column(Integer, primary_key=True, default=1)
    name             = Column(String(150), nullable=False, default="Centro Comercial El Puente")
    address          = Column(String(300), nullable=True)
    general_schedule = Column(Text, nullable=True)
    phone            = Column(String(150), nullable=True)  # antes 50 — muy corto para notas/placeholders largos
    parking          = Column(Text, nullable=True)
    wifi             = Column(Text, nullable=True)
    updated_at       = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "address": self.address,
            "general_schedule": self.general_schedule,
            "phone": self.phone,
            "parking": self.parking,
            "wifi": self.wifi,
        }