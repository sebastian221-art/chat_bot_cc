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
import re
from dataclasses import dataclass

import yaml
from sqlalchemy.orm import Session

from .catalogo import Local, catalogo, es_categoria_compuesta, locales
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
sucursal sucursales punto puntos puedes puede pueden recomendar recomiendame recomiendan sugerir sugieres
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
    fuertes: list = None   # palabras de PRODUCTO encontradas en lo que el local declara (nombre, rubro, productos)
    cercanos: list = None  # palabras cuyo grupo mayor aparece (candidato para el juez, no para la lista directa)
    relevancia: float = 0.0     # qué tanto responde: rareza de la palabra × qué tan principal es en el local
    modificadores: list = None  # «mujer», «niños», «colegio» que el local cumple (ordenan; no bastan solos)


# ── Motor de búsqueda de productos (11/11/2026) ───────────────────────────────────────────────
# Antes cada palabra pesaba igual: en «shampoo para mujer», «mujer» (21 locales) valía lo mismo que «shampoo»
# (2 locales), los empates se ordenaban alfabéticamente y se cortaba la lista: salían Alucinada, Americanino…
# y Milagros, que es el que vende shampoo, quedaba fuera. Ahora:
#   1. Las palabras de PÚBLICO («mujer», «dama», «niños», «colegio», «para mi casa») no traen locales solas:
#      solo ordenan, y las de niños/colegio filtran si hay locales que las cumplen.
#   2. Cada palabra vale según lo RARA que es (IDF): «shampoo» (2 locales) pesa mucho más que «ropa» (30).
#   3. Y según DÓNDE aparece en el local: nombre > rubro > sus primeros productos > el resto > descripción.
#   4. Se queda con los que tienen al menos la mitad de la relevancia del mejor: «ropa deportiva» trae a los
#      que venden ropa DEPORTIVA, no a todos los que venden ropa.

MODIFICADORES = {
    "femenino": "mujer mujeres dama damas femenino femenina femeninos femeninas chica chicas señora señoras",
    "masculino": "hombre hombres caballero caballeros masculino masculina masculinos chico chicos señor señores",
    "infantil": "niño niños niña niñas nino ninos nina ninas bebe bebes infantil infantiles kids",
    "escolar": "colegio colegios escolar escolares estudiante estudiantes",
}
_RAIZ_MODIF = {raiz(normalizar(w)): g for g, ws in MODIFICADORES.items() for w in ws.split()}
_MODIF_QUE_FILTRAN = {"infantil", "escolar"}
_RUBROS_COMIDA = {normalizar(x) for x in ("Restaurante", "Cafetería, heladería y postres", "Bar y bebidas",
                                          "Comidas rápidas", "Restaurantes", "Cafés, Repostería y Heladerías")}
_EQUIV_MODIF = {"femenino": {"mujer", "dama", "femenin", "chic", "señor"},
                "masculino": {"hombr", "caballer", "masculin", "chic", "señor"},
                "infantil": {"niñ", "nin", "beb", "infantil", "kid", "junior"},
                "escolar": {"colegi", "escolar", "estudiant", "maleta", "morral", "lonchera", "cartuchera"}}

PESO_CAMPO = {"nombre": 1.0, "rubro": 0.9, "rubro_compuesto": 0.55, "productos_top": 0.8, "productos": 0.65,
              "descripcion": 0.25}
UMBRAL_FUERTE = 0.6          # nombre, rubro simple o productos: lo que el local DECLARA que vende
UMBRAL_RELATIVO = 0.5        # se queda quien tenga al menos la mitad de la relevancia del mejor


def _grupo_modificador(c: Concepto) -> str | None:
    ps = palabras(c.palabra)
    if not ps:
        return None
    gs = {_RAIZ_MODIF.get(raiz(p)) for p in ps if p not in VACIAS}
    gs.discard(None)
    return gs.pop() if len(gs) == 1 and all(_RAIZ_MODIF.get(raiz(p)) or p in VACIAS for p in ps) else None


def _cumple_modificador(loc: Local, grupo: str) -> bool:
    rs = loc.raices_nombre | loc.raices_rubro | loc.raices_productos | loc.raices_publico | loc.raices_descripcion
    return bool(_EQUIV_MODIF.get(grupo, set()) & rs)


def _peso_en_local(c: Concepto, loc: Local) -> float:
    """Qué tan principal es lo buscado en el local. Por un sinónimo vale un poco menos que por la palabra misma
    («ropa para niñas»: Offcorss dice «ropa»; Ramona Flowers, que es de zapatos, solo dice «moda»)."""
    literal = {raiz(p) for p in palabras(c.palabra)}
    if " " not in c.palabra.strip() and c.raices - literal:     # una frase («lavar mi carro») va completa
        exacto = _peso_raices(c, literal, loc, con_frases=False)
        sinonimo = _peso_raices(c, c.raices, loc, con_frases=True) * 0.9
        return max(exacto, sinonimo)
    return _peso_raices(c, c.raices, loc, con_frases=True)


def _peso_raices(c: Concepto, raices_: set, loc: Local, con_frases: bool) -> float:
    w = 0.0
    if raices_ & loc.raices_nombre:
        w = PESO_CAMPO["nombre"]
    if raices_ & loc.raices_rubro:
        w = max(w, PESO_CAMPO["rubro_compuesto"] if es_categoria_compuesta(loc.rubro) else PESO_CAMPO["rubro"])
    if raices_ & loc.raices_productos_top:
        w = max(w, PESO_CAMPO["productos_top"])
    elif raices_ & loc.raices_productos:
        w = max(w, PESO_CAMPO["productos"])
    if not w and con_frases and c.frases:
        if any(contiene_frase(f, " | ".join(loc.productos[:10])) for f in c.frases):
            w = PESO_CAMPO["productos_top"]
        elif any(contiene_frase(f, " | ".join([loc.rubro] + loc.productos)) for f in c.frases):
            w = PESO_CAMPO["productos"]
    if not w and raices_ & loc.raices_descripcion:
        w = PESO_CAMPO["descripcion"]
    return w


_vocab_cache: dict = {"id": None, "vocab": []}


def _corregir_palabra(palabra: str, lista: list[Local]) -> str | None:
    """«gomistas» → «gomitas», «labiales» no (no está escrito en ningún local). Solo palabras de 5+ letras
    muy parecidas a una que algún local sí declara."""
    import difflib
    if len(palabra) < 5:
        return None
    if _vocab_cache["id"] != id(lista):
        vocab = set()
        for l in lista:
            for t in [l.nombre, l.rubro] + l.productos:
                vocab.update(w for w in palabras(t) if len(w) >= 5)
        _vocab_cache.update(id=id(lista), vocab=sorted(vocab))
    conocidas = {x for sec in _sinonimos().values() for g in sec.values() for x in g["todas"]}
    if palabra in conocidas:          # «davivienda» es un banco, no «vivienda» mal escrita
        return None
    cerca = [c for c in difflib.get_close_matches(palabra, _vocab_cache["vocab"], n=3, cutoff=0.84)
             if c != palabra and c[0] == palabra[0] and abs(len(c) - len(palabra)) <= 2]
    return cerca[0] if cerca else None


def buscar_locales(db: Session, consulta: str, incluir_torre: bool = False,
                   incluir_servicios: bool = True) -> list[Resultado]:
    lista = locales(db, incluir_torre=incluir_torre, incluir_servicios=incluir_servicios)
    todos = catalogo(db)["locales"]          # la misma lista mientras no cambie el catálogo (para los cachés)
    texto = normalizar(_y_por_ampersand(consulta))
    cons = [c for c in conceptos(texto, "locales") if c.palabra not in PALABRAS_DE_PEDIDO]
    # "restaurante de comida mexicana": si hay algo concreto (mexicana), "restaurante"/"comida" no cuentan
    # …pero solo cuenta como «concreta» una palabra que algún local declara: «me puedes RECOMENDAR dónde comer»
    # no puede tapar a «comer» (antes no salía ningún restaurante)
    concretos = [c for c in cons if normalizar(c.palabra) not in PALABRAS_GENERICAS and
                 (_grupo_modificador(c) or any(_peso_en_local(c, l) >= UMBRAL_FUERTE for l in lista))]
    if concretos:
        cons = concretos
    modifs = {id(c): _grupo_modificador(c) for c in cons}
    producto = [c for c in cons if not modifs[id(c)]]
    publico = [c for c in cons if modifs[id(c)]]
    if not producto:              # «¿tienen locales para niños?»: el público ES lo que busca
        producto, publico = cons, []
    for c in producto:   # palabra específica que nadie declara → se amplía a su grupo
        if c.respaldo and not any(c.raices & (l.raices_nombre | l.raices_rubro | l.raices_productos) for l in lista):
            c.raices, c.frases = c.respaldo
    for i, c in enumerate(producto):   # «gomistas» (mal escrita) → «gomitas»
        if " " not in c.palabra and not c.grupo and not any(_peso_en_local(c, l) for l in lista):
            bien = _corregir_palabra(c.palabra, todos)
            if bien:
                nuevo = conceptos(bien, "locales")
                if nuevo:
                    producto[i] = nuevo[0]
    pesos = {id(c): {l.id: _peso_en_local(c, l) for l in lista} for c in producto}
    # La CABEZA de lo que pide es la primera palabra de producto que algún local declara: «ROPA casual»,
    # «CASCOS para moto», «ROPA deportiva». Un local que no la tiene no responde («Havana Cocina CASUAL» no vende
    # ropa; «Parqueaderos» no vende cascos). Con «y» («bolsos y zapatos») vale cualquiera.
    cabeza = None
    union = len(producto) >= 2 and bool(re.search(r"\b(y|o|e)\b", texto))
    # La cabeza tiene que ser algo que se VENDE (rubro o productos de algún local), no solo parte de un nombre:
    # en «la empresa casa asociados» (era «Cala Asociados»), «casa» solo está en el nombre CASA DEL LIBRO.
    if len(producto) >= 2 and not union:
        cabeza = next((c for c in producto if any(c.raices & (l.raices_rubro | l.raices_productos) and
                                                  pesos[id(c)][l.id] >= UMBRAL_FUERTE for l in lista)), None)
    n = max(len(lista), 1)
    idf = {}
    for c in producto:
        df = sum(1 for w in pesos[id(c)].values() if w >= UMBRAL_FUERTE) or sum(1 for w in pesos[id(c)].values() if w)
        idf[id(c)] = math.log((n + 1) / (df + 1)) + 0.2
    resultados = []
    for loc in lista:
        exacto = _nombre_en_texto(loc.nombre, texto)
        relevancia, cubiertos, fuertes, cercanos = 0.0, [], [], []
        declarado = loc.raices_nombre | loc.raices_rubro | loc.raices_productos
        for c in producto:
            w = pesos[id(c)][loc.id]
            if w:
                relevancia += idf[id(c)] * w
                cubiertos.append(c.palabra)
                if w >= UMBRAL_FUERTE:
                    fuertes.append(c.palabra)
            if c.amplio and c.palabra not in fuertes and c.amplio & declarado:
                cercanos.append(c.palabra)
        mods = [c.palabra for c in publico if _cumple_modificador(loc, modifs[id(c)])]
        if not exacto:
            exacto = _palabra_unica_del_nombre(loc, texto, todos)
        if exacto or relevancia > 0 or cercanos:
            r = Resultado(loc, relevancia * 10 + (100 if exacto else 0), cubiertos, exacto, fuertes, cercanos,
                          relevancia, mods)
            r._grupos_publico = {modifs[id(c)] for c in publico}
            r._sin_cabeza = bool(cabeza) and pesos[id(cabeza)][loc.id] < UMBRAL_FUERTE
            r._union = union
            resultados.append(r)
    if not any(r.nombre_exacto for r in resultados):
        # «Manhata», «Firts Clases Store», «la empresa casa asociados» (Cala Asociados): casi el nombre de un local.
        # Si ya hay locales que declaran lo buscado, solo cuenta si el nombre está casi completo (2+ palabras).
        hay_fuertes = any(r.fuertes for r in resultados)
        parecido = _nombre_parecido(texto, lista, minimo=0.9 if hay_fuertes else 0.84, min_palabras=2 if hay_fuertes else 1)
        if parecido:
            resultados = [r for r in resultados if r.local.id != parecido.id]
            resultados.insert(0, Resultado(parecido, 100, [], True, [], [], 0.0, []))
    resultados.sort(key=lambda r: (-r.nombre_exacto, -r.relevancia, -len(r.modificadores or []),
                                   normalizar(r.local.nombre)))
    return resultados


_unicas_cache: dict = {"id": None, "df": {}}


def _palabra_unica_del_nombre(loc: Local, texto: str, lista: list[Local]) -> bool:
    """«Sura» → EPS Sura, «pádel» → Club House Pádel: una palabra del nombre (no la primera) que no es un
    producto ni aparece en el nombre de ningún otro local, escrita tal cual por el cliente."""
    if _unicas_cache["id"] != id(lista):
        en_nombres: dict = {}
        en_productos: dict = {}
        for l in lista:
            for w in set(palabras(_y_por_ampersand(l.nombre))):
                en_nombres[w] = en_nombres.get(w, 0) + 1
            for w in set(palabras(" ".join([l.rubro] + l.productos))):
                en_productos[w] = en_productos.get(w, 0) + 1
        _unicas_cache.update(id=id(lista), df=(en_nombres, en_productos))
    en_nombres, en_productos = _unicas_cache["df"]
    tw = set(palabras(texto))
    nombre_ws = set(palabras(_y_por_ampersand(loc.nombre)))
    resto = {w for w in tw - nombre_ws if w not in VACIAS and w not in PALABRAS_DE_PEDIDO and len(w) > 2}
    if resto:          # «tienes la RED social?» no es nombrar a Ibiza Social Club
        return False
    for w in palabras(_y_por_ampersand(loc.nombre))[1:]:
        if len(w) >= 4 and w in tw and w not in VACIAS and w not in PALABRAS_DE_PEDIDO \
                and w not in PALABRAS_GENERICAS and w not in _PALABRAS_COMUNES \
                and en_nombres.get(w, 0) == 1 and en_productos.get(w, 0) <= 1:
            return True
    return False


def _y_por_ampersand(t: str) -> str:
    """«J&A» y «JyA» son lo mismo: el & entre letras se escribe «y»."""
    return re.sub(r"(?i)\b([a-z0-9])\s*&\s*([a-z0-9])\b", r"\1y\2", t or "")


def _nombre_parecido(texto: str, lista: list[Local], minimo: float = 0.84, min_palabras: int = 1) -> Local | None:
    """Mensaje corto que es casi el nombre de un local: «Manhata» → Manhattan Accesorios, «Firts Clases Store»
    → First class store. Solo si uno solo es muy parecido."""
    import difflib
    q = [w for w in palabras(texto) if w not in VACIAS and w not in PALABRAS_DE_PEDIDO]
    if not q or len(q) > 4 or len(q) < min_palabras or sum(len(w) for w in q) < 5:
        return None
    qc = "".join(q)
    mejores = []
    for loc in lista:
        nw = [w for w in palabras(_y_por_ampersand(loc.nombre)) if w not in VACIAS]
        if not nw:
            continue
        p = difflib.SequenceMatcher(None, qc, "".join(nw)).ratio()
        if len(q) == 1:      # una palabra: contra cada palabra del nombre («manhata» ~ «manhattan»)
            p = max([p] + [difflib.SequenceMatcher(None, qc, w).ratio() for w in nw if len(w) >= 5])
        mejores.append((p, loc))
    mejores.sort(key=lambda x: -x[0])
    if mejores and mejores[0][0] >= minimo and (len(mejores) == 1 or mejores[0][0] - mejores[1][0] >= 0.05):
        return mejores[0][1]
    return None


def seleccionar_relevantes(resultados: list[Resultado]) -> list[Resultado]:
    """
    De todos los que tocan la búsqueda, los que de verdad responden:
      - si alguno coincide por nombre, solo esos;
      - si alguno DECLARA lo buscado (nombre, rubro, productos): los que tienen al menos la mitad de la
        relevancia del mejor (la palabra rara manda: «ropa DEPORTIVA»);
      - niños / colegio: si hay locales que lo cumplen, solo esos;
      - si nadie lo declara, los que lo mencionan en la descripción (el juez decide si de verdad lo ofrecen).
    Orden: primero los que más responden; a igual nivel, alfabético (equidad).
    """
    if not resultados:
        return []
    exactos = [r for r in resultados if r.nombre_exacto]
    if exactos:
        return exactos
    resultados = [r for r in resultados if r.cubiertos]
    if not resultados:
        return []
    con_fuertes = [r for r in resultados if r.fuertes]
    base = con_fuertes or resultados
    base = [r for r in base if not getattr(r, "_sin_cabeza", False)] or base
    mx = max(r.relevancia for r in base)
    # «bolsos y zapatos»: vale el que tenga una de las dos cosas (umbral más bajo)
    umbral = 0.3 if getattr(base[0], "_union", False) else UMBRAL_RELATIVO
    sel = [r for r in base if r.relevancia >= mx * umbral]
    grupos = getattr(base[0], "_grupos_publico", set()) or set()
    if grupos & {"femenino", "masculino", "infantil"}:
        # «cremas para mujer», «zapatos para dama»: nadie pide comida «para mujer» (salían Chivo Loco y Densa)
        no_comida = [r for r in sel if normalizar(r.local.rubro) not in _RUBROS_COMIDA]
        if no_comida:
            sel = no_comida
    if grupos & {"femenino", "masculino"} and "infantil" not in grupos:
        # «zapatos para dama»: una tienda infantil (Offcorss) no, salvo que diga que también vende para mujer
        sel = [r for r in sel if r.modificadores or not _cumple_modificador(r.local, "infantil")] or sel
    cumplen = [r for r in sel if r.modificadores]
    if grupos & _MODIF_QUE_FILTRAN and cumplen:
        sel = cumplen                     # niños / colegio: solo los que lo cumplen
    elif grupos & {"femenino", "masculino"} and len(cumplen) >= 2 and len(sel) >= 12:
        # «ropa para dama» (30 tiendas de ropa): los que dicen que venden para mujer, más los que lo tienen en el
        # nombre o el rubro. «bolso para dama» (11) no se recorta: un bolso casi siempre es para mujer.
        sel = [r for r in sel if r.modificadores or r.relevancia >= mx * 0.85]
    nivel = lambda r: 0 if r.relevancia >= mx * 0.85 else 1
    return sorted(sel, key=lambda r: (nivel(r), -len(r.modificadores or []), normalizar(r.local.nombre)))


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
    n = normalizar(_y_por_ampersand(nombre))
    texto_normalizado = normalizar(_y_por_ampersand(texto_normalizado))
    if len(n) < 3:
        return False
    if contiene_frase(n, texto_normalizado):
        return True
    # nombres largos o con números ("12B Burger Angus", "La Barra 1516"): basta la primera palabra distintiva
    ps = [p for p in palabras(n) if p not in VACIAS]
    if not ps:
        return False
    tw = palabras(texto_normalizado)
    if "&" in nombre:      # «J&A» → «jya»: esa sola palabra ya es el nombre
        amp = normalizar(_y_por_ampersand(re.search(r"\S*&\S*", nombre).group(0)))
        if amp and amp in tw:
            return True
    p = ps[0]
    distintiva = (len(p) >= 5 or (len(p) >= 3 and any(ch.isdigit() for ch in p))) and p not in _PALABRAS_COMUNES
    return distintiva and p in tw


# Primeras palabras de nombres que también son productos o rubros («Accesorios J&A», «Colchones Wonder», «Calzado
# Rich»): decir «accesorios» no es nombrar a ACCESORIOS J&A
_PALABRAS_COMUNES = set("""
accesorios colchones calzado drogas drogueria optica ortopedicos jugueteria dulceria artesanias moviles muebles
tienda tiendas almacen restaurante cafe casa club clinica centro gimnasio parqueaderos punto colegio
""".split())


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