"""
services/orders.py  ← NUEVO archivo
Lógica completa del flujo de domicilios:
  - Crear pedido desde conversación de WhatsApp
  - Cambiar estado del pedido
  - Generar mensajes automáticos de notificación al cliente
  - Listar productos de un local
"""
import logging
import random
import string
from datetime import datetime
from sqlalchemy.orm import Session
from models.order import Order, OrderItem, OrderRating, OrderStatus, STATUS_MESSAGES, Product

logger = logging.getLogger("mall_bot")


def _generate_order_number() -> str:
    """Genera un número de pedido único tipo PED-0042."""
    suffix = ''.join(random.choices(string.digits, k=4))
    return f"PED-{suffix}"


# ── Crear pedido ──────────────────────────────────────────────────

def create_order(
    db: Session,
    client_phone: str,
    client_name: str,
    store_name: str,
    items: list[dict],        # [{"product_name": ..., "quantity": ..., "unit_price": ..., "notes": ...}]
    delivery_address: str = "",
    notes: str = "",
    delivery_fee: float = 5000,
) -> Order:
    subtotal = sum(i["quantity"] * i["unit_price"] for i in items)
    total    = subtotal + delivery_fee

    order = Order(
        order_number=_generate_order_number(),
        client_phone=client_phone,
        client_name=client_name,
        store_name=store_name,
        delivery_address=delivery_address,
        notes=notes,
        subtotal=subtotal,
        delivery_fee=delivery_fee,
        total=total,
        status=OrderStatus.PENDING,
    )
    db.add(order)
    db.flush()  # obtener ID antes de commit

    for item in items:
        db.add(OrderItem(
            order_id=order.id,
            product_name=item["product_name"],
            quantity=item["quantity"],
            unit_price=item["unit_price"],
            subtotal=item["quantity"] * item["unit_price"],
            notes=item.get("notes", ""),
        ))

    db.commit()
    db.refresh(order)

    print(f"  🛵  Pedido {order.order_number} creado — {store_name} — ${total:,.0f} COP")
    return order


# ── Cambiar estado ────────────────────────────────────────────────

def update_order_status(
    db: Session,
    order_id: int,
    new_status: str,
    reject_reason: str = "",
) -> tuple[Order, str]:
    """
    Actualiza el estado del pedido.
    Retorna (order, mensaje_para_cliente).
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise ValueError(f"Pedido {order_id} no encontrado")

    order.status = new_status

    if new_status == OrderStatus.REJECTED and reject_reason:
        order.reject_reason = reject_reason

    if new_status == OrderStatus.ACCEPTED:
        order.accepted_at = datetime.utcnow()

    if new_status == OrderStatus.DELIVERED:
        order.delivered_at = datetime.utcnow()

    db.commit()
    db.refresh(order)

    client_msg = STATUS_MESSAGES.get(new_status, "")

    if new_status == OrderStatus.REJECTED and reject_reason:
        client_msg += f"\nMotivo: {reject_reason}"

    print(f"  📦  Pedido {order.order_number} → {new_status}")
    return order, client_msg


# ── Calificación ──────────────────────────────────────────────────

def rate_order(
    db: Session,
    order_id: int,
    score: int,
    comment: str = "",
) -> OrderRating:
    rating = OrderRating(
        order_id=order_id,
        score=max(1, min(5, score)),  # clamp 1-5
        comment=comment,
    )
    db.add(rating)
    db.commit()
    db.refresh(rating)
    return rating


# ── Consultas útiles ──────────────────────────────────────────────

def get_active_orders(db: Session, store_name: str | None = None) -> list[Order]:
    """Pedidos activos (pendiente, aceptado, preparando, listo, en camino)."""
    active_statuses = [
        OrderStatus.PENDING, OrderStatus.ACCEPTED,
        OrderStatus.PREPARING, OrderStatus.READY, OrderStatus.ON_THE_WAY,
    ]
    q = db.query(Order).filter(Order.status.in_(active_statuses))
    if store_name:
        q = q.filter(Order.store_name == store_name)
    return q.order_by(Order.created_at.desc()).all()


def get_store_menu(db: Session, store_name: str) -> list[Product]:
    """Productos activos de un local."""
    return (
        db.query(Product)
        .filter(Product.store_name == store_name, Product.active == True)
        .order_by(Product.category, Product.name)
        .all()
    )


def format_menu_for_bot(products: list[Product]) -> str:
    """
    Formatea el menú como texto para que el bot lo muestre en WhatsApp.
    """
    if not products:
        return "Este local no tiene productos registrados aún."

    # Agrupar por categoría
    by_category: dict[str, list] = {}
    for p in products:
        cat = p.category or "Otros"
        by_category.setdefault(cat, []).append(p)

    lines = []
    for cat, prods in by_category.items():
        lines.append(f"\n*{cat}*")
        for p in prods:
            price = f"${p.price:,.0f}"
            desc  = f" — {p.description[:60]}" if p.description else ""
            lines.append(f"• {p.name} ({price}){desc}")

    return "\n".join(lines)


def get_pending_orders_count(db: Session, store_name: str) -> int:
    """Cuántos pedidos pendientes tiene un local ahora mismo."""
    return (
        db.query(Order)
        .filter(Order.store_name == store_name, Order.status == OrderStatus.PENDING)
        .count()
    )