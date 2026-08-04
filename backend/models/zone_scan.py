from sqlalchemy import Column, Integer, String, DateTime, func
from models.database import Base


class ZoneScan(Base):
    """
    Un registro por cada vez que alguien escanea un QR de zona.
    Sirve para armar mapas de calor de tráfico real por zona del mall
    — sin necesitar cámaras ni sensores físicos.
    """
    __tablename__ = "zone_scans"

    id           = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(20), nullable=False, index=True)
    zone_code    = Column(String(20), nullable=False, index=True)
    timestamp    = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "phone_number": self.phone_number,
            "zone_code": self.zone_code,
            "timestamp": str(self.timestamp),
        }