"""
Flujo imagen: el cliente manda una foto de algo que busca (unos tenis, un vestido, una comida).
  1. Un modelo de visión describe QUÉ es y da los términos de búsqueda (JSON).
     Una marca muy icónica solo se menciona como referencia de estilo, nunca como "la tienen aquí".
  2. Con esos términos se usa la MISMA búsqueda de locales (lista completa, en orden, armada en código).
Si la foto no se puede analizar, se le pide que lo escriba con palabras.
"""
from __future__ import annotations

import base64

from ..config import cfg
from ..llm import completar
from ..nucleo.tipos import Contexto, Respuesta
from .base import Datos, Flujo, leer_prompt
from .locales import Locales


def _mime(imagen: bytes) -> str:
    if imagen[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if imagen[:4] == b"RIFF" and imagen[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


async def describir(ctx: Contexto) -> dict | None:
    datos = base64.b64encode(ctx.imagen).decode()
    contenido = [{"type": "text", "text": leer_prompt("flujos/imagen_vision.md")
                  + (f'\n\nEl cliente escribió junto a la foto: "{ctx.mensaje}"' if ctx.mensaje else "")},
                 {"type": "image_url", "image_url": {"url": f"data:{_mime(ctx.imagen)};base64,{datos}"}}]
    try:
        r = await completar(cfg().llm_vision, [{"role": "user", "content": contenido}], json_salida=True,
                            temperatura=0.2, max_tokens=400)
        ctx.traza.llm("vision", r)
        j = r.json()
    except Exception as e:
        ctx.traza.alerta(f"no se pudo analizar la foto: {e}")
        return None
    if not j.get("es_producto", True) or not (j.get("busqueda") or "").strip():
        return {"es_producto": False, "que_es": j.get("que_es")}
    return j


class Imagen(Flujo):
    nombre = "imagen"
    descripcion = "el cliente envió una foto para buscar algo parecido"
    temperatura = 0.5
    max_tokens = 450

    async def ejecutar(self, ctx: Contexto) -> Respuesta:
        if not ctx.imagen:
            return Respuesta("No me llegó la foto 😅 ¿Me la envías otra vez o me cuentas con palabras qué buscas?",
                             self.nombre)
        v = await describir(ctx)
        ctx.traza.paso("vision", v)
        if not v:
            return Respuesta("No pude ver bien la foto 😅 ¿Me cuentas con palabras qué buscas? Por ejemplo: "
                             "\"tenis blancos para correr\".", self.nombre)
        if not v.get("es_producto", True):
            return await Flujo.ejecutar(_Simple(self, Datos(hechos={
                "situacion": "la foto no muestra un producto que se pueda buscar en un local; dilo con amabilidad "
                             "y pregúntale qué busca", "en_la_foto_se_ve": v.get("que_es")})), ctx)
        # misma búsqueda de locales, con lo que se ve en la foto como categoría
        ctx.decision.entidades = {**(ctx.decision.entidades or {}), "categoria": v["busqueda"]}
        ctx.decision.consulta = v["busqueda"]
        r = await _LocalesDeFoto(v).ejecutar(ctx)
        r.flujo = self.nombre
        return r


class _LocalesDeFoto(Locales):
    def __init__(self, vision: dict):
        self.vision = vision

    def instrucciones(self) -> str:
        return leer_prompt("flujos/locales.md") + "\n\n" + leer_prompt("flujos/imagen.md")

    async def reunir(self, ctx):
        datos = await super().reunir(ctx)
        datos.hechos["lo_que_se_ve_en_la_foto"] = {k: self.vision.get(k) for k in
                                                   ("que_es", "color", "estilo", "referencia_de_estilo") if self.vision.get(k)}
        return datos


class _Simple(Flujo):
    def __init__(self, padre: Flujo, datos: Datos):
        self.nombre, self._datos = padre.nombre, datos

    async def reunir(self, ctx):
        return self._datos