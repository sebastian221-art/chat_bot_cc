"""Flujo conversación: saludos, despedidas, agradecimientos, preguntas sobre Any y temas fuera del mall."""
from __future__ import annotations

from ..nucleo.tipos import Contexto
from .base import Datos, Flujo


class Conversacion(Flujo):
    nombre = "conversacion"
    descripcion = ("saludos, despedidas, agradecimientos, preguntas sobre Any, charla y temas que NO son "
                   "del centro comercial (trivia, tareas, política, chistes)")
    temperatura = 0.7
    max_tokens = 300

    async def reunir(self, ctx: Contexto) -> Datos:
        return Datos(hechos={
            "centro_comercial": "Centro Comercial El Puente, San Gil (Santander)",
            "en_que_ayuda_any": ["encontrar locales y qué venden", "dónde comer", "cartelera y boletas de cine",
                                 "eventos y sorteos del mes", "horarios, parqueadero, wifi y servicios",
                                 "Torre Médica", "domicilios de los locales"],
        })

    def respaldo(self, ctx, datos):
        nombre = f", {ctx.nombre_real}" if ctx.nombre_real else ""
        return f"¡Hola{nombre}! Soy Any 🛍️, del Centro Comercial El Puente. ¿En qué te ayudo?"
