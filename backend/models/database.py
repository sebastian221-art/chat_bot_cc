import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from config import get_settings

settings = get_settings()

# Railway (y Heroku) a veces entregan la URL de Postgres con el prefijo
# "postgres://", pero SQLAlchemy 1.4+/2.0 solo acepta "postgresql://".
# Además forzamos el driver pg8000 (100% Python, sin dependencias
# nativas) para evitar el error "libpq.so.5 not found" que da
# psycopg2-binary en algunos builders de contenedores como Railpack.
db_url = settings.DATABASE_URL
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+pg8000://", 1)
elif db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+pg8000://", 1)

connect_args = {}
# El SQL de cada consulta en el log solo si se pide con SQL_ECHO=1. Con DEBUG=true en Railway se imprimían cientos
# de líneas por segundo: Railway descartaba logs («rate limit of 500 logs/sec») y el servidor gastaba CPU en eso.
engine_kwargs = {"echo": os.environ.get("SQL_ECHO", "").strip() in ("1", "true")}

if db_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
else:
    # Buena práctica para Postgres en la nube: evita errores por
    # conexiones que el proveedor cierra en silencio por inactividad.
    engine_kwargs["pool_pre_ping"] = True
    engine_kwargs["pool_recycle"] = 1800      # renueva conexiones cada 30 min (el proveedor corta las viejas)
    # Una consulta o conexión colgada ya no puede trancar a Any para siempre: a los 30 s da error y se sigue.
    if "pg8000" in db_url:
        connect_args = {"timeout": int(os.environ.get("DB_TIMEOUT_S", "30"))}

engine = create_engine(db_url, connect_args=connect_args, **engine_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    Base.metadata.create_all(bind=engine)