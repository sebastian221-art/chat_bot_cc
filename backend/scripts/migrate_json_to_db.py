"""
scripts/migrate_json_to_db.py

Migración de UNA SOLA VEZ: lee backend/data/tiendas.json (con los 114
locales reales del Centro Comercial El Puente que ya cargamos) y los
inserta en las tablas `stores` y `events` de la base de datos.

Cómo correrlo (desde la carpeta backend/, con el entorno virtual activo
y las variables de entorno ya apuntando a la base de datos de Railway):

    python scripts/migrate_json_to_db.py

Es seguro correrlo más de una vez: si un local con el mismo nombre y
local_number ya existe en la base de datos, lo salta en vez de duplicarlo.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from models.database import SessionLocal, create_tables
from models.store import Store
from models.event import Event

DATA_PATH = Path(__file__).parent.parent / "data" / "tiendas.json"


def main():
    print("🔄  Iniciando migración de tiendas.json → base de datos...")

    create_tables()

    with open(DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    stores_raw = data.get("stores", [])
    events_raw = data.get("events", [])

    db = SessionLocal()
    creadas, saltadas = 0, 0

    try:
        for s in stores_raw:
            # location_hint hoy trae "Local 104. Ubicación..." al inicio -
            # intentamos extraer el número si no viene aparte.
            local_number = s.get("local_number", "")
            if not local_number and s.get("location_hint", "").startswith("Local "):
                local_number = s["location_hint"].split(".")[0].replace("Local ", "").strip()

            existing = (
                db.query(Store)
                .filter(Store.name == s["name"], Store.local_number == local_number)
                .first()
            )
            if existing:
                saltadas += 1
                continue

            store = Store(
                name=s["name"],
                local_number=local_number or None,
                floor=s.get("floor", "Por confirmar"),
                category=s.get("category", "Por confirmar con el CC"),
                description=s.get("description", ""),
                schedule=s.get("schedule", ""),
                phone=s.get("phone", ""),
                location_hint=s.get("location_hint", ""),
                tags=s.get("tags", ""),
                active=True,
            )
            db.add(store)
            creadas += 1

        db.commit()
        print(f"✅  Tiendas migradas: {creadas} nuevas, {saltadas} ya existían (saltadas)")

        eventos_creados = 0
        for e in events_raw:
            existing = db.query(Event).filter(Event.name == e["name"], Event.date == e["date"]).first()
            if existing:
                continue
            event = Event(
                name=e["name"],
                date=e["date"],
                time=e.get("time", ""),
                location=e.get("location", ""),
                description=e.get("description", ""),
                priority=e.get("priority", 3),
            )
            db.add(event)
            eventos_creados += 1

        db.commit()
        print(f"✅  Eventos migrados: {eventos_creados} nuevos")

        total_stores_db = db.query(Store).count()
        total_events_db = db.query(Event).count()
        print(f"\n📊  Total en base de datos ahora: {total_stores_db} tiendas, {total_events_db} eventos")

    except Exception as e:
        db.rollback()
        print(f"❌  Error durante la migración: {e}")
        raise
    finally:
        db.close()

    print("\n🎉  Migración completa. Ya puedes recargar el panel y ver las tiendas reales.")


if __name__ == "__main__":
    main()