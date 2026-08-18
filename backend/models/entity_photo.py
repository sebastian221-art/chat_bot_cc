from sqlalchemy import Column, Integer, String, DateTime, func
from models.database import Base

# Qué tipo de cosa es cada foto — así una sola tabla sirve para varios
# tipos de contenido, sin repetir la misma tabla 4 veces.
VALID_ENTITY_TYPES = ["event", "raffle", "knowledge", "zone", "marketing"]

# Etiquetas válidas por tipo de entidad — cada una tiene sentido distinto:
# - event: solo necesita un afiche principal
# - raffle: afiche promocional Y, aparte, una foto del premio (ej. el carro)
# - knowledge/zone: una foto principal ilustrativa, sin mucha variedad
# - marketing: un afiche/foto principal de la promoción
ENTITY_LABELS = {
    "event": ["afiche", "otra"],
    "raffle": ["afiche", "premio", "otra"],
    "knowledge": ["principal", "otra"],
    "zone": ["principal", "otra"],
    "marketing": ["afiche", "otra"],
}

LABEL_DISPLAY = {
    "afiche": "Afiche",
    "premio": "Foto del premio",
    "otra": "Otra",
    "principal": "Principal",
}


class EntityPhoto(Base):
    """
    Galería genérica de fotos con etiqueta, reutilizable para Eventos,
    Sorteos, Base de Conocimiento y Zonas — evita tener 4 tablas casi
    idénticas. Las Tiendas usan su propia tabla aparte (store_photos)
    porque ya estaba construida y en uso antes de generalizar esto.
    """
    __tablename__ = "entity_photos"

    id          = Column(Integer, primary_key=True, index=True)
    entity_type = Column(String(20), nullable=False, index=True)  # event | raffle | knowledge | zone
    entity_id   = Column(Integer, nullable=False, index=True)
    photo_url   = Column(String(500), nullable=False)
    label       = Column(String(20), nullable=False, default="principal")
    created_at  = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "photo_url": self.photo_url,
            "label": self.label,
            "label_display": LABEL_DISPLAY.get(self.label, self.label),
        }


def get_entity_photo(db, entity_type: str, entity_id: int, label: str) -> str | None:
    """
    Busca la foto con esa etiqueta específica para un evento/sorteo/
    conocimiento/zona (ej. "premio" en un sorteo). Si no hay ninguna
    con esa etiqueta pero sí existe cualquier otra foto, la usa como
    respaldo — mejor mandar algo que nada.
    """
    photo = (
        db.query(EntityPhoto)
        .filter(EntityPhoto.entity_type == entity_type, EntityPhoto.entity_id == entity_id, EntityPhoto.label == label)
        .first()
    )
    if photo:
        return photo.photo_url
    any_photo = (
        db.query(EntityPhoto)
        .filter(EntityPhoto.entity_type == entity_type, EntityPhoto.entity_id == entity_id)
        .first()
    )
    return any_photo.photo_url if any_photo else None