"""
Flujo servicios del mall: horario general, dirección y pin, parqueadero, wifi,
baños, cajeros, mascotas, punto de información y demás info general.
Los datos salen de mall_info, info_points y la base de conocimiento (panel).
"""
from __future__ import annotations
import re

from ..conocimiento.buscador import buscar_conocimiento, conceptos
from ..conocimiento.servicios import info_mall
from ..conocimiento.texto import normalizar
from ..llm import Herramienta
from ..nucleo.tipos import Adjunto, Contexto
from .base import Datos, Flujo


_PIDE_FINANCIERO = re.compile(r"\bbanc|\bcajer|financ|cooperativ|corresponsal|credito|prestamo|consignar|consignacion|"
                              r"retirar plata|retiro de dinero|giros?\b|envio de dinero|pagar (?:recibos|facturas)")
_ES_FINANCIERO = re.compile(r"entidades financieras|cooperativa|corresponsal|bancari|\bbanco\b|ahorro y credito")


def entidades_financieras(db) -> list[dict]:
    from ..conocimiento.catalogo import locales
    out = []
    for l in locales(db, incluir_torre=True, incluir_servicios=False):
        t = normalizar(f"{l.rubro or ''} {' '.join(l.productos)} {(l.descripcion or '')[:200]}")
        if _ES_FINANCIERO.search(t):
            d = {"nombre": l.nombre, "zona": l.zona, "que_hace": ", ".join(l.productos[:8])[:200]}
            if l.piso:
                d["piso"] = l.piso
            if l.whatsapp:
                d["whatsapp"] = l.whatsapp
            out.append(d)
    return sorted(out, key=lambda d: normalizar(d["nombre"]))[:12]


class ServiciosMall(Flujo):
    nombre = "servicios_mall"
    descripcion = ("información general del centro comercial: horario general, dirección y cómo llegar, "
                   "parqueadero (tarifas, mensualidad, horas gratis por compras, cargadores para carros eléctricos), wifi, "
                   "baños, cajeros automáticos, mascotas, "
                   "punto de información, tarjetas bono regalo, auditorio y salones para eventos, pisos/niveles")
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
        from ..conocimiento.texto import normalizar
        if __import__("re").search(r"cuant\w* (locales|tiendas)|numero de (locales|tiendas)|(locales|tiendas) (hay|tiene)",
                                   normalizar(ctx.mensaje)):
            from ..conocimiento.catalogo import locales
            todos = locales(ctx.db)
            hechos["cantidad_de_locales"] = {"locales_comerciales": len([l for l in todos if not l.es_torre and not l.es_servicio]),
                                             "oficinas_y_consultorios_de_la_torre": len([l for l in todos if l.es_torre])}
        datos = Datos(hechos=hechos, entidades={"servicio": sorted(grupos)} if grupos else {})
        if _PIDE_FINANCIERO.search(normalizar(f"{ctx.mensaje} {consulta}")):
            # «¿Qué bancos hay?»: además de los cajeros, los locales financieros (corresponsal, cooperativa…).
            # Antes solo salía el dato de los cajeros y Any decía «no hay sucursales» sin saberlo.
            fin = entidades_financieras(ctx.db)
            if fin:
                hechos["entidades_financieras_del_centro_comercial"] = fin
                hechos["como_responder_bancos"] = (
                    "Da los cajeros Y estas entidades financieras (nombre, zona, qué hacen y WhatsApp si viene). "
                    "Si preguntan por la sucursal u oficina de un banco que no aparece aquí, di que no tienes "
                    "registrada una sucursal de ese banco (no afirmes que no existe) y ofrece lo que sí hay.")
        if "horario" in grupos and info.get("horario_general"):
            hechos["horario_general"] = info["horario_general"]
        if "parqueadero" in grupos and info.get("parqueadero"):
            hechos["parqueadero_oficial"] = info["parqueadero"]     # tal cual lo escribió el centro comercial
        if "wifi" in grupos and info.get("wifi"):
            hechos["wifi_oficial"] = info["wifi"]
        if "ubicacion" in grupos:
            hechos["direccion"] = info.get("direccion") or "no tengo la dirección exacta"
            if info.get("latitud") and info.get("longitud"):
                datos.adjuntos.append(Adjunto(tipo="ubicacion", latitud=info["latitud"], longitud=info["longitud"],
                                              titulo=info.get("nombre", "Centro Comercial El Puente"),
                                              direccion=info.get("direccion", "")))
        sin_dato = {"wifi": not info.get("wifi"), "cajero": True, "baño": True}
        faltan = [g for g in ("wifi", "cajero", "baño") if g in grupos and sin_dato[g]]
        if faltan and not frags and len(grupos - set(faltan) - {"punto_informacion"}) == 0:
            # Nadie cargó ese dato: respuesta fija y honesta (la IA tendía a afirmar "sí, hay wifi gratis")
            que = {"wifi": "del wifi", "cajero": "de los cajeros", "baño": "de la ubicación de los baños"}
            datos.respuesta_directa = (f"No tengo información {' ni '.join(que[g] for g in faltan)} del centro "
                                       f"comercial. El personal del centro comercial te orienta, o escribe a la línea "
                                       f"*317 432 0138* 👉 https://wa.me/573174320138")
            return datos
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