"""
scripts/diagnostico_columnas.py

Muestra el tamaño REAL de cada columna de texto de la tabla 'stores' en
la base de datos (no lo que dice el modelo, sino lo que existe de verdad
en PostgreSQL). Sirve para encontrar cuál columna varchar(20) está
causando el error "value too long".

Cómo correrlo (Railway → backend → Console):
    python scripts/diagnostico_columnas.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from models.database import engine


def main():
    print("🔍  Columnas REALES de la tabla 'stores' en la base de datos:")
    print("=" * 55)
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT column_name, data_type, character_maximum_length
            FROM information_schema.columns
            WHERE table_name = 'stores'
            ORDER BY ordinal_position
        """))
        for row in result:
            nombre, tipo, maxlen = row
            limite = f"({maxlen})" if maxlen else ""
            marca = "  <-- ⚠️ VARCHAR(20) — POSIBLE CULPABLE" if maxlen == 20 else ""
            print(f"  {nombre:20} {tipo}{limite}{marca}")
    print("=" * 55)
    print("Cualquier columna que diga VARCHAR(20) arriba es la que causa el error.")


if __name__ == "__main__":
    main()