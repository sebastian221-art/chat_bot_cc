# 📄 ARCHIVO: backend/services/orchestrator_switch.py
"""
EL SWITCH — el interruptor de doble flujo.

Controla si un mensaje va por el flujo VIEJO (actual, intacto) o por el
NUEVO (orquestador). Tiene 3 modos:

  - "off"        → TODO va por el flujo viejo. Los clientes ni se enteran
                   de que el orquestador existe. (Estado inicial, seguro.)
  - "solo_yo"    → Solo los mensajes de prueba (número que empieza por el
                   prefijo de prueba, o el teléfono del desarrollador) van
                   por el orquestador. Los clientes reales siguen en el
                   flujo viejo. Ideal para probar sin riesgo.
  - "produccion" → TODOS los mensajes van por el orquestador.

El estado se guarda en la base de datos (tabla orchestrator_config) para
que se pueda cambiar desde el panel y persista entre reinicios.

Por diseño, si algo falla al leer el switch, SIEMPRE cae a "off" — nunca
manda clientes al flujo nuevo por accidente.
"""
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import Session
from models.database import Base


class OrchestratorConfig(Base):
    __tablename__ = "orchestrator_config"

    id    = Column(Integer, primary_key=True, index=True)
    modo  = Column(String(15), nullable=False, default="off")   # "off" | "solo_yo" | "produccion"
    # Teléfono(s) de prueba que SÍ pasan por el orquestador en modo
    # "solo_yo" — separados por coma. El prefijo "htest_" y "test_"
    # siempre cuenta como prueba también.
    telefonos_prueba = Column(String(300), nullable=True, default="")


def get_modo(db: Session) -> str:
    """Lee el modo actual del switch. Si algo falla, devuelve 'off' (seguro)."""
    try:
        cfg = db.query(OrchestratorConfig).filter(OrchestratorConfig.id == 1).first()
        if not cfg:
            return "off"
        return cfg.modo or "off"
    except Exception:
        return "off"


def get_config(db: Session) -> dict:
    cfg = db.query(OrchestratorConfig).filter(OrchestratorConfig.id == 1).first()
    if not cfg:
        return {"modo": "off", "telefonos_prueba": ""}
    return {"modo": cfg.modo, "telefonos_prueba": cfg.telefonos_prueba or ""}


def set_modo(db: Session, modo: str, telefonos_prueba: str = None) -> dict:
    if modo not in ("off", "solo_yo", "produccion"):
        raise ValueError(f"Modo inválido: {modo}")
    cfg = db.query(OrchestratorConfig).filter(OrchestratorConfig.id == 1).first()
    if not cfg:
        cfg = OrchestratorConfig(id=1, modo=modo, telefonos_prueba=telefonos_prueba or "")
        db.add(cfg)
    else:
        cfg.modo = modo
        if telefonos_prueba is not None:
            cfg.telefonos_prueba = telefonos_prueba
    db.commit()
    return {"modo": cfg.modo, "telefonos_prueba": cfg.telefonos_prueba or ""}


def debe_usar_orquestador(db: Session, phone_number: str) -> bool:
    """
    Decide, para ESTE mensaje, si va por el orquestador (True) o por el
    flujo viejo (False). Es la función que el webhook consulta.
    """
    modo = get_modo(db)

    if modo == "off":
        return False
    if modo == "produccion":
        return True

    # modo == "solo_yo": solo pruebas y teléfonos autorizados
    if phone_number.startswith("htest_") or phone_number.startswith("test_"):
        return True
    cfg = get_config(db)
    autorizados = [t.strip() for t in (cfg.get("telefonos_prueba") or "").split(",") if t.strip()]
    return phone_number in autorizados