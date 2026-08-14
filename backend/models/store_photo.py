from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from models.database import Base

# Etiquetas válidas — el bot usa esto para decidir qué foto mandar
# según lo que pregunte el cliente (portada por defecto, carta si
# pregunta específicamente por el menú).
VALID_LABELS = ["portada", "carta", "otra"]

LABEL_DISPLAY = {
    "portada": "Portada / Local",
    "carta": "Carta",
    "otra": "Otra",
}


class StorePhoto(Base):
    """
    Una foto de una tienda, con etiqueta — reemplaza el campo único
    `photo_url` de antes (que solo permitía UNA foto sin distinción)
    por una galería real: portada, carta, u otras fotos.
    """
    __tablename__ = "store_photos"

    id         = Column(Integer, primary_key=True, index=True)
    store_id   = Column(Integer, ForeignKey("stores.id", ondelete="CASCADE"), nullable=False, index=True)
    photo_url  = Column(String(500), nullable=False)
    label      = Column(String(20), nullable=False, default="portada")  # portada | carta | otra
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    store = relationship("Store", backref="photos")

    def to_dict(self):
        return {
            "id": self.id,
            "store_id": self.store_id,
            "photo_url": self.photo_url,
            "label": self.label,
            "label_display": LABEL_DISPLAY.get(self.label, self.label),
        }