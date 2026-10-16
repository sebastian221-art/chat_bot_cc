# 📄 ARCHIVO: backend/services/sincronizador.py
"""
SINCRONIZADOR AUTOMÁTICO — Any se alimenta sola de las páginas oficiales.

El Centro Comercial no quiere estar actualizando a mano. Este módulo lee,
cada cierto tiempo (ver main.py → tarea en segundo plano) o cuando se pide
desde el panel, las fuentes oficiales y actualiza la base:

  🎬 CINELANDIA (cinelandia.com.co, ciudad=2 = San Gil) — todo es texto HTML:
     • Cartelera + horarios del día          → tabla cine_funciones
     • Confitería (combos y precios)          → info extra del local Cine
     • Tarifas de San Gil                     → info extra del local Cine
     • Próximos estrenos                      → info extra del local Cine

  🏢 EL PUENTE (elpuente.com.co, Wix):
     • Servicios (parqueadero, punto de info, auditorio, enfermería, baños…)
                                              → Base de conocimiento
     • Torre Médica y Empresarial (directorio por piso con teléfonos)
                                              → locales con zona "Torre Médica"
     • Campañas (eventos / sorteos / promos): la página NO tiene texto, es UN
       AFICHE (imagen). Se descarga la imagen más grande de la página, se
       calcula su hash y, SOLO si cambió, se lee con el modelo de VISIÓN de
       Groq para extraer eventos, sorteos y promociones en JSON → se cargan
       con PRIORIDAD ALTA para que roten bien.
     • Registro de facturas → Base de conocimiento con el LINK oficial.

REGLAS DE SEGURIDAD (para no dañar lo que ya está bien):
  - Si una fuente falla o devuelve vacío, NO se borra nada: se conserva lo
    que había y se registra el error en el resumen.
  - Todo es upsert por nombre/título: volver a correrlo no duplica.
  - Cada bloque va en su propio try/except: si falla uno, los demás siguen.
"""
import re
import json
import base64
import hashlib
import logging
import datetime
import unicodedata

import httpx
from sqlalchemy.orm import Session

logger = logging.getLogger("mall_bot")

# ── Fuentes oficiales ─────────────────────────────────────────────
CINE_CIUDAD        = 2  # San Gil en cinelandia.com.co
URL_CARTELERA      = "https://www.cinelandia.com.co/san-gil"
URL_CONFITERIA     = f"https://www.cinelandia.com.co/confiteria.php?ciudad={CINE_CIUDAD}"
URL_TARIFAS        = f"https://www.cinelandia.com.co/promos.php?ciudad={CINE_CIUDAD}"
URL_PROXIMAMENTE   = f"https://www.cinelandia.com.co/proximamente.php?ciudad={CINE_CIUDAD}"
URL_SERVICIOS      = "https://www.elpuente.com.co/servicios"
URL_TORRE          = "https://www.elpuente.com.co/torre-empresarial"
URL_CAMPANAS       = "https://www.elpuente.com.co/eventos-de-temporada"
URL_REGISTRO_FACT  = "https://www.elpuente.com.co/registro-de-facturas"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# Prioridad ALTA por defecto para lo que entra por sincronización
PRIORIDAD_EVENTO = 4
PRIORIDAD_SORTEO = 5
PRIORIDAD_PROMO  = 5


# ══════════════════════════════════════════════════════════════════
# UTILIDADES
# ══════════════════════════════════════════════════════════════════
def _norm(s: str) -> str:
    s = (s or "").lower().strip()
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _limpiar(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


async def _get(url: str, timeout: float = 25.0) -> str:
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers={"User-Agent": UA}) as c:
        r = await c.get(url)
        r.raise_for_status()
        return r.text


async def _get_bytes(url: str, timeout: float = 40.0) -> tuple[bytes, str]:
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers={"User-Agent": UA}) as c:
        r = await c.get(url)
        r.raise_for_status()
        return r.content, (r.headers.get("content-type") or "image/png").split(";")[0].strip()


def _soup(html: str):
    from bs4 import BeautifulSoup
    return BeautifulSoup(html, "html.parser")


def _texto_lineas(html: str) -> list[str]:
    """Texto visible de la página, una línea por bloque, sin scripts/estilos."""
    s = _soup(html)
    for t in s(["script", "style", "noscript", "svg"]):
        t.decompose()
    txt = s.get_text("\n")
    return [_limpiar(l) for l in txt.split("\n") if _limpiar(l)]


RE_HORA = re.compile(r"^\d{1,2}:\d{2}\s*[AP]\.?M\.?$", re.I)
RE_PRECIO = re.compile(r"\$?\s?(\d{1,3}(?:[.,]\d{3})+|\d{4,6})")


# ══════════════════════════════════════════════════════════════════
# 🎬 CINELANDIA
# ══════════════════════════════════════════════════════════════════
def leer_cartelera(html: str) -> dict:
    """
    Devuelve {"hoy": [peliculas], "proximas": [peliculas], "fecha": "AAAAMMDD"}.
    Cada película: {id, title, formato, genero, clasificacion, duracion,
    horarios[list], estreno(bool), fecha}.

    Se basa en los enlaces pelicula.php?id=N (cada película tiene varios:
    póster, título, horarios). Agrupa por id y lee la ficha del bloque
    contenedor por patrones de texto ("FORMATO:", "GENERO:", …).
    """
    soup = _soup(html)
    grupos: dict[str, dict] = {}

    for a in soup.find_all("a", href=True):
        m = re.search(r"pelicula\.php\?id=(\d+)", a["href"])
        if not m:
            continue
        pid = m.group(1)
        g = grupos.setdefault(pid, {"id": pid, "textos": [], "horarios": [], "fechas": set(), "anchor": None})
        t = _limpiar(a.get_text(" "))
        fm = re.search(r"fecha=(\d{8})", a["href"])
        if fm:
            g["fechas"].add(fm.group(1))
        if not t:
            continue
        if RE_HORA.match(t):
            if t.upper().replace(".", "") not in [h.upper().replace(".", "") for h in g["horarios"]]:
                g["horarios"].append(t.upper().replace(".", ""))
        else:
            g["textos"].append(t)
            if g["anchor"] is None and not t.lower().startswith("póster") and t.upper() not in ("COMPRAR ENTRADAS", "VER DETALLES", "VISIÓN 2D", "VISIÓN 3D"):
                g["anchor"] = a

    GENERICOS = {"comprar entradas", "ver detalles", "visión 2d", "visión 3d", "vision 2d", "vision 3d", "horarios", "clic"}
    peliculas = []
    for pid, g in grupos.items():
        # Título = el texto más largo que no sea botón/hora/"Póster de …"
        candidatos = [t for t in g["textos"] if _norm(t) not in GENERICOS and not t.lower().startswith("póster de") and not t.lower().startswith("poster de")]
        if not candidatos:
            # a veces solo viene "Póster de X"
            for t in g["textos"]:
                if t.lower().startswith(("póster de ", "poster de ")):
                    candidatos.append(t.split(" de ", 1)[1])
        if not candidatos:
            continue
        title = max(candidatos, key=len).strip()

        # Ficha técnica: subir por los padres del enlace hasta encontrar el bloque con FORMATO/DURACIÓN
        ficha = {"formato": "", "genero": "", "clasificacion": "", "duracion": "", "estreno": False}
        nodo = g["anchor"]
        bloque_txt = ""
        for _ in range(8):
            if nodo is None:
                break
            txt = _limpiar(nodo.get_text(" "))
            if ("DURACI" in txt.upper() or "FORMATO" in txt.upper()) and title.upper()[:10] in txt.upper():
                bloque_txt = txt
                break
            nodo = nodo.parent
        if bloque_txt:
            def _campo(pat):
                mm = re.search(pat + r"\s*:?\**\s*([^|]+?)(?=\s+(?:FORMATO|GENERO|GÉNERO|CLASIFICACI|DURACI|COMPRAR|\d{1,2}:\d{2})|$)", bloque_txt, re.I)
                return _limpiar(mm.group(1)) if mm else ""
            ficha["formato"]       = _campo(r"FORMATO")
            ficha["genero"]        = _campo(r"G[EÉ]NERO")
            ficha["clasificacion"] = _campo(r"CLASIFICACI[OÓ]N")
            ficha["duracion"]      = _campo(r"DURACI[OÓ]N")
            ficha["estreno"]       = "ESTRENO" in bloque_txt.upper()

        fechas = sorted(g["fechas"])
        peliculas.append({
            "id": pid, "title": title, "horarios": g["horarios"], "fecha": fechas[0] if fechas else "",
            **ficha,
        })

    # Fecha "de hoy" = la más común entre las películas con horarios
    fechas_con_horario = [p["fecha"] for p in peliculas if p["horarios"] and p["fecha"]]
    hoy = max(set(fechas_con_horario), key=fechas_con_horario.count) if fechas_con_horario else ""
    en_cartelera = [p for p in peliculas if p["horarios"] and (not hoy or p["fecha"] == hoy)]
    ids_hoy = {p["id"] for p in en_cartelera}
    proximas = [p for p in peliculas if p["id"] not in ids_hoy]
    return {"hoy": en_cartelera, "proximas": proximas, "fecha": hoy}


def leer_confiteria(html: str) -> list[dict]:
    """Devuelve [{nombre, precio, precio_tarjeta}]. Lee por patrones de texto:
    un nombre de combo seguido de 1–2 precios."""
    lineas = _texto_lineas(html)
    IGNORAR = {"precio", "con tarjeta", "tarjeta cliente", "sin tarjeta", "confitería", "confiteria", "combos", "resumen de confitería", "comprar", "agregar"}
    combos, nombre, precios = [], None, []

    def _cerrar():
        nonlocal nombre, precios
        if nombre and precios:
            combos.append({"nombre": nombre, "precio": precios[0], "precio_tarjeta": precios[1] if len(precios) > 1 else ""})
        nombre, precios = None, []

    for l in lineas:
        pm = RE_PRECIO.findall(l)
        if pm and len(l) <= 40:
            # línea de precio(s)
            for p in pm:
                precios.append(p.replace(".", ",") if "," not in p else p)
            if len(precios) >= 2:
                _cerrar()
            continue
        # posible nombre de combo
        if 2 <= len(l) <= 40 and _norm(l) not in IGNORAR and not RE_HORA.match(l) and "$" not in l:
            _cerrar()
            nombre = l
    _cerrar()
    # limpieza: quitar duplicados y nombres sin pinta de combo
    vistos, limpios = set(), []
    for c in combos:
        k = _norm(c["nombre"])
        if k in vistos or len(k) < 3:
            continue
        vistos.add(k)
        limpios.append(c)
    return limpios


def leer_tarifas(html: str) -> list[str]:
    """Devuelve líneas legibles de la tabla de tarifas (San Gil)."""
    soup = _soup(html)
    lineas = []
    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            celdas = [_limpiar(td.get_text(" ")) for td in tr.find_all(["td", "th"])]
            celdas = [c for c in celdas if c]
            if len(celdas) >= 3 and any(RE_PRECIO.search(c) for c in celdas):
                lineas.append(" | ".join(celdas))
    if not lineas:
        # respaldo: líneas de texto con precios
        for l in _texto_lineas(html):
            if RE_PRECIO.search(l) and len(l) < 160:
                lineas.append(l)
    vistas, unicas = set(), []
    for l in lineas:
        if l not in vistas:
            vistas.add(l); unicas.append(l)
    return unicas[:40]


def leer_proximamente(html: str) -> list[str]:
    """Títulos de próximos estrenos."""
    soup = _soup(html)
    titulos = []
    for a in soup.find_all("a", href=True):
        if "pelicula.php" in a["href"]:
            t = _limpiar(a.get_text(" "))
            if t and not RE_HORA.match(t) and t.upper() not in ("COMPRAR ENTRADAS", "VER DETALLES") and not t.lower().startswith(("póster", "poster")):
                if t not in titulos:
                    titulos.append(t)
    return titulos[:20]


async def sincronizar_cine(db: Session) -> dict:
    """Actualiza cartelera (cine_funciones) e info extra (tarifas, confitería, estrenos) del local Cine."""
    from services.cine import find_cine_store
    from models.cine_funcion import CineFuncion

    res = {"peliculas": 0, "combos": 0, "tarifas": 0, "proximas": 0, "errores": []}
    cine = find_cine_store(db)
    if not cine:
        res["errores"].append("No existe el local del Cine en el sistema (créalo o importa la plantilla de cine una vez).")
        return res

    # ── Cartelera ──
    try:
        html = await _get(URL_CARTELERA)
        cart = leer_cartelera(html)
        if cart["hoy"]:
            db.query(CineFuncion).filter(CineFuncion.store_id == cine.id).delete()
            for p in cart["hoy"]:
                ficha = " · ".join(x for x in [p["genero"], p["clasificacion"], p["formato"], p["duracion"]] if x)
                desc = ficha
                if p["estreno"]:
                    desc = ("ESTRENO · " + desc).strip(" ·")
                db.add(CineFuncion(store_id=cine.id, title=p["title"][:150], showtimes=", ".join(p["horarios"])[:200],
                                   description=desc, is_premiere=bool(p["estreno"]), active=True))
            res["peliculas"] = len(cart["hoy"])
            res["proximas"] = len(cart["proximas"])
            db.commit()
        else:
            res["errores"].append("Cartelera: la página no devolvió películas con horarios (se conservó la anterior).")
    except Exception as e:
        db.rollback()
        res["errores"].append(f"Cartelera: {str(e)[:120]}")
        cart = {"hoy": [], "proximas": [], "fecha": ""}

    # ── Info extra: tarifas + confitería + próximos estrenos ──
    bloques = []
    try:
        tar = leer_tarifas(await _get(URL_TARIFAS))
        if tar:
            bloques.append("💵 TARIFAS DE CINE (San Gil, compra en web; en taquilla pueden variar):\n" + "\n".join("  • " + t for t in tar))
            res["tarifas"] = len(tar)
    except Exception as e:
        res["errores"].append(f"Tarifas: {str(e)[:120]}")
    try:
        combos = leer_confiteria(await _get(URL_CONFITERIA))
        if combos:
            lin = []
            for c in combos:
                l = f"  • {c['nombre']}: ${c['precio']}"
                if c["precio_tarjeta"]:
                    l += f" (con Tarjeta Cliente ${c['precio_tarjeta']})"
                lin.append(l)
            bloques.append("🍿 CONFITERÍA Y COMBOS:\n" + "\n".join(lin))
            res["combos"] = len(combos)
    except Exception as e:
        res["errores"].append(f"Confitería: {str(e)[:120]}")
    try:
        prox = [p["title"] for p in cart.get("proximas", [])]
        if not prox:
            prox = leer_proximamente(await _get(URL_PROXIMAMENTE))
        if prox:
            bloques.append("🎬 PRÓXIMOS ESTRENOS: " + ", ".join(prox))
            res["proximas"] = len(prox)
    except Exception as e:
        res["errores"].append(f"Próximamente: {str(e)[:120]}")

    if bloques:
        hoy = datetime.date.today().strftime("%d/%m/%Y")
        cine.extra_info = f"(Actualizado automáticamente desde cinelandia.com.co el {hoy})\n\n" + "\n\n".join(bloques)
        db.commit()
    return res


# ══════════════════════════════════════════════════════════════════
# 🏢 EL PUENTE — SERVICIOS, TORRE MÉDICA, REGISTRO DE FACTURAS
# ══════════════════════════════════════════════════════════════════
SERVICIOS_CONOCIDOS = [
    "Parqueadero", "Punto de información", "Punto de informacion", "Registro de facturas",
    "Auditorio", "Enfermería", "Enfermeria", "Baños", "Banos", "Zonas de esparcimiento",
    "Horario de atención", "Horario de atencion", "Wifi", "Administración", "Administracion",
]


def leer_servicios(html: str) -> list[dict]:
    """Devuelve [{titulo, contenido}] segmentando el texto por los nombres de servicio conocidos."""
    lineas = _texto_lineas(html)
    # quitar menú/pie repetitivo
    lineas = [l for l in lineas if len(l) > 2]
    secciones, actual, buf = [], None, []

    def _es_titulo(l):
        n = _norm(l)
        return len(l) <= 40 and any(_norm(k) == n or n.startswith(_norm(k)) for k in SERVICIOS_CONOCIDOS)

    for l in lineas:
        if _es_titulo(l):
            if actual and buf:
                secciones.append({"titulo": actual, "contenido": " ".join(buf)})
            actual, buf = l, []
        elif actual:
            if len(buf) < 25:
                buf.append(l)
    if actual and buf:
        secciones.append({"titulo": actual, "contenido": " ".join(buf)})
    # unir duplicados del mismo título
    unidos: dict[str, str] = {}
    for s in secciones:
        k = _norm(s["titulo"])
        unidos[k] = (unidos.get(k, "") + " " + s["contenido"]).strip()
    return [{"titulo": t.capitalize(), "contenido": c[:1800]} for t, c in unidos.items() if len(c) > 30]


def leer_torre(html: str) -> list[dict]:
    """
    Devuelve [{piso, oficina, nombre, detalle, telefonos[list]}] del directorio
    de la Torre Médica. Segmenta por 'Piso N' y luego por 'Oficina(s) NNN'.
    """
    lineas = _texto_lineas(html)
    entidades: list[dict] = []
    piso = ""
    actual: dict | None = None

    RE_PISO = re.compile(r"^Piso\s+(\d)\b", re.I)
    # "Oficina 206", "Oficinas 201-204", "Oficinas 503, 509 y 512", y opcionalmente el nombre pegado
    RE_OFI = re.compile(r"^Oficinas?\s+(\d[\d\-–\s,y/]*)\s*(?:[:\-–]\s*)?(?P<resto>.*)$", re.I)

    def _cerrar():
        nonlocal actual
        if actual and len(actual.get("nombre", "")) >= 3:
            actual["detalle"] = " · ".join(actual["detalle"])[:400]
            actual["telefonos"] = actual["telefonos"][:6]
            entidades.append(actual)
        actual = None

    def _telefonos(x: str) -> list[str]:
        # Separar primero por los separadores típicos entre números (" - ", ",", "/", " y ")
        # y luego quedarse con cada grupo de 7+ dígitos (los espacios internos
        # de un mismo número, ej. "318 522 1963", sí se conservan).
        out = []
        for pieza in re.split(r"\s[-–]\s|[,;/]|\sy\s|\s{2,}", x):
            d = re.sub(r"\D", "", pieza)
            if 7 <= len(d) <= 15:
                out.append(d)
        return out

    for l in lineas:
        mp = RE_PISO.match(l)
        if mp:
            _cerrar()
            piso = f"Piso {mp.group(1)}"
            continue
        mo = RE_OFI.match(l)
        if mo:
            _cerrar()
            oficina = re.sub(r"-+", "-", _limpiar(mo.group(1)).replace(" y ", "-").replace("y", "-").replace(",", "-").replace(" ", "")).strip("-")
            actual = {"piso": piso or "Torre Médica", "oficina": oficina[:60], "nombre": "", "detalle": [], "telefonos": []}
            resto = _limpiar(mo.group("resto") or "")
            if resto:
                actual["nombre"] = resto[:150]
            continue
        if actual is None:
            continue
        if not actual["nombre"]:
            actual["nombre"] = l[:150]
            continue
        tels = _telefonos(l)
        if re.search(r"tel[eé]fono|tel\.|contacto|whatsapp|cel", l, re.I) or (tels and len(l) < 90):
            actual["telefonos"] += tels
        elif len(l) < 140 and len(actual["detalle"]) < 4:
            actual["detalle"].append(l)
    _cerrar()
    return entidades


def _tokens(s: str) -> set:
    return {t for t in re.findall(r"[a-z0-9]+", _norm(s)) if len(t) >= 4 and t not in {"clinica", "doctor", "doctora", "oficina", "centro", "salud", "medic", "medica", "medico", "especialistas", "asociados", "integral", "integrales"}}


def _buscar_store_parecido(db, nombre: str, zona: str = "torre"):
    """Encuentra un local existente con el mismo nombre (sin tildes) o que comparta un token distintivo."""
    from models.store import Store
    n = _norm(nombre)
    cands = db.query(Store).filter(Store.active == True).all()
    for s in cands:
        if _norm(s.name) == n:
            return s
    tk = _tokens(nombre)
    if not tk:
        return None
    mejores = []
    for s in cands:
        if zona and zona not in _norm(s.location_hint or "") and zona not in _norm(s.category or ""):
            continue
        comun = tk & _tokens(s.name)
        if comun:
            mejores.append((len(comun), s))
    if mejores:
        mejores.sort(key=lambda x: -x[0])
        return mejores[0][1]
    return None


async def sincronizar_mall(db: Session) -> dict:
    """Servicios → conocimiento; Torre Médica → locales; Registro de facturas → conocimiento."""
    from models.knowledge import KnowledgeEntry
    from models.store import Store

    res = {"servicios": 0, "torre": 0, "errores": []}
    hoy = datetime.date.today().strftime("%d/%m/%Y")

    def _upsert_conocimiento(titulo: str, contenido: str):
        k = db.query(KnowledgeEntry).filter(KnowledgeEntry.title.ilike(titulo)).first()
        if k:
            k.content = contenido
            k.active = True
        else:
            db.add(KnowledgeEntry(title=titulo[:150], content=contenido, active=True))

    # ── Servicios ──
    try:
        secs = leer_servicios(await _get(URL_SERVICIOS))
        for s in secs:
            _upsert_conocimiento(f"Servicio del mall: {s['titulo']}", s["contenido"] + f" (Fuente: elpuente.com.co/servicios, {hoy})")
        res["servicios"] = len(secs)
        db.commit()
    except Exception as e:
        db.rollback()
        res["errores"].append(f"Servicios: {str(e)[:120]}")

    # ── Registro de facturas: siempre con el link oficial ──
    try:
        _upsert_conocimiento(
            "Registro de facturas (sorteos)",
            "Para participar en los sorteos del Centro Comercial El Puente hay que REGISTRAR LAS FACTURAS de compra. "
            f"Se puede hacer en línea en este enlace oficial: {URL_REGISTRO_FACT} , o en el Punto de Información (Pasillo Barichara). "
            "Las facturas se registran dentro del mismo mes de la compra. Los martes y miércoles se dan números dobles. "
            "Cuando un cliente pregunte cómo registrar facturas o cómo participar en un sorteo, dale SIEMPRE este enlace.",
        )
        db.commit()
    except Exception as e:
        db.rollback()
        res["errores"].append(f"Registro facturas: {str(e)[:120]}")

    # ── Torre Médica ──
    try:
        ents = leer_torre(await _get(URL_TORRE))
        for e_ in ents:
            tel_principal = e_["telefonos"][0] if e_["telefonos"] else ""
            desc = e_["detalle"]
            if e_["telefonos"]:
                desc = (desc + " | Teléfonos: " + ", ".join(e_["telefonos"])).strip(" |")
            desc = (desc + f" | Torre Médica y Empresarial, {e_['piso']}, oficina {e_['oficina']}").strip(" |")
            st = _buscar_store_parecido(db, e_["nombre"], zona="torre")
            if st:
                st.floor = e_["piso"]
                st.local_number = e_["oficina"][:60] or st.local_number
                if tel_principal:
                    st.phone = re.sub(r"\D", "", tel_principal)[:60]
                st.description = desc[:4000]
                st.location_hint = st.location_hint or "Torre Médica"
            else:
                db.add(Store(
                    name=e_["nombre"], local_number=e_["oficina"][:60] or "S/N", floor=e_["piso"],
                    category="Torre Médica y Empresarial", description=desc[:4000],
                    phone=re.sub(r"\D", "", tel_principal)[:60], location_hint="Torre Médica",
                    tags="torre médica, consultorio, oficina, salud, " + _norm(e_["nombre"]), active=True,
                ))
            res["torre"] += 1
        db.commit()
    except Exception as e:
        db.rollback()
        res["errores"].append(f"Torre médica: {str(e)[:120]}")

    return res


# ══════════════════════════════════════════════════════════════════
# 🖼️ AFICHE DE CAMPAÑAS → VISIÓN → EVENTOS / SORTEOS / PROMOS
# ══════════════════════════════════════════════════════════════════
def _candidatas_afiche(html: str) -> list[str]:
    """
    Encuentra el AFICHE (la imagen más grande de Wix en la página) y devuelve
    varias URLs para descargarlo, de la más conveniente a la más cruda.

    Por qué así: Wix publica la MISMA imagen en varios tamaños (miniaturas de
    96px, 400px, 1920px…). Antes se elegía mal (salía la de 96px) y además
    al quitar el formato AVIF la URL quedaba inválida (403). Ahora:
      1. Se identifica la imagen por su tamaño ORIGINAL (…~mv2_d_1920_1920…).
      2. Se CONSTRUYE la URL de descarga en grande y en JPG (que la visión
         acepta), con respaldos si Wix rechaza alguna variante.
    """
    medias: dict[str, int] = {}
    for u in set(re.findall(r"https://static\.wixstatic\.com/media/([^/\s\"'<>)]+)", html)):
        m = re.search(r"mv2_d_(\d+)_(\d+)", u)
        area = int(m.group(1)) * int(m.group(2)) if m else 0
        medias[u] = max(medias.get(u, 0), area)
    if not medias:
        return []
    # también considerar tamaños pedidos w_,h_ cuando no hay mv2_d
    for u in list(medias):
        if medias[u] == 0:
            for mm in re.finditer(re.escape(u) + r"/v1/fill/w_(\d+),h_(\d+)", html):
                medias[u] = max(medias[u], int(mm.group(1)) * int(mm.group(2)))
    media, area = max(medias.items(), key=lambda kv: kv[1])
    if area < 600 * 600:
        return []
    base = f"https://static.wixstatic.com/media/{media}"
    return [
        f"{base}/v1/fill/w_1600,h_1600,al_c,q_85/afiche.jpg",   # grande, JPG
        f"{base}/v1/fill/w_1600,h_1600,al_c,q_85,enc_auto/afiche.png",
        f"{base}/v1/fit/w_1600,h_1600,q_85/afiche.jpg",
        base,                                                   # original tal cual
    ]


def _url_afiche(html: str) -> str | None:
    c = _candidatas_afiche(html)
    return c[0] if c else None


async def _descargar_afiche(html: str) -> tuple[bytes, str, str]:
    """Descarga el afiche probando varias URLs (con Referer, que Wix exige a veces)."""
    candidatas = _candidatas_afiche(html)
    if not candidatas:
        raise RuntimeError("no se encontró la imagen del afiche en la página")
    ultimo = ""
    headers = {"User-Agent": UA, "Referer": "https://www.elpuente.com.co/", "Accept": "image/*,*/*;q=0.8"}
    async with httpx.AsyncClient(timeout=40.0, follow_redirects=True, headers=headers) as c:
        for url in candidatas:
            try:
                r = await c.get(url)
                if r.status_code == 200 and r.content and len(r.content) > 5000:
                    mime = (r.headers.get("content-type") or "image/jpeg").split(";")[0].strip()
                    return r.content, mime, url
                ultimo = f"{r.status_code} en {url[:90]}"
            except Exception as e:
                ultimo = f"{str(e)[:60]} en {url[:90]}"
    raise RuntimeError(f"no se pudo descargar el afiche ({ultimo})")


def _preparar_imagen_para_vision(img: bytes, mime: str) -> tuple[bytes, str]:
    """
    Convierte a JPEG y limita a 1600px / calidad 85 para que el modelo de
    visión la acepte siempre (evita AVIF/WebP raros y archivos muy pesados).
    Si Pillow no puede abrirla, se devuelve tal cual.
    """
    try:
        from PIL import Image
        import io
        im = Image.open(io.BytesIO(img))
        im = im.convert("RGB")
        im.thumbnail((1600, 1600))
        out = io.BytesIO()
        im.save(out, format="JPEG", quality=85, optimize=True)
        return out.getvalue(), "image/jpeg"
    except Exception:
        return img, mime


PROMPT_AFICHE = """Eres un extractor de datos. Esta imagen es el AFICHE OFICIAL de campañas del mes del Centro Comercial El Puente (San Gil, Colombia). Lee TODO el texto del afiche y devuelve ÚNICAMENTE un JSON válido (sin explicaciones, sin markdown) con esta forma exacta:

{"mes": "<mes y año del afiche, ej. Octubre 2026>",
 "eventos": [{"nombre": "", "fecha_inicio": "DD/MM/AAAA", "fecha_fin": "DD/MM/AAAA", "lugar": "", "horario": "", "descripcion": ""}],
 "sorteos": [{"nombre": "", "premio": "", "mecanica": "", "fecha_fin": "DD/MM/AAAA", "lugar": ""}],
 "promociones": [{"titulo": "", "detalle": "", "vigencia": "DD/MM/AAAA", "aplica_en": ""}]}

Reglas:
- EVENTOS = actividades con fecha (shows, festivales, carreras, concursos, misas, etc.).
- SORTEOS = rifas/campañas donde se gana algo registrando facturas o participando (ej. "Latido Millonario", "250 Razones").
- PROMOCIONES = descuentos, 2x1, parqueadero gratis, beneficios por facturas, etc.
- Fechas en DD/MM/AAAA. El año es el del afiche; si solo dice el día y mes, usa el mes/año del afiche.
- Si un dato no aparece, deja el campo "" (vacío). NO inventes nada que no esté en la imagen.
- Copia montos y condiciones tal cual (ej. "$180.000", "20% OFF afiliados Coomuldesa y Cajasan").
/no_think"""


def _extraer_json(texto: str) -> dict | None:
    t = re.sub(r"<think>.*?</think>", "", texto or "", flags=re.S)
    t = t.strip().strip("`")
    t = re.sub(r"^json\s*", "", t, flags=re.I)
    i, j = t.find("{"), t.rfind("}")
    if i == -1 or j == -1:
        return None
    try:
        return json.loads(t[i:j + 1])
    except Exception:
        return None


async def leer_afiche_con_vision(img_bytes: bytes, mime: str) -> dict | None:
    from services.ai import _get_groq_client, settings, _strip_thinking_tags
    client = _get_groq_client()
    b64 = base64.b64encode(img_bytes).decode("utf-8")
    if mime not in ("image/png", "image/jpeg", "image/jpg", "image/webp"):
        mime = "image/png"
    completion = await client.chat.completions.create(
        model=settings.GROQ_VISION_MODEL,
        messages=[{"role": "user", "content": [
            {"type": "text", "text": PROMPT_AFICHE},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        ]}],
        max_tokens=2500,
        temperature=0.1,
    )
    raw = _strip_thinking_tags(completion.choices[0].message.content or "")
    return _extraer_json(raw)



def _buscar_por_nombre(db, modelo, campo: str, nombre: str):
    """
    Busca un registro por nombre de forma TOLERANTE para no duplicar lo que
    ya existe (ej. afiche dice "El Latido Millonario" y la base tiene
    "Latido Millonario (Sorteo Principal)"): primero igual exacto (sin
    mayúsculas), luego sin tildes/paréntesis y por contención en ambos
    sentidos, exigiendo al menos 2 palabras significativas en común.
    """
    col = getattr(modelo, campo)
    ex = db.query(modelo).filter(col.ilike(nombre)).first()
    if ex:
        return ex
    def _clave(x: str) -> str:
        x = re.sub(r"\(.*?\)", " ", x or "")
        x = _norm(x)
        x = re.sub(r"[^a-z0-9 ]+", " ", x)
        return re.sub(r"\s+", " ", x).strip()
    STOP = {"el", "la", "los", "las", "de", "del", "en", "y", "para", "por", "un", "una", "al", "con"}
    n = _clave(nombre)
    tn = {t for t in n.split() if t not in STOP and len(t) >= 3}
    if not tn:
        return None
    mejor, mejor_score = None, 0
    for r in db.query(modelo).all():
        c = _clave(getattr(r, campo) or "")
        if not c:
            continue
        if n in c or c in n:
            return r
        tc = {t for t in c.split() if t not in STOP and len(t) >= 3}
        comun = len(tn & tc)
        if comun >= 2 and comun >= min(len(tn), len(tc)) * 0.6 and comun > mejor_score:
            mejor, mejor_score = r, comun
    return mejor

async def sincronizar_campanas(db: Session, forzar: bool = False) -> dict:
    """Descarga el afiche; si cambió (o forzar=True), lo lee con visión y carga eventos/sorteos/promos."""
    from models.sync_estado import sync_get, sync_set
    from models.event import Event
    from models.raffle import Raffle
    from models.marketing import Marketing

    res = {"afiche_cambio": False, "eventos": 0, "sorteos": 0, "promos": 0, "errores": [], "mes": ""}
    try:
        html = await _get(URL_CAMPANAS)
        img, mime, url = await _descargar_afiche(html)
        img, mime = _preparar_imagen_para_vision(img, mime)
        h = hashlib.sha256(img).hexdigest()
        if not forzar and sync_get(db, "afiche_hash") == h:
            return res  # mismo afiche → nada que hacer
        res["afiche_cambio"] = True

        datos = await leer_afiche_con_vision(img, mime)
        if not datos:
            res["errores"].append("Campañas: la visión no devolvió un JSON válido (se conservó lo anterior).")
            return res
        res["mes"] = str(datos.get("mes") or "")

        def _f(d, *ks):
            for k in ks:
                v = d.get(k)
                if v:
                    return _limpiar(str(v))
            return ""

        # Eventos
        for e in datos.get("eventos") or []:
            nom = _f(e, "nombre")
            if not nom:
                continue
            fi, ff = _f(e, "fecha_inicio"), _f(e, "fecha_fin")
            fecha = f"{fi} al {ff}" if fi and ff and fi != ff else (fi or ff)
            hor = _f(e, "horario")
            desc = _f(e, "descripcion")
            if hor and len(hor) > 30:
                desc = (desc + " | Horario: " + hor).strip(" |")
                hor = ""
            ex = _buscar_por_nombre(db, Event, "name", nom)
            if ex:
                ex.date, ex.time, ex.location, ex.description = fecha[:30], hor[:30], _f(e, "lugar")[:150], desc
                ex.priority = max(ex.priority or 0, PRIORIDAD_EVENTO)
            else:
                db.add(Event(name=nom[:150], date=fecha[:30], time=hor[:30], location=(_f(e, "lugar") or "Centro Comercial El Puente")[:150],
                             description=desc, priority=PRIORIDAD_EVENTO))
            res["eventos"] += 1

        # Sorteos
        for s in datos.get("sorteos") or []:
            nom = _f(s, "nombre")
            if not nom:
                continue
            ex = _buscar_por_nombre(db, Raffle, "name", nom)
            premio = _f(s, "premio") or nom
            mec = _f(s, "mecanica")
            if ex:
                ex.prize, ex.requirements, ex.end_date = premio[:250], mec, _f(s, "fecha_fin")[:30]
                ex.location, ex.description, ex.active = _f(s, "lugar")[:150], mec, True
                ex.priority = max(ex.priority or 0, PRIORIDAD_SORTEO)
            else:
                db.add(Raffle(name=nom[:150], prize=premio[:250], requirements=mec, end_date=_f(s, "fecha_fin")[:30],
                              location=_f(s, "lugar")[:150], description=mec, priority=PRIORIDAD_SORTEO, active=True))
            res["sorteos"] += 1

        # Promociones
        for p in datos.get("promociones") or []:
            tit = _f(p, "titulo")
            if not tit:
                continue
            det = _f(p, "detalle")
            apl = _f(p, "aplica_en")
            desc = (det + (f". Aplica en: {apl}" if apl else "")).strip(". ")
            ex = _buscar_por_nombre(db, Marketing, "title", tit)
            if ex:
                ex.description, ex.valid_until, ex.active = desc, _f(p, "vigencia")[:30], True
                ex.priority = max(ex.priority or 0, PRIORIDAD_PROMO)
            else:
                db.add(Marketing(title=tit[:150], description=desc, priority=PRIORIDAD_PROMO,
                                 valid_until=_f(p, "vigencia")[:30], active=True))
            res["promos"] += 1

        db.commit()
        sync_set(db, "afiche_hash", h)
        sync_set(db, "afiche_url", url)
        sync_set(db, "afiche_json", json.dumps(datos, ensure_ascii=False)[:20000])
    except Exception as e:
        db.rollback()
        res["errores"].append(f"Campañas: {str(e)[:160]}")
    return res


# ══════════════════════════════════════════════════════════════════
# ORQUESTACIÓN
# ══════════════════════════════════════════════════════════════════
async def ejecutar_sincronizacion(db: Session, forzar_afiche: bool = False) -> dict:
    """Corre todo. Nunca lanza excepción: devuelve un resumen con errores por bloque."""
    from models.sync_estado import sync_set
    inicio = datetime.datetime.now()
    resumen = {"inicio": inicio.strftime("%d/%m/%Y %H:%M"), "cine": {}, "mall": {}, "campanas": {}}
    try:
        resumen["cine"] = await sincronizar_cine(db)
    except Exception as e:
        resumen["cine"] = {"errores": [str(e)[:160]]}
    try:
        resumen["mall"] = await sincronizar_mall(db)
    except Exception as e:
        resumen["mall"] = {"errores": [str(e)[:160]]}
    try:
        resumen["campanas"] = await sincronizar_campanas(db, forzar=forzar_afiche)
    except Exception as e:
        resumen["campanas"] = {"errores": [str(e)[:160]]}

    # Reindexar el RAG para que Any vea lo nuevo de inmediato
    try:
        from services.rag import load_stores_to_rag
        load_stores_to_rag(db)
        resumen["rag"] = "reindexado"
    except Exception as e:
        resumen["rag"] = f"error: {str(e)[:120]}"

    resumen["duracion_seg"] = round((datetime.datetime.now() - inicio).total_seconds(), 1)
    try:
        sync_set(db, "ultimo_resumen", json.dumps(resumen, ensure_ascii=False))
    except Exception:
        pass
    print(f"  🔄  Sincronización web: cine={resumen['cine']} | mall={resumen['mall']} | campañas={resumen['campanas']}")
    return resumen