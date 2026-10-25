"""
Tipos comunes del adaptador de modelos. Todos los proveedores hablan este
mismo idioma, así que cambiar de modelo es cambiar una variable de entorno.

Los mensajes usan el formato de OpenAI (es el más extendido):
  {"role": "system"|"user"|"assistant"|"tool", "content": "...",
   "tool_calls": [...], "tool_call_id": "..."}
Cada adaptador lo traduce al formato de su proveedor.
"""
from __future__ import annotations

import inspect
import json
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


class ErrorLLM(Exception):
    """El proveedor falló (red, cuota, clave, respuesta inválida)."""


@dataclass
class Herramienta:
    """Una herramienta que el modelo puede pedir. Siempre devuelve DATOS, nunca el texto final."""
    nombre: str
    descripcion: str
    parametros: dict                      # JSON Schema de los argumentos
    funcion: Callable[..., Any | Awaitable[Any]]

    def esquema_openai(self) -> dict:
        return {"type": "function",
                "function": {"name": self.nombre, "description": self.descripcion,
                             "parameters": self.parametros}}

    async def ejecutar(self, argumentos: dict) -> Any:
        r = self.funcion(**(argumentos or {}))
        if inspect.isawaitable(r):
            r = await r
        return r


@dataclass
class LlamadaHerramienta:
    id: str
    nombre: str
    argumentos: dict


@dataclass
class LLMRespuesta:
    texto: str = ""
    llamadas: list[LlamadaHerramienta] = field(default_factory=list)
    modelo: str = ""
    tokens_entrada: int = 0
    tokens_salida: int = 0
    ms: float = 0.0

    def json(self) -> dict:
        """Interpreta el texto como JSON (tolera ```json … ``` y texto alrededor)."""
        t = (self.texto or "").strip()
        if t.startswith("```"):
            t = t.strip("`")
            if t.lower().startswith("json"):
                t = t[4:]
        ini, fin = t.find("{"), t.rfind("}")
        if ini < 0 or fin <= ini:
            raise ErrorLLM(f"El modelo no devolvió JSON: {self.texto[:200]!r}")
        try:
            return json.loads(t[ini:fin + 1])
        except json.JSONDecodeError as e:
            raise ErrorLLM(f"JSON inválido del modelo: {e}") from e


class ClienteLLM:
    """Interfaz que implementa cada proveedor."""
    proveedor: str = ""

    def __init__(self, modelo: str):
        self.modelo = modelo

    async def completar(self, mensajes: list[dict], herramientas: list[Herramienta] | None = None,
                        json_salida: bool = False, temperatura: float = 0.3,
                        max_tokens: int = 900, razonamiento: str | None = None) -> LLMRespuesta:
        raise NotImplementedError

    @property
    def nombre(self) -> str:
        return f"{self.proveedor}:{self.modelo}"
