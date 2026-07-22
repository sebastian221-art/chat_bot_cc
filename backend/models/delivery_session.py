# 📄 ARCHIVO: backend/models/delivery_session.py
"""
Estado del flujo de domicilio por usuario.

Pasos v2:
  idle → asking_store* → collecting_all → confirming → waiting_local → [completed|cancelled]
  (* asking_store se salta si el usuario mencionó el local desde el inicio)
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, func
from models.database import Base

STEPS = [
    "idle",
    "asking_store",       # solo si no especificó local al inicio
    "collecting_all",     # recibe nombre+dirección+pago+productos en 1 mensaje
    "confirming",         # esperando SÍ/NO del cliente
    "waiting_local",      # pedido enviado, esperando respuesta del local
    "completed",
    "cancelled",
]


class DeliverySession(Base):
    __tablename__ = "delivery_sessions"

    id           = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(20), unique=True, index=True, nullable=False)

    step              = Column(String(30), default="idle", nullable=False)

    store_name        = Column(String(150), nullable=True)
    client_name       = Column(String(100), nullable=True)
    delivery_address  = Column(Text,        nullable=True)
    payment_method    = Column(String(50),  nullable=True)
    products_text     = Column(Text,        nullable=True)
    notes             = Column(Text,        nullable=True)

    order_id          = Column(Integer, nullable=True)
    menu_sent         = Column(Boolean, default=False)
    local_notified    = Column(Boolean, default=False)
    step_attempts     = Column(Integer, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def reset(self):
        self.step             = "idle"
        self.store_name       = None
        self.client_name      = None
        self.delivery_address = None
        self.payment_method   = None
        self.products_text    = None
        self.notes            = None
        self.order_id         = None
        self.menu_sent        = False
        self.local_notified   = False
        self.step_attempts    = 0

    def order_summary(self) -> str:
        lines = [
            "📋 *Resumen de tu pedido:*\n",
            f"🏪 *Local:* {self.store_name}",
            f"👤 *Recibe:* {self.client_name}",
            f"📍 *Dirección:* {self.delivery_address}",
            f"💳 *Pago:* {self.payment_method}",
            f"🛒 *Pedido:* {self.products_text}",
        ]
        if self.notes:
            lines.append(f"📝 *Notas:* {self.notes}")
        lines.append("\n¿Todo correcto? Responde *SÍ* para enviar o *NO* para cancelar.")
        return "\n".join(lines)

    def local_notification_text(self) -> str:
        return (
            f"🛵 *NUEVO DOMICILIO CONFIRMADO*\n"
            f"Cliente: {self.client_name}\n"
            f"Tel: {self.phone_number}\n"
            f"Dirección: {self.delivery_address}\n"
            f"Pago: {self.payment_method}\n"
            f"Pedido: {self.products_text}"
            + (f"\nNotas: {self.notes}" if self.notes else "")
        )

    def to_dict(self):
        return {
            "id":               self.id,
            "phone_number":     self.phone_number,
            "step":             self.step,
            "store_name":       self.store_name,
            "client_name":      self.client_name,
            "delivery_address": self.delivery_address,
            "payment_method":   self.payment_method,
            "products_text":    self.products_text,
            "notes":            self.notes,
            "order_id":         self.order_id,
            "local_notified":   self.local_notified,
        }