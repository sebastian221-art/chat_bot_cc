"""
Adaptador para cualquier API compatible con OpenAI (chat/completions):
Groq, OpenAI, Gemini (endpoint OpenAI), DeepSeek o un servidor local.
Usa httpx directo: sin SDKs que se desactualicen (el SDK groq==0.11 del
sistema viejo no aceptaba reasoning_effort).
"""
from __future__ import annotations

import asyncio
import json
import os
import time

import httpx

from .base import ClienteLLM, ErrorLLM, Herramienta, LlamadaHerramienta, LLMRespuesta

PROVEEDORES = {
    #            URL base                                                   variable de la clave
    "groq":     ("https://api.groq.com/openai/v1",                          "GROQ_API_KEY"),
    "openai":   ("https://api.openai.com/v1",                               "OPENAI_API_KEY"),
    "gemini":   ("https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY"),
    "deepseek": ("https://api.deepseek.com/v1",                             "DEEPSEEK_API_KEY"),
    "local":    (None,                                                      "ANY_LLM_LOCAL_KEY"),
}

REINTENTOS = 2          # además del primer intento
ESTADOS_REINTENTABLES = {408, 409, 429, 500, 502, 503, 504}


class ClienteOpenAICompat(ClienteLLM):
    def __init__(self, proveedor: str, modelo: str, timeout_s: int = 25):
        super().__init__(modelo)
        if proveedor not in PROVEEDORES:
            raise ErrorLLM(f"Proveedor desconocido: {proveedor}")
        self.proveedor = proveedor
        url, var_clave = PROVEEDORES[proveedor]
        self.url = (url or os.environ.get("ANY_LLM_LOCAL_URL", "")).rstrip("/")
        self.clave = os.environ.get(var_clave, "")
        self.timeout_s = timeout_s
        if not self.url:
            raise ErrorLLM("Falta ANY_LLM_LOCAL_URL para el proveedor local")

    def _es_modelo_razonador_openai(self) -> bool:
        m = self.modelo.lower()
        return self.proveedor == "openai" and (m.startswith("gpt-5") or m.startswith("o"))

    def _cuerpo(self, mensajes, herramientas, json_salida, temperatura, max_tokens, razonamiento) -> dict:
        cuerpo: dict = {"model": self.modelo, "messages": mensajes}
        if self._es_modelo_razonador_openai():
            # GPT-5 / o-series: no aceptan temperature y usan max_completion_tokens
            cuerpo["max_completion_tokens"] = max_tokens
            if razonamiento:
                cuerpo["reasoning_effort"] = razonamiento
        else:
            cuerpo["temperature"] = temperatura
            cuerpo["max_tokens"] = max_tokens
            if razonamiento and "gpt-oss" in self.modelo:
                cuerpo["reasoning_effort"] = razonamiento
        if herramientas:
            cuerpo["tools"] = [h.esquema_openai() for h in herramientas]
            cuerpo["tool_choice"] = "auto"
        if json_salida and not herramientas:
            cuerpo["response_format"] = {"type": "json_object"}
        return cuerpo

    async def completar(self, mensajes, herramientas: list[Herramienta] | None = None,
                        json_salida=False, temperatura=0.3, max_tokens=900, razonamiento=None) -> LLMRespuesta:
        if not self.clave and self.proveedor != "local":
            raise ErrorLLM(f"Falta la clave {PROVEEDORES[self.proveedor][1]}")
        cuerpo = self._cuerpo(mensajes, herramientas, json_salida, temperatura, max_tokens, razonamiento)
        cabeceras = {"Content-Type": "application/json"}
        if self.clave:
            cabeceras["Authorization"] = f"Bearer {self.clave}"

        t0 = time.perf_counter()
        ultimo_error = ""
        async with httpx.AsyncClient(timeout=self.timeout_s) as http:
            for intento in range(REINTENTOS + 1):
                try:
                    r = await http.post(f"{self.url}/chat/completions", json=cuerpo, headers=cabeceras)
                except httpx.HTTPError as e:
                    ultimo_error = f"red: {e}"
                else:
                    if r.status_code == 200:
                        return self._interpretar(r.json(), (time.perf_counter() - t0) * 1000)
                    ultimo_error = f"HTTP {r.status_code}: {r.text[:300]}"
                    # Groq a veces rechaza response_format o tool_choice con 400: se reintenta sin ellos
                    if r.status_code == 400 and ("response_format" in r.text or "json" in r.text.lower()):
                        cuerpo.pop("response_format", None)
                    elif r.status_code not in ESTADOS_REINTENTABLES:
                        break
                if intento < REINTENTOS:
                    await asyncio.sleep(0.6 * (2 ** intento))
        raise ErrorLLM(f"{self.nombre} falló: {ultimo_error}")

    def _interpretar(self, datos: dict, ms: float) -> LLMRespuesta:
        try:
            msg = datos["choices"][0]["message"]
        except (KeyError, IndexError) as e:
            raise ErrorLLM(f"Respuesta inesperada de {self.nombre}: {str(datos)[:300]}") from e
        llamadas = []
        for tc in msg.get("tool_calls") or []:
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            llamadas.append(LlamadaHerramienta(id=tc.get("id", ""), nombre=tc["function"]["name"], argumentos=args))
        uso = datos.get("usage") or {}
        return LLMRespuesta(texto=(msg.get("content") or "").strip(), llamadas=llamadas, modelo=self.nombre,
                            tokens_entrada=uso.get("prompt_tokens", 0), tokens_salida=uso.get("completion_tokens", 0),
                            ms=ms)
