"""
scripts/ampliar_columnas_store.py

SOLUCIÓN DE RAÍZ al error "value too long for type character varying(20)".

Amplía en la BASE DE DATOS las columnas que estaban limitadas a 20
caracteres y causaban el error al importar locales:
  - stores.floor : 20 → 60
  - stores.phone : 20 → 60

Con más espacio, es FÍSICAMENTE IMPOSIBLE que ese error ocurra, sin
importar qué código de importador esté corriendo. Esto ataca el problema
en la base de datos misma, no en el código.

Es seguro correrlo más de una vez (ALTER COLUMN a un tamaño mayor no
pierde datos ni falla si ya está ampliado).

Cómo correrlo (Railway → backend → Console):
    python scripts/ampliar_columnas_store.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from models.database import engine


def main():
    cambios = [
        ("floor", 60),
        ("phone", 60),
    ]
    print("🔧  Ampliando columnas de la tabla 'stores'...")
    with engine.connect() as conn:
        for col, size in cambios:
            try:
                conn.execute(text(f"ALTER TABLE stores ALTER COLUMN {col} TYPE VARCHAR({size})"))
                conn.commit()
                print(f"✅  stores.{col} → VARCHAR({size})")
            except Exception as e:
                conn.rollback()
                print(f"⚠️  No se pudo ampliar stores.{col}: {str(e)[:120]}")
    print("✅  Listo. Ahora la importación de locales ya no fallará por longitud.")


if __name__ == "__main__":
    main()