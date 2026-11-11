"""
El directorio COMPLETO del centro comercial en un texto compacto, para que el cerebro lo lea entero en cada
mensaje. Así ya no depende de que una palabra coincida: lee lo que cada local dice que vende y razona.

Cada cosa lleva un ID corto:
  L<id>  locales, servicios del centro comercial y oficinas/consultorios de la Torre
  K<n>   información oficial del centro comercial (horario, parqueadero, mascotas, punto de información…)
  E<id>  eventos vigentes · S<id> sorteos vigentes · P<id> promociones vigentes

Sin teléfonos ni links (eso lo pone el código después, de la base): el cerebro solo elige.
Se arma una vez por minuto (la base cambia desde el panel).
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from any.conocimiento.catalogo import Local, locales, partir_descripcion
from any.conocimiento.texto import normalizar

TTL_S = 60
_cache: dict = {}


@dataclass
class Directorio:
    texto: str                                   # lo que lee el cerebro
    locales: dict = field(default_factory=dict)  # "L786" → Local
    info: dict = field(default_factory=dict)     # "K3" → {"titulo", "contenido", "fuente"}
    eventos: dict = field(default_factory=dict)  # "E12" → Event
    sorteos: dict = field(default_factory=dict)  # "S4" → Raffle
    promos: dict = field(default_factory=dict)   # "P9" → Marketing
    hoy: object = None

    def nombre(self, id_: str) -> str:
        l = self.locales.get(id_)
        if l:
            return l.nombre
        k = self.info.get(id_)
        if k:
            return k["titulo"]
        for d, campo in ((self.eventos, "name"), (self.sorteos, "name"), (self.promos, "title")):
            if id_ in d:
                return getattr(d[id_], campo, id_)
        return id_


def _corto(t: str, n: int) -> str:
    t = re.sub(r"\s+", " ", t or "").strip()
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + "…"


_RELLENO_VENDE = {"plazoleta de comidas", "la ceiba", "venta", "tienda", "almacen", "local", "centro comercial"}


def _vende(l: Local, limite: int = 240) -> str:
    """Lo que el local declara vender, sin las frases de relleno del formulario («dónde venden collares»),
    sin repetir el nombre ni la zona."""
    fuera = {normalizar(l.nombre), normalizar(l.zona or "")}
    out, vistos = [], set()
    for p in l.productos:
        n = normalizar(p)
        n = re.sub(r"\s+en san gil$", "", n)
        if not n or n in fuera or n in vistos or n.startswith("donde ") or n in _RELLENO_VENDE:
            continue
        vistos.add(n)
        out.append(re.sub(r"(?i)\s+en san gil$", "", p.strip()))
    return _corto(", ".join(out), limite)


def linea_local(id_: str, l: Local, compacto: bool = False) -> str:
    if l.es_torre:
        lugar = "Torre Médica y Empresarial" + "".join(
            f", {x}" for x in [l.piso, f"oficina {l.numero}" if l.numero and l.numero.upper() != "S/N" else ""] if x)
    elif l.es_servicio:
        lugar = "servicio del centro comercial" + (f", {l.zona}" if l.zona else "")
    else:
        lugar = l.zona or "zona sin registrar"
        if re.search(r"\d", l.numero or ""):        # «¿cuál es el local 167?»: el número también identifica
            lugar += f", local {(l.numero or '').replace('_', '').strip()}"
    desc, publico = partir_descripcion(l.descripcion or "")
    if compacto:     # para modelos con límite de tokens por minuto (Groq): lo esencial para elegir bien
        vende = _vende(l, 120) or _corto(desc, 90) or "-"
        extra = f" | para: {_corto(publico, 30)}" if publico and re.search(r"(?i)mujer|hombre|niñ|infantil|bebe", publico) else ""
        return f"{id_} | {l.nombre} | {lugar} | {l.rubro or '-'} | {vende}{extra}"
    partes = [id_, l.nombre, lugar, l.rubro or "-", "vende: " + (_vende(l) or "-")]
    d = _corto(re.sub(r"(?i),?\s*(ubicad[oa] )?en (el municipio de )?san gil,? santander|,?\s*san gil,? santander", "", desc), 180)
    if d:
        partes.append("desc: " + d)
    if publico:
        partes.append("para: " + _corto(publico, 60))
    tiene = [n for n, v in (("carta", any(_carta(l))), ("instagram", _ig(l)), ("foto", l.fotos.get("portada")),
                             ("horario", l.horario), ("whatsapp", l.whatsapp)) if v]
    if tiene:
        partes.append("tiene: " + ",".join(tiene))
    return " | ".join(partes)


def _carta(l: Local):
    from any.flujos.locales import carta_de
    return carta_de(l)


def _ig(l: Local):
    from any.flujos.locales import instagram_de
    return instagram_de(l)


def construir(db, hoy=None, compacto: bool = False) -> Directorio:
    """compacto=True: versión corta (~3 veces menos tokens) para modelos con límite de tokens por minuto."""
    from datetime import date
    hoy = hoy or date.today()
    clave = (id(db.get_bind()), hoy, compacto)
    c = _cache.get(clave)
    if c and time.monotonic() - c[0] < TTL_S:
        return c[1]
    d = Directorio(texto="", hoy=hoy)
    comercio, torre, servicios = [], [], []
    for l in sorted(locales(db, incluir_torre=True, incluir_servicios=True), key=lambda x: normalizar(x.nombre)):
        id_ = f"L{l.id}"
        d.locales[id_] = l
        (torre if l.es_torre else servicios if l.es_servicio else comercio).append(linea_local(id_, l, compacto))

    # Información oficial: completa (es poca, ~6 000 caracteres) para que el cerebro sepa qué hay
    from any.conocimiento.buscador import fragmentos_del_mall
    info_lineas = []
    n = 0
    for f in fragmentos_del_mall(db):
        if re.search(r"(?i)use tab to navigate|menu items", f.contenido or ""):
            continue          # texto basura copiado de la página web (no es información)
        n += 1
        id_ = f"K{n}"
        d.info[id_] = f.dict()
        info_lineas.append(f"{id_} | {f.titulo} | {_corto(f.contenido, 160 if compacto else 700)}")
    try:
        from any.conocimiento.areas import directorio as areas
        for a in areas():
            n += 1
            id_ = f"K{n}"
            titulo = f"Contacto de área: {a.get('area')}"
            contenido = "; ".join(f"{k}: {v}" for k, v in a.items() if k not in ("area",) and v)
            d.info[id_] = {"titulo": titulo, "contenido": contenido, "fuente": "areas", "area": a}
            sin_links = re.sub(r"https?://\S+", "", contenido)
            info_lineas.append(f"{id_} | {titulo}" + ("" if compacto else f" | {_corto(sin_links, 200)}"))
    except Exception:
        pass

    ev_lineas, so_lineas, pr_lineas = [], [], []
    try:
        from any.flujos.eventos import eventos_vigentes
        for e in eventos_vigentes(db, hoy):
            id_ = f"E{e.id}"
            d.eventos[id_] = e
            ev_lineas.append(" | ".join(x for x in [id_, e.name, e.date or "", e.time or "", e.location or "",
                                                     _corto(e.description or "", 160)] if x))
    except Exception:
        db.rollback()
    try:
        from any.flujos.sorteos_promos import promos_vigentes, sorteos_vigentes
        for s in sorteos_vigentes(db, hoy):
            id_ = f"S{s.id}"
            d.sorteos[id_] = s
            so_lineas.append(" | ".join(x for x in [id_, s.name, s.prize or "", f"hasta {s.end_date}" if s.end_date else ""] if x))
        for m in promos_vigentes(db, hoy):
            id_ = f"P{m.id}"
            d.promos[id_] = m
            loc = next((l.nombre for l in d.locales.values() if m.store_id and l.id == m.store_id), "")
            pr_lineas.append(" | ".join(x for x in [id_, m.title, loc, _corto(m.description or "", 140),
                                                     f"hasta {m.valid_until}" if m.valid_until else ""] if x))
    except Exception:
        db.rollback()

    bloques = [
        ("## LOCALES COMERCIALES (ID | nombre | zona | categoría | qué vende)" if compacto else
         "## LOCALES COMERCIALES (ID | nombre | zona | categoría | vende | descripción | para quién | qué datos tiene)"),
        "\n".join(comercio),
        "## SERVICIOS DEL CENTRO COMERCIAL",
        "\n".join(servicios) or "(ninguno)",
        "## TORRE MÉDICA Y EMPRESARIAL (consultorios y oficinas)",
        "\n".join(torre) or "(ninguno)",
        "## INFORMACIÓN OFICIAL DEL CENTRO COMERCIAL",
        "\n".join(info_lineas) or "(ninguna)",
        "## EVENTOS VIGENTES",
        "\n".join(ev_lineas) or "(ninguno)",
        "## SORTEOS VIGENTES",
        "\n".join(so_lineas) or "(ninguno)",
        "## PROMOCIONES VIGENTES",
        "\n".join(pr_lineas) or "(ninguna)",
    ]
    d.texto = "\n".join(bloques)
    for k in [k for k in _cache if k[:2] != clave[:2]]:
        _cache.pop(k, None)
    _cache[clave] = (time.monotonic(), d)
    return d
