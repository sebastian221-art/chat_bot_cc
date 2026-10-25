"""
Flujo Torre Médica y Empresarial: consultorios y oficinas de la torre.
Aquí SÍ se da el piso (única excepción a la regla de zonas). Busca la especialidad en los
consultorios; si nada coincide, lista todos (en vez de decir "no tengo datos"), siempre en
orden alfabético y armado en código, igual que la lista de locales.
"""
from __future__ import annotations

import re

from ..conocimiento.buscador import buscar_conocimiento, buscar_locales, seleccionar_relevantes, encontrar_local
from ..conocimiento.catalogo import Local, locales
from ..conocimiento.texto import normalizar
from ..nucleo.tipos import Contexto
from .base import Datos, Flujo

MARCA = "{LISTA}"


def linea_consultorio(l: Local) -> str:
    lugar = ", ".join(x for x in [l.piso, f"consultorio {l.numero}" if l.numero and l.numero.upper() != "S/N" else ""] if x)
    s = f"• *{l.nombre}*" + (f" — {lugar}" if lugar else "")
    return s + (f" · 👉 {l.whatsapp}" if l.whatsapp else "")


_SALUD = re.compile(r"medic|odont|ortodon|dermat|salud|clinic|cirug|cirujan|renal|nefro|dialisis|respirat|nutric|"
                    r"ecograf|veterin|internista|ginec|obstet|urolog|oncolog|pediatr|eps\b|sura|sanitas|vacun|enfermer|"
                    r"terapi|psicolog|laborator|optometr|fisioter|maxilofacial|implante|citolog|doctor|\bdra?\b")
_NO_SALUD = re.compile(r"abogad|juridic|derecho|contador|contable|electrificadora|\bessa\b|electricidad")


def busca_salud(texto: str) -> bool:
    return bool(re.search(r"doctor|medic|salud|consulta|cita|especialista|enferm|dolor|vacun|odont|dentist|pediatr|"
                          r"ginec|laborator|examen|terapia|clinic", normalizar(texto)))


def es_de_salud(l: Local) -> bool:
    t = normalizar(f"{l.nombre} {l.descripcion} {' '.join(l.productos)} {l.rubro or ''}")
    return bool(_SALUD.search(t)) and not _NO_SALUD.search(t)


class TorreMedica(Flujo):
    nombre = "torre_medica"
    descripcion = "Torre Médica y Empresarial: consultorios, especialistas, laboratorios, vacunación, oficinas de la torre"
    temperatura = 0.4
    max_tokens = 500

    async def reunir(self, ctx: Contexto) -> Datos:
        db = ctx.db
        d = ctx.decision
        consulta = (d.consulta if d and d.consulta else ctx.mensaje)
        termino = str((d.entidades.get("especialidad") if d else None) or consulta)
        torre = [l for l in locales(db) if l.es_torre]
        nombrado = encontrar_local(db, str(d.entidades.get("local")), incluir_torre=True) if d and d.entidades.get("local") else None
        info = [f.dict() for f in buscar_conocimiento(db, "torre medica empresarial horario", k=2)]
        hechos: dict = {"torre": "Torre Médica y Empresarial del Centro Comercial El Puente", "info_general": info}
        if nombrado and nombrado.es_torre:
            hechos["modo"] = "ficha"
            hechos["consultorio"] = nombrado.ficha(completa=True)
            return Datos(hechos=hechos, entidades={"local": nombrado.nombre}, meta={})
        res = [r for r in buscar_locales(db, termino, incluir_torre=True) if r.local.es_torre]
        sel = [r.local for r in seleccionar_relevantes(res)]
        if sel:
            hechos["modo"] = "coinciden"
            hechos["busqueda"] = termino
        else:
            sel = torre
            if busca_salud(f"{ctx.mensaje} {termino}"):
                sel = [l for l in torre if es_de_salud(l)] or torre   # "doctor": no se muestran abogados ni oficinas
            hechos["modo"] = "sin_coincidencia"
            hechos["busqueda"] = termino
            hechos["nota"] = ("Ningún consultorio menciona eso; se muestra el directorio completo de la torre "
                              "para que el cliente revise o pregunte directamente.")
        sel = sorted(sel, key=lambda l: normalizar(l.nombre))
        hechos["como_escribir"] = (f"Frase corta de entrada; luego {MARCA} en una línea sola (ahí va la lista con piso, "
                                   f"consultorio y WhatsApp); opcional una línea final. No escribas tú la lista.")
        hechos["consultorios_para_tu_contexto"] = [{"nombre": l.nombre, "que_es": ", ".join(l.productos[:6]),
                                                    "descripcion": l.descripcion[:120]} for l in sel[:30]]
        lineas = {l.nombre: linea_consultorio(l) for l in sel}
        return Datos(hechos=hechos, entidades={"especialidad": termino},
                     meta={"lista": "\n".join(lineas.values()), "lista_equidad": list(lineas),
                           "lineas_equidad": lineas, "telefonos_validos": [l.telefono for l in sel if l.telefono]})

    def componer(self, ctx, datos, texto):
        lista = datos.meta.get("lista")
        if not lista:
            return texto
        from .locales import poner_lista
        return poner_lista(texto, lista)

    def respaldo(self, ctx, datos):
        return f"En la *Torre Médica y Empresarial* están estos consultorios:\n{MARCA}" if datos.meta.get("lista") else None