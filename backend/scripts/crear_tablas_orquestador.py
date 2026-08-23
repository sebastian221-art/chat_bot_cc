"""
scripts/crear_tablas_orquestador.py

Crea las 2 tablas nuevas del orquestador:
  - orchestrator_traces  (las trazas de cada decisión)
  - orchestrator_config  (el estado del switch)

Es seguro correrlo más de una vez (create_all no recrea tablas que ya
existen). No toca ninguna tabla existente.

Cómo correrlo (Railway → backend → Console):
    python scripts/crear_tablas_orquestador.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from models.database import engine, Base
from models.orchestrator_trace import OrchestratorTrace       # noqa: F401
from services.orchestrator_switch import OrchestratorConfig   # noqa: F401


def main():
    print("🔄  Creando tablas del orquestador...")
    Base.metadata.create_all(bind=engine, tables=[
        OrchestratorTrace.__table__,
        OrchestratorConfig.__table__,
    ])
    print("✅  Listo — orchestrator_traces y orchestrator_config creadas.")
    print("    El switch arranca en 'off' por defecto (nada cambia para los clientes).")


if __name__ == "__main__":
    main()