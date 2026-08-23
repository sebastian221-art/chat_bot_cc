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
    from services.ai import _get_groq_client, settings
    client = _get_groq_client()

    lista_tools = "\n".join(
        f"- {h['nombre']}: {h['descripcion']}"
        for h in HERRAMIENTAS
    )
    prompt = f"""Eres el enrutador de un asistente de centro comercial. Tu única tarea es elegir QUÉ HERRAMIENTA debe manejar el mensaje del cliente.

Herramientas disponibles:
{lista_tools}

Mensaje del cliente: "{mensaje}"

Responde ÚNICAMENTE con el nombre exacto de la herramienta más adecuada (una sola palabra, sin explicación, sin puntuación). Si ninguna encaja claramente, responde: conversacion_general"""

    try:
        completion = await client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=20,
            temperature=0.0,
        )
        eleccion = (completion.choices[0].message.content or "").strip().lower()
        # Validar que sea una herramienta real
        if herramienta_por_nombre(eleccion):
            traza.paso("decision_ia", f"La IA eligió la herramienta '{eleccion}' para este mensaje")
            return eleccion
        traza.paso("decision_ia", f"La IA respondió '{eleccion}' (no válida) → se usa conversacion_general")
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
    Herramienta GENERAL / piloteo — por ahora, en el esqueleto, delega
    en la lógica conversacional que YA existe (generate_response), para
    demostrar que el orquestador puede reutilizar lo viejo sin
    reescribirlo. Aquí es donde luego vivirá el comportamiento
    propositivo y el manejo de lo fuera de tema.
    """
    traza.paso("ejecucion", "Ejecutando conversación general — reutiliza generate_response() del flujo existente")
    from services.ai import generate_response

    texto, tienda_id, evento_id, sorteo_id, marketing_id = await generate_response(
        user_message=mensaje,
        user_name="",
        conversation_history=[],
        db=db,
        phone_number=phone_number,
    )
    traza.paso("resultado_ia", f"generate_response devolvió {len(texto)} caracteres")
    return {"text": texto, "image_urls": [], "location": None}


# Mapa de nombre de herramienta → función que la ejecuta.
# En el esqueleto solo 2 están conectadas de verdad; las demás caen al
# general por ahora, y se irán conectando una a una.
EJECUTORES = {
    "emergencia": _ejecutar_emergencia,
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

    # 3. Registrar el resultado en la traza
    traza.respuesta = resultado.get("text", "")
    traza.fotos = len(resultado.get("image_urls", []))
    traza.ubicacion = "si" if resultado.get("location") else "no"
    traza.paso("fin", f"Respuesta lista ({len(traza.respuesta)} caracteres, {traza.fotos} fotos)")

    # 4. Guardar la traza (esto es lo que hace todo visible en el panel)
    traza.guardar(db)

    return resultado