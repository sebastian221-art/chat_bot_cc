"""
Contrato de un flujo (especialista). Cada tema vive en su propio archivo y
solo implementa tres cosas:

    class MiFlujo(Flujo):
        nombre = "mi_flujo"
        descripcion = "qué atiende (lo lee el router)"
        async def reunir(self, ctx) -> Datos:      # datos verificados, en código, sin IA
        def herramientas(self, ctx) -> list:       # 0 a 4 herramientas para que el modelo busque más

El resto lo pone esta base, igual para todos:
  1. reunir datos verificados (determinista, probado por separado);
  2. armar el prompt: persona única + instrucciones del flujo (prompts/flujos/<nombre>.md)
     + datos verificados + historial;
  3. dejar que el modelo redacte, pidiendo herramientas si le faltan datos
     (máximo N vueltas; la última vuelta SIEMPRE obliga a responder con texto:
     así no se repite la falla del agente v1 que se quedaba sin respuesta);
  4. devolver la Respuesta con los adjuntos que el flujo decidió en código.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from ..config import cfg
from ..llm import ErrorLLM, Herramienta, completar
from ..nucleo.tipos import Adjunto, Contexto, Respuesta

_PROMPTS = os.path.join(os.path.dirname(__file__), "..", "prompts")
_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
          "octubre", "noviembre", "diciembre"]


def leer_prompt(nombre: str) -> str:
    ruta = os.path.join(_PROMPTS, nombre)
    if not os.path.exists(ruta):
        return ""
    with open(ruta, encoding="utf-8") as f:
        return f.read().strip()


def persona(ctx: Contexto) -> str:
    a = ctx.ahora
    saludo = ("Es el PRIMER mensaje de esta sesión: preséntate brevemente como Any al responder."
              if ctx.sesion_nueva else
              "La conversación ya está en curso: NO te vuelvas a presentar ni a saludar como si fuera nueva.")
    nombre = ctx.nombre_real
    cliente = f"- El cliente se llama {nombre}." if nombre else "- No sabes el nombre del cliente: no uses ninguno."
    return leer_prompt("persona.md").format(
        saludo=saludo, dia_semana=_DIAS[a.weekday()], fecha=f"{a.day} de {_MESES[a.month - 1]} de {a.year}",
        hora=a.strftime("%I:%M %p").lstrip("0").lower(), cliente=cliente)


@dataclass
class Datos:
    """Lo que el flujo reunió en código. `hechos` va al modelo; `adjuntos` se envían tal cual."""
    hechos: dict = field(default_factory=dict)
    adjuntos: list[Adjunto] = field(default_factory=list)
    entidades: dict = field(default_factory=dict)        # para recordar en el siguiente turno
    respuesta_directa: str | None = None                 # si se puede responder sin IA (raro)
    meta: dict = field(default_factory=dict)             # para guardias: lista_equidad, telefonos_validos…


class Flujo:
    nombre: str = ""
    descripcion: str = ""
    con_estado: bool = False
    temperatura: float = 0.5
    max_tokens: int = 700

    async def reunir(self, ctx: Contexto) -> Datos:
        return Datos()

    def herramientas(self, ctx: Contexto) -> list[Herramienta]:
        return []

    def instrucciones(self) -> str:
        return leer_prompt(f"flujos/{self.nombre}.md")

    def respaldo(self, ctx: Contexto, datos: Datos) -> str | None:
        """Texto si el modelo falla. None = mensaje de error técnico general."""
        return None

    def componer(self, ctx: Contexto, datos: Datos, texto: str) -> str:
        """Último paso del flujo: puede insertar en código lo que no debe redactar la IA (p. ej. una lista)."""
        return texto

    # ── Ejecución común ───────────────────────────────────────────

    def _mensajes(self, ctx: Contexto, datos: Datos) -> list[dict]:
        hechos = dict(datos.hechos)
        if datos.adjuntos:
            hechos["se_adjunta"] = [_describir(a) for a in datos.adjuntos]
        if ctx.promo and not datos.meta.get("sin_promo"):
            hechos["novedad_de_pasada"] = ctx.promo["datos"]
            hechos["como_mencionar_la_novedad"] = ("Al final, en UNA línea aparte que empiece con \"De paso:\", menciona "
                                                    "esta novedad con su nombre y sus datos clave. Sin exagerar y sin "
                                                    "inventar nada más.")
        sistema = persona(ctx) + "\n\n" + self.instrucciones()
        msgs = [{"role": "system", "content": sistema},
                {"role": "system", "content": "DATOS VERIFICADOS (única fuente de verdad para este turno):\n"
                                              + json.dumps(hechos, ensure_ascii=False, indent=1, default=str)}]
        for t in ctx.historial[-cfg().historial_mensajes:]:
            msgs.append({"role": t.rol, "content": t.texto})
        consulta = ctx.decision.consulta if ctx.decision and ctx.decision.consulta else ""
        contenido = ctx.mensaje
        if consulta and consulta.strip().lower() != ctx.mensaje.strip().lower():
            contenido += f"\n\n(Interpretación con el contexto: {consulta})"
        msgs.append({"role": "user", "content": contenido})
        return msgs

    async def ejecutar(self, ctx: Contexto) -> Respuesta:
        datos = await self.reunir(ctx)
        ctx.traza.paso("datos_reunidos", {"flujo": self.nombre, "hechos": datos.hechos,
                                          "adjuntos": [a.dict() for a in datos.adjuntos]})
        if datos.respuesta_directa:
            return Respuesta(self.componer(ctx, datos, datos.respuesta_directa), self.nombre, datos.adjuntos, entidades=datos.entidades,
                             meta=datos.meta)
        herramientas = self.herramientas(ctx)
        por_nombre = {h.nombre: h for h in herramientas}
        msgs = self._mensajes(ctx, datos)
        modelo = cfg().modelo_de_flujo(self.nombre)
        vueltas = max(1, cfg().max_vueltas_herramientas)
        texto = ""
        try:
            for vuelta in range(vueltas):
                ultima = vuelta == vueltas - 1
                r = await completar(modelo, msgs, herramientas=None if ultima else (herramientas or None),
                                    temperatura=self.temperatura, max_tokens=self.max_tokens, razonamiento="low")
                ctx.traza.llm(f"flujo_{self.nombre}", r)
                if not r.llamadas:
                    texto = r.texto
                    break
                msgs.append({"role": "assistant", "content": r.texto or "",
                             "tool_calls": [{"id": c.id, "type": "function",
                                             "function": {"name": c.nombre,
                                                          "arguments": json.dumps(c.argumentos, ensure_ascii=False)}}
                                            for c in r.llamadas]})
                for c in r.llamadas:
                    h = por_nombre.get(c.nombre)
                    try:
                        resultado = await h.ejecutar(c.argumentos) if h else {"error": "herramienta desconocida"}
                    except Exception as e:  # una herramienta rota no tumba la respuesta
                        resultado = {"error": f"falló la consulta: {e}"}
                    ctx.traza.paso("herramienta", {"nombre": c.nombre, "argumentos": c.argumentos,
                                                   "resultado": resultado})
                    msgs.append({"role": "tool", "tool_call_id": c.id,
                                 "content": json.dumps(resultado, ensure_ascii=False, default=str)[:6000]})
        except ErrorLLM as e:
            ctx.traza.alerta(f"modelo falló en {self.nombre}: {e}")
            texto = self.respaldo(ctx, datos) or ""
            datos.meta["respaldo"] = True
        texto = self.componer(ctx, datos, texto)
        return Respuesta(texto, self.nombre, datos.adjuntos, entidades=datos.entidades, meta=datos.meta)


def _describir(a: Adjunto) -> str:
    if a.tipo == "ubicacion":
        return f"pin de ubicación de WhatsApp: {a.titulo} ({a.direccion})"
    if a.tipo == "documento":
        return f"documento PDF: {a.nombre_archivo or 'archivo'}"
    return f"foto: {a.leyenda or 'imagen'}"