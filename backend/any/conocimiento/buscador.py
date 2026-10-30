"""
Búsqueda en el conocimiento del mall, por palabra completa y con sinónimos.

  buscar_locales(db, "tenis para correr")      → locales ordenados por relevancia
  buscar_conocimiento(db, "dónde hay baños")   → fragmentos de info del mall

Cómo puntúa:
  1. La consulta se parte en CONCEPTOS (cada palabra útil + sus sinónimos).
  2. Un local cubre un concepto si alguna raíz del concepto aparece en su
     nombre, rubro, productos o descripción (pesos distintos).
  3. Gana quien cubre más conceptos; a igualdad, el que tiene más puntaje.
El nombre exacto de un local siempre gana ("Jarris", "12B Burger").

Fase 2 agrega embeddings multilingües (búsqueda híbrida) y reescritura de la
consulta con el contexto; esta capa queda como la parte léxica de esa mezcla.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass

import yaml
from sqlalchemy.orm import Session

from .catalogo import Local, es_categoria_compuesta, locales
from .texto import VACIAS, contiene_frase, normalizar, palabras, raices, raiz

_RUTA_SINONIMOS = os.path.join(os.path.dirname(__file__), "..", "datos", "sinonimos.yaml")
_sinonimos_cache: dict | None = None


def _sinonimos() -> dict:
    """{'locales': {grupo: {'todas': [...], 'especificos': {...}}}, 'servicios': {...}} desde el YAML."""
    global _sinonimos_cache
    if _sinonimos_cache is None:
        with open(_RUTA_SINONIMOS, encoding="utf-8") as f:
            crudo = yaml.safe_load(f) or {}
        out = {}
        for sec, grupos in crudo.items():
            out[sec] = {}
            for k, v in (grupos or {}).items():
                if isinstance(v, dict):
                    gen = [normalizar(x) for x in v.get("generales") or []]
                    esp = [normalizar(x) for x in v.get("especificos") or []]
                    padre = v.get("amplia_a")
                else:
                    gen, esp, padre = [normalizar(x) for x in v], [], None
                out[sec][k] = {"todas": gen + esp, "especificos": set(esp), "padre": padre}
        _sinonimos_cache = out
    return _sinonimos_cache


def recargar_sinonimos():
    global _sinonimos_cache
    _sinonimos_cache = None


@dataclass
class Concepto:
    palabra: str          # cómo lo escribió el cliente
    raices: set           # raíces que lo representan (con sinónimos si es una palabra general)
    frases: list          # sinónimos de varias palabras ("retirar plata")
    grupo: str | None = None
    respaldo: tuple | None = None   # (raíces, frases) del grupo, si la palabra es específica
    amplio: set | None = None       # raíces del grupo mayor: candidatos para el juez ("vestido" → toda la ropa)


def conceptos(consulta: str, seccion: str = "locales") -> list[Concepto]:
    grupos = _sinonimos().get(seccion, {})
    texto = normalizar(consulta)
    usados: set = set()
    grupos_usados: set = set()
    salida: list[Concepto] = []
    # 1) frases de sinónimos de varias palabras presentes en la consulta
    for nombre, g in grupos.items():
        for frase in g["todas"]:
            if " " in frase and contiene_frase(frase, texto):
                salida.append(_concepto_de_grupo(frase, nombre, g))
                grupos_usados.add(nombre)
                usados.update(raiz(p) for p in palabras(frase))
                break
    # 2) palabras sueltas
    for p in palabras(texto):
        if p in VACIAS or len(p) < 2:
            continue
        r = raiz(p)
        if r in usados:
            continue
        usados.add(r)
        grupo = next((n for n, g in grupos.items() if any(raiz(x) == r for x in g["todas"] if " " not in x)), None)
        if grupo and grupo in grupos_usados:
            continue
        if grupo:
            grupos_usados.add(grupo)
            c = _concepto_de_grupo(p, grupo, grupos[grupo])
            padre = grupos.get(grupos[grupo].get("padre") or "")
            if padre:
                c.amplio = {raiz(x) for x in padre["todas"] if " " not in x}
            salida.append(c)
        else:
            salida.append(Concepto(palabra=p, raices={r}, frases=[]))
    return salida


def _concepto_de_grupo(palabra: str, grupo: str, g: dict) -> Concepto:
    sueltas = {raiz(x) for x in g["todas"] if " " not in x}
    frases = [x for x in g["todas"] if " " in x]
    es_especifica = any(raiz(e) == raiz(palabra) or e == palabra for e in g["especificos"])
    if es_especifica:   # "sandalias": se busca sola; el grupo queda de respaldo
        propias = {raiz(x) for x in palabras(palabra)} if " " in palabra else {raiz(palabra)}
        return Concepto(palabra=palabra, raices=propias, frases=[palabra] if " " in palabra else [],
                        grupo=grupo, respaldo=(sueltas, frases), amplio=sueltas)
    return Concepto(palabra=palabra, raices=sueltas, frases=frases, grupo=grupo)


# ── Locales ───────────────────────────────────────────────────────

PESOS = {"nombre": 6, "rubro": 5, "productos": 4, "descripcion": 2}
PESO_FUERTE = 4   # nombre, rubro o productos: lo que el local declara que vende

# Palabras que dicen QUÉ quiere saber del local, no QUÉ busca: no cuentan para buscar
PALABRAS_DE_PEDIDO = set("""
todos todas cuales cual cuantos cuantas venden vende venta ventas numero telefono whatsapp wasap
carta menu instagram insta foto fotos imagen horario horarios abre abren cierra cierran ubicacion
queda quedan ubicado ubicada direccion regalame regalas dame das pasame pasas tienes tiene hay
porfa xfa fa q k ver info informacion mas otro otra otros otras donde zona sobre sobra saber
servicio servicios atencion consultorio consultorios cerca cercano cercana marca marcas comprar compro algo puedo
empresa empresas oficina oficinas firma firmas negocio negocios asesoria asesorias establecimiento establecimientos
sucursal sucursales punto puntos
""".split())


# Dicen la clase de sitio, no lo que se busca: solo cuentan si no hay nada más concreto en la pregunta
PALABRAS_GENERICAS = set("""
restaurante restaurantes comida comidas comer tienda tiendas almacen almacenes local locales sitio sitios lugar
lugares opcion opciones recomendacion recomiendas recomienda bueno buena mejor
""".split())


@dataclass
class Resultado:
    local: Local
    puntaje: float
    cubiertos: list        # palabras del cliente que encontró (en cualquier campo)
    nombre_exacto: bool = False
    fuertes: list = None   # palabras encontradas en nombre, rubro o productos
    cercanos: list = None  # palabras cuyo grupo mayor aparece (candidato para el juez, no para la lista directa)


def buscar_locales(db: Session, consulta: str, incluir_torre: bool = False,
                   incluir_servicios: bool = True) -> list[Resultado]:
    lista = locales(db, incluir_torre=incluir_torre, incluir_servicios=incluir_servicios)
    cons = [c for c in conceptos(consulta, "locales") if c.palabra not in PALABRAS_DE_PEDIDO]
    # "restaurante de comida mexicana": si hay algo concreto (mexicana), "restaurante"/"comida" no cuentan;
    # si no, todos los restaurantes cubrían 2 de 3 palabras y salían en la lista
    concretos = [c for c in cons if normalizar(c.palabra) not in PALABRAS_GENERICAS]
    if concretos:
        cons = concretos
    for c in cons:   # palabra específica que nadie declara → se amplía a su grupo
        if c.respaldo and not any(c.raices & (l.raices_nombre | l.raices_rubro | l.raices_productos) for l in lista):
            c.raices, c.frases = c.respaldo
    texto = normalizar(consulta)
    resultados = []
    for loc in lista:
        exacto = _nombre_en_texto(loc.nombre, texto)
        puntaje, cubiertos, fuertes, cercanos = 0.0, [], [], []
        declarado = loc.raices_nombre | loc.raices_rubro | loc.raices_productos
        for c in cons:
            mejor = 0
            for campo, peso in PESOS.items():
                rs = getattr(loc, f"raices_{campo}")
                if campo == "rubro" and es_categoria_compuesta(loc.rubro):
                    peso = PESO_FUERTE - 1      # «Calzado, Marroquinería y Accesorios» no dice que venda zapatos
                if c.raices & rs:
                    mejor = max(mejor, peso)
            if not mejor and c.frases:
                todo = " ".join([loc.rubro, " ".join(loc.productos), loc.descripcion])
                if any(contiene_frase(f, todo) for f in c.frases):
                    mejor = PESOS["productos"]
            if mejor:
                puntaje += mejor
                cubiertos.append(c.palabra)
                if mejor >= PESO_FUERTE:
                    fuertes.append(c.palabra)
            if c.amplio and c.palabra not in fuertes and c.amplio & declarado:
                cercanos.append(c.palabra)
        if exacto:
            puntaje += 100
        if puntaje > 0 or cercanos:
            resultados.append(Resultado(loc, puntaje, cubiertos, exacto, fuertes, cercanos))
    resultados.sort(key=lambda r: (-r.nombre_exacto, -len(r.fuertes), -len(r.cubiertos), -r.puntaje,
                                   normalizar(r.local.nombre)))
    return resultados


def seleccionar_relevantes(resultados: list[Resultado]) -> list[Resultado]:
    """
    De todos los que tocan la búsqueda, los que de verdad responden:
      - si alguno coincide por nombre, solo esos;
      - si hay coincidencias en lo que el local declara que vende (nombre, rubro, productos),
        solo los que cubren el MÁXIMO de esas palabras — la descripción sola no basta;
      - si no, los que más palabras cubren en cualquier campo.
    El orden final es alfabético (equidad: ningún local va primero por puntaje).
    """
    if not resultados:
        return []
    exactos = [r for r in resultados if r.nombre_exacto]
    if exactos:
        return exactos
    resultados = [r for r in resultados if r.cubiertos]
    if not resultados:
        return []
    mx = max(len(r.fuertes) for r in resultados)
    if mx:
        sel = [r for r in resultados if len(r.fuertes) == mx]
        if len(sel) < 3 and mx >= 2:   # "tenis para correr": si casi nadie cubre todo, vale cubrir casi todo
            sel = [r for r in resultados if len(r.fuertes) >= mx - 1]
    else:
        mc = max(len(r.cubiertos) for r in resultados)
        sel = [r for r in resultados if len(r.cubiertos) == mc]
    return sorted(sel, key=lambda r: normalizar(r.local.nombre))


def encontrar_local(db: Session, nombre: str, incluir_torre: bool = True) -> Local | None:
    """El local que el cliente nombró, tolerando tildes, mayúsculas, nombres a medias y errores leves."""
    import difflib
    n = normalizar(nombre)
    if len(n) < 2:
        return None
    mejor, puntaje = None, 0.0
    for loc in locales(db, incluir_torre=incluir_torre):
        ln = normalizar(loc.nombre)
        if ln == n or (len(n) >= 6 and ln.replace(" ", "") == n.replace(" ", "")):     # "Happy landia"
            return loc
        p = 0.0
        tn = {w for w in palabras(n) if w not in VACIAS}
        tl = {w for w in palabras(ln) if w not in VACIAS}
        if contiene_frase(n, ln) or contiene_frase(ln, n):
            p = 0.9 + min(len(n), len(ln)) / max(len(n), len(ln)) / 10
        elif len(tn) >= 2 and tn <= tl:
            p = 0.88          # "Benítez abogados" → "Benítez y Bravo Abogados" (todas sus palabras están)
        else:
            p = difflib.SequenceMatcher(None, n, ln).ratio()
            primera = next((w for w in palabras(ln) if w not in VACIAS), "")
            if primera and (primera == n or difflib.SequenceMatcher(None, n, primera).ratio() >= 0.88):
                p = max(p, 0.88)
        if p > puntaje:
            mejor, puntaje = loc, p
    return mejor if puntaje >= 0.85 else None


def _nombre_en_texto(nombre: str, texto_normalizado: str) -> bool:
    n = normalizar(nombre)
    if len(n) < 3:
        return False
    if contiene_frase(n, texto_normalizado):
        return True
    # nombres largos o con números ("12B Burger Angus", "La Barra 1516"): basta la primera palabra distintiva
    ps = [p for p in palabras(n) if p not in VACIAS]
    if not ps:
        return False
    p = ps[0]
    distintiva = len(p) >= 5 or (len(p) >= 3 and any(ch.isdigit() for ch in p))
    return distintiva and p in palabras(texto_normalizado)


# ── Conocimiento general del mall ─────────────────────────────────

@dataclass
class Fragmento:
    titulo: str
    contenido: str
    fuente: str          # conocimiento | info_mall | punto_interes
    puntaje: float = 0.0

    def dict(self) -> dict:
        return {"titulo": self.titulo, "contenido": self.contenido, "fuente": self.fuente}


def fragmentos_del_mall(db: Session) -> list[Fragmento]:
    from models.knowledge import KnowledgeEntry
    from models.mall_info import MallInfo
    from models.info_point import InfoPoint

    out: list[Fragmento] = []
    mi = db.query(MallInfo).first()
    if mi:
        campos = [("Dirección del centro comercial", mi.address), ("Horario general", mi.general_schedule),
                  ("Teléfono / línea del centro comercial", mi.phone), ("Parqueadero", mi.parking),
                  ("WiFi", mi.wifi)]
        out += [Fragmento(t, v.strip(), "info_mall") for t, v in campos if v and v.strip()]
    for p in db.query(InfoPoint).all():
        lugar = ", ".join(x for x in [p.location, p.floor] if x and x.strip())
        out.append(Fragmento(p.name, f"{p.name}: {lugar}" if lugar else p.name, "punto_interes"))
    for k in db.query(KnowledgeEntry).filter(KnowledgeEntry.active.is_(True)).all():
        out.append(Fragmento(k.title, (k.content or "").strip(), "conocimiento"))
    return out


def buscar_conocimiento(db: Session, consulta: str, k: int = 4, minimo: float = 0.5) -> list[Fragmento]:
    frags = fragmentos_del_mall(db)
    if not frags:
        return []
    cons = conceptos(consulta, "servicios")
    if not cons:
        return []
    docs = [(f, set(raices(f.titulo)), set(raices(f.contenido))) for f in frags]
    n = len(docs)

    def idf(rs: set) -> float:
        df = sum(1 for _, t, c in docs if rs & (t | c))
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    for f, rt, rc in docs:
        s = 0.0
        texto = f.titulo + " " + f.contenido
        for c in cons:
            golpe_t = bool(c.raices & rt) or any(contiene_frase(x, f.titulo) for x in c.frases)
            golpe_c = bool(c.raices & rc) or any(contiene_frase(x, texto) for x in c.frases)
            if golpe_t or golpe_c:
                s += idf(c.raices) * (2.0 if golpe_t else 1.0)
        f.puntaje = round(s, 3)
    elegidos = sorted((f for f, _, _ in docs if f.puntaje >= minimo), key=lambda f: -f.puntaje)
    if elegidos:   # filtro de relevancia: fuera lo que puntúa menos de la mitad del mejor
        tope = elegidos[0].puntaje
        elegidos = [f for f in elegidos if f.puntaje >= tope * 0.5]
    return elegidos[:k]