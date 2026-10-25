"""
Adaptador para la API de Claude (Anthropic Messages). Traduce el formato
OpenAI que usa el resto del sistema al formato de Anthropic y de vuelta.
"""
from __future__ import annotations

import asyncio
import json
import os
import time

import httpx

from .base import ClienteLLM, ErrorLLM, Herramienta, LlamadaHerramienta, LLMRespuesta

URL = "https://api.anthropic.com/v1/messages"
VERSION = "2023-06-01"
ESTADOS_REINTENTABLES = {408, 429, 500, 502, 503, 504, 529}


def _contenido(c):
    """Texto o lista OpenAI (texto + image_url en data URI) → bloques de Anthropic."""
    if not isinstance(c, list):
        return c
    bloques = []
    for b in c:
        if b.get("type") == "text":
            bloques.append({"type": "text", "text": b["text"]})
        elif b.get("type") == "image_url":
            url = b["image_url"]["url"]
            if url.startswith("data:") and ";base64," in url:
                media, datos = url[5:].split(";base64,", 1)
                bloques.append({"type": "image", "source": {"type": "base64", "media_type": media, "data": datos}})
            else:
                bloques.append({"type": "image", "source": {"type": "url", "url": url}})
    return bloques


def _traducir(mensajes: list[dict]) -> tuple[str, list[dict]]:
    sistema, salida = [], []
    for m in mensajes:
        rol = m["role"]
        if rol == "system":
            sistema.append(m["content"])
        elif rol == "user":
            salida.append({"role": "user", "content": _contenido(m["content"])})
        elif rol == "assistant":
            bloques = []
            if m.get("content"):
                bloques.append({"type": "text", "text": m["content"]})
            for tc in m.get("tool_calls") or []:
                args = tc["function"].get("arguments") or "{}"
                bloques.append({"type": "tool_use", "id": tc["id"], "name": tc["function"]["name"],
                                "input": json.loads(args) if isinstance(args, str) else args})
            salida.append({"role": "assistant", "content": bloques or ""})
        elif rol == "tool":
            bloque = {"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": m["content"]}
            # Anthropic exige que los resultados vayan en un turno de usuario
            if salida and salida[-1]["role"] == "user" and isinstance(salida[-1]["content"], list):
                salida[-1]["content"].append(bloque)
            else:
                salida.append({"role": "user", "content": [bloque]})
    return "\n\n".join(sistema), salida


class ClienteAnthropic(ClienteLLM):
    proveedor = "anthropic"

    def __init__(self, modelo: str, timeout_s: int = 25):
        super().__init__(modelo)
        self.clave = os.environ.get("ANTHROPIC_API_KEY", "")
        self.timeout_s = timeout_s

    async def completar(self, mensajes, herramientas: list[Herramienta] | None = None,
                        json_salida=False, temperatura=0.3, max_tokens=900, razonamiento=None) -> LLMRespuesta:
        if not self.clave:
            raise ErrorLLM("Falta la clave ANTHROPIC_API_KEY")
        sistema, msgs = _traducir(mensajes)
        if json_salida:
            sistema += "\n\nResponde SOLO con un objeto JSON válido, sin texto antes ni después."
        cuerpo: dict = {"model": self.modelo, "max_tokens": max_tokens, "temperature": temperatura,
                        "system": sistema, "messages": msgs}
        if herramientas:
            cuerpo["tools"] = [{"name": h.nombre, "description": h.descripcion, "input_schema": h.parametros}
                               for h in herramientas]
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
                        return self._interpretar(r.json(), (time.perf_counter() - t0) * 1000)
                    error = f"HTTP {r.status_code}: {r.text[:300]}"
                    if r.status_code not in ESTADOS_REINTENTABLES:
                        break
                if intento < 2:
                    await asyncio.sleep(0.6 * (2 ** intento))
        raise ErrorLLM(f"{self.nombre} falló: {error}")

    def _interpretar(self, datos: dict, ms: float) -> LLMRespuesta:
        textos, llamadas = [], []
        for b in datos.get("content", []):
            if b.get("type") == "text":
                textos.append(b["text"])
            elif b.get("type") == "tool_use":
                llamadas.append(LlamadaHerramienta(id=b["id"], nombre=b["name"], argumentos=b.get("input") or {}))
        uso = datos.get("usage") or {}
        return LLMRespuesta(texto="\n".join(textos).strip(), llamadas=llamadas, modelo=self.nombre,
                            tokens_entrada=uso.get("input_tokens", 0), tokens_salida=uso.get("output_tokens", 0), ms=ms)