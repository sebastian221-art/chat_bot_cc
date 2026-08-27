"""
scripts/agregar_columnas_trazas.py

Agrega las 2 columnas nuevas a la tabla orchestrator_traces para que las
trazas guarden los LINKS de las fotos enviadas y el contenido agregado:
  - fotos_urls      (links de las fotos)
  - contenido_extra (qué evento/promo/sorteo/foto/ubicación se agregó)

Es seguro correrlo más de una vez (si la columna ya existe, no hace nada).

Cómo correrlo (Railway → backend → Console):
    python scripts/agregar_columnas_trazas.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from models.database import engine


def main():
    columnas = [
        ("fotos_urls", "TEXT"),
        ("contenido_extra", "TEXT"),
    ]
    with engine.connect() as conn:
        for nombre, tipo in columnas:
            try:
                conn.execute(text(f"ALTER TABLE orchestrator_traces ADD COLUMN {nombre} {tipo}"))
                conn.commit()
                print(f"✅  Columna '{nombre}' agregada.")
            except Exception as e:
                # Si ya existe, Postgres lanza error — lo ignoramos
                print(f"ℹ️   Columna '{nombre}' ya existe o no se pudo agregar: {str(e)[:80]}")
    print("✅  Listo.")


if __name__ == "__main__":
    main()