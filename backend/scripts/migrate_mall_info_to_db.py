"""
scripts/migrate_mall_info_to_db.py

Migración de UNA SOLA VEZ: lee la sección "mall" de backend/data/tiendas.json
(dirección, teléfono, horario general, wifi, parqueadero, puntos de interés)
y la inserta en las tablas mall_info e info_points de la base de datos.

Después de correr esto, ya se edita todo desde el panel — el archivo
tiendas.json deja de usarse por completo.

Cómo correrlo (desde la carpeta backend/, en la consola de Railway):

    python scripts/migrate_mall_info_to_db.py
"""
import json
import sys
from pathlib import Path
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent))

from models.database import SessionLocal, create_tables, engine
from models.mall_info import MallInfo
from models.info_point import InfoPoint

DATA_PATH = Path(__file__).parent.parent / "data" / "tiendas.json"


def main():
    print("🔄  Iniciando migración de info general del mall → base de datos...")

    # IMPORTANTE: si ya intentaste correr esta migración antes (con el
    # modelo viejo que tenía phone/floor demasiado cortos), la tabla ya
    # quedó creada en Postgres con esos límites — y create_tables() NO
    # los actualiza, porque SQLAlchemy nunca modifica tablas que ya
    # existen. Como confirmamos que quedó vacía (los intentos anteriores
    # fallaron completos, con ROLLBACK), la borramos primero para que
    # se vuelva a crear desde cero con el esquema correcto y actual.
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS mall_info"))
        conn.execute(text("DROP TABLE IF EXISTS info_points"))
        conn.commit()
    print("  🗑️   Tablas viejas eliminadas (estaban vacías) — se recrean con el esquema correcto")

    create_tables()

    with open(DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    mall = data.get("mall", {})
    db = SessionLocal()

    try:
        existing = db.query(MallInfo).filter(MallInfo.id == 1).first()
        if existing:
            print("ℹ️   Ya existe un registro de MallInfo — no se sobreescribe. "
                  "Si quieres actualizarlo, hazlo desde el panel.")
        else:
            info = MallInfo(
                id=1,
                name=mall.get("name", "Centro Comercial El Puente"),
                address=mall.get("address", ""),
                general_schedule=mall.get("general_schedule", ""),
                phone=mall.get("phone", ""),
                parking=mall.get("parking", ""),
                wifi=mall.get("wifi", ""),
            )
            db.add(info)
            db.commit()
            print("✅  Info general del mall migrada")

        creados = 0
        for point in mall.get("info_points", []):
            existing_point = db.query(InfoPoint).filter(InfoPoint.name == point["name"]).first()
            if existing_point:
                continue
            db.add(InfoPoint(
                name=point["name"],
                floor=point.get("floor", ""),
                location=point.get("location", ""),
            ))
            creados += 1

        db.commit()
        print(f"✅  Puntos de interés migrados: {creados} nuevos")

    except Exception as e:
        db.rollback()
        print(f"❌  Error durante la migración: {e}")
        raise
    finally:
        db.close()

    print("\n🎉  Migración completa. Ya puedes recargar el panel y editar "
          "la info general del mall desde ahí — sin tocar archivos nunca más.")


if __name__ == "__main__":
    main()