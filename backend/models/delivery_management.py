from sqlalchemy import Column, Integer, String, Text, DateTime, func
from models.database import Base


class DeliveryManagement(Base):
    """
    Una gestión completa de domicilio (distinta de una simple transferencia).
    Se crea cuando el cliente pide EXPLÍCITAMENTE que se le ayude a
    gestionar el pedido — el bot recolecta los datos en esta fila
    mientras la conversación avanza, y al completarse arma el link
    personalizado con el pedido ya escrito.
    """
    __tablename__ = "delivery_managements"

    id              = Column(Integer, primary_key=True, index=True)
    phone_number    = Column(String(20), nullable=False, index=True)
    store_name      = Column(String(150), nullable=False)

    # collecting = recolectando datos | completed = link ya entregado | closed = local cerrado, no se inició
    status          = Column(String(20), nullable=False, default="collecting", index=True)

    customer_name   = Column(String(150), nullable=True)
    customer_phone  = Column(String(20), nullable=True)
    address         = Column(String(300), nullable=True)
    order_details   = Column(Text, nullable=True)
    payment_method  = Column(String(50), nullable=True)

    generated_link  = Column(String(1500), nullable=True)

    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    completed_at    = Column(DateTime(timezone=True), nullable=True)

    REQUIRED_FIELDS = {
        "customer_name": "tu nombre",
        "customer_phone": "tu número de celular de contacto",
        "address": "la dirección de entrega",
        "order_details": "qué quieres pedir",
        "payment_method": "si pagas en efectivo o por transferencia",
    }

    def missing_fields(self) -> list[str]:
        return [label for field, label in self.REQUIRED_FIELDS.items() if not getattr(self, field)]

    def is_complete(self) -> bool:
        return len(self.missing_fields()) == 0

    def to_dict(self):
        return {
            "id": self.id,
            "phone_number": self.phone_number,
            "store_name": self.store_name,
            "status": self.status,
            "customer_name": self.customer_name,
            "customer_phone": self.customer_phone,
            "address": self.address,
            "order_details": self.order_details,
            "payment_method": self.payment_method,
            "generated_link": self.generated_link,
            "created_at": str(self.created_at),
            "completed_at": str(self.completed_at) if self.completed_at else None,
        }