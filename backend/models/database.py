from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from config import get_settings

settings = get_settings()

# Railway (y Heroku) a veces entregan la URL de Postgres con el prefijo
# "postgres://", pero SQLAlchemy 1.4+/2.0 solo acepta "postgresql://".
# Lo corregimos automáticamente para que funcione sin importar cuál
# formato entregue el proveedor.
db_url = settings.DATABASE_URL
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

connect_args = {}
engine_kwargs = {"echo": settings.DEBUG}

if db_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
else:
    # Buena práctica para Postgres en la nube: evita errores por
    # conexiones que el proveedor cierra en silencio por inactividad.
    engine_kwargs["pool_pre_ping"] = True

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