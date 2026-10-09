# 📄 ARCHIVO: backend/scripts/add_catalogo_link.py
"""
MIGRACIÓN SEGURA: agrega la columna `catalogo_link` a la tabla `stores`.

Es un ADD COLUMN simple y sin riesgo: la columna es nullable, así que
no afecta ningún dato existente. Se puede correr varias veces sin
problema (usa IF NOT EXISTS).

Cómo correrlo en Railway:
    1. Abrir la consola del servicio backend en Railway.
    2. Ejecutar:  python backend/scripts/add_catalogo_link.py
       (o, estando dentro de backend/:  python scripts/add_catalogo_link.py)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("❌ No hay DATABASE_URL en el entorno.")
    sys.exit(1)

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)

with engine.begin() as conn:
    conn.execute(text(
        "ALTER TABLE stores ADD COLUMN IF NOT EXISTS catalogo_link VARCHAR(500)"
    ))
    print("✅ Columna 'catalogo_link' lista en la tabla 'stores'.")