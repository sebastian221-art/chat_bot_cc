"""
Llamadas al modelo para Any 3.0.

- Con Claude (anthropic:…) el directorio va en un bloque con caché: se cobra completo la primera vez y luego
  ~10 % mientras siga igual (cambia solo cuando se edita la base). También es más rápido.
- Con otro proveedor se usa el registro normal de Any 2.0.
- Si el modelo principal falla, se intenta con el de respaldo (ANY3_LLM_RESPALDO).

No modifica el adaptador de Any 2.0: hereda de él.
"""
from __future__ import annotations

import asyncio
import logging
import time

import httpx

from any.llm import ErrorLLM
from any.llm.anthropic import ESTADOS_REINTENTABLES, URL, VERSION, ClienteAnthropic, _traducir
from any.llm.base import LLMRespuesta
from any.llm.registro import cliente

from . import config

log = logging.getLogger("any3.llm")


class ClienteAnthropicConCache(ClienteAnthropic):
    """Igual al de Any 2.0, pero cada mensaje de sistema es un bloque y el primero (el directorio, que es lo
    grande y lo que no cambia) se marca para caché."""

    async def completar(self, mensajes, herramientas=None, json_salida=False, temperatura=0.3, max_tokens=900,
                        razonamiento=None) -> LLMRespuesta:
        if not self.clave:
            raise ErrorLLM("Falta la clave ANTHROPIC_API_KEY")
        sistemas = [m["content"] for m in mensajes if m["role"] == "system"]
        _, msgs = _traducir([m for m in mensajes if m["role"] != "system"])
        bloques = [{"type": "text", "text": s} for s in sistemas if s]
        if bloques and len(bloques[0]["text"]) > 6000:
            bloques[0]["cache_control"] = {"type": "ephemeral"}
        if json_salida:
            bloques.append({"type": "text", "text": "Responde SOLO con un objeto JSON válido, sin texto antes ni después."})
        cuerpo = {"model": self.modelo, "max_tokens": max_tokens, "temperature": temperatura,
                  "system": bloques, "messages": msgs}
        cab = {"x-api-key": self.clave, "anthropic-version": VERSION, "content-type": "application/json"}
        t0 = time.perf_counter()
        error = ""
        async with httpx.AsyncClient(timeout=self.timeout_s) as http:
            for intento in range(3):
                try:
                    r = await http.post(URL, json=cuerpo, headers=cab)
                except httpx.HTTPError as e:
                    error = f"red: {e}"
                else:
                    if r.status_code == 200:
                        datos = r.json()
                        resp = self._interpretar(datos, (time.perf_counter() - t0) * 1000)
                        uso = datos.get("usage") or {}
                        # los tokens leídos de caché cuentan aparte: se suman para que la traza muestre el total
                        resp.tokens_entrada += int(uso.get("cache_read_input_tokens") or 0) + \
                            int(uso.get("cache_creation_input_tokens") or 0)
                        resp.cache = int(uso.get("cache_read_input_tokens") or 0)
                        return resp
                    error = f"HTTP {r.status_code}: {r.text[:300]}"
                    if r.status_code not in ESTADOS_REINTENTABLES:
                        break
                if intento < 2:
                    await asyncio.sleep(0.6 * (2 ** intento))
        raise ErrorLLM(f"{self.nombre} falló: {error}")


def _cliente(spec: str, timeout_s: int):
    proveedor, modelo = spec.split(":", 1)
    if proveedor.strip().lower() == "anthropic":
        return ClienteAnthropicConCache(modelo, timeout_s)
    return cliente(spec)


async def completar(mensajes: list[dict], spec: str | None = None, json_salida: bool = False,
                    temperatura: float = 0.2, max_tokens: int = 900, razonamiento: str | None = "low",
                    timeout_s: int = 30, herramientas=None) -> LLMRespuesta:
    specs = [spec or config.modelo()]
    r = config.respaldo()
    if r and r not in specs:
        specs.append(r)
    errores = []
    for s in specs:
        try:
            return await _cliente(s, timeout_s).completar(mensajes, herramientas, json_salida, temperatura,
                                                          max_tokens, razonamiento)
        except ErrorLLM as e:
            log.warning("Any 3.0: el modelo %s falló: %s", s, e)
            errores.append(str(e))
        except Exception as e:     # cualquier otra cosa (red rara, formato) también pasa al respaldo
            log.warning("Any 3.0: el modelo %s falló: %r", s, e)
            errores.append(repr(e))
    raise ErrorLLM(" | ".join(errores))
