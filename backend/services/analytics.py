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

logger = logging.getLogger("mall_bot")

# ── Nombres de tiendas conocidas para detectar menciones ─────────
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
    """Top tiendas mencionadas en conversaciones de los últimos N días."""
    since = datetime.utcnow() - timedelta(days=days)

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
        for store in KNOWN_STORES:
            if store in clean:
                # Normalizar nombre
                display = store.title().replace("Mcdonald", "McDonald's")
                store_counts[display] += 1

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