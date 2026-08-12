"""
scripts/add_photos_and_location.py

Migración de UNA SOLA VEZ: agrega las columnas nuevas de fotos (zonas,
eventos, sorteos, base de conocimiento) y las coordenadas del mall —
usa ALTER TABLE, no toca ningún dato existente.

Es seguro correrlo más de una vez (usa IF NOT EXISTS).

Cómo correrlo (Railway → backend → Console):
    python scripts/add_photos_and_location.py
"""
import sys
from pathlib import Path
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent))

from models.database import engine

ALTERS = [
    "ALTER TABLE zones ADD COLUMN IF NOT EXISTS photo_url VARCHAR(500)",
    "ALTER TABLE events ADD COLUMN IF NOT EXISTS photo_url VARCHAR(500)",
    "ALTER TABLE raffles ADD COLUMN IF NOT EXISTS photo_url VARCHAR(500)",
    "ALTER TABLE knowledge_entries ADD COLUMN IF NOT EXISTS photo_url VARCHAR(500)",
    "ALTER TABLE mall_info ADD COLUMN IF NOT EXISTS latitude VARCHAR(30)",
    "ALTER TABLE mall_info ADD COLUMN IF NOT EXISTS longitude VARCHAR(30)",
]


def main():
    print("🔄  Agregando columnas de fotos + ubicación...")
    with engine.connect() as conn:
        for statement in ALTERS:
            conn.execute(text(statement))
            print(f"  ✓  {statement}")
        conn.commit()
    print("✅  Listo — ningún dato existente se tocó.")


if __name__ == "__main__":
    main()