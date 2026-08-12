import urllib.parse
from sqlalchemy import Column, Integer, String, DateTime, func
from models.database import Base


class Zone(Base):
    """
    Una zona física del mall (columna, pasillo, sector) donde se pega
    un QR. El QR codifica un link de WhatsApp con el código de zona
    ya escrito — el cliente solo tiene que tocar "Enviar".
    """
    __tablename__ = "zones"

    id          = Column(Integer, primary_key=True, index=True)
    code        = Column(String(20), unique=True, nullable=False, index=True)  # ej: "A5"
    floor       = Column(String(20), nullable=False)
    description = Column(String(200), nullable=False)  # ej: "Ala norte, cerca de la fuente"
    photo_url   = Column(String(500), nullable=True)  # foto de esta zona del mall
    created_at  = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "floor": self.floor,
            "description": self.description,
            "photo_url": self.photo_url,
        }

    def whatsapp_qr_link(self, bot_phone_number: str) -> str:
        """
        El link exacto que hay que convertir en imagen QR e imprimir
        para pegar físicamente en esta zona del mall. Al escanearlo,
        WhatsApp abre el chat con el bot con este texto ya escrito —
        el cliente solo toca "Enviar".
        """
        text = urllib.parse.quote(f"Estoy en Zona {self.code}")
        digits = "".join(c for c in bot_phone_number if c.isdigit())
        return f"https://wa.me/{digits}?text={text}"