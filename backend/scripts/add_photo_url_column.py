"""
scripts/add_photo_url_column.py

Migración de UNA SOLA VEZ: agrega la columna `photo_url` a la tabla
`stores` que ya existe con datos reales — usa ALTER TABLE en vez de
recrear la tabla, para no perder ninguno de los 114 locales ya
cargados.

Es seguro correrlo más de una vez (usa IF NOT EXISTS).

Cómo correrlo (Railway → backend → Console):
    python scripts/add_photo_url_column.py
"""
import sys
from pathlib import Path
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent))

from models.database import engine


def main():
    print("🔄  Agregando columna photo_url a la tabla stores...")
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE stores ADD COLUMN IF NOT EXISTS photo_url VARCHAR(500)"))
        conn.commit()
    print("✅  Listo — la columna photo_url ya existe. Ningún dato existente se tocó.")


if __name__ == "__main__":
    main()