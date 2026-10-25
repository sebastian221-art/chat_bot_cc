"""
Flujo servicios del mall: horario general, dirección y pin, parqueadero, wifi,
baños, cajeros, mascotas, punto de información y demás info general.
Los datos salen de mall_info, info_points y la base de conocimiento (panel).
"""
from __future__ import annotations

from ..conocimiento.buscador import buscar_conocimiento, conceptos
from ..conocimiento.servicios import info_mall
from ..llm import Herramienta
from ..nucleo.tipos import Adjunto, Contexto
from .base import Datos, Flujo


class ServiciosMall(Flujo):
    nombre = "servicios_mall"
    descripcion = ("información general del centro comercial: horario general, dirección y cómo llegar, "
                   "parqueadero, wifi, baños, cajeros, mascotas, punto de información, pisos/niveles")
    temperatura = 0.4

    def _consulta(self, ctx: Contexto) -> str:
        d = ctx.decision
        partes = [d.consulta if d and d.consulta else ctx.mensaje]
        if d and d.entidades.get("servicio"):
            partes.append(str(d.entidades["servicio"]))
        return " ".join(partes)

    async def reunir(self, ctx: Contexto) -> Datos:
        consulta = self._consulta(ctx)
        frags = buscar_conocimiento(ctx.db, consulta, k=4)
        info = info_mall(ctx.db)
        grupos = {c.grupo for c in conceptos(consulta, "servicios") if c.grupo}
        hechos = {"fragmentos_relevantes": [f.dict() for f in frags]}
        datos = Datos(hechos=hechos, entidades={"servicio": sorted(grupos)} if grupos else {})
        if "horario" in grupos and info.get("horario_general"):
            hechos["horario_general"] = info["horario_general"]
        if "ubicacion" in grupos:
            hechos["direccion"] = info.get("direccion") or "no tengo la dirección exacta"
            if info.get("latitud") and info.get("longitud"):
                datos.adjuntos.append(Adjunto(tipo="ubicacion", latitud=info["latitud"], longitud=info["longitud"],
                                              titulo=info.get("nombre", "Centro Comercial El Puente"),
                                              direccion=info.get("direccion", "")))
        if not frags and len(hechos) == 1:
            hechos["nota"] = "No hay información verificada para esta pregunta."
            hechos["linea_centro_comercial"] = "317 432 0138 · https://wa.me/573174320138"
        return datos

    def herramientas(self, ctx: Contexto) -> list[Herramienta]:
        db = ctx.db
        return [Herramienta(
            nombre="buscar_info_mall",
            descripcion="Busca en la información oficial del centro comercial (servicios, políticas, horarios, "
                        "puntos de interés). Úsala solo si los datos entregados no responden la pregunta.",
            parametros={"type": "object", "properties": {"consulta": {"type": "string"}}, "required": ["consulta"]},
            funcion=lambda consulta: {"resultados": [f.dict() for f in buscar_conocimiento(db, consulta, k=4)]},
        )]

    def respaldo(self, ctx, datos):
        frags = datos.hechos.get("fragmentos_relevantes") or []
        if frags:
            return frags[0]["contenido"]
        return None
