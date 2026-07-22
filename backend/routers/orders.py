# 📄 ARCHIVO: backend/routers/orders.py
"""
Endpoints de domicilios.
FIX: sesión solo se resetea en DELIVERED y CANCELLED — no en ACCEPTED.
     Así el cliente puede seguir consultando el estado de su pedido.
"""
import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from pydantic import BaseModel
from typing import Optional

from models.database import get_db
from models.order import Order, OrderRating, OrderStatus, Product, STATUS_MESSAGES
from models.delivery_session import DeliverySession
from services.orders import (
    create_order,
    update_order_status,
    rate_order,
    get_active_orders,
    get_store_menu,
)

logger = logging.getLogger("mall_bot")
router = APIRouter(tags=["orders"])

VALID_STATUSES = [
    "pending", "accepted", "rejected",
    "preparing", "ready", "on_the_way",
    "delivered", "cancelled",
]

# Solo estos estados terminan el flujo y limpian la sesión del cliente
TERMINAL_STATUSES = {OrderStatus.DELIVERED, OrderStatus.CANCELLED, OrderStatus.REJECTED}


# ── Schemas ───────────────────────────────────────────────────────

class StatusUpdate(BaseModel):
    status:                str
    reject_reason:         Optional[str]  = ""
    delivery_time_minutes: Optional[int]  = None
    store_message:         Optional[str]  = ""
    total:                 Optional[float] = None


class ProductIn(BaseModel):
    store_name:  str
    name:        str
    description: Optional[str]  = ""
    price:       float
    category:    Optional[str]  = ""
    photo_url:   Optional[str]  = ""
    active:      Optional[bool] = True


class OrderIn(BaseModel):
    client_phone:     str
    client_name:      Optional[str] = "Cliente"
    store_name:       str
    delivery_address: Optional[str] = ""
    notes:            Optional[str] = ""
    payment_method:   Optional[str] = ""
    items:            list[dict]


# ══════════════════════════════════════════════════════════════════
# ORDERS — Panel admin
# ══════════════════════════════════════════════════════════════════

@router.get("/orders")
def list_active_orders(db: Session = Depends(get_db)):
    orders = get_active_orders(db)
    return [o.to_dict() for o in orders]


@router.get("/orders/all")
def list_all_orders(limit: int = 100, db: Session = Depends(get_db)):
    orders = (
        db.query(Order)
        .order_by(desc(Order.created_at))
        .limit(limit)
        .all()
    )
    return [o.to_dict() for o in orders]


@router.get("/orders/stats")
def order_stats(db: Session = Depends(get_db)):
    today    = datetime.utcnow().date()
    week_ago = datetime.utcnow() - timedelta(days=7)

    total_today = db.query(Order).filter(
        func.date(Order.created_at) == today
    ).count()

    delivered_today = db.query(Order).filter(
        func.date(Order.created_at) == today,
        Order.status == OrderStatus.DELIVERED,
    ).count()

    revenue_today = db.query(func.sum(Order.total)).filter(
        func.date(Order.created_at) == today,
        Order.status == OrderStatus.DELIVERED,
    ).scalar() or 0

    pending_now = db.query(Order).filter(
        Order.status == OrderStatus.PENDING
    ).count()

    top_stores = (
        db.query(Order.store_name, func.count(Order.id).label("total"))
        .filter(Order.created_at >= week_ago)
        .group_by(Order.store_name)
        .order_by(desc("total"))
        .limit(5)
        .all()
    )

    avg_ratings = (
        db.query(Order.store_name, func.avg(OrderRating.score).label("avg"))
        .join(OrderRating, Order.id == OrderRating.order_id)
        .filter(Order.created_at >= week_ago)
        .group_by(Order.store_name)
        .all()
    )

    hourly = [
        {
            "hora":    f"{h:02d}:00",
            "pedidos": db.query(Order).filter(
                func.date(Order.created_at) == today,
                func.extract("hour", Order.created_at) == h,
            ).count(),
        }
        for h in range(24)
    ]

    return {
        "total_today":     total_today,
        "delivered_today": delivered_today,
        "pending_now":     pending_now,
        "revenue_today":   revenue_today,
        "top_stores":      [{"store": s, "total": t} for s, t in top_stores],
        "avg_ratings":     [{"store": s, "avg": round(float(a), 1)} for s, a in avg_ratings],
        "hourly_chart":    hourly,
    }


# ══════════════════════════════════════════════════════════════════
# ORDERS — Por local (micro-panel)
# ══════════════════════════════════════════════════════════════════

@router.get("/orders/store/{store_name}")
def orders_by_store(store_name: str, db: Session = Depends(get_db)):
    orders = get_active_orders(db, store_name=store_name)
    return [o.to_dict() for o in orders]


@router.put("/orders/{order_id}/status")
async def change_status(
    order_id: int,
    body: StatusUpdate,
    db: Session = Depends(get_db),
):
    """
    El local cambia el estado de un pedido.
    FIX: la sesión del cliente solo se resetea cuando el pedido
    termina (DELIVERED, CANCELLED, REJECTED). En ACCEPTED y estados
    intermedios la sesión permanece en waiting_local para que el
    cliente pueda consultar el estado.
    """
    if body.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Estado inválido: {body.status}")

    try:
        order, base_msg = update_order_status(
            db, order_id, body.status, body.reject_reason or ""
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Guardar campos extra que informa el local
    if body.delivery_time_minutes is not None:
        order.delivery_time_minutes = body.delivery_time_minutes
    if body.store_message:
        order.store_message = body.store_message
    if body.total is not None and body.total > 0:
        order.total = body.total
    db.commit()
    db.refresh(order)

    # ── Notificación WhatsApp al cliente ─────────────────────────
    client_msg = _build_client_notification(order, body)

    if client_msg and order.client_phone:
        try:
            from services.whatsapp import send_text_message
            await send_text_message(to=order.client_phone, message=client_msg)

            from models.conversation import Conversation
            db.add(Conversation(
                phone_number=order.client_phone,
                user_name=order.client_name or "Cliente",
                role="assistant",
                message=client_msg,
            ))

            # ── FIX CLAVE: solo resetear sesión si el pedido terminó ──
            if body.status in TERMINAL_STATUSES:
                session = db.query(DeliverySession).filter(
                    DeliverySession.phone_number == order.client_phone
                ).first()
                if session:
                    session.reset()
                    print(f"  🔄  Sesión de {order.client_phone} reseteada (pedido {body.status})")

            db.commit()
            print(f"  📲  WhatsApp enviado a {order.client_phone}: {client_msg[:60]}")
        except Exception as e:
            logger.error(f"Error enviando WhatsApp: {e}")

    return {
        "ok":             True,
        "order":          order.to_dict(),
        "client_message": client_msg,
    }


def _build_client_notification(order: Order, body: StatusUpdate) -> str:
    """Construye el mensaje que recibe el cliente al cambiar el estado."""

    if body.status == OrderStatus.ACCEPTED:
        lines = [
            f"✅ *¡Tu pedido fue aceptado!* 🎉",
            f"",
            f"📋 *{order.order_number}*  ·  {order.store_name}",
        ]
        if body.delivery_time_minutes:
            lines.append(f"⏱️ Tiempo estimado: *{body.delivery_time_minutes} minutos*")
        if body.total and body.total > 0:
            lines.append(f"💰 Total: *${order.total:,.0f} COP*")
        if body.store_message:
            lines.append(f"💬 {body.store_message}")
        lines.append("")
        lines.append("🛵 Te avisamos cuando tu pedido salga a domicilio.")
        return "\n".join(lines)

    if body.status == OrderStatus.REJECTED:
        lines = [
            f"😔 Lo sentimos, *{order.store_name}* no puede atender tu pedido.",
        ]
        if body.reject_reason:
            lines.append(f"Motivo: {body.reject_reason}")
        lines.append("Puedes intentar con otro local escribiendo *domicilio* 😊")
        return "\n".join(lines)

    if body.status == OrderStatus.PREPARING:
        return (
            f"👨‍🍳 *¡Ya están preparando tu pedido!*\n"
            f"#{order.order_number} de {order.store_name} está en cocina 🔥"
        )

    if body.status == OrderStatus.ON_THE_WAY:
        return (
            f"🛵 *¡Tu pedido va en camino!*\n"
            f"Ya salió de {order.store_name}. ¡Pronto llegará! 🏠"
        )

    if body.status == OrderStatus.DELIVERED:
        return (
            f"🏠 *¡Pedido entregado!* ¡Que lo disfrutes! 😋\n\n"
            f"¿Cómo estuvo tu experiencia con {order.store_name}?\n"
            f"Cuéntame del *1 al 5* ⭐ _(1 = malo, 5 = excelente)_"
        )

    if body.status == OrderStatus.CANCELLED:
        return f"❌ Tu pedido #{order.order_number} fue cancelado."

    return STATUS_MESSAGES.get(body.status, "")


@router.post("/orders/{order_id}/rate")
def submit_rating(
    order_id: int, score: int, comment: str = "", db: Session = Depends(get_db)
):
    if not 1 <= score <= 5:
        raise HTTPException(status_code=400, detail="Score debe ser entre 1 y 5")
    rating = rate_order(db, order_id, score, comment)
    return {"ok": True, "rating": rating.to_dict()}


@router.post("/orders", status_code=201)
def create_new_order(body: OrderIn, db: Session = Depends(get_db)):
    order = create_order(
        db=db,
        client_phone=body.client_phone,
        client_name=body.client_name or "Cliente",
        store_name=body.store_name,
        items=body.items,
        delivery_address=body.delivery_address or "",
        notes=body.notes or "",
    )
    if body.payment_method:
        order.payment_method = body.payment_method
        db.commit()
    return {"ok": True, "order": order.to_dict()}


# ══════════════════════════════════════════════════════════════════
# DELIVERY SESSIONS
# ══════════════════════════════════════════════════════════════════

@router.get("/delivery-sessions")
def list_delivery_sessions(db: Session = Depends(get_db)):
    sessions = db.query(DeliverySession).filter(
        DeliverySession.step != "idle"
    ).all()
    return [s.to_dict() for s in sessions]


@router.delete("/delivery-sessions/{phone}")
def reset_delivery_session(phone: str, db: Session = Depends(get_db)):
    session = db.query(DeliverySession).filter(
        DeliverySession.phone_number == phone
    ).first()
    if session:
        session.reset()
        db.commit()
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════
# PRODUCTS
# ══════════════════════════════════════════════════════════════════

@router.get("/products/{store_name}")
def get_products(store_name: str, db: Session = Depends(get_db)):
    products = get_store_menu(db, store_name)
    return [p.to_dict() for p in products]


@router.post("/products", status_code=201)
def add_product(body: ProductIn, db: Session = Depends(get_db)):
    product = Product(**body.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return {"ok": True, "product": product.to_dict()}


@router.put("/products/{product_id}")
def edit_product(product_id: int, body: ProductIn, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    for key, val in body.model_dump().items():
        setattr(product, key, val)
    db.commit()
    return {"ok": True, "product": product.to_dict()}


@router.delete("/products/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    name = product.name
    db.delete(product)
    db.commit()
    return {"ok": True, "removed": name}


@router.patch("/products/{product_id}/toggle")
def toggle_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    product.active = not product.active
    db.commit()
    return {"ok": True, "active": product.active, "product": product.name}