"""
scripts/add_store_extra_info.py

Migración de UNA SOLA VEZ: agrega la columna `extra_info` a la tabla
`stores` (que ya tiene datos reales) — usa ALTER TABLE, no toca ningún
local existente.

Cómo correrlo (Railway → backend → Console):
    python scripts/add_store_extra_info.py
"""
import sys
from pathlib import Path
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent))

from models.database import engine


def main():
    print("🔄  Agregando columna extra_info a la tabla stores...")
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE stores ADD COLUMN IF NOT EXISTS extra_info TEXT"))
        conn.commit()
    print("✅  Listo — ningún local existente se tocó.")


if __name__ == "__main__":
    main()