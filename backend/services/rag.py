import logging
from pathlib import Path
from typing import List
import chromadb
from chromadb.config import Settings as ChromaSettings
from sqlalchemy.orm import Session

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
    events = db.query(Event).all()
    raffles = db.query(Raffle).filter(Raffle.active == True).all()
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