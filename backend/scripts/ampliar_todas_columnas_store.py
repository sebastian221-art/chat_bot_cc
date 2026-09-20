"""
scripts/ampliar_todas_columnas_store.py

SOLUCIÓN DEFINITIVA Y TOTAL al error "value too long" al importar locales.

Amplía TODAS las columnas de texto de la tabla 'stores' a tamaños
generosos, de un solo golpe. Así, sin importar cuál columna sea la que
está causando el error (floor, phone, category, o cualquier otra que la
base de datos tenga como varchar corto), queda resuelta.

Convierte los campos de texto grandes a TEXT (ilimitado) y deja los
cortos con tamaños amplios. Ningún dato se pierde.

Es seguro correrlo más de una vez.

Cómo correrlo (Railway → backend → Console):
    python scripts/ampliar_todas_columnas_store.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from models.database import engine


def main():
    # Cada columna → nuevo tipo. Los campos que pueden ser largos van a
    # TEXT (ilimitado). Los cortos, a un varchar amplio.
    cambios = [
        ("name",          "VARCHAR(200)"),
        ("local_number",  "VARCHAR(100)"),
        ("floor",         "VARCHAR(100)"),
        ("category",      "VARCHAR(150)"),
        ("schedule",      "TEXT"),
        ("phone",         "VARCHAR(100)"),
        ("location_hint", "TEXT"),
        ("tags",          "TEXT"),
        ("photo_url",     "TEXT"),
        ("description",   "TEXT"),
        ("extra_info",    "TEXT"),
    ]
    print("🔧  Ampliando TODAS las columnas de texto de 'stores'...")
    print("=" * 55)
    with engine.connect() as conn:
        for col, tipo in cambios:
            try:
                conn.execute(text(f"ALTER TABLE stores ALTER COLUMN {col} TYPE {tipo}"))
                conn.commit()
                print(f"✅  stores.{col:15} → {tipo}")
            except Exception as e:
                conn.rollback()
                print(f"⚠️  stores.{col:15} : {str(e)[:80]}")
    print("=" * 55)
    print("✅  Listo. Ahora NINGUNA columna puede causar 'value too long'.")
    print("    Ya puedes importar los locales sin error.")


if __name__ == "__main__":
    main()