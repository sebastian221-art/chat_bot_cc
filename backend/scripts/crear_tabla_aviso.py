"""
scripts/crear_tabla_aviso.py

Crea la tabla 'aviso_privacidad_mostrado' que recuerda a qué clientes ya
se les mostró el aviso de tratamiento de datos (para no repetirlo).

Seguro de correr más de una vez. No toca ninguna otra tabla.

Cómo correrlo (Railway → backend → Console):
    python scripts/crear_tabla_aviso.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from models.database import engine, Base
from services.proteccion_datos import AvisoMostrado  # noqa: F401


def main():
    print("🔄  Creando tabla del aviso de privacidad...")
    Base.metadata.create_all(bind=engine, tables=[AvisoMostrado.__table__])
    print("✅  Listo — tabla 'aviso_privacidad_mostrado' creada.")


if __name__ == "__main__":
    main()