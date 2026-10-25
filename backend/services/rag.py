import logging
import re
from pathlib import Path
from typing import List
import chromadb
from chromadb.config import Settings as ChromaSettings
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from models.store import Store
from models.event import Event
from models.raffle import Raffle
from models.knowledge import KnowledgeEntry
from models.mall_info import MallInfo
from models.info_point import InfoPoint

logger = logging.getLogger("mall_bot")

CHROMA_PATH = Path(__file__).parent.parent / "data" / "chroma_db"

_collection = None


def _get_collection():
    global _collection
    if _collection is not None:
        return _collection

    client = chromadb.PersistentClient(
        path=str(CHROMA_PATH),
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    _collection = client.get_or_create_collection(
        name="mall_stores",
        metadata={"hnsw:space": "cosine"},
    )
    return _collection


def _get_mall_info(db: Session) -> MallInfo | None:
    return db.query(MallInfo).filter(MallInfo.id == 1).first()


def _build_mall_text(mall_info: MallInfo | None) -> str:
    if not mall_info:
        return ""
    lines = [
        f"INFORMACIÓN GENERAL DEL MALL: {mall_info.name or 'Centro Comercial El Puente'}",
        f"DIRECCIÓN: {mall_info.address or ''}",
        f"HORARIO GENERAL DEL MALL: {mall_info.general_schedule or ''}",
        f"TELÉFONO CENTRAL: {mall_info.phone or ''}",
        f"PARQUEADERO: {mall_info.parking or ''}",
        f"WIFI GRATIS: {mall_info.wifi or ''}",
    ]
    return "\n".join(l for l in lines if l.split(": ", 1)[1])


def load_stores_to_rag(db: Session) -> int:
    """
    Reindexar todo en ChromaDB, leyendo TODO desde la base de datos
    (Postgres/SQLite) — tiendas, eventos, conocimiento, e info general
    del mall. Ya no depende de ningún archivo JSON.
    Se llama al arrancar el backend y cada vez que se crea/edita/borra
    algo desde el panel.
    """
    collection = _get_collection()
    mall_info = _get_mall_info(db)
    info_points = db.query(InfoPoint).all()

    stores = db.query(Store).filter(Store.active == True).all()
    events = [e for e in db.query(Event).all() if e.esta_vigente()]            # eventos ya pasados no se indexan
    raffles = [r for r in db.query(Raffle).filter(Raffle.active == True).all() if r.esta_vigente()]
    knowledge = db.query(KnowledgeEntry).filter(KnowledgeEntry.active == True).all()

    # Limpiar colección antes de reindexar
    existing = collection.get()
    if existing and existing.get("ids"):
        collection.delete(ids=existing["ids"])

    documents, metadatas, ids = [], [], []

    # ── 1. Info general del mall ──────────────────────────────────
    mall_text = _build_mall_text(mall_info)
    if mall_text:
        documents.append(mall_text)
        metadatas.append({"source": "mall_info", "type": "general"})
        ids.append("mall_general")

    # ── 2. Puntos de interés (baños, cajeros, ascensor, etc.) ──────
    for point in info_points:
        text = (
            f"SERVICIO DEL MALL: {point.name}\n"
            f"PISO: {point.floor or ''}\n"
            f"UBICACIÓN EXACTA: {point.location or ''}"
        )
        documents.append(text)
        metadatas.append({"source": "poi", "type": "service", "name": point.name})
        ids.append(f"poi_{point.id:04d}")

    # ── 3. Tiendas — desde la base de datos ─────────────────────────
    for store in stores:
        documents.append(store.to_rag_text())
        metadatas.append({
            "source": "store",
            "type": "store",
            "name": store.name,
            "floor": store.floor,
            "category": store.category,
        })
        ids.append(f"store_{store.id:04d}")

    # ── 4. Eventos — desde la base de datos ─────────────────────────
    for event in events:
        documents.append(event.to_rag_text())
        metadatas.append({
            "source": "event",
            "type": "event",
            "name": event.name,
            "priority": event.priority,
        })
        ids.append(f"event_{event.id:04d}")

    # ── 4b. Sorteos y campañas — distintos de eventos ────────────────
    for raffle in raffles:
        documents.append(raffle.to_rag_text())
        metadatas.append({
            "source": "raffle",
            "type": "raffle",
            "name": raffle.name,
            "priority": raffle.priority,
        })
        ids.append(f"raffle_{raffle.id:04d}")

    # ── 5. Base de Conocimiento libre — desde la base de datos ──────
    for entry in knowledge:
        documents.append(entry.to_rag_text())
        metadatas.append({
            "source": "knowledge",
            "type": "knowledge",
            "title": entry.title,
        })
        ids.append(f"knowledge_{entry.id:04d}")

    collection.add(documents=documents, metadatas=metadatas, ids=ids)

    total = len(documents)
    print(f"  ✅  RAG: {len(stores)} tiendas + {len(events)} eventos + {len(raffles)} sorteos + "
          f"{len(info_points)} servicios + "
          f"{len(knowledge)} entradas de conocimiento = {total} indexadas")
    return len(stores)


def search_stores(query: str, n_results: int = 8) -> List[str]:
    """Busca en el índice semántico. Devuelve los documentos más relevantes."""
    collection = _get_collection()

    if collection.count() == 0:
        logger.warning("Colección RAG vacía en búsqueda - probablemente falta reindexar")
        return []

    try:
        total = collection.count()
        results = collection.query(
            query_texts=[query],
            n_results=min(n_results, total),
        )
        return results.get("documents", [[]])[0]
    except Exception as e:
        logger.error(f"Error RAG búsqueda: {str(e)}")
        return []


_VACIAS = {"de", "del", "la", "las", "el", "los", "para", "y", "con", "en", "un", "una", "a"}


def _palabras(texto: str) -> list[str]:
    """Texto → palabras sin tildes, en minúscula, sin palabras vacías."""
    import re
    import unicodedata
    t = unicodedata.normalize("NFD", (texto or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return [w for w in re.findall(r"[a-z0-9ñ]+", t) if w not in _VACIAS]


def _raiz(w: str) -> str:
    """Raíz simple: quita plural y género ("deportivos" → "deportiv", "niñas" → "nin")."""
    if len(w) > 4 and w.endswith("es"):
        w = w[:-2]
    elif len(w) > 3 and w.endswith("s"):
        w = w[:-1]
    if len(w) > 4 and w[-1] in "aoe":
        w = w[:-1]
    return w


def _coincide_palabra(t: str, palabras_local: list[str]) -> bool:
    rt = _raiz(t)
    for w in palabras_local:
        if w == t or _raiz(w) == rt:
            return True
        # Términos escritos como raíz a propósito ("hamburgues", "tecnolog"):
        # la palabra del local puede seguir hasta 3 letras más.
        if w.startswith(t) and len(w) - len(t) <= 3:
            return True
    return False


def _tags_sin_rubro(tags: str | None) -> str:
    """El rubro del Excel "Droguerías, Salud y Ópticas" agrupa tres tipos de
    local: con él, toda droguería parecía óptica al buscar "gafas". Se quita
    solo la palabra "Ópticas" de ese rubro; el resto del rubro se conserva
    porque muchos locales solo se encuentran por él (heladerías, peluquerías)."""
    t = tags or ""
    return re.sub(r"^(\s*Droguer[ií]as,\s*Salud)\s+y\s+[ÓO]pticas", r"\1", t)


def _coincide_frase(frase: list[str], palabras_local: list[str]) -> bool:
    return all(_coincide_palabra(t, palabras_local) for t in frase)


def find_all_stores_by_category(db: Session, terminos: List[str]) -> List[Store]:
    """
    Búsqueda JUSTA por categoría/tipo — trae TODOS los locales que
    coincidan con alguno de los términos dados (en su categoría,
    subcategoría, nombre, descripción o palabras clave), SIN límite y
    SIN ranking de "parecido".

    Esto es distinto a search_stores() (que es semántica y tope de 8):
    aquí el objetivo es la EQUIDAD COMERCIAL — cuando alguien pregunta
    "¿dónde comer hamburguesas?" o "¿zapatos formales?", deben salir
    TODOS los locales de ese tipo, no una selección, para que ningún
    local pueda reclamar que se promociona más a otros.

    El orden es alfabético (neutral) — no hay "primero" ni "destacado".
    Devuelve objetos Store (no texto), para que quien llame decida cómo
    presentarlos.
    """
    if not terminos:
        return []

    # BÚSQUEDA POR PALABRA COMPLETA (fase 0, 24/10/2026). Antes era
    # LIKE '%término%' y comparaba pedazos de texto: "niño" encontraba
    # "AmericaNINO", "bar" encontraba "BARbería", y la frase "ropa
    # infantil" NO encontraba un local con tags "ropa, infantil".
    # Ahora cada local se parte en palabras (categoría, nombre y tags;
    # nunca la descripción, que mete falsos positivos) y un término
    # coincide si TODAS sus palabras están en el local. Se tolera plural
    # y género ("deportiva" = "deportivos", "niños" = "niñas").
    frases = [_palabras(t) for t in terminos]
    frases = [f for f in frases if f]
    stores = []
    for s in db.query(Store).filter(Store.active == True).order_by(Store.name.asc()).all():
        palabras_local = _palabras(" ".join([s.category or "", s.name or "", _tags_sin_rubro(s.tags)]))
        if any(_coincide_frase(f, palabras_local) for f in frases):
            stores.append(s)
    # Los consultorios/oficinas de la TORRE MÉDICA no son locales
    # comerciales: no deben aparecer en búsquedas tipo "droguerías",
    # "ópticas", etc. (antes inflaban el resultado — ej. "droguerías"
    # daba 14). Se filtran aquí. La torre médica tiene su propia
    # herramienta (torre_medica) para cuando sí la pregunten.
    stores = [s for s in stores if "torre" not in (s.location_hint or "").lower()]
    return stores


def _expandir_sinonimos(query: str) -> str:
    """
    Añade sinónimos comunes a la consulta para que la búsqueda encuentre
    la información aunque el cliente use una palabra distinta a la que
    está guardada. Ej: si la base dice "mascotas" y el cliente dice
    "perro", igual la encuentra. Es aditivo — solo agrega palabras, no
    quita nada de la consulta original.
    """
    q = query.lower()
    SINONIMOS = {
        "mascota": ["perro", "gato", "perrito", "cachorro", "animal", "peludo"],
        "wifi": ["internet", "wi-fi", "conexión", "conexion", "red", "wifi"],
        "parqueadero": ["parqueo", "estacionamiento", "carro", "vehículo", "vehiculo", "parquear"],
        "baño": ["baños", "sanitario", "servicios", "tocador", "wc"],
        "factura": ["facturas", "compra", "recibo", "tiquete", "registrar"],
        "horario": ["hora", "abren", "cierran", "atienden", "abierto"],
    }
    extra = []
    for base, sins in SINONIMOS.items():
        # Si el cliente usó CUALQUIER sinónimo, agregamos la palabra base
        # y los demás sinónimos, para que la búsqueda tenga más de dónde
        # agarrar.
        if base in q or any(s in q for s in sins):
            extra.append(base)
            extra.extend(sins)
    if extra:
        return query + " " + " ".join(set(extra))
    return query


def search_knowledge_and_events(query: str, n_results: int = 4) -> List[str]:
    """
    Busca SOLO entre Base de Conocimiento, Eventos y Sorteos — filtrando
    por metadata para que las 138+ tiendas nunca puedan "ganarle" el
    espacio a esta información en la búsqueda combinada normal.

    Sin esto, una pregunta genérica (ej. "¿se permiten mascotas?") corre
    el riesgo de que los 8 resultados de la búsqueda general se llenen
    solo con tiendas semánticamente parecidas, y la política de mascotas
    real (que sí existe en la Base de Conocimiento) nunca llegue a
    aparecer en el contexto que recibe la IA.
    """
    collection = _get_collection()

    if collection.count() == 0:
        return []

    query = _expandir_sinonimos(query)  # perro→mascota, internet→wifi, etc.

    try:
        results = collection.query(
            query_texts=[query],
            n_results=n_results,
            where={"source": {"$in": ["knowledge", "event", "raffle"]}},
        )
        return results.get("documents", [[]])[0]
    except Exception as e:
        logger.error(f"Error RAG búsqueda filtrada (conocimiento/eventos/sorteos): {str(e)}")
        return []