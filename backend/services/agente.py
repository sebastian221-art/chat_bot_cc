# 📄 ARCHIVO: backend/services/agente.py  ← ARCHIVO NUEVO
"""
AGENTE DE ANY — la IA lleva la conversación; las herramientas le dan DATOS.

Esto reemplaza (cuando el switch lo active) al orquestador por reglas.
La diferencia de fondo:

  ORQUESTADOR (actual): reglas eligen UNA herramienta → la herramienta
  arma un texto fijo con plantilla → se pega una promo al final.
  Resultado: respuestas correctas pero robóticas; cada caso nuevo exige
  una regla nueva; los seguimientos ("¿y ese descuento en qué es?") se
  pierden porque las herramientas no ven el historial.

  AGENTE (este archivo): el modelo recibe la persona de Any, las reglas
  del mall, el historial reciente y la fecha de hoy, y tiene herramientas
  que devuelven JSON (locales, eventos, cine, info del mall…). Él decide
  cuáles llamar, lee los datos y redacta la respuesta. Puede encadenar
  varias (buscar un local y luego sus datos), ordenar eventos por fecha,
  filtrar "planes familiares", leer "inscríbete ese día por $10.000" y
  responderlo sin que nadie haya programado ese caso.

Lo que NO se deja en manos de la IA (reglas duras, en código):
  - Emergencia y queja: van por las respuestas determinísticas de siempre.
  - Equidad comercial: si el agente llamó buscar_locales, se verifica que
    TODOS los nombres devueltos aparezcan en la respuesta; si faltan, se
    completa la lista. Ningún local queda por fuera por decisión del modelo.
  - Nunca se manda texto vacío ni razonamiento interno al cliente.
  - La promo del final la elige el código (rotación existente); la IA solo
    decide si este turno es buen momento para pegarla (tono).
  - Traza completa en el panel, igual que el orquestador.

Cómo se cambia el comportamiento: editando PERSONA (el prompt), o
agregando/ajustando una herramienta en HERRAMIENTAS + _ejecutar_herramienta.
No hay que tocar nada más. Cada herramienta es una función pequeña que
reutiliza la lógica de datos que ya existe en el proyecto.
"""
import json
import re
import time
import logging
import datetime
import unicodedata

from sqlalchemy.orm import Session

from models.orchestrator_trace import OrchestratorTrace

logger = logging.getLogger("mall_bot")

CONTACTO_MALL = "317 432 0138"
MAX_VUELTAS = 5          # máximo de rondas de herramientas por mensaje
MAX_HISTORIAL = 10       # mensajes previos que ve el modelo
MAX_TOKENS_RESPUESTA = 900

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


def _sin_tildes(t: str) -> str:
    t = (t or "").lower()
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")


def _link_wa(tel: str | None) -> str | None:
    d = re.sub(r"\D", "", tel or "")
    if not d:
        return None
    if d.startswith("3") and len(d) == 10:
        d = "57" + d
    return f"https://wa.me/{d}"


def _zona(store) -> str:
    """Solo la zona (nunca el nivel/piso). Torre: sí dice el piso."""
    try:
        from services.category_search import ubicacion_mostrable
        return ubicacion_mostrable(store) or ""
    except Exception:
        return (store.location_hint or "")


# ══════════════════════════════════════════════════════════════════
# PERSONA Y REGLAS (esto es lo que se edita para cambiar cómo habla Any)
# ══════════════════════════════════════════════════════════════════

PERSONA = """Eres Any, la asistente virtual del Centro Comercial El Puente en San Gil, Santander. Atiendes por WhatsApp. Eres cálida, cercana y resolutiva, como una persona real de San Gil que conoce el centro comercial de memoria. Tu trabajo es RESOLVER lo que el cliente necesita con la información que tienes a la mano.

CÓMO TRABAJAS
- Tienes herramientas que consultan la base de datos real del centro comercial. ÚSALAS antes de responder cualquier dato (locales, horarios, teléfonos, eventos, sorteos, promociones, cine, parqueadero, servicios). No respondas de memoria.
- Puedes llamar varias herramientas en un mismo turno y encadenarlas (buscar un local y luego pedir sus datos). Hazlo cuando haga falta para responder completo.
- Lee los datos con criterio: si preguntan "cuál es el siguiente evento", ordena por fecha y responde el más próximo. Si preguntan "planes familiares", filtra lo que sí sea para familias. Si preguntan "cómo participo" y la descripción ya dice cómo, respóndelo tú; no mandes al cliente a averiguarlo.
- Usa el historial: si el cliente dice "y ese descuento en qué es?" o "y de ropa?", se refiere a lo que acaban de hablar.
- Hoy es {fecha_hoy}. Úsalo para "este fin de semana", "mañana", "qué hay hoy", y para saber si un evento ya pasó.

REGLAS DEL CENTRO COMERCIAL (obligatorias)
1. NUNCA INVENTES. Si un dato no está en lo que devolvieron las herramientas, dilo con naturalidad y ofrece la mejor alternativa real: el WhatsApp del local, el contacto correcto, o el link oficial. Jamás inventes procedimientos, requisitos, precios ni horarios.
2. EQUIDAD: cuando listes locales de una categoría, nombra TODOS los que devolvió la herramienta, en orden alfabético, cada uno en su propia línea con el formato "• *Nombre* — Zona · Tel: número". No destaques ninguno, no recortes la lista, no recomiendes uno sobre otro. Si el cliente pide "el mejor" o "cuál me recomiendas", explica amablemente que todos son opciones del centro comercial y que te cuente qué busca para orientarlo.
3. NUNCA hables de "niveles" ni "pisos" del centro comercial: ubica siempre por ZONA (Pasillo Barichara, Pasillo Vélez, Pasillo Socorro, Pasillo Charalá, Pasillo Páramo, Pasillo Curití, Plaza Principal, Zona Terrazas, Plazoleta de Comidas La Ceiba, Paseo de la Cruz). Si preguntan "qué significa nivel 2" o "en qué piso", responde con la zona y di que en el Punto de Información los orientan; no expliques niveles. Única excepción: la Torre Médica/Empresarial, donde sí se dice el piso del consultorio.
4. CARTA / MENÚ / CATÁLOGO / INSTAGRAM: si el local tiene link, entrégalo tal cual. Si NO tiene, dilo claro ("por ahora no tengo la carta de X") y pasa su WhatsApp. Nunca digas "te la comparto 👇" si no hay nada que compartir.
5. NO uses el Punto de Información como salida fácil. Primero resuelve con los datos; si falta algo, el contacto directo del local; el Punto de Información o la línea del centro comercial ({contacto_mall}) solo cuando de verdad es el canal que corresponde (inscripciones presenciales, registro de facturas, objetos perdidos, quejas).
6. Registro de facturas para sorteos: el link oficial es https://www.elpuente.com.co/registro-de-facturas (también en el Punto de Información). Compra de boletas de cine: https://www.cinelandia.com.co/san-gil o en taquilla.
7. Alquiler de salones/locales/stands, publicidad, proveedores, empleo: lo maneja la Administración; usa la herramienta contacto_administracion y entrega esos datos sin inventar condiciones.
8. Si el cliente pregunta algo que no es del centro comercial (tarea, chiste, política, otra ciudad), responde breve y amable y vuelve con gracia a lo tuyo. No inventes servicios que el centro comercial no tiene.

ESTILO (WhatsApp)
- Breve y directo: 2 a 5 líneas para preguntas simples; listas solo cuando hay varios locales/eventos. Nada de párrafos largos.
- Usa el nombre del cliente de vez en cuando, no en cada mensaje. Si no lo tienes, no lo inventes.
- Varía aperturas y cierres; no empieces todo con "¡Claro!" ni termines todo con "¿en qué más te ayudo?". A veces el dato va primero y listo.
- Negrita de WhatsApp con *asteriscos simples* (nunca **dobles**), emojis con moderación (1-2), sin títulos en mayúsculas.
- Da solo lo que preguntaron. Si piden la dirección, no agregues horario y teléfono sin que los pidan.
- Responde SIEMPRE en español. Nunca muestres tu razonamiento, nombres de herramientas ni JSON al cliente.

PROMOCIÓN DEL TURNO
Si en el contexto aparece "PROMO_SUGERIDA", es un evento/sorteo/promo que el centro comercial quiere visibilizar. Pégalo al final en 1 línea con su propio emoji SOLO si encaja con el tono (no después de una queja, una emergencia, un saludo de una línea, una mala noticia, ni si la respuesta ya es larga o ya habla de eventos/promos). Si no encaja, omítelo sin decir nada. Si lo usas, copia los datos tal cual (fecha, lugar, precio), sin cambiarlos.
"""


# ══════════════════════════════════════════════════════════════════
# HERRAMIENTAS (definición para el modelo — formato OpenAI tools)
# ══════════════════════════════════════════════════════════════════

HERRAMIENTAS = [
    {"type": "function", "function": {
        "name": "buscar_locales",
        "description": "Busca TODOS los locales del centro comercial que venden un tipo de producto, comida o servicio (ej. 'hamburguesas', 'vestidos', 'zapatos', 'peluquería', 'cerveza', 'celulares'). Devuelve la lista completa en orden alfabético con zona y teléfono. Úsala para cualquier pregunta tipo 'dónde venden X', 'qué locales tienen X', 'necesito X'.",
        "parameters": {"type": "object", "properties": {
            "que_busca": {"type": "string", "description": "El producto, comida o servicio que busca el cliente, en singular y sin artículos. Ej: 'hamburguesa', 'vestido', 'tenis', 'peluquería', 'cerveza'."}
        }, "required": ["que_busca"]}}},
    {"type": "function", "function": {
        "name": "datos_local",
        "description": "Devuelve la ficha completa de UN local por su nombre (o parte del nombre): zona, teléfono, link de WhatsApp, horario, descripción, carta/catálogo o Instagram si lo tiene, y si es el cine, su cartelera. Úsala cuando el cliente nombra un local o pregunta por 'la carta de X', 'el número de X', 'el Instagram de X', 'a qué hora abre X'.",
        "parameters": {"type": "object", "properties": {
            "nombre": {"type": "string", "description": "Nombre del local tal como lo escribió el cliente (ej. 'la barra', 'mercagan', 'chevignon')."}
        }, "required": ["nombre"]}}},
    {"type": "function", "function": {
        "name": "eventos",
        "description": "Lista los eventos vigentes del centro comercial con fecha, hora, lugar y descripción (incluye cómo inscribirse si está en la descripción). Úsala para 'qué eventos hay', 'qué hay este fin de semana', 'cómo participo en X', 'a qué hora es la misa', 'planes familiares'.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "sorteos",
        "description": "Lista los sorteos y campañas vigentes: premio, cómo participar, fecha límite y dónde registrarse. Úsala para 'qué están sorteando', 'cómo participo en el sorteo', 'qué me gano', 'cómo registro facturas'.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "promociones",
        "description": "Lista las promociones y descuentos vigentes (del centro comercial o de locales), con detalle y vigencia. Úsala para 'hay promociones', 'descuentos', 'ofertas', 'ese descuento en qué es'.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "cartelera_cine",
        "description": "Devuelve la cartelera actual del cine (películas, horarios, género, clasificación, duración, sinopsis), las tarifas, los combos de confitería, el link de compra en línea y la ubicación del cine. Úsala para cualquier pregunta de cine, películas, boletas, precios de entradas, crispetas o combos.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "info_mall",
        "description": "Información general del centro comercial: dirección, horarios, parqueadero (tarifas, minutos gratis), wifi, línea de atención, puntos de servicio (baños, cajeros, punto de información, administración) y la base de conocimiento (mascotas, registro de facturas, políticas, alquiler de espacios, torre médica, etc.). Úsala para parqueadero, horarios del mall, baños, cajeros, mascotas, wifi, dónde queda la administración, torre médica, y cualquier pregunta general que no sea de un local puntual.",
        "parameters": {"type": "object", "properties": {
            "tema": {"type": "string", "description": "Tema puntual para filtrar la base de conocimiento (ej. 'parqueadero', 'mascotas', 'facturas', 'torre médica', 'baños'). Opcional."}
        }}}},
    {"type": "function", "function": {
        "name": "contacto_administracion",
        "description": "Datos de contacto de la Administración del centro comercial, para: alquiler de salones, locales, stands o espacios; publicidad y pauta; proveedores; empleo y hojas de vida; convenios.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "ubicacion_mall",
        "description": "Dirección del centro comercial y su pin de ubicación para enviarlo por WhatsApp. Úsala SOLO cuando pregunten dónde queda el centro comercial en sí (no un local).",
        "parameters": {"type": "object", "properties": {}}}},
]


# ══════════════════════════════════════════════════════════════════
# EJECUCIÓN DE HERRAMIENTAS (devuelven dict → se pasan al modelo como JSON)
# ══════════════════════════════════════════════════════════════════

def _local_resumen(s) -> dict:
    return {"nombre": s.name, "zona": _zona(s) or None, "telefono": s.phone or None}


def _local_ficha(db, s) -> dict:
    d = {
        "id": s.id, "nombre": s.name, "categoria": s.category, "zona": _zona(s) or None,
        "telefono": s.phone or None, "whatsapp": _link_wa(s.phone), "horario": s.schedule or None,
        "descripcion": s.description or None, "palabras_clave": s.tags or None,
    }
    link = s.carta_como_link() if hasattr(s, "carta_como_link") else None
    foto_carta = None
    try:
        foto_carta = next((p.photo_url for p in (s.photos or []) if p.label == "carta"), None)
    except Exception:
        pass
    if foto_carta:
        d["carta"] = {"tipo": "foto", "nota": "La carta se adjunta como imagen automáticamente; dile al cliente que se la compartes."}
    elif link:
        d["carta_o_catalogo_link"] = link
        d["es_instagram"] = "instagram" in link.lower()
    else:
        d["carta"] = None
        d["nota_carta"] = "Este local NO tiene carta, catálogo ni Instagram cargado. Si lo piden, dilo claro y pasa el WhatsApp."
    if s.extra_info and "cine" not in (s.category or "").lower():
        d["informacion_adicional"] = s.extra_info[:1500]
    try:
        funcs = [f for f in s.cine_funciones if f.active]
        if funcs:
            d["cartelera"] = [{"titulo": f.title, "horarios": f.showtimes, "ficha": f.description, "estreno": f.is_premiere} for f in funcs]
    except Exception:
        pass
    return d


def _t_buscar_locales(db, que_busca: str) -> dict:
    from services.category_search import detectar_categoria
    from services.rag import find_all_stores_by_category
    from models.store import Store
    from sqlalchemy import func, or_

    q = (que_busca or "").strip()
    categoria, terminos = None, []
    det = detectar_categoria(q, exigir_intencion=False)
    if det:
        categoria, terminos = det
    stores = find_all_stores_by_category(db, terminos) if terminos else []

    # Respaldo: búsqueda literal por el término (y su singular/plural) en
    # categoría, nombre y tags, para cosas que no están en el diccionario
    # de categorías ("cerveza", "celulares", "lentes").
    if not stores:
        base = _sin_tildes(q)
        variantes = {base}
        if base.endswith("es") and len(base) > 4:
            variantes.add(base[:-2])
        if base.endswith("s") and len(base) > 3:
            variantes.add(base[:-1])
        else:
            variantes.add(base + "s")
        conds = []
        for v in variantes:
            like = f"%{v}%"
            conds += [func.lower(Store.category).like(like), func.lower(Store.name).like(like), func.lower(Store.tags).like(like)]
        stores = (db.query(Store).filter(Store.active == True).filter(or_(*conds)).order_by(Store.name.asc()).all())
        stores = [s for s in stores if "torre" not in (s.location_hint or "").lower()]
        categoria = categoria or q

    stores = [s for s in stores if s.active]
    return {
        "busqueda": q, "categoria_detectada": categoria, "total": len(stores),
        "regla": "Lista TODOS estos locales, en este mismo orden alfabético, uno por línea: • *Nombre* — Zona · Tel: número. Sin destacar ninguno.",
        "locales": [_local_resumen(s) for s in stores],
        "_nombres": [s.name for s in stores],  # uso interno (verificación de equidad)
    }


def _t_datos_local(db, nombre: str) -> dict:
    from services.store_transfer import find_store_by_message, _significant_words, _contains_word
    from models.store import Store
    st = find_store_by_message(db, nombre or "")
    if not st:
        # Candidatos parecidos para que el modelo pueda preguntar "¿cuál de estos?"
        msg = _sin_tildes(nombre)
        cands = []
        for s in db.query(Store).filter(Store.active == True).all():
            if any(_contains_word(msg, w) for w in _significant_words(s.name)) or any(_contains_word(_sin_tildes(s.name), w) for w in re.findall(r"[a-z0-9ñ]{4,}", msg)):
                cands.append(s.name)
        return {"encontrado": False, "buscado": nombre, "candidatos": cands[:6],
                "nota": "No hay un local con ese nombre exacto. Si hay candidatos, pregunta cuál; si no, dilo y ofrece buscar por tipo de producto."}
    return {"encontrado": True, **_local_ficha(db, st)}


def _fecha_orden(texto: str):
    m = re.findall(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})", texto or "")
    if not m:
        return None
    d, mo, a = (int(x) for x in m[0])
    if a < 100:
        a += 2000
    try:
        return datetime.date(a, mo, d)
    except ValueError:
        return None


def _t_eventos(db) -> dict:
    from models.event import Event
    evs = [e for e in db.query(Event).all() if e.esta_vigente()]
    evs.sort(key=lambda e: (_fecha_orden(e.date) or datetime.date.max, -(e.priority or 0)))
    hoy = datetime.date.today()
    out = []
    for e in evs:
        f = _fecha_orden(e.date)
        out.append({
            "id": e.id, "nombre": e.name, "fecha": e.date, "hora": e.time or None, "lugar": e.location,
            "descripcion": e.description or None,
            "dias_para_el_evento": (f - hoy).days if f else None,
        })
    return {"hoy": hoy.strftime("%d/%m/%Y"), "total": len(out), "eventos_ordenados_por_fecha": out,
            "nota": "Ya vienen ordenados del más próximo al más lejano. Si la descripción dice cómo inscribirse o el precio, úsalo."}


def _t_sorteos(db) -> dict:
    from models.raffle import Raffle
    rs = [r for r in db.query(Raffle).filter(Raffle.active == True).order_by(Raffle.priority.desc()).all() if r.esta_vigente()]
    return {"total": len(rs), "sorteos": [{
        "id": r.id, "nombre": r.name, "premio": r.prize, "como_participar": r.requirements or None,
        "fecha_limite": r.end_date or None, "donde_registrarse": r.location or None, "descripcion": r.description or None,
    } for r in rs], "link_registro_facturas": "https://www.elpuente.com.co/registro-de-facturas"}


def _t_promociones(db) -> dict:
    from models.marketing import Marketing
    ps = [p for p in db.query(Marketing).filter(Marketing.active == True).order_by(Marketing.priority.desc()).all() if p.esta_vigente()]
    return {"total": len(ps), "promociones": [{
        "id": p.id, "titulo": p.title, "detalle": p.description or None,
        "local": p.store.name if p.store else "general del centro comercial", "valida_hasta": p.valid_until or None,
    } for p in ps]}


def _t_cartelera_cine(db) -> dict:
    from services.cine import find_cine_store, bloque_info_extra, resumir_tarifas, URL_COMPRA_CINE
    cine = find_cine_store(db)
    if not cine:
        return {"disponible": False, "nota": "No hay cine registrado."}
    funcs = [f for f in cine.cine_funciones if f.active]
    tarifas_raw = bloque_info_extra(cine, "tarifa")
    tarifas = resumir_tarifas(tarifas_raw) if tarifas_raw else ""
    confiteria = bloque_info_extra(cine, "confiter")
    return {
        "disponible": True, "cine": cine.name, "zona": _zona(cine) or None, "telefono": cine.phone or None,
        "horario_del_local": cine.schedule or None, "compra_en_linea": URL_COMPRA_CINE,
        "peliculas": [{"id": f.id, "titulo": f.title, "horarios": f.showtimes, "ficha": f.description, "estreno": bool(f.is_premiere)} for f in funcs],
        "tarifas": tarifas or tarifas_raw or None,
        "confiteria": confiteria or None,
        "nota": "Para comprar/reservar: taquilla o el link. No inventes pasos de compra. Si piden una película puntual, da sus horarios y sinopsis; si piden toda la cartelera, lista título + horarios + ficha corta.",
    }


def _t_info_mall(db, tema: str = "") -> dict:
    from models.mall_info import MallInfo
    from models.info_point import InfoPoint
    from models.knowledge import KnowledgeEntry
    mi = db.query(MallInfo).filter(MallInfo.id == 1).first()
    pts = db.query(InfoPoint).all()
    kn = db.query(KnowledgeEntry).filter(KnowledgeEntry.active == True).all()
    t = _sin_tildes(tema)
    palabras = [w for w in re.findall(r"[a-z0-9ñ]{4,}", t)]
    if palabras:
        kn_f = [k for k in kn if any(w in _sin_tildes(k.title + " " + k.content) for w in palabras)]
        kn = kn_f or kn
    def _lim(s, n=600):
        return (s or "")[:n] or None
    return {
        "nombre": mi.name if mi else "Centro Comercial El Puente",
        "direccion": mi.address if mi else None,
        "horarios": _lim(mi.general_schedule) if mi else None,
        "linea_atencion": (mi.phone if mi and mi.phone and "pendiente" not in mi.phone.lower() else CONTACTO_MALL),
        "parqueadero": _lim(mi.parking) if mi and mi.parking and "pendiente" not in mi.parking.lower() else None,
        "wifi": _lim(mi.wifi) if mi and mi.wifi and "pendiente" not in mi.wifi.lower() else None,
        "puntos_de_servicio": [{"nombre": p.name, "ubicacion": p.location or None} for p in pts],
        "base_de_conocimiento": [{"titulo": k.title, "contenido": _lim(k.content, 900)} for k in kn[:8]],
        "registro_facturas_link": "https://www.elpuente.com.co/registro-de-facturas",
    }


def _t_contacto_administracion(db) -> dict:
    from models.store import Store
    adm = (db.query(Store).filter(Store.active == True)
           .filter(Store.name.ilike("%administraci%")).first())
    return {
        "administracion_telefono": adm.phone if adm and adm.phone else None,
        "administracion_whatsapp": _link_wa(adm.phone) if adm and adm.phone else None,
        "linea_centro_comercial": CONTACTO_MALL, "linea_whatsapp": _link_wa(CONTACTO_MALL),
        "ubicacion_oficinas": _zona(adm) if adm else None,
        "nota": "Ellos confirman disponibilidad, condiciones y costos. No inventes tarifas ni requisitos.",
    }


def _t_ubicacion_mall(db) -> dict:
    from models.mall_info import MallInfo
    mi = db.query(MallInfo).filter(MallInfo.id == 1).first()
    lat = float(mi.latitude) if mi and mi.latitude else 6.55167
    lng = float(mi.longitude) if mi and mi.longitude else -73.13409
    return {"direccion": mi.address if mi else "Calle 10 # 12-184, San Gil, Santander",
            "_location": {"latitude": lat, "longitude": lng, "name": "Centro Comercial El Puente",
                          "address": mi.address if mi else "Calle 10 # 12-184, San Gil"},
            "nota": "El pin de ubicación se envía automáticamente; solo di que se lo compartes."}


def _ejecutar_herramienta(db, nombre: str, args: dict) -> dict:
    try:
        if nombre == "buscar_locales":
            return _t_buscar_locales(db, args.get("que_busca", ""))
        if nombre == "datos_local":
            return _t_datos_local(db, args.get("nombre", ""))
        if nombre == "eventos":
            return _t_eventos(db)
        if nombre == "sorteos":
            return _t_sorteos(db)
        if nombre == "promociones":
            return _t_promociones(db)
        if nombre == "cartelera_cine":
            return _t_cartelera_cine(db)
        if nombre == "info_mall":
            return _t_info_mall(db, args.get("tema", ""))
        if nombre == "contacto_administracion":
            return _t_contacto_administracion(db)
        if nombre == "ubicacion_mall":
            return _t_ubicacion_mall(db)
        return {"error": f"herramienta desconocida: {nombre}"}
    except Exception as e:
        logger.exception("Error en herramienta %s", nombre)
        return {"error": f"La herramienta falló: {str(e)[:120]}. Responde con lo que tengas y ofrece el contacto correcto."}


# ══════════════════════════════════════════════════════════════════
# TRAZA (mismo modelo que el orquestador → se ve en el panel)
# ══════════════════════════════════════════════════════════════════

class _Traza:
    def __init__(self, phone, mensaje, modo):
        self.phone, self.mensaje, self.modo = phone, mensaje, modo
        self.inicio = time.time(); self.pasos = []; self.herramientas = []
        self.respuesta = ""; self.fotos = []; self.ubicacion = None; self.contenido = []

    def paso(self, nombre, detalle):
        self.pasos.append({"paso": nombre, "detalle": detalle[:400], "ms": round((time.time() - self.inicio) * 1000, 1)})

    def guardar(self, db):
        try:
            # herramienta_elegida es VARCHAR(50) en la BD → se recorta; la
            # lista completa de herramientas queda en razon_decision y pasos.
            usadas = ",".join(dict.fromkeys(self.herramientas)) if self.herramientas else "sin_herramientas"
            tr = OrchestratorTrace(
                phone_number=self.phone, mensaje_usuario=self.mensaje,
                herramienta_elegida=("agente:" + usadas)[:50],
                metodo_decision="agente",
                razon_decision=f"Agente IA · {len(self.herramientas)} llamada(s): {', '.join(self.herramientas) or 'ninguna'}",
                respuesta_bot=self.respuesta, fotos_enviadas=len(self.fotos),
                fotos_urls=json.dumps(self.fotos, ensure_ascii=False),
                contenido_extra=json.dumps(self.contenido, ensure_ascii=False),
                ubicacion_enviada="si" if self.ubicacion else "no",
                pasos=json.dumps(self.pasos, ensure_ascii=False),
                tiempo_total_ms=round((time.time() - self.inicio) * 1000, 1), modo=self.modo,
            )
            db.add(tr); db.commit()
        except Exception:
            db.rollback()
            logger.exception("No se pudo guardar la traza del agente")


# ══════════════════════════════════════════════════════════════════
# HISTORIAL, PROMO Y LIMPIEZA
# ══════════════════════════════════════════════════════════════════

def _historial(db, phone: str, excluir_texto: str) -> list[dict]:
    from models.conversation import Conversation
    filas = (db.query(Conversation).filter(Conversation.phone_number == phone)
             .order_by(Conversation.timestamp.desc(), Conversation.id.desc()).limit(MAX_HISTORIAL + 1).all())
    filas = list(reversed(filas))
    # El mensaje actual ya quedó guardado por el webhook; no lo repetimos.
    if filas and filas[-1].role == "user" and (filas[-1].message or "").strip() == (excluir_texto or "").strip():
        filas = filas[:-1]
    out = []
    for f in filas[-MAX_HISTORIAL:]:
        if not (f.message or "").strip():
            continue
        if f.role == "assistant" and "ley 1581" in (f.message or "").lower():
            continue  # el aviso de privacidad no aporta al hilo
        out.append({"role": "assistant" if f.role != "user" else "user", "content": f.message[:1200]})
    return out


def _promo_sugerida(db, phone: str) -> dict | None:
    try:
        from services.ai import _texto_promo_para_pegar
        return _texto_promo_para_pegar(db, phone)
    except Exception:
        return None


def _limpiar(texto: str) -> str:
    t = re.sub(r"<think>.*?</think>", "", texto or "", flags=re.DOTALL | re.IGNORECASE)
    if "<think" in t.lower():
        t = t[: t.lower().index("<think")]
    t = re.sub(r"\*\*(.+?)\*\*", r"*\1*", t)        # negrita markdown → WhatsApp
    t = re.sub(r"^#{1,6}\s*", "", t, flags=re.M)    # sin títulos markdown
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def _asegurar_equidad(texto: str, nombres: list[str], locales: list[dict], traza) -> str:
    """Si el modelo omitió locales de la lista, se completan (regla del mall)."""
    if not nombres:
        return texto
    plano = _sin_tildes(texto)
    faltan = [l for l, n in zip(locales, nombres) if _sin_tildes(n) not in plano]
    if not faltan:
        return texto
    traza.paso("equidad", f"El modelo omitió {len(faltan)} local(es) → se completan: {', '.join(n['nombre'] for n in faltan)[:200]}")
    extra = "\n".join(f"• *{l['nombre']}*" + (f" — {l['zona']}" if l.get('zona') else "") + (f" · Tel: {l['telefono']}" if l.get('telefono') else "") for l in faltan)
    return texto.rstrip() + "\n\nTambién:\n" + extra


# ══════════════════════════════════════════════════════════════════
# PUNTO DE ENTRADA
# ══════════════════════════════════════════════════════════════════

async def procesar_con_agente(db: Session, phone_number: str, mensaje: str, modo: str = "prueba", user_name: str = "") -> dict:
    """
    Mismo contrato que procesar_con_orquestador: devuelve
    {"text", "image_urls", "location", "mentioned_store_id"}.
    """
    from services.ai import _get_groq_client, settings

    traza = _Traza(phone_number, mensaje, modo)
    nombre = (user_name or "").strip().split(" ")[0] if user_name else ""
    if nombre.lower() in ("usuario", "cliente", "tester", "none", "null"):
        nombre = ""
    traza.paso("inicio", f"Mensaje: '{mensaje}'" + (f" (cliente: {nombre})" if nombre else ""))

    # ── Reglas duras que NO pasan por la IA ──
    try:
        from services.orchestrator import _decidir_por_reglas, _ejecutar_emergencia, _ejecutar_queja, Traza as _TrazaOrq
        t_aux = _TrazaOrq(phone_number, mensaje, modo)
        regla = _decidir_por_reglas(mensaje, t_aux)
        if regla in ("emergencia", "queja"):
            ejecutor = _ejecutar_emergencia if regla == "emergencia" else _ejecutar_queja
            res = await ejecutor(db, phone_number, mensaje, t_aux)
            traza.herramientas.append(regla)
            traza.paso("regla_dura", f"{regla} → respuesta determinística (sin IA)")
            traza.respuesta = res["text"]; traza.guardar(db)
            return {"text": res["text"], "image_urls": [], "location": None, "mentioned_store_id": None}
    except Exception as e:
        traza.paso("regla_dura_error", str(e)[:120])

    # ── Contexto para el modelo ──
    hoy = datetime.date.today()
    fecha_hoy = f"{DIAS[hoy.weekday()]} {hoy.day} de {MESES[hoy.month - 1]} de {hoy.year}"
    system = PERSONA.format(fecha_hoy=fecha_hoy, contacto_mall=CONTACTO_MALL)
    if nombre:
        system += f"\nEl cliente se llama {nombre}."
    promo = _promo_sugerida(db, phone_number)
    if promo and promo.get("texto"):
        system += f"\n\nPROMO_SUGERIDA (opcional, ver reglas): {promo['texto']}"
        traza.paso("promo", f"Promo sugerida al modelo: {promo.get('nombre', '')}")

    messages = [{"role": "system", "content": system}]
    hist = _historial(db, phone_number, mensaje)
    messages += hist
    messages.append({"role": "user", "content": mensaje})
    traza.paso("contexto", f"{len(hist)} mensajes de historial · fecha {fecha_hoy}")

    client = _get_groq_client()
    texto_final = ""
    nombres_equidad, locales_equidad = [], []
    fotos, location, mentioned_store_id = [], None, None

    for vuelta in range(MAX_VUELTAS + 1):
        try:
            t0 = time.time()
            comp = await client.chat.completions.create(
                model=settings.GROQ_MODEL, messages=messages, tools=HERRAMIENTAS, tool_choice="auto",
                temperature=0.4, max_tokens=MAX_TOKENS_RESPUESTA,
            )
            msg = comp.choices[0].message
            traza.paso("modelo", f"vuelta {vuelta + 1}: {round((time.time() - t0) * 1000)} ms · tool_calls={len(msg.tool_calls or [])}")
        except Exception as e:
            traza.paso("modelo_error", str(e)[:200])
            logger.exception("Fallo llamando a Groq en el agente")
            break

        calls = msg.tool_calls or []
        if not calls or vuelta == MAX_VUELTAS:
            texto_final = _limpiar(msg.content or "")
            break

        # El modelo pidió herramientas → ejecutarlas y devolverle los datos
        messages.append({"role": "assistant", "content": msg.content or "", "tool_calls": [
            {"id": c.id, "type": "function", "function": {"name": c.function.name, "arguments": c.function.arguments or "{}"}}
            for c in calls]})
        for c in calls:
            try:
                args = json.loads(c.function.arguments or "{}")
            except Exception:
                args = {}
            res = _ejecutar_herramienta(db, c.function.name, args)
            traza.herramientas.append(c.function.name)
            resumen = {k: v for k, v in res.items() if k in ("total", "encontrado", "categoria_detectada", "busqueda", "disponible", "error")}
            traza.paso("herramienta", f"{c.function.name}({json.dumps(args, ensure_ascii=False)}) → {json.dumps(resumen, ensure_ascii=False)}")

            # Efectos laterales (fotos, pin, contexto) se deciden en código
            if c.function.name == "buscar_locales":
                nombres_equidad = res.pop("_nombres", []) or nombres_equidad
                locales_equidad = res.get("locales", []) or locales_equidad
            if c.function.name == "datos_local" and res.get("encontrado"):
                mentioned_store_id = res.get("id")
                try:
                    from models.store import Store
                    st = db.query(Store).filter(Store.id == mentioned_store_id).first()
                    if st and any(p in _sin_tildes(mensaje) for p in ("carta", "menu", "catalogo")):
                        f = st.get_photo_by_label("carta")
                        if f and any(p.label == "carta" for p in (st.photos or [])):
                            fotos = [f]
                except Exception:
                    pass
            if c.function.name == "ubicacion_mall":
                location = res.pop("_location", None)
            if c.function.name == "cartelera_cine" and res.get("disponible"):
                try:
                    from services.cine import find_cine_store
                    cs = find_cine_store(db)
                    mentioned_store_id = mentioned_store_id or (cs.id if cs else None)
                except Exception:
                    pass
            messages.append({"role": "tool", "tool_call_id": c.id, "name": c.function.name,
                             "content": json.dumps(res, ensure_ascii=False)[:12000]})

    # ── Redes de seguridad ──
    if texto_final:
        texto_final = _asegurar_equidad(texto_final, nombres_equidad, locales_equidad, traza)
    if not texto_final.strip():
        traza.paso("respaldo", "El modelo no devolvió texto → respaldo con contacto real")
        texto_final = (f"{nombre + ', d' if nombre else 'D'}isculpa, tuve un problema para procesar tu mensaje 😅. "
                       f"¿Me lo repites de otra forma? Si es urgente, la línea del centro comercial es {CONTACTO_MALL}.")
    if promo and promo.get("foto") and not fotos and promo.get("nombre") and _sin_tildes(promo["nombre"]) in _sin_tildes(texto_final):
        fotos = [promo["foto"]]
    fotos = fotos[:2]

    traza.respuesta = texto_final; traza.fotos = fotos; traza.ubicacion = location
    if location:
        traza.contenido.append({"tipo": "ubicacion", "detalle": location.get("name")})
    for f in fotos:
        traza.contenido.append({"tipo": "foto", "detalle": f})
    traza.paso("fin", f"Respuesta lista ({len(texto_final)} caracteres, {len(fotos)} fotos, {len(traza.herramientas)} herramientas)")
    traza.guardar(db)

    return {"text": texto_final, "image_urls": fotos, "location": location, "mentioned_store_id": mentioned_store_id}