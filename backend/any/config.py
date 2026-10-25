"""
Configuración de Any 2.0. Todo sale de variables de entorno con valores por
defecto razonables; nada de secretos en el código.

Modelos: cada rol usa "proveedor:modelo". Proveedores: groq, openai,
anthropic, gemini, deepseek, local (cualquier servidor compatible con OpenAI).
  ANY_LLM_ROUTER   = modelo que decide el flujo         (por defecto Groq gpt-oss-120b)
  ANY_LLM_FLUJOS   = modelo que redacta en los flujos   (por defecto Groq gpt-oss-120b)
  ANY_LLM_RESPALDO = modelo si el principal falla       (vacío = sin respaldo)
  ANY_LLM_FLUJO_<NOMBRE> = modelo solo para un flujo (ej. ANY_LLM_FLUJO_LOCALES)
"""
import os
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

ZONA_HORARIA = ZoneInfo("America/Bogota")


def _env(nombre: str, defecto: str = "") -> str:
    return (os.environ.get(nombre) or defecto).strip()


def _int(nombre: str, defecto: int) -> int:
    try:
        return int(_env(nombre, str(defecto)))
    except ValueError:
        return defecto


@dataclass
class ConfigAny:
    llm_router: str = field(default_factory=lambda: _env("ANY_LLM_ROUTER", "groq:openai/gpt-oss-120b"))
    llm_flujos: str = field(default_factory=lambda: _env("ANY_LLM_FLUJOS", "groq:openai/gpt-oss-120b"))
    llm_respaldo: str = field(default_factory=lambda: _env("ANY_LLM_RESPALDO", ""))
    # Modelo que ve fotos (el mismo que usaba el sistema viejo, salvo que se cambie)
    llm_vision: str = field(default_factory=lambda: _env(
        "ANY_LLM_VISION", "groq:" + (_env("GROQ_VISION_MODEL") or "qwen/qwen3.6-27b")))

    historial_mensajes: int = field(default_factory=lambda: _int("ANY_HISTORIAL", 12))
    sesion_horas: int = field(default_factory=lambda: _int("ANY_SESION_HORAS", 4))
    max_vueltas_herramientas: int = field(default_factory=lambda: _int("ANY_MAX_VUELTAS", 4))
    timeout_llm_s: int = field(default_factory=lambda: _int("ANY_TIMEOUT_LLM", 25))

    verify_token: str = field(default_factory=lambda: _env("ANY_VERIFY_TOKEN") or _env("VERIFY_TOKEN"))
    # Permite usar /any/prueba sin sesión del panel (solo para pruebas locales)
    prueba_abierta: bool = field(default_factory=lambda: _env("ANY_PRUEBA_ABIERTA") == "1")

    def modelo_de_flujo(self, flujo: str) -> str:
        return _env(f"ANY_LLM_FLUJO_{flujo.upper()}", self.llm_flujos)


def cfg() -> ConfigAny:
    """Se lee en cada llamada: cambiar una variable de entorno no exige reiniciar el código de pruebas."""
    return ConfigAny()