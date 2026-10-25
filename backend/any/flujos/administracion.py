"""
Flujo administración: alquiler de espacios, salón de eventos, locales disponibles, pauta,
empleo, proveedores y trámites. Any no da precios, disponibilidad ni condiciones: remite a la
Administración con sus datos reales (local "Administración" del directorio) y lo que diga la
base de conocimiento.
"""
from __future__ import annotations

from ..conocimiento.buscador import buscar_conocimiento
from ..conocimiento.servicios import local_de_servicio
from ..nucleo.tipos import Contexto
from .base import Datos, Flujo


class Administracion(Flujo):
    nombre = "administracion"
    descripcion = ("alquiler de espacios o locales, salón de eventos, pauta, empleo, proveedores, oficinas y trámites "
                   "con la administración del centro comercial")
    temperatura = 0.4
    max_tokens = 400

    async def reunir(self, ctx: Contexto) -> Datos:
        db = ctx.db
        d = ctx.decision
        consulta = (d.consulta if d and d.consulta else ctx.mensaje)
        adm = local_de_servicio(db, "Administración")
        hechos: dict = {
            "administracion": adm.ficha(completa=True) if adm else "no tengo los datos de la Administración",
            "informacion_relacionada": [f.dict() for f in buscar_conocimiento(db, consulta, k=3)],
            "linea_centro_comercial": "317 432 0138 · https://wa.me/573174320138",
        }
        if adm and adm.zona and adm.zona.lower().startswith("oficinas"):
            hechos["nota_ubicacion"] = ("La zona exacta de las oficinas no está en el directorio: no la inventes; "
                                        "ofrece el contacto para que le indiquen.")
        return Datos(hechos=hechos, entidades={"tema": "administracion"},
                     meta={"telefonos_validos": [adm.telefono] if adm and adm.telefono else []})