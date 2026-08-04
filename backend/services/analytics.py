"""
services/analytics.py  ← NUEVO archivo
Analiza las conversaciones para generar métricas de negocio:
  - Top tiendas más consultadas
  - Palabras/temas más frecuentes
  - Horas pico por día
  - Tendencias de la semana
  - Intenciones detectadas (domicilio, ubicación, horario, etc.)
"""
import re
import logging
from datetime import datetime, timedelta
from collections import Counter
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from models.conversation import Conversation
from models.store import Store
from models.conversation_flag import ConversationFlag

logger = logging.getLogger("mall_bot")

# ── Nombres de tiendas conocidas para detectar menciones ─────────
# NOTA: ya no se usa — get_top_stores ahora consulta los nombres reales
# de la tabla `stores`. Se deja por si se necesita como referencia.
KNOWN_STORES = [
    "nike", "adidas", "zara", "studio f", "totto", "ishop", "apple",
    "samsung", "falabella", "mcdonald", "mcdonalds", "crepes", "waffles",
    "el corral", "subway", "juan valdez", "óptica", "optica", "éxito",
    "exito", "bodytech", "cine colombia", "claro", "librería nacional",
    "libreria", "dropi", "farmacia",
]

# ── Categorías para clasificar consultas ─────────────────────────
CATEGORY_KEYWORDS = {
    "Ropa y Moda":        ["ropa", "vestido", "blusa", "pantalón", "moda", "zara", "studio f", "falabella"],
    "Calzado Deportivo":  ["zapatillas", "tenis", "zapatos", "nike", "adidas", "deportivo"],
    "Comida y Restaurantes": ["comida", "comer", "restaurante", "almuerzo", "cena", "desayuno",
                               "hamburguesa", "pizza", "pollo", "ensalada"],
    "Cafetería":          ["café", "cafe", "cappuccino", "tinto", "juan valdez", "frappé"],
    "Domicilios":         ["domicilio", "delivery", "pedir", "pedido", "a casa", "llevar"],
    "Tecnología":         ["celular", "iphone", "samsung", "laptop", "computador", "apple", "tablet"],
    "Entretenimiento":    ["cine", "película", "pelicula", "gym", "gimnasio", "bodytech"],
    "Salud":              ["farmacia", "medicamento", "dropi", "óptica", "optica", "gafas"],
    "Horarios":           ["horario", "abre", "cierra", "hora", "cuándo"],
    "Ubicación":          ["dónde", "donde", "piso", "cómo llego", "queda", "ubicación"],
    "Parqueadero":        ["parqueadero", "parqueo", "carro", "moto", "parcar"],
    "Eventos":            ["evento", "feria", "show", "concierto", "actividad"],
}


def _clean_message(text: str) -> str:
    """Limpia el mensaje para análisis."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\sáéíóúñü]', ' ', text)
    return text


def get_top_stores(db: Session, days: int = 7, limit: int = 10) -> list[dict]:
    """
    Top locales mencionados en conversaciones de los últimos N días.
    Usa los nombres REALES de la tabla `stores` (no una lista fija de
    marcas de ejemplo) — así funciona con el directorio real de
    cualquier centro comercial, no solo con cadenas conocidas.
    """
    since = datetime.utcnow() - timedelta(days=days)

    store_names = [s.name for s in db.query(Store.name).filter(Store.active == True).all()]
    if not store_names:
        return []

    messages = (
        db.query(Conversation.message)
        .filter(
            Conversation.role == "user",
            Conversation.timestamp >= since,
        )
        .all()
    )

    store_counts = Counter()
    for (msg,) in messages:
        clean = _clean_message(msg)
        for name in store_names:
            if name.lower() in clean:
                store_counts[name] += 1

    return [
        {"store": store, "mentions": count, "rank": i + 1}
        for i, (store, count) in enumerate(store_counts.most_common(limit))
    ]


def get_top_categories(db: Session, days: int = 7) -> list[dict]:
    """Categorías más consultadas en los últimos N días."""
    since = datetime.utcnow() - timedelta(days=days)

    messages = (
        db.query(Conversation.message)
        .filter(Conversation.role == "user", Conversation.timestamp >= since)
        .all()
    )

    cat_counts = Counter()
    for (msg,) in messages:
        clean = _clean_message(msg)
        for category, keywords in CATEGORY_KEYWORDS.items():
            if any(kw in clean for kw in keywords):
                cat_counts[category] += 1

    total = sum(cat_counts.values()) or 1
    return [
        {
            "category": cat,
            "mentions": count,
            "percentage": round(count / total * 100, 1),
        }
        for cat, count in cat_counts.most_common()
    ]


def get_hourly_heatmap(db: Session, days: int = 7) -> list[dict]:
    """
    Mapa de calor: mensajes por hora y por día de la semana.
    Devuelve lista de {day, hour, count} para pintar la matriz en el panel.
    """
    since = datetime.utcnow() - timedelta(days=days)

    records = (
        db.query(Conversation.timestamp)
        .filter(Conversation.role == "user", Conversation.timestamp >= since)
        .all()
    )

    heatmap = {}
    days_labels = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]

    for (ts,) in records:
        if ts:
            day  = days_labels[ts.weekday()]
            hour = ts.hour
            key  = f"{day}_{hour}"
            heatmap[key] = heatmap.get(key, 0) + 1

    result = []
    for day in days_labels:
        for hour in range(0, 24):
            result.append({
                "day":   day,
                "hour":  hour,
                "count": heatmap.get(f"{day}_{hour}", 0),
            })
    return result


def get_top_words(db: Session, days: int = 7, limit: int = 20) -> list[dict]:
    """
    Palabras más frecuentes en mensajes de usuarios (excluye stopwords).
    """
    stopwords = {
        "el", "la", "los", "las", "un", "una", "de", "del", "en", "y", "o",
        "a", "al", "se", "que", "qué", "me", "mi", "te", "tu", "su", "por",
        "con", "para", "hay", "hay", "tiene", "tienen", "es", "son", "está",
        "están", "si", "no", "sí", "más", "como", "cómo", "donde", "cuál",
        "cuándo", "hola", "buenas", "gracias", "bueno", "quiero", "quisiera",
        "puedes", "podría", "favor", "porfavor", "please",
    }

    since = datetime.utcnow() - timedelta(days=days)

    messages = (
        db.query(Conversation.message)
        .filter(Conversation.role == "user", Conversation.timestamp >= since)
        .all()
    )

    word_counts = Counter()
    for (msg,) in messages:
        words = _clean_message(msg).split()
        for word in words:
            if len(word) > 3 and word not in stopwords:
                word_counts[word] += 1

    return [
        {"word": word, "count": count}
        for word, count in word_counts.most_common(limit)
    ]


def get_weekly_summary(db: Session) -> dict:
    """
    Resumen semanal para el dashboard de analytics.
    Compara esta semana vs la anterior.
    """
    now       = datetime.utcnow()
    week_ago  = now - timedelta(days=7)
    two_weeks = now - timedelta(days=14)

    this_week = db.query(func.count(Conversation.id)).filter(
        Conversation.role == "user",
        Conversation.timestamp >= week_ago,
    ).scalar() or 0

    last_week = db.query(func.count(Conversation.id)).filter(
        Conversation.role == "user",
        Conversation.timestamp >= two_weeks,
        Conversation.timestamp < week_ago,
    ).scalar() or 1  # evitar división por cero

    change_pct = round((this_week - last_week) / last_week * 100, 1)

    new_users = db.query(func.count(func.distinct(Conversation.phone_number))).filter(
        Conversation.timestamp >= week_ago,
    ).scalar() or 0

    return {
        "messages_this_week": this_week,
        "messages_last_week": last_week,
        "change_percentage":  change_pct,
        "trend":              "up" if change_pct >= 0 else "down",
        "new_users_this_week": new_users,
        "top_stores":     get_top_stores(db, days=7, limit=5),
        "top_categories": get_top_categories(db, days=7),
        "top_words":      get_top_words(db, days=7, limit=15),
    }


# ══════════════════════════════════════════════════════════════════
# MOTOR DE ACCIONES SUGERIDAS
# ══════════════════════════════════════════════════════════════════
#
# No usa IA generativa a propósito — son reglas sobre los mismos datos
# que ya se calculan arriba, así que es instantáneo, gratis y 100%
# predecible (nunca inventa una recomendación rara).

def _category_counts_for_window(db: Session, start, end) -> Counter:
    messages = (
        db.query(Conversation.message)
        .filter(
            Conversation.role == "user",
            Conversation.timestamp >= start,
            Conversation.timestamp < end,
        )
        .all()
    )
    counts = Counter()
    for (msg,) in messages:
        clean = _clean_message(msg)
        for category, keywords in CATEGORY_KEYWORDS.items():
            if any(kw in clean for kw in keywords):
                counts[category] += 1
    return counts


def generate_insights(db: Session) -> list[dict]:
    """
    Devuelve una lista de "tarjetas" de acción sugerida, cada una con:
      { type, icon, title, finding, action, severity }
    severity: "up" (tendencia positiva) | "down" (alerta) | "info" | "urgent"
    """
    insights = []
    now       = datetime.utcnow()
    week_ago  = now - timedelta(days=7)
    two_weeks = now - timedelta(days=14)

    # ── 1. Categorías en alza o en baja fuerte ──────────────────────
    this_week_counts = _category_counts_for_window(db, week_ago, now)
    last_week_counts = _category_counts_for_window(db, two_weeks, week_ago)

    for category, this_count in this_week_counts.items():
        last_count = last_week_counts.get(category, 0)
        if this_count < 5:
            continue  # muy pocos datos para que la comparación sea confiable
        if last_count == 0:
            continue  # categoría nueva, no hay línea base para comparar
        change = round((this_count - last_count) / last_count * 100, 0)
        if change >= 30:
            insights.append({
                "type": "categoria_alza",
                "icon": "trending-up",
                "severity": "up",
                "title": f"{category} está en alza",
                "finding": f"Las consultas sobre {category.lower()} subieron {int(change)}% esta semana ({this_count} vs {last_count}).",
                "action": f"Considera destacar promociones o contenido de {category.lower()} — hay demanda creciente ahora mismo.",
            })
        elif change <= -30:
            insights.append({
                "type": "categoria_baja",
                "icon": "trending-down",
                "severity": "down",
                "title": f"{category} bajó fuerte",
                "finding": f"Las consultas sobre {category.lower()} cayeron {abs(int(change))}% esta semana ({this_count} vs {last_count}).",
                "action": "Revisa si hay algo cambiando en esa categoría (cierre de local, cambio de horario, etc.).",
            })

    # ── 2. Hora pico de la semana ────────────────────────────────────
    heatmap = get_hourly_heatmap(db, days=7)
    if heatmap:
        peak = max(heatmap, key=lambda h: h["count"])
        if peak["count"] > 0:
            insights.append({
                "type": "hora_pico",
                "icon": "clock",
                "severity": "info",
                "title": "Hora pico de la semana",
                "finding": f"El mayor volumen de consultas es los {peak['day']} a las {peak['hour']:02d}:00.",
                "action": "Ese es el mejor momento para lanzar una promoción o anuncio — máxima audiencia activa.",
            })

    # ── 3. Conversaciones esperando atención humana ──────────────────
    pending = db.query(ConversationFlag).filter(ConversationFlag.needs_human == True).count()
    if pending > 0:
        insights.append({
            "type": "escalamiento_pendiente",
            "icon": "alert-triangle",
            "severity": "urgent",
            "title": f"{pending} conversación(es) esperando atención humana",
            "finding": "Hay clientes que pidieron hablar con una persona y todavía no han sido atendidos.",
            "action": "Ve a la pestaña Conversaciones y respóndeles — están marcados en rojo.",
        })

    # ── 4. Categoría líder del mes (contexto general) ────────────────
    top_month = get_top_categories(db, days=30)
    if top_month:
        leader = top_month[0]
        insights.append({
            "type": "categoria_lider",
            "icon": "star",
            "severity": "info",
            "title": f"{leader['category']} es la categoría más consultada del mes",
            "finding": f"Representa el {leader['percentage']}% de todas las consultas de los últimos 30 días.",
            "action": f"Vale la pena asegurar que la información de {leader['category'].lower()} esté siempre actualizada y completa.",
        })

    return insights