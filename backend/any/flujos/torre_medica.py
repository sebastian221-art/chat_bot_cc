"""
Flujo Torre Médica y Empresarial: consultorios y oficinas de la torre.
Aquí SÍ se da el piso (única excepción a la regla de zonas). Busca la especialidad en los
consultorios; si nada coincide, lista todos (en vez de decir "no tengo datos"), siempre en
orden alfabético y armado en código, igual que la lista de locales.
"""
from __future__ import annotations

import re

from ..conocimiento.buscador import buscar_conocimiento, buscar_locales, seleccionar_relevantes, encontrar_local
from ..conocimiento.catalogo import Local, locales, locales_por_numero, numero_en_texto
from ..conocimiento.texto import normalizar
from ..nucleo.tipos import Contexto
from .base import Datos, Flujo

MARCA = "{LISTA}"


def linea_consultorio(l: Local) -> str:
    lugar = ", ".join(x for x in [l.piso, f"consultorio {l.numero}" if l.numero and l.numero.upper() != "S/N" else ""] if x)
    s = f"• *{l.nombre}*" + (f" — {lugar}" if lugar else "")
    if l.whatsapp:
        return s + f" · 👉 {l.whatsapp}"
    return s + (f" · ☎️ solo fijo: {l.fijo}" if l.fijo else "")


_SALUD = re.compile(r"medic|odont|ortodon|dermat|salud|clinic|cirug|cirujan|renal|nefro|dialisis|respirat|nutric|"
                    r"ecograf|veterin|internista|ginec|obstet|urolog|oncolog|pediatr|eps\b|sura|sanitas|vacun|enfermer|"
                    r"terapi|psicolog|laborator|optometr|fisioter|maxilofacial|implante|citolog|doctor|\bdra?\b")
_NO_SALUD = re.compile(r"abogad|juridic|derecho|contador|contable|electrificadora|\bessa\b|electricidad")


def busca_salud(texto: str) -> bool:
    if _SALUD.search(normalizar(texto)) or re.search(r"logo\b|logia\b|ologa\b|cardio|neuro|psiqu|oftalm|otorrino|"
                                                    r"traumat|ortoped|fisiatr|fonoaud", normalizar(texto)):
        return True
    return bool(re.search(r"doctor|medic|salud|consulta|cita|especialista|enferm|dolor|vacun|odont|dentist|pediatr|"
                          r"ginec|laborator|examen|terapia|clinic", normalizar(texto)))


def es_de_salud(l: Local) -> bool:
    t = normalizar(f"{l.nombre} {l.descripcion} {' '.join(l.productos)} {l.rubro or ''}")
    return bool(_SALUD.search(t)) and not _NO_SALUD.search(t)


class TorreMedica(Flujo):
    nombre = "torre_medica"
    descripcion = ("Torre Médica y Empresarial: consultorios, especialistas, laboratorios, vacunación y empresas u "
                   "oficinas de la torre (contadores, abogados, EPS, Fenalco, ESSA…)")
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
        numero = numero_en_texto(ctx.mensaje)
        if numero:
            return self._por_numero(db, numero, hechos)
        piso = d.entidades.get("piso") if d else None
        if piso:
            en_piso = [l for l in torre if re.search(rf"\b{int(piso)}\b", l.piso or "")]
            hechos["modo"] = "coinciden" if en_piso else "piso_sin_registro"
            hechos["busqueda"] = f"piso {piso} de la Torre"
            if not en_piso:
                hechos["nota"] = f"No hay oficinas registradas en el piso {piso}; ofrece la línea 317 432 0138."
                return Datos(hechos=hechos, meta={})
            lineas = {l.nombre: linea_consultorio(l) for l in sorted(en_piso, key=lambda l: normalizar(l.nombre))}
            hechos["como_escribir"] = f"Frase corta de entrada; luego {MARCA} en una línea sola; no escribas tú la lista."
            return Datos(hechos=hechos, entidades={"especialidad": f"piso {piso}"},
                         meta={"lista": "\n".join(lineas.values()), "lista_equidad": list(lineas),
                               "lineas_equidad": lineas, "telefonos_validos": [l.telefono for l in en_piso if l.telefono]})
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
            # "Ortopédicos", "tienda ortopédica": no es un consultorio pero SÍ hay un local que lo vende
            comerciales = [r.local for r in seleccionar_relevantes(buscar_locales(db, termino)) if not r.local.es_torre] \
                or [r.local for r in seleccionar_relevantes(buscar_locales(db, ctx.mensaje)) if not r.local.es_torre]
            if comerciales:
                from .locales import linea_lista
                hechos["modo"] = "locales_comerciales"
                hechos["busqueda"] = termino
                hechos["nota"] = ("No es un consultorio de la Torre, pero estos LOCALES del centro comercial lo venden: "
                                  "preséntalos así (sin decir que no hay).")
                sel = sorted(comerciales, key=lambda l: normalizar(l.nombre))
                if len(sel) == 1:
                    hechos["modo"] = "ficha"
                    hechos["consultorio"] = sel[0].ficha(completa=True)
                    return Datos(hechos=hechos, entidades={"local": sel[0].nombre},
                                 meta={"telefonos_validos": [sel[0].telefono] if sel[0].telefono else []})
                lineas = {l.nombre: linea_lista(l) for l in sel}
                hechos["como_escribir"] = f"Frase corta de entrada; luego {MARCA} en una línea sola; no escribas tú la lista."
                return Datos(hechos=hechos, entidades={"categoria": termino},
                             meta={"lista": "\n".join(lineas.values()), "lista_equidad": list(lineas),
                                   "lineas_equidad": lineas, "telefonos_validos": [l.telefono for l in sel if l.telefono]})
            sel = torre
            if busca_salud(f"{ctx.mensaje} {termino}"):
                sel = [l for l in torre if es_de_salud(l)] or torre   # "doctor": no se muestran abogados ni oficinas
            hechos["modo"] = "sin_coincidencia"
            hechos["busqueda"] = termino
            hechos["nota"] = ("Ningún consultorio menciona eso; se muestra el directorio de la torre para que el "
                              "cliente revise o pregunte directamente.")
        sel = sorted(sel, key=lambda l: normalizar(l.nombre))
        hechos["como_escribir"] = (f"Frase corta de entrada; luego {MARCA} en una línea sola (ahí va la lista con piso, "
                                   f"consultorio y WhatsApp); opcional una línea final. No escribas tú la lista.")
        hechos["consultorios_para_tu_contexto"] = [{"nombre": l.nombre, "que_es": ", ".join(l.productos[:6]),
                                                    "descripcion": l.descripcion[:120]} for l in sel[:30]]
        lineas = {l.nombre: linea_consultorio(l) for l in sel}
        return Datos(hechos=hechos, entidades={"especialidad": termino},
                     meta={"lista": "\n".join(lineas.values()), "lista_equidad": list(lineas),
                           "lineas_equidad": lineas, "telefonos_validos": [l.telefono for l in sel if l.telefono]})

    def _por_numero(self, db, numero: int, hechos: dict) -> Datos:
        """«¿Qué hay en la oficina 506?»: se busca por el número, no por palabras (antes decía «está vacía»)."""
        en_numero = [l for l in locales_por_numero(db, numero) if l.es_torre] or locales_por_numero(db, numero)
        hechos["numero_preguntado"] = numero
        if len(en_numero) == 1:
            hechos["modo"] = "ficha"
            hechos["consultorio"] = en_numero[0].ficha(completa=True)
            return Datos(hechos=hechos, entidades={"local": en_numero[0].nombre},
                         meta={"telefonos_validos": [en_numero[0].telefono] if en_numero[0].telefono else []})
        if not en_numero:
            hechos["modo"] = "numero_sin_registro"
            hechos["nota"] = (f"No hay ninguna oficina o consultorio registrado con el número {numero} en el directorio. "
                              "NO digas que está vacía (puede que no esté registrada): di que no la tienes en el "
                              "directorio y ofrece la línea del centro comercial 317 432 0138.")
            return Datos(hechos=hechos, meta={})
        hechos["modo"] = "coinciden"
        hechos["busqueda"] = f"oficina {numero}"
        hechos["nota"] = f"Estos comparten la oficina {numero} según el directorio."
        lineas = {l.nombre: linea_consultorio(l) for l in en_numero}
        hechos["como_escribir"] = (f"Frase corta de entrada; luego {MARCA} en una línea sola; no escribas tú la lista.")
        return Datos(hechos=hechos, entidades={"especialidad": f"oficina {numero}"},
                     meta={"lista": "\n".join(lineas.values()), "lista_equidad": list(lineas), "lineas_equidad": lineas,
                           "telefonos_validos": [l.telefono for l in en_numero if l.telefono]})

    def componer(self, ctx, datos, texto):
        lista = datos.meta.get("lista")
        if not lista:
            return texto
        from .locales import poner_lista
        return poner_lista(texto, lista)

    def respaldo(self, ctx, datos):
        return f"En la *Torre Médica y Empresarial* están estos consultorios:\n{MARCA}" if datos.meta.get("lista") else None