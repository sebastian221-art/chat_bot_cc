"""
Any 3.0 — el agente. Vive AL LADO de Any 2.0 sin cambiarla.

    cerebro (lee TODO el directorio y entiende la pregunta)
      → datos verificados en código (los mismos de Any 2.0)
      → redactor (los mismos prompts de Any 2.0, ya pulidos)
      → vigilante (otra IA revisa la respuesta contra los datos; si algo está mal, se corrige o se usa la
        respuesta armada por código)
      → guardias de salida de Any 2.0

Solo atiende los números de ANY3_NUMEROS (por defecto el de Sebastián). Si algo falla, responde Any 2.0.
"""
from .config import atiende  # noqa: F401
