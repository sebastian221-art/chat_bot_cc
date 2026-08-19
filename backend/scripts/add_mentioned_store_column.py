"""
scripts/add_mentioned_store_column.py

Migración de UNA SOLA VEZ: agrega la columna `mentioned_store_id` a la
tabla `conversations` que ya existe con datos reales — usa ALTER TABLE
en vez de recrear la tabla, para no perder ningún mensaje ya guardado.

Es seguro correrlo más de una vez (usa IF NOT EXISTS).

Cómo correrlo (Railway → backend → Console):
    python scripts/add_mentioned_store_column.py
"""
import sys
from pathlib import Path
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent))

from models.database import engine


def main():
    print("🔄  Agregando columna mentioned_store_id a la tabla conversations...")
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS mentioned_store_id INTEGER"))
        conn.commit()
    print("✅  Listo — la columna mentioned_store_id ya existe. Ningún dato existente se tocó.")


if __name__ == "__main__":
    main()