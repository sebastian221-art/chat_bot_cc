"""
Catálogo normalizado de lo que hay en el centro comercial, leído de la base
de datos compartida (la misma que edita el panel).

Convierte cada fila de `stores` en un `Local` limpio:
  - zona     = location_hint (Pasillo Barichara, Zona Terrazas…). Nunca "Nivel"/"Piso".
  - piso     = solo para la Torre Médica (ahí sí se da el piso del consultorio).
  - rubro    = primer elemento de los tags si es un rubro conocido (así viene del Excel).
  - productos= el resto de los tags, sin el nombre del local ni palabras genéricas.
Descarta filas basura del Excel (nombre "Teléfono:") y duplicados.
Se guarda en memoria 60 s para no consultar la base en cada mensaje.
"""
from __future__ import annotations

import re

import time
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from .texto import link_whatsapp, normalizar, raices, telefono_fijo

ZONAS_OFICIALES = [
    "Pasillo Barichara", "Pasillo Vélez", "Pasillo Socorro", "Pasillo Charalá", "Pasillo Páramo",
    "Pasillo Curití", "Plaza Principal", "Zona Terrazas", "Plazoleta de Comidas La Ceiba", "Paseo de la Cruz",
    "Paseo San Gil", "Paseo Chicamocha", "Dunas Club Bar", "Pasillo Pinchote", "Plazoleta Guanentá",
    "Lobby Torre Empresarial", "Zona de Parqueaderos",
]
TAGS_GENERICOS = {"torre medica", "consultorio", "oficina", "salud", "administracion", "servicios", "mall", "cine"}
CATEGORIAS_TORRE = {"torre medica y empresarial"}
CATEGORIAS_SERVICIO = {"servicios del centro comercial"}
TTL_S = 60


@dataclass
class Local:
    id: int
    nombre: str
    numero: str
    zona: str
    rubro: str
    productos: list[str]
    descripcion: str
    horario: str
    telefono: str
    whatsapp: str | None
    carta_link: str | None
    categoria: str
    es_torre: bool
    es_servicio: bool
    es_cine: bool
    piso: str | None = None
    fotos: dict = field(default_factory=dict)   # etiqueta → url (portada, carta, otra)
    # Precalculado para buscar rápido
    raices_nombre: set = field(default_factory=set)
    raices_rubro: set = field(default_factory=set)
    raices_productos: set = field(default_factory=set)
    raices_descripcion: set = field(default_factory=set)
    raices_productos_top: set = field(default_factory=set)   # los primeros productos: lo principal que vende
    raices_publico: set = field(default_factory=set)         # «Para: Mujeres», «Ideal para: Moda»: a quién va dirigido

    @property
    def fijo(self) -> str | None:
        """Número para llamar cuando el local solo tiene fijo (sin WhatsApp)."""
        return None if self.whatsapp else telefono_fijo(self.telefono)

    def ficha(self, completa: bool = False) -> dict:
        """Lo que se le entrega al modelo. Sin IDs internos visibles."""
        d = {"nombre": self.nombre, "zona": self.zona}
        if self.es_torre:
            d["piso"] = self.piso
            d["consultorio"] = self.numero
        elif re.search(r"\d", self.numero or ""):
            d["numero_de_local"] = (self.numero or "").replace("_", "").strip()     # "¿en qué local está TRU?"
        if self.telefono:
            d["telefono"] = self.telefono
        if self.whatsapp:
            d["whatsapp"] = self.whatsapp
        elif self.fijo:
            d["solo_telefono_fijo"] = f"{self.fijo} (no tiene WhatsApp: que llamen a ese número)"
        if completa:
            d.update({"rubro": self.rubro, "que_vende": ", ".join(self.productos[:25]),
                      "descripcion": self.descripcion,
                      # sin horario cargado el modelo inventaba uno ("8 am – 6 pm, horario estándar de la Torre")
                      "horario": self.horario or "NO REGISTRADO: no des ningún horario; di que lo confirmen con el local"})
            if self.carta_link and not re.search(r"instagram\.com|wa\.me/|whatsapp", self.carta_link, re.I):
                d["carta_o_catalogo"] = self.carta_link     # un Instagram no es la carta: va como "instagram"
        return {k: v for k, v in d.items() if v}


# Categorías de la página web que juntan varias cosas ("Calzado, Marroquinería y Accesorios"): un local de
# esa categoría puede vender solo una de ellas (MANTRA solo bolsos), así que la categoría NO basta para
# decir que vende zapatos — eso lo tiene que decir su propio "qué vende".
CATEGORIAS_COMPUESTAS = {normalizar(c) for c in [
    "Calzado, Marroquinería y Accesorios", "Cafés, Repostería y Heladerías", "Vehículos, Concesionarios y Accesorios",
    "Hogar, Decoración y Colchones", "Droguerías, Salud y Ópticas", "Entretenimiento, Cines y Juegos",
    "Belleza, Cosméticos y Peluquerías", "Tecnología, Audio y Telecomunicaciones",
    # categorías nuevas de la base del centro comercial (nov. 2026)
    "Cafetería, heladería y postres", "Droguería, óptica y ortopedia", "Hogar, colchones y decoración",
    "Regalos, juguetes y artesanías", "Vehículos, motos y servicios automotrices", "Calzado y marroquinería",
    "Calzado y ropa deportiva", "Servicios financieros y trámites",
]}


def es_categoria_compuesta(rubro: str) -> bool:
    return normalizar(rubro) in CATEGORIAS_COMPUESTAS


def _rubro_y_productos(tags: str, nombre: str) -> tuple[str, list[str]]:
    partes = [p.strip() for p in (tags or "").split(",") if p.strip()]
    if not partes:
        return "", []
    nom = normalizar(nombre)
    if len(partes) >= 2 and es_categoria_compuesta(f"{partes[0]}, {partes[1]}"):
        partes = [f"{partes[0]}, {partes[1]}"] + partes[2:]      # la categoría de la web va completa
    rubro = partes[0] if normalizar(partes[0]) not in TAGS_GENERICOS else ""
    resto = partes[1:] if rubro else partes
    productos, vistos = [], set()
    pal_nom = set(re.findall(r"[a-z0-9ñ]+", nom))
    for p in resto:
        n = normalizar(p)
        if n == nom or n in TAGS_GENERICOS or n in vistos:
            continue
        pal_p = set(re.findall(r"[a-z0-9ñ]+", n))
        if pal_p and pal_p <= pal_nom:
            continue          # «Eden Vivero», «Vivero Eden» solo repiten el nombre: no es lo que vende
        vistos.add(n)
        productos.append(p)
    return rubro, productos


N_PRODUCTOS_PRINCIPALES = 10

# Cosas de dos palabras que NO son la primera palabra: «ropa vieja» (plato) no es ropa, «ropa de cama» no es ropa
# para vestir, «vestido de baño» no es un vestido.
_COMPUESTOS = [(re.compile(r"(?i)\bropa\s+vieja\b"), "ropavieja"), (re.compile(r"(?i)\bropa\s+de\s+(cama|hogar)\b"), "ropadecama"),
               (re.compile(r"(?i)\bvestidos?\s+de\s+ba[ñn]o\b"), "vestidodebaño")]


def _compuestos(t: str) -> str:
    for rx, rep in _COMPUESTOS:
        t = rx.sub(rep, t or "")
    return t

# El formulario de los locales le pegó a casi todas las descripciones el mismo relleno: «Para: Familiar / General.
# Ideal para: Moda / Compras Diarias. Métodos de pago: … Cercanía a parqueadero: … | Instagram: …». Ese relleno
# metía «niños», «mujeres», «familia», «parqueadero» en 113 locales y los hacía salir en búsquedas que no eran suyas.
_RELLENO = re.compile(r"(?is)(?:\.\s*|\s)(?:para|ideal para|m[eé]todos de pago|cercan[ií]a a parqueadero)\s*:")


def partir_descripcion(desc: str) -> tuple[str, str]:
    """(lo que de verdad describe al local, el público «Para: … Ideal para: …»)."""
    d = re.split(r"\s\|\s*(?:instagram|otros contactos)\s*:", desc or "", flags=re.I)[0]
    m = _RELLENO.search(d)
    if not m:
        return d, ""
    resto = d[m.start():]
    publico = " ".join(re.findall(r"(?is)\b(?:para|ideal para)\s*:\s*([^.:|]*?)(?=\.\s|\s+\w[\w ]*:|$)", resto))
    return d[:m.start()], publico


def _es_basura(nombre: str) -> bool:
    n = normalizar(nombre).strip(" :.")
    return not n or n in {"telefono", "tel", "celular", "nombre", "local"} or nombre.strip().endswith(":")


def _zona(store) -> str:
    z = (store.location_hint or "").strip()
    if z:
        return z
    return ""


def _construir(db: Session) -> dict:
    from models.store import Store
    try:
        from models.store_photo import StorePhoto  # noqa: F401  (relación .photos)
    except Exception:
        pass
    locales, vistos = [], set()
    for s in db.query(Store).filter(Store.active.is_(True)).order_by(Store.name).all():
        if _es_basura(s.name):
            continue
        clave = (normalizar(s.name), normalizar(s.local_number or ""))
        if clave in vistos:
            continue
        vistos.add(clave)
        cat = normalizar(s.category)
        es_torre = cat in CATEGORIAS_TORRE or normalizar(s.location_hint or "") == "torre medica"
        rubro, productos = _rubro_y_productos(s.tags, s.name)
        if es_torre and not rubro:
            rubro = "Torre Médica y Empresarial"
        piso = None
        if es_torre:
            f = (s.floor or "").strip()
            piso = f if f.lower().startswith("piso") else None
        fotos = {}
        try:
            for p in s.photos or []:
                fotos.setdefault(p.label or "otra", p.photo_url)
        except Exception:
            pass
        if s.photo_url:
            fotos.setdefault("portada", s.photo_url)
        loc = Local(
            id=s.id, nombre=s.name.strip(), numero=(s.local_number or "").strip(), zona=_zona(s),
            rubro=rubro, productos=productos, descripcion=(s.description or "").strip(),
            horario=(s.schedule or "").strip(), telefono=(s.phone or "").strip(),
            whatsapp=link_whatsapp(s.phone), carta_link=(s.catalogo_link or "").strip() or None,
            categoria=s.category or "", es_torre=es_torre, es_servicio=cat in CATEGORIAS_SERVICIO,
            es_cine=cat == "cine", piso=piso, fotos=fotos,
        )
        # palabras de 3 letras del nombre («Sur», «de», «La») no cuentan: «sura» → «sur» metía a «Fenalco Sur de
        # Santander» en los seguros. El nombre completo se reconoce aparte (Tru, vo5, FDS siguen funcionando).
        loc.raices_nombre = set(raices(" ".join(w for w in re.findall(r"\w+", loc.nombre) if len(w) >= 4 or
                                                 any(ch.isdigit() for ch in w) or (w.isupper() and len(w) >= 2)),
                                       quitar_vacias=False))
        loc.raices_rubro = set(raices(loc.rubro))
        loc.raices_productos = set(r for p in productos for r in raices(_compuestos(p)))
        texto_desc, publico = partir_descripcion(loc.descripcion)
        loc.raices_descripcion = set(raices(_compuestos(texto_desc)))
        loc.raices_productos_top = set(r for p in productos[:N_PRODUCTOS_PRINCIPALES] for r in raices(_compuestos(p)))
        loc.raices_publico = set(raices(publico))
        locales.append(loc)
    return {"locales": locales, "por_id": {l.id: l for l in locales}}


_cache: dict = {"t": 0.0, "datos": None, "bd": None}


def catalogo(db: Session) -> dict:
    clave_bd = str(db.get_bind().url)
    if _cache["datos"] is None or time.time() - _cache["t"] > TTL_S or _cache["bd"] != clave_bd:
        _cache.update(t=time.time(), datos=_construir(db), bd=clave_bd)
    return _cache["datos"]


def invalidar():
    _cache["datos"] = None


def locales(db: Session, incluir_torre: bool = True, incluir_servicios: bool = True) -> list[Local]:
    out = catalogo(db)["locales"]
    return [l for l in out if (incluir_torre or not l.es_torre) and (incluir_servicios or not l.es_servicio)]


def local_por_id(db: Session, id_: int) -> Local | None:
    return catalogo(db)["por_id"].get(id_)


# ── Número de oficina, consultorio o local ("¿qué hay en la oficina 506?") ─────
_NUM_EN_TEXTO = re.compile(r"\b(?:oficinas?|ofi|consultorios?|locales?|local|n[uú]mero|no\.|n[°º]|#)\s*(?:n[uú]mero|no\.?|#)?\s*(\d{3})\b(?!\s*\d)")


def numeros_de(local_number: str) -> set[int]:
    """«201-204» → {201, 202, 203, 204}; «503, 509 y 512» → {503, 509, 512}; «205_» → {205}."""
    t = re.sub(r"[_]", "", local_number or "")
    nums: set[int] = set()
    for a, b in re.findall(r"(\d{3})\s*-\s*(\d{3})", t):
        a, b = int(a), int(b)
        if 0 < b - a <= 10:
            nums.update(range(a, b + 1))
    nums.update(int(x) for x in re.findall(r"(?<!\d)(\d{3})(?!\d)", t))
    return nums


def numero_en_texto(texto: str) -> int | None:
    """El número de oficina/local que pregunta el cliente, o None. Un mensaje que es solo «506» también cuenta."""
    n = normalizar(texto or "").strip(" ?¿.!¡")
    if re.fullmatch(r"\d{3}", n):
        return int(n)
    m = _NUM_EN_TEXTO.search(n)
    return int(m.group(1)) if m else None


def locales_por_numero(db: Session, numero: int) -> list[Local]:
    return sorted([l for l in catalogo(db)["locales"] if numero in numeros_de(l.numero)], key=lambda l: normalizar(l.nombre))