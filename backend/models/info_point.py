from sqlalchemy import Column, Integer, String
from models.database import Base


class InfoPoint(Base):
    """
    Un punto de interés del mall (punto de pago, acceso peatonal,
    punto de información, etc.) — lista libre que el admin gestiona
    desde el panel.
    """
    __tablename__ = "info_points"

    id       = Column(Integer, primary_key=True, index=True)
    name     = Column(String(150), nullable=False)
    floor    = Column(String(50), nullable=True)
    location = Column(String(300), nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "floor": self.floor,
            "location": self.location,
        }