from sqlalchemy import Column, Integer, String, DateTime, func
from models.database import Base


class DeliveryTransfer(Base):
    """
    Un registro por cada vez que el bot transfiere exitosamente a un
    cliente al WhatsApp de una tienda para su domicilio. Como ya no
    gestionamos el pedido completo, esto reemplaza a la tabla `orders`
    como la fuente real de "cuántos domicilios se están generando" —
    no sabemos si se concretó la venta, pero sí sabemos que el cliente
    fue conectado con la tienda correcta.
    """
    __tablename__ = "delivery_transfers"

    id           = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(20), nullable=False, index=True)
    store_name   = Column(String(150), nullable=False, index=True)
    timestamp    = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "phone_number": self.phone_number,
            "store_name": self.store_name,
            "timestamp": str(self.timestamp),
        }