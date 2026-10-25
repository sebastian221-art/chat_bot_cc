"""
Modelo simulado: permite probar TODO el recorrido (router, flujos, guardias,
trazas, envío) sin clave y sin gastar. Se usa con "simulado:<lo-que-sea>".

Por defecto:
  - si piden JSON (router) → usa `router_por_defecto`, un clasificador por
    palabras SOLO para pruebas de plomería (no es la lógica real de Any);
  - si piden texto → devuelve los datos que el flujo le entregó, para poder
    verificar que el flujo reunió lo correcto.
Las pruebas pueden reemplazar `MANEJADOR` por su propia función.
"""
from __future__ import annotations

import json
import re

from .base import ClienteLLM, LLMRespuesta

MANEJADOR = None   # función(mensajes, herramientas, json_salida) -> LLMRespuesta


_PISTAS = [
    ("emergencia_queja", r"robaron|incendio|accidente|herid|queja|reclamo|pésimo|pesimo|mal servicio"),
    ("cine", r"cine|pel[ií]cula|boleta|cartelera|funci[oó]n"),
    ("torre_medica", r"m[eé]dic|consultorio|pediatr|odont|vacun|laboratorio|doctor"),
    ("sorteos_promos", r"sorteo|factura|premio|promo|descuento"),
    ("eventos", r"evento|concurso|disfraz|run run|carrera|misa|festival"),
    ("administracion", r"alquil|arrend|empleo|trabajo|pauta|proveedor|sal[oó]n"),
    ("domicilios", r"domicilio|pedido|a domicilio"),
    ("servicios_mall", r"horario|parqueader|wifi|ba[ñn]o|cajero|mascota|direcci[oó]n|ubicaci[oó]n|"
                       r"c[oó]mo llego|abren|cierran|nivel|piso|punto de informaci"),
    ("conversacion", r"^(hola|buenas|gracias|chao|adi[oó]s|ok|listo)\b"),
]


def router_por_defecto(mensajes: list[dict]) -> dict:
    texto = ""
    for m in reversed(mensajes):
        if m["role"] == "user":
            texto = m["content"].lower()
            break
    # el prompt del router pone el mensaje del cliente después de "MENSAJE:"
    if "mensaje:" in texto:
        texto = texto.rsplit("mensaje:", 1)[1]
    texto = texto.strip()
    flujo = "locales"
    for nombre, patron in _PISTAS:
        if re.search(patron, texto):
            flujo = nombre
            break
    return {"flujo": flujo, "entidades": {}, "es_seguimiento": False,
            "consulta_reescrita": texto, "razon": "simulado por palabras"}


class ClienteSimulado(ClienteLLM):
    proveedor = "simulado"

    async def completar(self, mensajes, herramientas=None, json_salida=False, temperatura=0.3,
                        max_tokens=900, razonamiento=None) -> LLMRespuesta:
        if MANEJADOR:
            return MANEJADOR(mensajes, herramientas, json_salida)
        if json_salida:
            return LLMRespuesta(texto=json.dumps(router_por_defecto(mensajes), ensure_ascii=False),
                                modelo=self.nombre)
        datos = ""
        for m in mensajes:
            if m["role"] == "system" and "DATOS VERIFICADOS" in m["content"]:
                datos = m["content"].split("DATOS VERIFICADOS", 1)[1]
        return LLMRespuesta(texto=f"[simulado] {datos.strip()[:1500]}", modelo=self.nombre)
