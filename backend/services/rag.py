import json
import logging
from pathlib import Path
from typing import List
import chromadb
from chromadb.config import Settings as ChromaSettings

logger = logging.getLogger("mall_bot")

DATA_PATH   = Path(__file__).parent.parent / "data" / "tiendas.json"
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


def _build_store_text(store: dict) -> str:
    """
    Construye un texto rico y completo para cada tienda.
    Cuanto más detallado, mejor puede responder la IA.
    """
    lines = []

    lines.append(f"TIENDA: {store['name']}")
    lines.append(f"PISO Y UBICACIÓN: {store['floor']} — {store.get('location_hint', '')}")
    lines.append(f"CATEGORÍA: {store['category']}")

    if store.get('description'):
        lines.append(f"QUÉ VENDE / DESCRIPCIÓN: {store['description']}")

    if store.get('schedule'):
        lines.append(f"HORARIO: {store['schedule']}")

    if store.get('phone'):
        lines.append(f"TELÉFONO: {store['phone']}")

    if store.get('tags'):
        # Convertir tags en texto legible
        tags_readable = store['tags'].replace(',', ', ')
        lines.append(f"PRODUCTOS Y PALABRAS CLAVE: {tags_readable}")

    return "\n".join(lines)


def _build_mall_text(mall_info: dict) -> str:
    """Texto completo con info general del mall."""
    lines = [
        f"INFORMACIÓN GENERAL DEL MALL: {mall_info.get('name', 'Centro Comercial El Puente')}",
        f"DIRECCIÓN: {mall_info.get('address', '')}",
        f"HORARIO GENERAL DEL MALL: {mall_info.get('general_schedule', '')}",
        f"TELÉFONO CENTRAL: {mall_info.get('phone', '')}",
        f"PARQUEADERO: {mall_info.get('parking', '')}",
        f"WIFI GRATIS: {mall_info.get('wifi', '')}",
    ]
    return "\n".join(l for l in lines if l.split(': ')[1])


def load_stores_to_rag() -> int:
    collection = _get_collection()

    with open(DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    stores    = data.get("stores", [])
    mall_info = data.get("mall", {})
    events    = data.get("events", [])

    # Limpiar colección antes de reindexar
    existing = collection.get()
    if existing and existing.get("ids"):
        collection.delete(ids=existing["ids"])

    documents, metadatas, ids = [], [], []

    # ── 1. Info general del mall ──────────────────────────────────
    documents.append(_build_mall_text(mall_info))
    metadatas.append({"source": "mall_info", "type": "general"})
    ids.append("mall_general")

    # ── 2. Puntos de interés (baños, cajeros, ascensor, etc.) ──────
    for idx, point in enumerate(mall_info.get("info_points", [])):
        text = (
            f"SERVICIO DEL MALL: {point['name']}\n"
            f"PISO: {point['floor']}\n"
            f"UBICACIÓN EXACTA: {point['location']}"
        )
        documents.append(text)
        metadatas.append({"source": "poi", "type": "service", "name": point['name']})
        ids.append(f"poi_{idx:03d}")

    # ── 3. Tiendas — texto completo y detallado ───────────────────
    for i, store in enumerate(stores):
        documents.append(_build_store_text(store))
        metadatas.append({
            "source": "store",
            "type": "store",
            "name": store["name"],
            "floor": store["floor"],
            "category": store["category"],
        })
        ids.append(f"store_{i:03d}")

    # ── 4. Eventos ────────────────────────────────────────────────
    for idx, event in enumerate(events):
        text = (
            f"EVENTO: {event['name']}\n"
            f"FECHA: {event['date']}\n"
            f"HORA: {event.get('time', '')}\n"
            f"LUGAR: {event['location']}\n"
            f"DESCRIPCIÓN: {event.get('description', '')}"
        )
        documents.append(text)
        metadatas.append({"source": "event", "type": "event", "name": event['name']})
        ids.append(f"event_{idx:03d}")

    collection.add(documents=documents, metadatas=metadatas, ids=ids)

    total = len(documents)
    print(f"  ✅  RAG: {len(stores)} tiendas + {len(events)} eventos + {len(mall_info.get('info_points',[]))} servicios = {total} entradas indexadas")
    return len(stores)


def search_stores(query: str, n_results: int = 8) -> List[str]:
    """
    Busca en el índice semántico.
    Devuelve los documentos más relevantes para la consulta.
    """
    collection = _get_collection()

    if collection.count() == 0:
        load_stores_to_rag()

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