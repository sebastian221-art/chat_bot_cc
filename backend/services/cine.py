# 📄 ARCHIVO: backend/services/cine.py
"""
Cartelera de cine — detección determinística, sin depender de que la
búsqueda semántica (RAG) encuentre la tienda del Cine por casualidad.
Mismo patrón que ya usa store_transfer.py para "número de tienda":
palabras clave claras → respuesta directa, construida con datos reales
de la base de datos, no adivinada por la IA.
"""
import re
import unicodedata
from sqlalchemy.orm import Session
from models.store import Store
from models.cine_funcion import CineFuncion


def _plano(t: str) -> str:
    """minúsculas y sin tildes, para comparar títulos con lo que escribe la gente."""
    t = unicodedata.normalize("NFD", (t or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


# Palabras de títulos que NO sirven para identificar una película (chocan
# con otras consultas del mall o son demasiado comunes).
PALABRAS_TITULO_GENERICAS = {"punto", "muerto", "madre", "nueva", "parte", "gran", "nuevo", "mundo", "vida",
                             "amor", "casa", "dos", "the", "los", "las", "del", "una", "uno", "para", "con",
                             "jones", "bestia", "corazon", "isla", "caida", "zona", "street"}

URL_COMPRA_CINE = "https://www.cinelandia.com.co/san-gil"

DIAS = ["LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES", "SABADO", "DOMINGO"]
DIA_CORTO = {"LUNES": "Lun", "MARTES": "Mar", "MIERCOLES": "Mié", "JUEVES": "Jue", "VIERNES": "Vie", "SABADO": "Sáb", "DOMINGO": "Dom"}


def _dias_a_texto(dias: list[str]) -> str:
    """['JUEVES','VIERNES','SABADO','DOMINGO'] → 'Jue a Dom'; ['LUNES','MIERCOLES'] → 'Lun y Mié'."""
    idx = sorted({DIAS.index(d) for d in dias if d in DIAS})
    if not idx:
        return ""
    if len(idx) == 7:
        return "Todos los días"
    # ¿consecutivos?
    if idx == list(range(idx[0], idx[-1] + 1)) and len(idx) >= 3:
        return f"{DIA_CORTO[DIAS[idx[0]]]} a {DIA_CORTO[DIAS[idx[-1]]]}"
    nombres = [DIA_CORTO[DIAS[i]] for i in idx]
    return " y ".join([", ".join(nombres[:-1]), nombres[-1]]) if len(nombres) > 1 else nombres[0]


def resumir_tarifas(bloque: str) -> str:
    """
    Convierte la tabla cruda de Cinelandia (28 filas tipo
    "2D JUEVES ⏰ DESDE 03:01 PM HASTA 11:00 PM | $ 18.000 | $ 14.000 💳 | $ 25.000 | $ 18.000 💳")
    en un resumen legible agrupado por franja y días. Columnas de la web:
    General · General con Tarjeta Cinelandia · VIP · VIP con Tarjeta.
    Si el formato no coincide, devuelve "" y se usa el bloque tal cual.
    """
    pat = re.compile(r"(2D|3D)\s+([A-ZÁÉÍÓÚ]+)\s*⏰?\s*DESDE\s+([\d:]+\s*[AP]M)\s+HASTA\s+([\d:]+\s*[AP]M)\s*\|\s*\$?\s*([\d.]+)\s*\|\s*\$?\s*([\d.]+)\s*💳?\s*\|\s*\$?\s*([\d.]+)\s*\|\s*\$?\s*([\d.]+)", re.I)
    grupos: dict[tuple, list[str]] = {}
    for linea in (bloque or "").split("\n"):
        m = pat.search(linea)
        if not m:
            continue
        fmt, dia, desde, hasta, g, gt, v, vt = m.groups()
        dia = _plano(dia).upper()
        franja = "antes de 3:00 pm" if desde.strip().upper().startswith("12:05") or "AM" in desde.upper() else "después de 3:00 pm"
        grupos.setdefault((franja, fmt.upper(), g, gt, v, vt), []).append(dia)
    if not grupos:
        return ""

    def _p(x):  # "18.000" → "$18.000"
        return "$" + x.replace(",", ".")

    # Agrupar por (franja, días) para juntar 2D y 3D en una misma línea
    por_dias: dict[tuple, dict] = {}
    for (franja, fmt, g, gt, v, vt), dias in grupos.items():
        key = (franja, _dias_a_texto(dias))
        por_dias.setdefault(key, {})[fmt] = (g, gt, v, vt)
    orden = {"antes de 3:00 pm": 0, "después de 3:00 pm": 1}
    lineas = ["General · (💳 con Tarjeta Cinelandia) · VIP"]
    for (franja, dias_txt), fmts in sorted(por_dias.items(), key=lambda kv: (orden.get(kv[0][0], 9), kv[0][1])):
        partes = []
        for fmt in ("2D", "3D"):
            if fmt in fmts:
                g, gt, v, vt = fmts[fmt]
                if g == gt == v == vt:
                    partes.append(f"{fmt} {_p(g)} cualquier silla")
                else:
                    partes.append(f"{fmt} {_p(g)} (💳 {_p(gt)}) · VIP {_p(v)} (💳 {_p(vt)})")
        if len(fmts) == 2 and fmts["2D"] == fmts["3D"]:
            g, gt, v, vt = fmts["2D"]
            partes = [f"2D y 3D {_p(g)} cualquier silla" if g == gt == v == vt else f"2D y 3D {_p(g)} (💳 {_p(gt)}) · VIP {_p(v)} (💳 {_p(vt)})"]
        lineas.append(f"• {dias_txt} {franja}: " + " | ".join(partes))
    return "\n".join(lineas)


CARTELERA_KEYWORDS = [
    "cartelera", "película", "peliculas", "películas", "pelicula",
    "que dan en el cine", "qué dan en el cine", "funciones de cine",
    "horario de cine", "horarios de cine", "hora de la función",
    "hora de la funcion", "que hay en el cine", "qué hay en el cine",
    "estrenos", "estreno",
]


def is_cartelera_intent(message: str) -> bool:
    msg = message.lower()
    return any(k in msg for k in CARTELERA_KEYWORDS)


def find_cine_store(db: Session) -> Store | None:
    """Encuentra la tienda del Cine — por categoría 'Cine' primero (más confiable), o por nombre si no."""
    store = db.query(Store).filter(Store.category.ilike("%cine%")).first()
    if store:
        return store
    return db.query(Store).filter(Store.name.ilike("%cine%")).first()


def palabras_clave_titulo(titulo: str) -> list[str]:
    """Palabras distintivas de un título (4+ letras, sin genéricas). "Vértigo 2: Punto Muerto" → ["vertigo"]."""
    return [w for w in re.findall(r"[a-z0-9]+", _plano(titulo)) if len(w) >= 4 and w not in PALABRAS_TITULO_GENERICAS]


def find_cine_funcion_by_message(db: Session, store_id: int, message: str) -> CineFuncion | None:
    """
    Si el cliente mencionó una película puntual, la encuentra. Tolerante:
    sin tildes, y basta con una palabra distintiva del título ("tadeo",
    "vertigo", "coyote"). Si varias coinciden, gana la que más palabras
    comparte; si hay empate real, no se adivina (devuelve None).
    """
    msg = _plano(message)
    funciones = db.query(CineFuncion).filter(CineFuncion.store_id == store_id, CineFuncion.active == True).all()
    exact = [f for f in funciones if _plano(f.title) and _plano(f.title) in msg]
    if len(exact) == 1:
        return exact[0]
    puntajes = []
    for f in funciones:
        claves = palabras_clave_titulo(f.title)
        if not claves:
            # título sin palabras distintivas (ej. "ZONA CERO") → exigir el título completo
            continue
        n = sum(1 for w in claves if re.search(rf"\b{re.escape(w)}\b", msg))
        if n:
            puntajes.append((n, f))
    if not puntajes:
        # último intento: títulos cortos completos sin tildes ("zona cero")
        cortos = [f for f in funciones if len(_plano(f.title)) <= 15 and _plano(f.title) in msg]
        return cortos[0] if len(cortos) == 1 else None
    puntajes.sort(key=lambda t: -t[0])
    if len(puntajes) > 1 and puntajes[0][0] == puntajes[1][0]:
        return None
    return puntajes[0][1]


def bloque_info_extra(store: Store, clave: str) -> str:
    """
    Saca de store.extra_info el bloque que empieza con la palabra clave
    ("tarifa" → "💵 TARIFAS DE CINE…", "confiter" → "🍿 CONFITERÍA Y COMBOS…").
    Los bloques van separados por línea en blanco (así los escriben el
    importador de la plantilla de cine y el sincronizador web).
    """
    texto = store.extra_info or ""
    if not texto.strip():
        return ""
    for bloque in re.split(r"\n\s*\n", texto):
        primera = _plano(bloque.strip().split("\n", 1)[0])
        if clave in primera:
            return bloque.strip()
    return ""


def build_cartelera_message(store: Store | None) -> str:
    """Arma la respuesta completa de la cartelera actual — con datos reales, sin que la IA tenga que adivinar."""
    if not store:
        return "No tengo registrado el local del cine en el directorio todavía — te recomiendo preguntar en el Punto de Información (Piso 1). 😊"

    funciones = [f for f in store.cine_funciones if f.active]
    if not funciones:
        return f"Por ahora no tengo la cartelera de *{store.name}* cargada. Te recomiendo llamar al {store.phone or 'cine'} o preguntar en el Punto de Información (Piso 1) para la programación más actualizada. 🎬"

    lines = [f"🎬 Cartelera de *{store.name}*:\n"]
    for f in funciones:
        linea = f"• *{f.title}*"
        if f.is_premiere:
            linea += " 🆕 ESTRENO"
        if f.showtimes:
            linea += f"\n   🕒 {f.showtimes}"
        # Solo la FICHA corta (género · clasificación · duración). La sinopsis
        # y el tráiler quedan para cuando pregunten por esa película — así la
        # cartelera completa cabe en un solo mensaje y es fácil de leer.
        ficha = _ficha_corta(f.description)
        if ficha:
            linea += f"\n   {ficha}"
        lines.append(linea)

    lines.append("\n¿Te cuento más de alguna? Dime el nombre y te paso horarios y sinopsis.")
    return "\n\n".join(lines)


def _ficha_corta(descripcion: str | None) -> str:
    """Primera línea de la descripción (la ficha), sin la sinopsis ni el tráiler."""
    if not descripcion:
        return ""
    primera = descripcion.strip().split("\n", 1)[0].strip()
    if _plano(primera).startswith(("sinopsis", "trailer", "tráiler")) or len(primera) > 120:
        return ""
    return primera


def build_funcion_especifica_message(funcion: CineFuncion, store: Store) -> str:
    """Respuesta enfocada en UNA película puntual — cuando el cliente ya la mencionó por nombre."""
    lines = [f"🎬 *{funcion.title}*"]
    if funcion.is_premiere:
        lines.append("🆕 Es un estreno")
    if funcion.showtimes:
        lines.append(f"🕒 Horarios: {funcion.showtimes}")
    if funcion.description:
        lines.append(funcion.description.strip())
    ubic = store.floor if (store.floor or "").strip().lower() not in ("", "por confirmar") else ""
    lines.append(f"\n📍 En {store.name}" + (f", {ubic}." if ubic else "."))
    return "\n".join(lines)