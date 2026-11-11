"""
Configuración de Any 3.0 (variables de entorno, sin secretos en el código).

  ANY3_NUMEROS         números que atiende Any 3.0 (coma). Por defecto 3154559242. "todos" = todos.
                       "ninguno" = apagada.
  ANY3_LLM             modelo del cerebro y del redactor. Por defecto Claude Haiku si hay ANTHROPIC_API_KEY;
                       si no, Groq gpt-oss-120b.
  ANY3_LLM_VIGILANTE   modelo que revisa las respuestas (por defecto el mismo).
  ANY3_LLM_RESPALDO    modelo si el principal falla (por defecto Groq gpt-oss-120b).
  ANY3_VIGILANTE       "0" para apagar la revisión (no recomendado).
  ANY3_DIRECTORIO      auto | completo | compacto (compacto = ~3 veces menos tokens, para Groq con límite bajo).
"""
from __future__ import annotations

import os
from contextvars import ContextVar

GROQ = "groq:openai/gpt-oss-120b"
HAIKU = "anthropic:claude-haiku-5-5"


def _env(n: str, d: str = "") -> str:
    return (os.environ.get(n) or d).strip().strip("'\"").strip()


def _numero(n: str) -> str:
    d = "".join(c for c in (n or "") if c.isdigit())
    return "57" + d if len(d) == 10 else d


def numeros() -> set[str] | str:
    crudo = _env("ANY3_NUMEROS", "3154559242")
    if crudo.lower() in ("todos", "*"):
        return "todos"
    if crudo.lower() in ("ninguno", "0", "no", "off"):
        return set()
    return {_numero(x) for x in crudo.replace(";", ",").replace(" ", ",").split(",") if _numero(x)}


def atiende(telefono: str) -> bool:
    """¿Este cliente lo atiende Any 3.0? Nunca lanza error (ante la duda, Any 2.0)."""
    try:
        n = numeros()
        if n == "todos":
            return True
        return _numero(telefono) in n or (telefono or "") in n
    except Exception:
        return False


# Para el examen: probar otro modelo sin cambiar la variable de entorno (solo dentro de esa tarea)
MODELO_FORZADO: ContextVar[str] = ContextVar("any3_modelo", default="")


def modelo() -> str:
    return MODELO_FORZADO.get() or _env("ANY3_LLM") or (HAIKU if _env("ANTHROPIC_API_KEY") else GROQ)


def modelo_vigilante() -> str:
    return MODELO_FORZADO.get() or _env("ANY3_LLM_VIGILANTE") or modelo()


def respaldo() -> str:
    r = _env("ANY3_LLM_RESPALDO", GROQ)
    return "" if r == modelo() else r


def vigilante_activo() -> bool:
    return _env("ANY3_VIGILANTE", "1") != "0"


def directorio_modo() -> str:
    """ANY3_DIRECTORIO: completo (mejor), compacto (para límites bajos de tokens) o auto (completo y, si el
    proveedor lo rechaza por tamaño, compacto)."""
    m = _env("ANY3_DIRECTORIO", "auto").lower()
    return m if m in ("auto", "completo", "compacto") else "auto"
