"""
Punto único para pedirle algo a un modelo.

    from any.llm.registro import completar
    r = await completar("groq:openai/gpt-oss-120b", mensajes, json_salida=True)

Si el modelo principal falla y hay ANY_LLM_RESPALDO, se intenta con ese.
"""
from __future__ import annotations

import logging

from ..config import cfg
from .base import ClienteLLM, ErrorLLM, Herramienta, LLMRespuesta

log = logging.getLogger("any.llm")


def cliente(spec: str) -> ClienteLLM:
    """'proveedor:modelo' → cliente. El modelo puede contener ':' o '/'."""
    if ":" not in spec:
        raise ErrorLLM(f"Modelo mal escrito: {spec!r} (formato proveedor:modelo)")
    proveedor, modelo = spec.split(":", 1)
    proveedor = proveedor.strip().lower()
    t = cfg().timeout_llm_s
    if proveedor == "anthropic":
        from .anthropic import ClienteAnthropic
        return ClienteAnthropic(modelo, t)
    if proveedor == "simulado":
        from .simulado import ClienteSimulado
        return ClienteSimulado(modelo)
    from .openai_compat import ClienteOpenAICompat
    return ClienteOpenAICompat(proveedor, modelo, t)


async def completar(spec: str, mensajes: list[dict], herramientas: list[Herramienta] | None = None,
                    json_salida: bool = False, temperatura: float = 0.3, max_tokens: int = 900,
                    razonamiento: str | None = None) -> LLMRespuesta:
    specs = [spec]
    respaldo = cfg().llm_respaldo
    if respaldo and respaldo != spec:
        specs.append(respaldo)
    errores = []
    for s in specs:
        try:
            return await cliente(s).completar(mensajes, herramientas, json_salida, temperatura,
                                              max_tokens, razonamiento)
        except ErrorLLM as e:
            log.warning("LLM %s falló: %s", s, e)
            errores.append(str(e))
    raise ErrorLLM(" | ".join(errores))
