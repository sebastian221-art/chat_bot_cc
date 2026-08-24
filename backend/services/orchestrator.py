# 📄 ARCHIVO: backend/services/orchestrator.py
"""
ORQUESTADOR CENTRAL — el cerebro único del flujo nuevo.

Recibe cada mensaje en UN solo punto, decide qué herramienta usar
(híbrido: reglas para lo obvio, IA para lo ambiguo), la ejecuta, y
GUARDA UNA TRAZA completa de todo lo que pensó — para que el flujo sea
totalmente visible desde el panel.

Este es el ESQUELETO (paso 1): la estructura completa funciona de punta
a punta, con 2 herramientas conectadas de verdad (emergencia y
conversación general) para poder ver el sistema andando. Las demás
herramientas se irán conectando una a una, reutilizando la lógica que
YA existe (no se reescribe nada).

Convive con el flujo viejo mediante un switch (ver orchestrator_switch).
Mientras el switch no lo active, este código no toca a ningún cliente.
"""
import json
import time
import logging

from sqlalchemy.orm import Session

from models.orchestrator_trace import OrchestratorTrace
from services.orchestrator_tools import HERRAMIENTAS, herramienta_por_nombre

logger = logging.getLogger("mall_bot")


class Traza:
    """Acumula los pasos del razonamiento para guardarlos al final."""
    def __init__(self, phone_number: str, mensaje: str, modo: str = "prueba"):
        self.phone_number = phone_number
        self.mensaje = mensaje
        self.modo = modo
        self.pasos = []
        self.inicio = time.time()
        self.herramienta_elegida = None
        self.metodo_decision = None
        self.razon_decision = None
        self.respuesta = None
        self.fotos = 0
        self.ubicacion = "no"

    def paso(self, nombre: str, detalle: str):
        ms = round((time.time() - self.inicio) * 1000, 1)
        self.pasos.append({"paso": nombre, "detalle": detalle, "ms": ms})

    def guardar(self, db: Session):
        trace = OrchestratorTrace(
            phone_number=self.phone_number,
            mensaje_usuario=self.mensaje,
            herramienta_elegida=self.herramienta_elegida,
            metodo_decision=self.metodo_decision,
            razon_decision=self.razon_decision,
            respuesta_bot=self.respuesta,
            fotos_enviadas=self.fotos,
            ubicacion_enviada=self.ubicacion,
            pasos=json.dumps(self.pasos, ensure_ascii=False),
            tiempo_total_ms=round((time.time() - self.inicio) * 1000, 1),
            modo=self.modo,
        )
        db.add(trace)
        db.commit()
        return trace


# ══════════════════════════════════════════════════════════════════
# DECISIÓN — qué herramienta usar (híbrido: reglas primero, IA después)
# ══════════════════════════════════════════════════════════════════

def _decidir_por_reglas(mensaje: str, traza: Traza) -> str | None:
    """
    Decisión RÁPIDA por palabras clave — para lo obvio, sin gastar IA.
    Recorre las herramientas EN ORDEN (las urgentes/específicas primero)
    y devuelve la primera que coincida. Si ninguna coincide con reglas
    claras, devuelve None y se pasa a la decisión por IA.
    """
    msg = mensaje.lower()
    for h in HERRAMIENTAS:
        palabras = h.get("palabras_clave", [])
        if not palabras:
            continue  # herramientas sin palabras clave se deciden por IA/lógica especial
        for palabra in palabras:
            if palabra in msg:
                traza.paso("decision_reglas", f"La palabra '{palabra}' coincide con la herramienta '{h['nombre']}'")
                return h["nombre"]
    return None


async def _decidir_por_ia(mensaje: str, traza: Traza) -> str:
    """
    Decisión FLEXIBLE por IA — para lo ambiguo o nuevo. Le da a la IA la
    lista de herramientas con sus descripciones y le pide que elija la
    más adecuada. Esto es lo que permite "pilotear" lo inesperado.

    Si la IA falla o elige algo inválido, cae a 'conversacion_general'
    (el fallback seguro).
    """
    from services.ai import _get_groq_client, settings, _strip_thinking_tags
    client = _get_groq_client()

    lista_tools = "\n".join(
        f"- {h['nombre']}: {h['descripcion']}"
        for h in HERRAMIENTAS
    )
    prompt = f"""Eres el enrutador de un asistente de centro comercial (Centro Comercial El Puente). Tu ÚNICA tarea es elegir qué herramienta debe manejar el mensaje del cliente. NO respondas al cliente, solo clasifica.

Herramientas disponibles:
{lista_tools}

Mensaje del cliente: "{mensaje}"

Reglas de decisión:
- Si el cliente busca/pregunta por un producto, comida, tienda o servicio → la herramienta de información que corresponda.
- Si es un saludo, charla casual, agradecimiento, o algo que NO es del centro comercial (preguntas generales, trivia, temas personales) → conversacion_general.
- Si expresa molestia, reclamo o inconformidad → queja.
- Si es una situación de peligro o urgencia → emergencia.

Responde SOLO con el nombre exacto de una herramienta de la lista (una palabra). Nada más."""

    try:
        completion = await client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,   # antes 20 — muy poco: el modelo razona internamente y no alcanzaba a escribir el nombre
            temperature=0.0,
        )
        raw = completion.choices[0].message.content or ""
        limpio = _strip_thinking_tags(raw).strip().lower()
        # El modelo a veces devuelve el nombre dentro de una frase — buscamos
        # cuál de las herramientas reales aparece en su respuesta.
        eleccion = None
        for h in HERRAMIENTAS:
            if h["nombre"] in limpio:
                eleccion = h["nombre"]
                break
        if eleccion:
            traza.paso("decision_ia", f"La IA eligió la herramienta '{eleccion}' (respuesta cruda: '{limpio[:40]}')")
            return eleccion
        traza.paso("decision_ia", f"La IA no dio una herramienta clara ('{limpio[:40]}') → se usa conversacion_general")
        return "conversacion_general"
    except Exception as e:
        traza.paso("decision_ia_error", f"Error al consultar la IA: {str(e)} → se usa conversacion_general")
        return "conversacion_general"


async def decidir_herramienta(mensaje: str, traza: Traza) -> tuple[str, str]:
    """
    Decisión HÍBRIDA. Devuelve (nombre_herramienta, metodo).
    1. Intenta por reglas (rápido, barato, para lo obvio).
    2. Si no hay match claro, decide por IA (flexible, para lo ambiguo).
    """
    por_reglas = _decidir_por_reglas(mensaje, traza)
    if por_reglas:
        traza.metodo_decision = "reglas"
        traza.razon_decision = f"Decisión por reglas (palabra clave) → {por_reglas}"
        return por_reglas, "reglas"

    traza.paso("decision", "Ninguna regla clara coincidió → se consulta a la IA para decidir")
    por_ia = await _decidir_por_ia(mensaje, traza)
    traza.metodo_decision = "ia"
    traza.razon_decision = f"Decisión por IA → {por_ia}"
    return por_ia, "ia"


# ══════════════════════════════════════════════════════════════════
# EJECUCIÓN — correr la herramienta elegida
# ══════════════════════════════════════════════════════════════════

# Contacto del mall para emergencias y quejas (del Info General)
CONTACTO_MALL = "317 432 0138"


async def _ejecutar_emergencia(db, phone_number, mensaje, traza) -> dict:
    """
    Herramienta de EMERGENCIA — respuesta inmediata, calmada y con la
    ruta correcta. NO usa IA (para que sea instantánea y siempre
    consistente en un momento crítico). Máxima prioridad.
    """
    traza.paso("ejecucion", "Ejecutando herramienta de emergencia — respuesta directa con contacto de seguridad")
    texto = (
        "🚨 Entiendo que es una situación urgente. Por favor, dirígete de inmediato al *Punto de "
        "Información* (Piso 1) o busca al personal de *seguridad* más cercano — ellos pueden actuar "
        "al instante.\n\n"
        f"También puedes llamar directamente a la administración del centro comercial al *{CONTACTO_MALL}*.\n\n"
        "Estamos para ayudarte."
    )
    return {"text": texto, "image_urls": [], "location": None}


async def _ejecutar_conversacion_general(db, phone_number, mensaje, traza) -> dict:
    """
    Herramienta GENERAL / piloteo. Delega en _route_message (el flujo
    viejo probado) porque este NO solo genera el texto — también adjunta
    automáticamente las FOTOS de la tienda/evento/sorteo/marketing que
    se haya mencionado (toda esa lógica ya existe y funciona ahí). Si
    llamáramos a generate_response directo, perderíamos las fotos.

    Mantiene las 2 redes de seguridad: si _route_message devuelve texto
    vacío, se reintenta; si sigue vacío, respaldo amable.
    """
    traza.paso("ejecucion", "Conversación general → delega en _route_message (incluye fotos de tienda/evento/sorteo)")
    from routers.webhook import _route_message

    async def _intentar():
        r = await _route_message(db, phone_number, "", mensaje)
        return r

    resultado = None
    try:
        resultado = await _intentar()
    except Exception as e:
        traza.paso("error", f"_route_message falló: {str(e)}")

    # Red 1: reintento si vino vacío
    if not resultado or not (resultado.get("text") or "").strip():
        traza.paso("reintento", "_route_message devolvió vacío → se reintenta una vez")
        try:
            resultado = await _intentar()
        except Exception as e:
            traza.paso("reintento_error", f"El reintento falló: {str(e)}")

    # Red 2: respaldo amable si sigue vacío
    if not resultado or not (resultado.get("text") or "").strip():
        traza.paso("respaldo", "Sigue vacío → mensaje de respaldo")
        return {
            "text": (
                "¡Hola! Soy Any 🛍️, tu asistente del Centro Comercial El Puente. "
                "¿En qué te puedo ayudar? Puedo orientarte con tiendas, comida, horarios, "
                "servicios o cualquier cosa del centro comercial 😊"
            ),
            "image_urls": [], "location": None,
        }

    fotos = len(resultado.get("image_urls") or [])
    traza.paso("resultado_ia", f"Respuesta final: {len((resultado.get('text') or ''))} caracteres, {fotos} foto(s)")
    return {
        "text": resultado.get("text", ""),
        "image_urls": resultado.get("image_urls", []),
        "location": resultado.get("location"),
    }


# ══════════════════════════════════════════════════════════════════
# HERRAMIENTAS conectadas a la lógica que YA existe (no se reescribe)
# ══════════════════════════════════════════════════════════════════

async def _ejecutar_queja(db, phone_number, mensaje, traza) -> dict:
    """
    Herramienta de QUEJA — recoge la inconformidad con empatía y la
    escala al contacto del mall. NO usa IA, para que siempre responda
    con el mismo criterio de servicio (empatía + canal correcto).
    """
    traza.paso("ejecucion", "Ejecutando herramienta de queja — respuesta empática con canal de escalamiento")
    texto = (
        "Lamento mucho lo que pasó, y gracias por tomarte el tiempo de contarnos — "
        "tu comentario es importante para el centro comercial. 🙏\n\n"
        "Para que tu queja quede registrada formalmente y le den seguimiento, te recomiendo "
        f"comunicarte con la administración al *{CONTACTO_MALL}*, o acercarte al *Punto de "
        "Información* (Piso 1). Ahí podrán ayudarte de manera directa.\n\n"
        "¿Hay algo más en lo que te pueda apoyar mientras tanto?"
    )
    return {"text": texto, "image_urls": [], "location": None}


async def _ejecutar_numero_tienda(db, phone_number, mensaje, traza) -> dict:
    """Reutiliza la lógica del flujo viejo: buscar tienda + armar su info de contacto."""
    from services.store_transfer import find_store_by_message, build_phone_info_message
    from routers.webhook import _pick_store_photo, _wrap

    store = find_store_by_message(db, mensaje)
    if store:
        traza.paso("ejecucion", f"Tienda encontrada: '{store.name}' → se arma su número + link (lógica existente)")
        return {
            "text": build_phone_info_message(store),
            "image_urls": _wrap([_pick_store_photo(store, mensaje)]),
            "location": None,
        }
    traza.paso("ejecucion", "No se identificó una tienda puntual → cae a conversación general")
    return await _ejecutar_conversacion_general(db, phone_number, mensaje, traza)


async def _ejecutar_cartelera_cine(db, phone_number, mensaje, traza) -> dict:
    """Reutiliza services/cine.py — la misma cartelera determinística del flujo viejo."""
    from services.cine import find_cine_store, find_cine_funcion_by_message, build_cartelera_message, build_funcion_especifica_message
    from routers.webhook import _wrap

    cine_store = find_cine_store(db)
    if not cine_store:
        traza.paso("ejecucion", "No hay tienda de cine registrada")
        return {"text": build_cartelera_message(None), "image_urls": [], "location": None}

    funcion = find_cine_funcion_by_message(db, cine_store.id, mensaje)
    if funcion:
        traza.paso("ejecucion", f"Película puntual: '{funcion.title}'")
        from models.entity_photo import get_entity_photo
        poster = get_entity_photo(db, "cine_funcion", funcion.id, "poster")
        return {"text": build_funcion_especifica_message(funcion, cine_store), "image_urls": _wrap([poster]), "location": None}

    traza.paso("ejecucion", f"Cartelera completa de '{cine_store.name}'")
    from models.entity_photo import get_entity_photo
    posters = []
    for f in cine_store.cine_funciones:
        if f.active and len(posters) < 2:
            p = get_entity_photo(db, "cine_funcion", f.id, "poster")
            if p:
                posters.append(p)
    return {"text": build_cartelera_message(cine_store), "image_urls": posters, "location": None}


async def _ejecutar_busqueda_categoria(db, phone_number, mensaje, traza) -> dict:
    """
    Búsqueda justa por categoría. Con un matiz de CALIDAD para no soltar
    "chorreros":
      - Si la categoría tiene MUCHOS locales (>8, ej. "ropa"→24,
        "zapatos"→16) y la petición es amplia, primero PREGUNTA para
        acotar (qué estilo/tipo busca), en vez de listar 24 de corrido.
      - Si son pocos (2-8, ej. "hamburguesas"→6), lista directo — ahí
        la lista completa sí es útil y no abruma.
      - Con 0-1, cae a conversación general (que pilotea/pregunta).
    """
    from services.category_search import detectar_categoria, construir_lista_locales
    from services.rag import find_all_stores_by_category

    UMBRAL_ACOTAR = 8  # más locales que esto → mejor preguntar primero

    cat = detectar_categoria(mensaje)
    if cat:
        nombre_cat, terminos = cat
        locales = find_all_stores_by_category(db, terminos)
        traza.paso("ejecucion", f"Categoría '{nombre_cat}' → {len(locales)} locales (búsqueda justa)")

        if len(locales) > UMBRAL_ACOTAR:
            # Demasiados para listar de golpe → acotar con una pregunta,
            # manteniendo la personalidad y ofreciendo orientar.
            traza.paso("acotar", f"{len(locales)} locales es mucho → se pregunta para acotar en vez de soltar la lista")
            texto = (
                f"¡Tenemos bastantes opciones de {nombre_cat} en el centro comercial! 😊 "
                f"Para recomendarte la ideal y no abrumarte con toda la lista, cuéntame un poco más: "
                f"¿qué estás buscando en particular — algún estilo, marca, rango de precio o para quién es? "
                f"Con esa pista te digo el local perfecto. Y si prefieres verlos todos, dime \"muéstrame todos\" y te paso la lista completa."
            )
            return {"text": texto, "image_urls": [], "location": None}

        if len(locales) >= 2:
            return {"text": construir_lista_locales(locales, nombre_cat), "image_urls": [], "location": None}

    traza.paso("ejecucion", "No se detectó categoría con 2+ locales → cae a conversación general")
    return await _ejecutar_conversacion_general(db, phone_number, mensaje, traza)


async def _ejecutar_ubicacion_mall(db, phone_number, mensaje, traza) -> dict:
    """Manda el pin real del mall — misma lógica del flujo viejo."""
    from models.mall_info import MallInfo

    mall_info = db.query(MallInfo).filter(MallInfo.id == 1).first()
    if mall_info and mall_info.latitude and mall_info.longitude:
        try:
            location = {
                "latitude": float(mall_info.latitude),
                "longitude": float(mall_info.longitude),
                "name": mall_info.name,
                "address": mall_info.address or "",
            }
            traza.paso("ejecucion", f"Ubicación del mall → pin real ({location['latitude']}, {location['longitude']})")
            texto = f"📍 {mall_info.name} está ubicado en {mall_info.address or 'el centro de la ciudad'}. Te comparto la ubicación exacta 😊"
            return {"text": texto, "image_urls": [], "location": location}
        except ValueError:
            pass
    traza.paso("ejecucion", "Sin coordenadas del mall → cae a conversación general")
    return await _ejecutar_conversacion_general(db, phone_number, mensaje, traza)


async def _ejecutar_gestion_domicilio(db, phone_number, mensaje, traza) -> dict:
    """
    La gestión de domicilio del flujo viejo tiene varios pasos
    entrelazados (identificar la tienda, validar horario, recolectar
    datos, detectar cancelaciones). En vez de reimplementar eso —donde
    es fácil introducir bugs— delegamos en _route_message del flujo
    viejo, que ya orquesta todo el domicilio correctamente. Reutilización
    pura: el orquestador decide "esto es domicilio", y deja que la
    maquinaria probada lo maneje.
    """
    traza.paso("ejecucion", "Gestión de domicilio → delega en el flujo probado (_route_message) para no romper el paso a paso")
    from routers.webhook import _route_message
    resultado = await _route_message(db, phone_number, "", mensaje)
    return {
        "text": resultado.get("text", ""),
        "image_urls": resultado.get("image_urls", []),
        "location": resultado.get("location"),
    }


async def _ejecutar_torre_medica(db, phone_number, mensaje, traza) -> dict:
    """
    Torre médica / servicios de salud. Busca en la base de conocimiento
    (donde se cargará la info de la torre médica). Si encuentra algo
    relevante, responde con eso. Si NO hay datos cargados, da una
    respuesta HONESTA y CONSISTENTE — sin inventar ubicaciones, y SIN
    adjuntar fotos ni el pin del mall de relleno (que era justo el bug:
    mandaba la foto de la última hamburguesa y el mapa sin venir al
    caso). Cuando cargues los datos de la torre médica, responderá con
    el consultorio exacto.
    """
    from services.rag import search_knowledge_and_events

    traza.paso("ejecucion", "Consulta de servicios médicos → busca en la base de conocimiento")

    # Buscar en la base de conocimiento algo sobre torre médica/servicios
    try:
        docs = search_knowledge_and_events(mensaje, n_results=3)
    except Exception:
        docs = []

    # Filtrar a lo que de verdad hable de salud/torre médica
    relevantes = [d for d in docs if any(
        k in d.lower() for k in ("médic", "medic", "salud", "torre", "consultorio", "clínic", "clinic", "radiograf", "laboratorio")
    )]

    if relevantes:
        traza.paso("resultado", f"Encontró {len(relevantes)} entrada(s) relevante(s) en la base de conocimiento")
        from services.ai import generate_response
        # Usamos la IA solo para redactar con base en lo encontrado, pero
        # SIN la maquinaria de fotos del flujo viejo.
        contexto = "\n".join(relevantes[:2])
        texto, *_ = await generate_response(
            user_message=mensaje,
            user_name="",
            conversation_history=[{"role": "system", "content": f"Información disponible sobre servicios médicos del centro comercial:\n{contexto}"}],
            db=db,
            phone_number=phone_number,
        )
        if (texto or "").strip():
            return {"text": texto.strip(), "image_urls": [], "location": None}

    # Sin datos → respuesta honesta, consistente, sin fotos ni pin de relleno
    traza.paso("respaldo_honesto", "Sin datos de torre médica cargados → respuesta honesta y consistente (sin foto ni ubicación de relleno)")
    texto = (
        "El Centro Comercial El Puente cuenta con una *Torre Médica y Empresarial* donde hay varios "
        "consultorios y servicios de salud. Para orientarte al consultorio exacto que necesitas, te "
        "recomiendo acercarte al *Punto de Información* (Piso 1) o llamar a la administración al "
        f"*{CONTACTO_MALL}* — con gusto te indican dónde dirigirte. 😊"
    )
    return {"text": texto, "image_urls": [], "location": None}


# Mapa de nombre de herramienta → función que la ejecuta.
# Ahora TODAS las herramientas están conectadas, reutilizando la lógica
# que ya funcionaba en el flujo viejo (no se reescribió nada).
EJECUTORES = {
    "emergencia": _ejecutar_emergencia,
    "queja": _ejecutar_queja,
    "numero_tienda": _ejecutar_numero_tienda,
    "cartelera_cine": _ejecutar_cartelera_cine,
    "busqueda_categoria": _ejecutar_busqueda_categoria,
    "ubicacion_mall": _ejecutar_ubicacion_mall,
    "gestion_domicilio": _ejecutar_gestion_domicilio,
    "torre_medica": _ejecutar_torre_medica,
    "conversacion_general": _ejecutar_conversacion_general,
}


# ══════════════════════════════════════════════════════════════════
# PUNTO DE ENTRADA — lo que llama el webhook cuando el switch está ON
# ══════════════════════════════════════════════════════════════════

async def procesar_con_orquestador(db: Session, phone_number: str, mensaje: str, modo: str = "prueba") -> dict:
    """
    Punto de entrada único del orquestador. Recibe el mensaje, decide,
    ejecuta, guarda la traza, y devuelve la respuesta en el MISMO
    formato que el flujo viejo (text, image_urls, location) — para que
    el switch pueda intercambiarlos sin que el resto del código note la
    diferencia.
    """
    traza = Traza(phone_number, mensaje, modo)
    traza.paso("inicio", f"Mensaje recibido: '{mensaje}'")

    # 1. Decidir qué herramienta usar (híbrido)
    nombre_tool, metodo = await decidir_herramienta(mensaje, traza)
    traza.herramienta_elegida = nombre_tool

    # 2. Ejecutar la herramienta (si no está conectada aún, cae al general)
    ejecutor = EJECUTORES.get(nombre_tool)
    if not ejecutor:
        traza.paso("ejecucion", f"La herramienta '{nombre_tool}' aún no está conectada en el esqueleto → se usa conversacion_general")
        ejecutor = EJECUTORES["conversacion_general"]

    resultado = await ejecutor(db, phone_number, mensaje, traza)

    # Red de seguridad GLOBAL: si CUALQUIER herramienta devolvió texto
    # vacío (por el motivo que sea), nunca lo mandamos así al cliente —
    # ponemos un respaldo amable. Es la última barrera antes del cliente.
    if not (resultado.get("text") or "").strip():
        traza.paso("respaldo_global", "La herramienta devolvió texto vacío → respaldo global (el cliente nunca recibe vacío)")
        resultado["text"] = (
            "¡Hola! Soy Any 🛍️, tu asistente del Centro Comercial El Puente. "
            "Cuéntame en qué te puedo ayudar — tiendas, comida, horarios, servicios o lo que necesites 😊"
        )

    # 3. Registrar el resultado en la traza
    traza.respuesta = resultado.get("text", "")
    traza.fotos = len(resultado.get("image_urls", []))
    traza.ubicacion = "si" if resultado.get("location") else "no"
    traza.paso("fin", f"Respuesta lista ({len(traza.respuesta)} caracteres, {traza.fotos} fotos)")

    # 4. Guardar la traza (esto es lo que hace todo visible en el panel)
    traza.guardar(db)

    return resultado