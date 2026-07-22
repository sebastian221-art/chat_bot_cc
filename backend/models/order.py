# 📄 ARCHIVO: backend/models/order.py
"""
Tablas para el sistema de domicilios.
ACTUALIZADO: añadidos payment_method, delivery_time_minutes, store_message.
"""
from sqlalchemy import (
    Column, Integer, String, Text, Float,
    Boolean, DateTime, ForeignKey, func
)
from sqlalchemy.orm import relationship
from models.database import Base


class OrderStatus:
    PENDING    = "pending"
    ACCEPTED   = "accepted"
    REJECTED   = "rejected"
    PREPARING  = "preparing"
    READY      = "ready"
    ON_THE_WAY = "on_the_way"
    DELIVERED  = "delivered"
    CANCELLED  = "cancelled"


STATUS_MESSAGES = {
    OrderStatus.ACCEPTED:   "✅ ¡Tu pedido fue aceptado! Ya están preparándolo 🙌",
    OrderStatus.REJECTED:   "😔 Lo sentimos, el local no puede atender tu pedido ahora.",
    OrderStatus.PREPARING:  "👨‍🍳 Tu pedido está en preparación. ¡Ya casi!",
    OrderStatus.READY:      "✅ ¡Tu pedido está listo y sale en camino!",
    OrderStatus.ON_THE_WAY: "🛵 ¡Tu pedido va en camino! Pronto llegará.",
    OrderStatus.DELIVERED:  "🏠 ¡Pedido entregado! ¿Cómo estuvo? Cuéntame del 1 al 5 ⭐",
    OrderStatus.CANCELLED:  "❌ Tu pedido fue cancelado.",
}


class Product(Base):
    __tablename__ = "products"

    id          = Column(Integer, primary_key=True, index=True)
    store_name  = Column(String(150), index=True, nullable=False)
    name        = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    price       = Column(Float, nullable=False)
    photo_url   = Column(String(500), nullable=True)
    category    = Column(String(80), nullable=True)
    active      = Column(Boolean, default=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self):
        return {
            "id":          self.id,
            "store_name":  self.store_name,
            "name":        self.name,
            "description": self.description,
            "price":       self.price,
            "photo_url":   self.photo_url,
            "category":    self.category,
            "active":      self.active,
        }

    def to_bot_text(self) -> str:
        price_fmt = f"${self.price:,.0f}"
        desc = f" — {self.description}" if self.description else ""
        return f"{self.name} ({price_fmt}){desc}"


class StoreUser(Base):
    __tablename__ = "store_users"

    id            = Column(Integer, primary_key=True, index=True)
    store_name    = Column(String(150), index=True, nullable=False)
    email         = Column(String(200), unique=True, nullable=False)
    password_hash = Column(String(200), nullable=False)
    is_active     = Column(Boolean, default=True)
    is_open       = Column(Boolean, default=True)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())

    orders = relationship("Order", back_populates="store_user", foreign_keys="Order.store_user_id")


class Order(Base):
    __tablename__ = "orders"

    id             = Column(Integer, primary_key=True, index=True)
    order_number   = Column(String(20), unique=True, nullable=False)
    client_phone   = Column(String(20), nullable=False, index=True)
    client_name    = Column(String(100), nullable=True)
    store_name     = Column(String(150), nullable=False, index=True)
    store_user_id  = Column(Integer, ForeignKey("store_users.id"), nullable=True)

    status         = Column(String(30), default=OrderStatus.PENDING, index=True)
    reject_reason  = Column(String(300), nullable=True)
    delivery_address = Column(Text, nullable=True)
    notes          = Column(Text, nullable=True)
    payment_method = Column(String(50), nullable=True)   # ← NUEVO

    # El local rellena estos al aceptar ↓
    delivery_time_minutes = Column(Integer, nullable=True)   # ← NUEVO ej: 35
    store_message         = Column(Text, nullable=True)      # ← NUEVO mensaje libre del local

    subtotal       = Column(Float, default=0)
    delivery_fee   = Column(Float, default=5000)
    total          = Column(Float, default=0)

    created_at     = Column(DateTime(timezone=True), server_default=func.now())
    accepted_at    = Column(DateTime(timezone=True), nullable=True)
    delivered_at   = Column(DateTime(timezone=True), nullable=True)

    items      = relationship("OrderItem",   back_populates="order", cascade="all, delete-orphan")
    rating     = relationship("OrderRating", back_populates="order", uselist=False)
    store_user = relationship("StoreUser",   back_populates="orders", foreign_keys=[store_user_id])

    def to_dict(self):
        return {
            "id":                   self.id,
            "order_number":         self.order_number,
            "client_phone":         self.client_phone,
            "client_name":          self.client_name,
            "store_name":           self.store_name,
            "status":               self.status,
            "reject_reason":        self.reject_reason,
            "delivery_address":     self.delivery_address,
            "notes":                self.notes,
            "payment_method":       self.payment_method,
            "delivery_time_minutes":self.delivery_time_minutes,
            "store_message":        self.store_message,
            "subtotal":             self.subtotal,
            "delivery_fee":         self.delivery_fee,
            "total":                self.total,
            "items":                [i.to_dict() for i in self.items],
            "rating":               self.rating.to_dict() if self.rating else None,
            "created_at":           str(self.created_at),
            "delivered_at":         str(self.delivered_at) if self.delivered_at else None,
        }


class OrderItem(Base):
    __tablename__ = "order_items"

    id           = Column(Integer, primary_key=True, index=True)
    order_id     = Column(Integer, ForeignKey("orders.id"), nullable=False)
    product_name = Column(String(200), nullable=False)
    quantity     = Column(Integer, default=1)
    unit_price   = Column(Float, nullable=False)
    subtotal     = Column(Float, nullable=False)
    notes        = Column(String(300), nullable=True)

    order = relationship("Order", back_populates="items")

    def to_dict(self):
        return {
            "product_name": self.product_name,
            "quantity":     self.quantity,
            "unit_price":   self.unit_price,
            "subtotal":     self.subtotal,
            "notes":        self.notes,
        }


class OrderRating(Base):
    __tablename__ = "order_ratings"

    id         = Column(Integer, primary_key=True, index=True)
    order_id   = Column(Integer, ForeignKey("orders.id"), unique=True, nullable=False)
    score      = Column(Integer, nullable=False)
    comment    = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    order = relationship("Order", back_populates="rating")

    def to_dict(self):
        return {
            "score":      self.score,
            "comment":    self.comment,
            "created_at": str(self.created_at),
        }