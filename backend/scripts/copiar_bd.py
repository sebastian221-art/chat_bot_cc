# 📄 ARCHIVO: backend/scripts/copiar_bd.py  ← ARCHIVO NUEVO
"""
COPIA la base de datos de Railway (Postgres) a un archivo SQLite local,
con TODO el conocimiento: locales, fotos, eventos, sorteos, promos, cine,
info del mall, base de conocimiento, zonas, conversaciones, trazas…
Así el proyecto corre en tu PC con los datos reales y SIN tocar producción.

USO (desde backend/):

  Windows (PowerShell):
    $env:ORIGEN="postgresql+pg8000://postgres:CLAVE@HOST:PUERTO/railway"
    python scripts/copiar_bd.py

  Mac/Linux:
    ORIGEN="postgresql+pg8000://postgres:CLAVE@HOST:PUERTO/railway" python3 scripts/copiar_bd.py

  Opcional: $env:DESTINO="sqlite:///./local.db"  (por defecto crea backend/local.db)

De dónde sale ORIGEN: Railway → servicio Postgres → pestaña "Connect" (o
"Variables") → DATABASE_PUBLIC_URL. Empieza por "postgresql://…"; cámbiale
el inicio por "postgresql+pg8000://" (el driver que usa el proyecto).

Es SOLO LECTURA sobre Railway: únicamente hace SELECT. Si el destino ya
existe, lo reemplaza.
"""
import os, sys, time
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))
os.chdir(BASE)

ORIGEN = os.environ.get("ORIGEN", "").strip()
DESTINO = os.environ.get("DESTINO", "sqlite:///./local.db").strip()
if not ORIGEN:
    print("❌ Falta ORIGEN (la URL pública del Postgres de Railway). Lee la cabecera de este archivo.")
    sys.exit(1)
if ORIGEN.startswith("postgres://"):
    ORIGEN = "postgresql+pg8000://" + ORIGEN[len("postgres://"):]
elif ORIGEN.startswith("postgresql://"):
    ORIGEN = "postgresql+pg8000://" + ORIGEN[len("postgresql://"):]

# Variables mínimas para poder importar los modelos sin tocar nada más
for k, v in {"DATABASE_URL": DESTINO, "GROQ_API_KEY": "x", "JWT_SECRET": "x", "WHATSAPP_TOKEN": "x",
             "WHATSAPP_PHONE_ID": "x", "VERIFY_TOKEN": "x", "SYNC_AUTOMATICO": "0", "DEBUG": "0"}.items():
    os.environ.setdefault(k, v)

import logging
logging.disable(logging.WARNING)
import main  # noqa: registra TODOS los modelos en Base.metadata
from models.database import Base
from sqlalchemy import create_engine, select, insert, text

if DESTINO.startswith("sqlite:///"):
    ruta = Path(DESTINO.replace("sqlite:///", ""))
    if ruta.exists():
        ruta.unlink()
        print(f"  (se reemplaza {ruta})")

print(f"🔌 Conectando a Railway…")
src = create_engine(ORIGEN, pool_pre_ping=True)
dst = create_engine(DESTINO)
Base.metadata.create_all(dst)

t0 = time.time()
total = 0
with src.connect() as cs, dst.begin() as cd:
    for tabla in Base.metadata.sorted_tables:
        try:
            cols_src = {c["name"] for c in __import__("sqlalchemy").inspect(src).get_columns(tabla.name)}
        except Exception:
            print(f"  · {tabla.name:28} (no existe en Railway, se salta)")
            continue
        cols = [c for c in tabla.columns if c.name in cols_src]
        filas = cs.execute(select(*cols)).mappings().all()
        if filas:
            cd.execute(insert(tabla), [dict(f) for f in filas])
        total += len(filas)
        print(f"  ✓ {tabla.name:28} {len(filas):>6} filas")

print(f"\n✅ Copia lista: {total} filas en {DESTINO}  ({time.time() - t0:.1f}s)")
print("   Ahora arranca el proyecto con DATABASE_URL apuntando a ese archivo (ver pasos).")