# 📄 ARCHIVO: backend/services/cine.py
"""
Cartelera de cine — detección determinística, sin depender de que la
búsqueda semántica (RAG) encuentre la tienda del Cine por casualidad.
Mismo patrón que ya usa store_transfer.py para "número de tienda":
palabras clave claras → respuesta directa, construida con datos reales
de la base de datos, no adivinada por la IA.
"""
from sqlalchemy.orm import Session
from models.store import Store
from models.cine_funcion import CineFuncion

CARTELERA_KEYWORDS = [
    "cartelera", "película", "peliculas", "películas", "pelicula",
    "que dan en el cine", "qué dan en el cine", "funciones de cine",
    "horario de cine", "horarios de cine", "hora de la función",
    "hora de la funcion", "que hay en el cine", "qué hay en el cine",
    "estrenos", "estreno",
]


def is_cartelera_intent(message: str) -> bool:
    msg = message.lower()
    return any(k in msg for k in CARTELERA_KEYWORDS)


def find_cine_store(db: Session) -> Store | None:
    """Encuentra la tienda del Cine — por categoría 'Cine' primero (más confiable), o por nombre si no."""
    store = db.query(Store).filter(Store.category.ilike("%cine%")).first()
    if store:
        return store
    return db.query(Store).filter(Store.name.ilike("%cine%")).first()


def find_cine_funcion_by_message(db: Session, store_id: int, message: str) -> CineFuncion | None:
    """Si el cliente mencionó una película puntual por nombre, la encuentra — mismo mecanismo que las demás búsquedas por nombre."""
    msg = message.lower()
    funciones = db.query(CineFuncion).filter(CineFuncion.store_id == store_id, CineFuncion.active == True).all()
    exact = [f for f in funciones if f.title.lower() in msg]
    if len(exact) == 1:
        return exact[0]
    return None


def build_cartelera_message(store: Store | None) -> str:
    """Arma la respuesta completa de la cartelera actual — con datos reales, sin que la IA tenga que adivinar."""
    if not store:
        return "No tengo registrado el local del cine en el directorio todavía — te recomiendo preguntar en el Punto de Información (Piso 1). 😊"

    funciones = [f for f in store.cine_funciones if f.active]
    if not funciones:
        return f"Por ahora no tengo la cartelera de *{store.name}* cargada. Te recomiendo llamar al {store.phone or 'cine'} o preguntar en el Punto de Información (Piso 1) para la programación más actualizada. 🎬"

    lines = [f"🎬 Esto es lo que está en cartelera en *{store.name}* ahora mismo:\n"]
    for f in funciones:
        linea = f"• *{f.title}*"
        if f.is_premiere:
            linea += " 🆕 ESTRENO"
        if f.showtimes:
            linea += f"\n   🕒 {f.showtimes}"
        if f.description:
            linea += f"\n   {f.description}"
        lines.append(linea)

    lines.append("\n¿Quieres que te cuente más de alguna en particular?")
    return "\n\n".join(lines)


def build_funcion_especifica_message(funcion: CineFuncion, store: Store) -> str:
    """Respuesta enfocada en UNA película puntual — cuando el cliente ya la mencionó por nombre."""
    lines = [f"🎬 *{funcion.title}*"]
    if funcion.is_premiere:
        lines.append("🆕 Es un estreno")
    if funcion.showtimes:
        lines.append(f"🕒 Horarios: {funcion.showtimes}")
    if funcion.description:
        lines.append(funcion.description)
    lines.append(f"\n📍 En {store.name}, {store.floor}.")
    return "\n".join(lines)