"""
El vigilante: otra IA lee la respuesta YA TERMINADA junto con los datos verificados y dice si tiene algo grave
(inventa, contradice, no responde, niega lo que sí hay, locales que no son). El harness decide qué hacer:
quitar locales de la lista, reescribir una vez con la corrección, o usar la respuesta armada por código.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from . import config, llm


@dataclass
class Veredicto:
    ok: bool = True
    gravedad: str = "ninguna"
    problemas: list = field(default_factory=list)
    quitar: list = field(default_factory=list)
    correccion: str = ""
    error: str = ""         # el vigilante mismo falló (se deja pasar la respuesta: las guardias de código siguen)

    def dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v not in (None, "", [])}


def _prompt() -> str:
    with open(os.path.join(os.path.dirname(__file__), "prompts", "vigilante.md"), encoding="utf-8") as f:
        return f.read().strip()


def _recortar(hechos: dict, limite: int = 14000) -> str:
    t = json.dumps(hechos, ensure_ascii=False, default=str, indent=0)
    return t if len(t) <= limite else t[:limite] + "…(recortado)"


async def revisar(ctx, hechos: dict, texto: str, interpretacion: str = "") -> Veredicto:
    if not config.vigilante_activo() or not (texto or "").strip():
        return Veredicto()
    conversacion = "\n".join(("Cliente: " if t.rol == "user" else "Any: ") + t.texto[:300]
                             for t in ctx.historial[-4:])
    usuario = (f"CONVERSACIÓN PREVIA:\n{conversacion or '(primer mensaje)'}\n\n"
               f"MENSAJE DEL CLIENTE: {ctx.mensaje}\n"
               + (f"INTERPRETACIÓN: {interpretacion}\n" if interpretacion else "")
               + f"\nDATOS VERIFICADOS:\n{_recortar(hechos)}\n\nRESPUESTA A REVISAR:\n{texto}")
    try:
        import asyncio
        r = await asyncio.wait_for(llm.completar(
            [{"role": "system", "content": _prompt()}, {"role": "user", "content": usuario}],
            spec=config.modelo_vigilante(), json_salida=True, temperatura=0, max_tokens=1500, razonamiento="low",
            timeout_s=15), timeout=20)
        ctx.traza.llm("vigilante", r)
        j = r.json()
    except Exception as e:
        ctx.traza.alerta(f"el vigilante no pudo revisar: {e}")
        return Veredicto(error=str(e)[:200])
    v = Veredicto(ok=bool(j.get("ok", True)), gravedad=str(j.get("gravedad") or "ninguna").lower(),
                  problemas=[str(p) for p in (j.get("problemas") or [])][:6],
                  quitar=[str(n) for n in (j.get("quitar") or [])][:30],
                  correccion=str(j.get("correccion") or "")[:600])
    if v.gravedad != "grave" and not v.quitar:
        v.ok = True
    if v.gravedad == "grave" or v.quitar:
        v.ok = False
    return v
