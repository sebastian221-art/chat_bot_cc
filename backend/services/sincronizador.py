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
import asyncio
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

    def _es_ficha(t: str) -> bool:
        u = t.upper()
        return any(k in u for k in ("FORMATO", "GENERO", "GÉNERO", "CLASIFICACI", "DURACI", "COMPRAR ENTRADAS"))

    for a in soup.find_all("a", href=True):
        m = re.search(r"pelicula\.php\?id=(\d+)", a["href"])
        if not m:
            continue
        pid = m.group(1)
        g = grupos.setdefault(pid, {"id": pid, "textos": [], "horarios": [], "fechas": set(), "anchor": None, "alts": []})
        for img in a.find_all("img"):
            alt = _limpiar(img.get("alt") or "")
            if alt and alt not in g["alts"]:
                g["alts"].append(alt)
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
            if _es_ficha(t) or g["anchor"] is None:
                if not t.lower().startswith("póster") and t.upper() not in ("COMPRAR ENTRADAS", "VER DETALLES", "VISIÓN 2D", "VISIÓN 3D"):
                    g["anchor"] = a

    GENERICOS = {"comprar entradas", "ver detalles", "visión 2d", "visión 3d", "vision 2d", "vision 3d", "horarios", "clic"}

    peliculas = []
    for pid, g in grupos.items():
        # TÍTULO. Fuentes, en orden de confianza:
        #   1. alt de la imagen del póster: "Póster de STREET FIGHTER"
        #   2. texto de enlace corto que no sea botón ni ficha técnica
        # Antes se tomaba "el texto más largo" y salía la ficha completa
        # ("FORMATO: 2D GENERO: … COMPRAR ENTRADAS") como título.
        title = ""
        for t in g["alts"]:
            tl = t.lower()
            if tl.startswith(("póster de ", "poster de ")):
                title = t.split(" de ", 1)[1].strip()
                break
        if not title:
            candidatos = [t for t in g["textos"] if _norm(t) not in GENERICOS and not _es_ficha(t)
                          and not t.lower().startswith(("póster de", "poster de")) and len(t) <= 80]
            if candidatos:
                # el más repetido (título aparece en tarjeta y en lista); si empata, el más largo
                title = max(candidatos, key=lambda t: (candidatos.count(t), len(t))).strip()
        if not title:
            continue

        # Ficha técnica: subir por los padres del enlace hasta encontrar el bloque con FORMATO/DURACIÓN
        ficha = {"formato": "", "genero": "", "clasificacion": "", "duracion": "", "estreno": False}
        # Subimos por los padres hasta el bloque (fila) que tiene la ficha
        # técnica Y el título (ahí también está el sello "ESTRENO"). Si no
        # aparece así, nos quedamos con el primer bloque que tenga la ficha.
        nodo = g["anchor"]
        bloque_txt = primer_ficha = ""
        for _ in range(8):
            if nodo is None:
                break
            txt = _limpiar(nodo.get_text(" "))
            tiene_ficha = ("DURACI" in txt.upper() or "FORMATO" in txt.upper())
            if tiene_ficha and len(txt) < 2500 and not primer_ficha:
                primer_ficha = txt
            if tiene_ficha and len(txt) < 2500 and title.upper() in txt.upper():
                bloque_txt = txt
                break
            nodo = nodo.parent
        bloque_txt = bloque_txt or primer_ficha
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


def leer_ficha_pelicula(html: str) -> dict:
    """
    De la página de UNA película (pelicula.php?id=N) saca:
      sinopsis (texto después del título "Sinopsis"), trailer (enlace de
      YouTube), y clasificacion/duracion/formato si vienen.
    Todo opcional: si algo no está, queda "".
    """
    out = {"sinopsis": "", "trailer": "", "clasificacion": "", "duracion": "", "formato": ""}
    try:
        soup = _soup(html)
        for a in soup.find_all("a", href=True):
            h = a["href"]
            if "youtube.com/watch" in h or "youtu.be/" in h:
                out["trailer"] = h.strip()
                break
        lineas = _texto_lineas(html)
        CORTES = ("tráiler", "trailer", "horario", "título original", "titulo original", "país", "pais", "director",
                  "idioma", "comprar", "funciones", "formato", "clasificaci", "duraci", "compartir", "ver el tr")
        for i, l in enumerate(lineas):
            if _norm(l).rstrip(":") == "sinopsis":
                partes = []
                for l2 in lineas[i + 1:i + 12]:
                    n2 = _norm(l2)
                    if any(n2.startswith(c) for c in CORTES) or (len(l2) < 25 and partes):
                        break
                    if len(l2) >= 25:
                        partes.append(l2)
                out["sinopsis"] = _cap(" ".join(partes), 700)
                break
        for l in lineas:
            n = _norm(l)
            if not out["clasificacion"] and ("apta para" in n or "todo público" in n or "todo publico" in n or n.startswith("+")):
                out["clasificacion"] = l[:60]
            if not out["duracion"]:
                m = re.search(r"\b(\d{2,3})\s*MIN\b", l, re.I)
                if m:
                    out["duracion"] = f"{m.group(1)} MIN"
            if not out["formato"] and re.search(r"FORMATO\s*:?\s*(2D|3D)", l, re.I):
                out["formato"] = re.search(r"(2D|3D)", l, re.I).group(1).upper()
    except Exception:
        pass
    return out


def _cap(t: str, n: int) -> str:
    t = (t or "").strip()
    if len(t) <= n:
        return t
    corte = t[:n].rsplit(". ", 1)[0]
    return (corte if len(corte) > n * 0.5 else t[:n]).rstrip(".") + "…"


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
            # Ficha de cada película (sinopsis + tráiler) — en paralelo, y si
            # alguna falla no detiene la cartelera.
            async def _ficha(p):
                try:
                    return leer_ficha_pelicula(await _get(f"https://www.cinelandia.com.co/pelicula.php?id={p['id']}&ciudad=2"))
                except Exception:
                    return {}
            fichas = await asyncio.gather(*[_ficha(p) for p in cart["hoy"]])

            db.query(CineFuncion).filter(CineFuncion.store_id == cine.id).delete()
            for p, fx in zip(cart["hoy"], fichas):
                fx = fx or {}
                clasif = p["clasificacion"] or fx.get("clasificacion", "")
                dur = p["duracion"] or fx.get("duracion", "")
                fmt = p["formato"] or fx.get("formato", "")
                ficha = " · ".join(x for x in [p["genero"], clasif, fmt, dur] if x)
                desc = ("ESTRENO · " + ficha).strip(" ·") if p["estreno"] else ficha
                if fx.get("sinopsis"):
                    desc += "\n" + fx["sinopsis"]
                if fx.get("trailer"):
                    desc += "\nTráiler: " + fx["trailer"]
                db.add(CineFuncion(store_id=cine.id, title=p["title"][:150], showtimes=", ".join(p["horarios"])[:200],
                                   description=desc.strip(), is_premiere=bool(p["estreno"]), active=True))
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
            # Si el administrador la corrigió a mano (ya no tiene la marca "Fuente: elpuente.com.co")
            # o la desactivó, la web NO la vuelve a sobrescribir ni a activar.
            if "elpuente.com.co" not in (k.content or "") or k.active is False:
                return
            k.content = contenido
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

    Por qué así: Wix publica la MISMA imagen en varios tamaños y con el
    identificador escrito de varias formas (a veces completo
    "…~mv2_d_1920_1920_s_2.png" y a veces recortado "…~mv2_d_1920_1920").
    Si se arma la URL con el identificador RECORTADO, Wix responde 403.
    Ahora:
      1. Se agrupan todas las apariciones por el código único de la imagen
         (lo que va antes de "~mv2") y se queda con la versión MÁS COMPLETA
         (la que termina en .png/.jpg/.webp…).
      2. Se elige la imagen de mayor tamaño original (…_d_1920_1920…).
      3. Se construyen URLs de descarga en grande y en JPG, con respaldos.
    """
    html = html.replace("%7E", "~").replace("%7e", "~").replace("\\/", "/")
    # codigo -> (identificador más completo, área)
    por_codigo: dict[str, tuple[str, int]] = {}
    patron = re.compile(r"https://static\.wixstatic\.com/media/([A-Za-z0-9_]+~mv2[A-Za-z0-9_.\-]*)")
    for ident in set(patron.findall(html)):
        codigo = ident.split("~mv2", 1)[0]
        m = re.search(r"mv2_d_(\d+)_(\d+)", ident)
        area = int(m.group(1)) * int(m.group(2)) if m else 0
        if area == 0:
            for mm in re.finditer(re.escape(ident) + r"/v1/(?:fill|fit)/w_(\d+),h_(\d+)", html):
                area = max(area, int(mm.group(1)) * int(mm.group(2)))
        tiene_ext = bool(re.search(r"\.(png|jpe?g|webp|gif|avif)$", ident, re.I))
        prev = por_codigo.get(codigo)
        # preferimos el identificador con extensión (completo); si empatan, el más largo
        if prev is None:
            por_codigo[codigo] = (ident, area)
        else:
            prev_ident, prev_area = prev
            prev_ext = bool(re.search(r"\.(png|jpe?g|webp|gif|avif)$", prev_ident, re.I))
            mejor = ident if (tiene_ext and not prev_ext) or (tiene_ext == prev_ext and len(ident) > len(prev_ident)) else prev_ident
            por_codigo[codigo] = (mejor, max(area, prev_area))
    if not por_codigo:
        return []
    media, area = max(por_codigo.values(), key=lambda t: t[1])
    if area < 600 * 600:
        return []
    base = f"https://static.wixstatic.com/media/{media}"
    cands = [
        f"{base}/v1/fill/w_1600,h_1600,al_c,q_85/afiche.jpg",   # grande, JPG
        f"{base}/v1/fit/w_1600,h_1600,q_85/afiche.jpg",
        f"{base}/v1/fill/w_1600,h_1600,al_c,q_85,enc_auto/afiche.png",
        base,                                                   # original tal cual
    ]
    # además, la URL exacta tal como aparece en la página (sin AVIF, que la visión no lee)
    for u in re.findall(re.escape(base) + r"/v1/[^\s\"'<>)]+", html):
        u2 = re.sub(r",?enc_avif", "", u).replace(",quality_auto", "")
        if u2 not in cands:
            cands.insert(3, u2)
            break
    return cands


def _url_afiche(html: str) -> str | None:
    c = _candidatas_afiche(html)
    return c[0] if c else None


async def _descargar_afiche(html: str) -> tuple[bytes, str, str]:
    """
    Descarga el afiche probando varias URLs y varias ESTRATEGIAS:
      1. Directo a Wix con cabeceras idénticas a un navegador (+ Referer).
      2. Directo a Wix sin Referer.
      3. A través de un servicio público de imágenes (images.weserv.nl), que
         descarga la imagen desde SUS servidores y nos la entrega en JPG.
         Sirve cuando Wix bloquea las IPs de servidores (como Railway) con 403.
    """
    import urllib.parse
    candidatas = _candidatas_afiche(html)
    if not candidatas:
        raise RuntimeError("no se encontró la imagen del afiche en la página")
    intentos: list[str] = []
    nav = {
        "User-Agent": UA,
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
        "Accept-Encoding": "identity",
        "Sec-Fetch-Dest": "image", "Sec-Fetch-Mode": "no-cors", "Sec-Fetch-Site": "cross-site",
        "Cache-Control": "no-cache", "Pragma": "no-cache",
    }
    con_ref = dict(nav, Referer="https://www.elpuente.com.co/", Origin="https://www.elpuente.com.co")

    def _ok(r) -> bool:
        ct = (r.headers.get("content-type") or "").lower()
        return r.status_code == 200 and r.content and len(r.content) > 5000 and "text/html" not in ct

    async with httpx.AsyncClient(timeout=40.0, follow_redirects=True) as c:
        # Estrategias 1 y 2: directo a Wix
        for headers, etiqueta in ((con_ref, "wix+ref"), (nav, "wix")):
            for url in candidatas:
                try:
                    r = await c.get(url, headers=headers)
                    if _ok(r):
                        mime = (r.headers.get("content-type") or "image/jpeg").split(";")[0].strip()
                        return r.content, mime, url
                    intentos.append(f"{etiqueta}:{r.status_code}")
                except Exception as e:
                    intentos.append(f"{etiqueta}:{str(e)[:40]}")
        # Estrategia 3: proxy público de imágenes
        originales = [candidatas[-1]] + [u for u in candidatas if u != candidatas[-1]][:2]
        for url in originales:
            sin_esquema = re.sub(r"^https?://", "", url)
            purl = ("https://images.weserv.nl/?url=" + urllib.parse.quote(sin_esquema, safe="")
                    + "&w=1600&h=1600&fit=inside&output=jpg&q=85")
            try:
                r = await c.get(purl, headers={"User-Agent": UA, "Accept": "image/*,*/*;q=0.8"})
                if _ok(r):
                    return r.content, "image/jpeg", url
                intentos.append(f"proxy:{r.status_code}")
            except Exception as e:
                intentos.append(f"proxy:{str(e)[:40]}")
    raise RuntimeError(
        "Wix bloqueó la descarga del afiche desde el servidor (" + ", ".join(intentos[:12]) + "). "
        "Solución: súbelo manualmente con el botón 'Leer afiche (subir imagen)'."
    )


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
    except Exception as e:
        # Si el formato no se pudo abrir (p. ej. AVIF sin soporte), avisamos claro
        # en vez de mandarle a la visión algo que va a rechazar con "invalid image data".
        if mime not in ("image/jpeg", "image/png", "image/webp", "image/gif"):
            raise RuntimeError(
                f"no pude convertir la imagen ({mime or 'formato desconocido'}): {str(e)[:60]}. "
                "Súbela en JPG o PNG (en el navegador: clic derecho → Guardar imagen como → JPG/PNG, "
                "o abre la imagen y expórtala/pegala en Paint y guárdala como PNG)."
            )
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
- HORARIOS: cópialos EXACTOS como están escritos, con a.m./p.m. y el día si lo dice (ej. "5:00 p.m.", "Sábado 24 · 8:00 p.m.", "11:30 a.m. y 4:00 p.m. todos los domingos", "3:00 p.m. a 2:45 a.m."). Si la hora no se lee con claridad, deja "" — NUNCA la adivines ni la cambies.
- Las fechas y días de la semana también EXACTOS (ej. "Viernes 23 de octubre", "del 23 al 25 de octubre"). No confundas el día del show con el último día del evento.
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


async def _vision_json(client, settings, _strip, img_bytes: bytes, mime: str, prompt: str) -> dict | None:
    b64 = base64.b64encode(img_bytes).decode("utf-8")
    completion = await client.chat.completions.create(
        model=settings.GROQ_VISION_MODEL,
        messages=[{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        ]}],
        max_tokens=2500,
        temperature=0.1,
    )
    raw = _strip(completion.choices[0].message.content or "")
    return _extraer_json(raw)


def _recortes_afiche(img_bytes: bytes) -> list[bytes]:
    """
    Parte el afiche en 4 cuadrantes (con 12% de solape) y agranda cada uno
    a 1600px. La letra chica (horarios, fechas, "a.m./p.m.") se lee MUCHO
    mejor en recortes grandes que en la imagen completa pequeña.
    """
    try:
        from PIL import Image
        import io
        im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        W, H = im.size
        sol_w, sol_h = int(W * 0.12), int(H * 0.12)
        cajas = [
            (0, 0, W // 2 + sol_w, H // 2 + sol_h),
            (W // 2 - sol_w, 0, W, H // 2 + sol_h),
            (0, H // 2 - sol_h, W // 2 + sol_w, H),
            (W // 2 - sol_w, H // 2 - sol_h, W, H),
        ]
        out = []
        for c in cajas:
            t = im.crop(c)
            esc = 1600 / max(t.size)
            if esc > 1:
                t = t.resize((int(t.size[0] * esc), int(t.size[1] * esc)), Image.LANCZOS)
            buf = io.BytesIO()
            t.save(buf, format="JPEG", quality=90)
            out.append(buf.getvalue())
        return out
    except Exception:
        return []


def _fusionar_lecturas(lecturas: list[dict]) -> dict:
    """
    Une lo leído en la imagen completa y en los 4 recortes. Misma entidad
    (nombre parecido) → se conserva la versión con MÁS campos llenos, y los
    campos vacíos se completan con lo que trajeron las otras lecturas.
    """
    def _clave(n: str) -> str:
        return " ".join(w for w in _norm(n).split() if len(w) > 2)[:40]

    def _mejor(a: dict, b: dict) -> dict:
        res = dict(a)
        for k, v in b.items():
            if v and not res.get(k):
                res[k] = v
        # si b tiene el mismo campo pero más largo (más detalle), tomarlo
        for k in ("descripcion", "mecanica", "detalle", "horario"):
            if b.get(k) and len(str(b[k])) > len(str(res.get(k) or "")) + 15:
                res[k] = b[k]
        return res

    final = {"mes": "", "eventos": [], "sorteos": [], "promociones": []}
    for lec in lecturas:
        if not lec:
            continue
        if lec.get("mes") and not final["mes"]:
            final["mes"] = str(lec["mes"])
        for tipo, campo in (("eventos", "nombre"), ("sorteos", "nombre"), ("promociones", "titulo")):
            for item in lec.get(tipo) or []:
                if not isinstance(item, dict) or not item.get(campo):
                    continue
                k = _clave(str(item[campo]))
                if not k:
                    continue
                hit = None
                for ex in final[tipo]:
                    ke = _clave(str(ex[campo]))
                    if ke == k or (len(k) > 6 and (k in ke or ke in k)) or len(set(k.split()) & set(ke.split())) >= 2:
                        hit = ex
                        break
                if hit is None:
                    final[tipo].append(dict(item))
                else:
                    idx = final[tipo].index(hit)
                    final[tipo][idx] = _mejor(hit, item)
    return final


async def leer_afiche_con_vision(img_bytes: bytes, mime: str) -> dict | None:
    """
    Lee el afiche con el modelo de visión en DOS pasadas: la imagen completa
    (para no perder nada) y 4 recortes agrandados (para leer bien la letra
    chica: horarios, fechas, precios). Luego fusiona todo.
    """
    from services.ai import _get_groq_client, settings, _strip_thinking_tags
    client = _get_groq_client()
    if mime not in ("image/png", "image/jpeg", "image/jpg", "image/webp"):
        mime = "image/png"
    lecturas = []
    try:
        lecturas.append(await _vision_json(client, settings, _strip_thinking_tags, img_bytes, mime, PROMPT_AFICHE))
    except Exception as e:
        logger.warning(f"Visión afiche (completo) falló: {e}")
    for i, rec in enumerate(_recortes_afiche(img_bytes)):
        try:
            lecturas.append(await _vision_json(client, settings, _strip_thinking_tags, rec, "image/jpeg",
                                               PROMPT_AFICHE + f"\n\nNOTA: esta imagen es SOLO UNA PARTE (recorte {i + 1} de 4) del afiche. Extrae únicamente lo que se ve completo en este recorte; si un bloque está cortado, omítelo."))
        except Exception as e:
            logger.warning(f"Visión afiche (recorte {i + 1}) falló: {e}")
    lecturas = [l for l in lecturas if l]
    if not lecturas:
        return None
    return _fusionar_lecturas(lecturas)


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
    """Descarga el afiche de la web; si cambió (o forzar=True), lo lee con visión y carga eventos/sorteos/promos."""
    res = {"afiche_cambio": False, "eventos": 0, "sorteos": 0, "promos": 0, "errores": [], "mes": ""}
    try:
        html = await _get(URL_CAMPANAS)
        img, mime, url = await _descargar_afiche(html)
    except Exception as e:
        res["errores"].append(f"Campañas: {str(e)[:260]}")
        return res
    return await procesar_afiche(db, img, mime, url, forzar=forzar)


async def procesar_afiche_subido(db: Session, img: bytes, mime: str) -> dict:
    """Afiche subido a mano desde el panel (cuando Wix bloquea la descarga). Siempre se lee."""
    return await procesar_afiche(db, img, mime, "subido manualmente desde el panel", forzar=True)


# Nombres de lugares que la visión suele leer mal en el afiche (letra
# pequeña) → nombre real. Se aplica a lo que llega del afiche y, en cada
# sincronización, a lo que ya está guardado.
CORRECCIONES_LUGAR = {
    "plazuela guamera": "Plazoleta Guanentá",
    "plazuela guanenta": "Plazoleta Guanentá",
    "plazoleta guamera": "Plazoleta Guanentá",
    "plazuela de comidas centro comercial la ceiba": "Plazoleta de Comidas La Ceiba",
    "plazoleta de comidas centro comercial la ceiba": "Plazoleta de Comidas La Ceiba",
    "plazuela de comidas la ceiba": "Plazoleta de Comidas La Ceiba",
    "plazuela de comidas": "Plazoleta de Comidas La Ceiba",
    "lobby torre empresarial": "Lobby Torre Empresarial",
}


def corregir_lugar(texto: str) -> str:
    if not texto:
        return texto
    t = _norm(texto)
    for malo, bueno in CORRECCIONES_LUGAR.items():
        if malo in t:
            return bueno
    return texto


def corregir_lugares_guardados(db: Session) -> int:
    """Aplica CORRECCIONES_LUGAR a eventos y sorteos ya guardados. Devuelve cuántos cambió."""
    from models.event import Event
    from models.raffle import Raffle
    n = 0
    try:
        for e in db.query(Event).all():
            nuevo = corregir_lugar(e.location or "")
            if nuevo != (e.location or ""):
                e.location = nuevo; n += 1
            for malo, bueno in CORRECCIONES_LUGAR.items():
                if e.description and malo in _norm(e.description):
                    e.description = re.sub(re.escape(malo), bueno, e.description, flags=re.I); n += 1
        for r in db.query(Raffle).all():
            nuevo = corregir_lugar(r.location or "")
            if nuevo != (r.location or ""):
                r.location = nuevo; n += 1
        if n:
            db.commit()
    except Exception:
        db.rollback()
    return n


async def procesar_afiche(db: Session, img: bytes, mime: str, url: str, forzar: bool = False) -> dict:
    """Lee el afiche con visión (si cambió o forzar=True) y carga eventos/sorteos/promos."""
    from models.sync_estado import sync_get, sync_set
    from models.event import Event
    from models.raffle import Raffle
    from models.marketing import Marketing

    res = {"afiche_cambio": False, "eventos": 0, "sorteos": 0, "promos": 0, "errores": [], "mes": ""}
    try:
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
            lugar = corregir_lugar(_f(e, "lugar"))
            ex = _buscar_por_nombre(db, Event, "name", nom)
            if ex:
                ex.date, ex.time, ex.location, ex.description = fecha[:30], hor[:30], lugar[:150], desc
                ex.priority = max(ex.priority or 0, PRIORIDAD_EVENTO)
            else:
                db.add(Event(name=nom[:150], date=fecha[:30], time=hor[:30], location=(lugar or "Centro Comercial El Puente")[:150],
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
        try:
            resumen["lugares_corregidos"] = corregir_lugares_guardados(db)
        except Exception:
            pass
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