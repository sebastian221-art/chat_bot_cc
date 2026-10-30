"""
Router: decide qué especialista atiende el mensaje.

Orden:
  1. Reglas duras (solo lo crítico, por palabra completa): emergencia.
  2. Flujo con estado activo (un domicilio a medias, una navegación QR):
     el flujo dice si el mensaje sigue siendo suyo.
  3. Router IA: devuelve JSON {flujo, entidades, es_seguimiento, consulta_reescrita, razon}.
  4. Respaldo: si la IA falla, "conversacion" (que responde sin inventar).
"""
from __future__ import annotations
import re

from ..conocimiento.texto import alguna_frase, normalizar
from ..config import cfg
from ..flujos import FLUJOS, RESPALDO, catalogo_para_router, nombres_validos
from ..flujos.base import leer_prompt
from ..llm import ErrorLLM, completar
from . import mensajes
from .tipos import Contexto, Decision

# Si el cliente nombra un tema de forma inequívoca y el router lo dejó "pegado" al tema anterior,
# gana el tema nombrado ("¿hay promociones?" después de hablar del cine → sorteos_promos).
TEMA_NOMBRADO = {
    "sorteos_promos": ["promocion", "promociones", "descuento", "descuentos", "sorteo", "sorteos", "registrar factura",
                       "registro de facturas"],
    "eventos": ["evento", "eventos", "actividades del centro comercial"],
    "cine": ["pelicula", "peliculas", "cartelera", "cine", "boleta de cine"],
}

CLAVES_ENTIDADES = {"local", "categoria", "pelicula", "evento", "especialidad", "servicio", "zona", "pide", "tipo"}


def regla_emergencia(texto: str) -> str | None:
    return alguna_frase(mensajes.frases("frases_emergencia"), texto)


_VERBO_ALQUILER = re.compile(r"\b(alquil|arriend|arrend|rent|reserv|cotiz|hacer|realizar|organizar|celebrar)\w*")
_COSA_EVENTO = re.compile(r"\b(salon|salones|capacitacion\w*|conferencia\w*|graduacion\w*|grado|fiesta\w*|"
                          r"reunion\w*|evento empresarial|eventos empresariales)\b")
# nombres de locales que también son palabras comunes de una respuesta ("claro", "tennis")
_NOMBRES_AMBIGUOS = {"claro", "tennis", "si", "no", "ok", "rich"}


def regla_salon_eventos(texto: str) -> bool:
    n = normalizar(texto or "")
    return bool(re.search(r"\bauditorio\b", n) or (_VERBO_ALQUILER.search(n) and _COSA_EVENTO.search(n)))


_ORDINALES = {"primer": 1, "primero": 1, "segundo": 2, "tercer": 3, "tercero": 3, "cuarto": 4, "quinto": 5, "sexto": 6}


def piso_en_texto(texto: str) -> int | None:
    """«piso 5», «quinto piso», «5to piso» → 5. Solo pisos de la Torre (2 a 6)."""
    n = normalizar(texto or "")
    m = re.search(r"\bpiso\s*(\d)\b", n) or re.search(r"\b(\d)\s*(?:o|to|er|ro|do)?\s*piso\b", n)
    num = int(m.group(1)) if m else None
    if num is None:
        m = re.search(r"\b(" + "|".join(_ORDINALES) + r")\s+piso\b", n)
        num = _ORDINALES[m.group(1)] if m else None
    return num if num and 2 <= num <= 6 else None


# «Háblame de Claro», «info de la tienda Enjoy», «¿dónde queda Rich?»: lo que sigue es el nombre del local.
# Con ese inicio también valen los nombres que son palabras comunes («claro», «tennis»).
_PIDE_LOCAL = re.compile(r"^(?:hola\s+(?:any|ani)\s*,?\s*)?(?:any\s*,?\s*)?"
                         r"(?:hablame|cuentame|dime|dame info(?:rmacion)?|info(?:rmacion)?|que (?:es|venden en|hay en)|"
                         r"donde (?:queda|esta|encuentro)|ubicacion|telefono|whatsapp|numero)"
                         r"(?:\s+(?:de|del|sobre|acerca de))?(?:\s+(?:la|el))?(?:\s+(?:tienda|local|almacen|negocio))?\s+")


def local_por_nombre_exacto(ctx: Contexto):
    n = normalizar(ctx.mensaje or "").strip(" .!¡?¿,\"'“”‘’«»")     # «“Háblame de claro» copiado con comillas
    m = _PIDE_LOCAL.match(n)
    con_pedido = bool(m and len(n) > m.end())
    if con_pedido:
        n = n[m.end():].strip(" .!¡?¿,\"'“”‘’«»")
    if len(n) < 3 or (n in _NOMBRES_AMBIGUOS and not con_pedido) or len(n.split()) > 6:
        return None
    try:
        from ..conocimiento.catalogo import locales
        for l in locales(ctx.db):
            ln = normalizar(l.nombre).strip(" .")
            if not (l.es_servicio or l.es_cine) and (ln == n or (len(n) >= 6 and ln.replace(" ", "") == n.replace(" ", ""))):
                return l
    except Exception:
        return None
    return None


async def decidir(ctx: Contexto) -> Decision:
    # 1. Emergencia: nunca depende del modelo
    frase = regla_emergencia(ctx.mensaje)
    if frase:
        return Decision("emergencia_queja", {"tipo": "emergencia"}, False, ctx.mensaje,
                        f"regla de emergencia: «{frase}»", "regla")

    # 1b. Foto del cliente y QR de zona: reglas exactas
    if ctx.imagen:
        return Decision("imagen", {}, False, ctx.mensaje, "el cliente envió una foto", "regla")
    from ..flujos.navegacion_qr import codigo_qr
    cod = codigo_qr(ctx.db, ctx.mensaje)
    if cod:
        return Decision("navegacion_qr", {"zona": cod}, False, ctx.mensaje, f"QR de la zona {cod}", "regla")

    # 2. Flujo con estado activo
    activo = ctx.estado.flujo_activo
    if activo and activo in FLUJOS and hasattr(FLUJOS[activo], "sigue_en_flujo"):
        if FLUJOS[activo].sigue_en_flujo(ctx):
            return Decision(activo, dict(ctx.estado.ultimas_entidades), True, ctx.mensaje,
                            f"continúa el flujo activo {activo}", "estado")

    # 2b. Mensaje sin palabras ("?", "...", un emoji): se pide aclarar, sin preguntarle al modelo
    if not re.search(r"[0-9A-Za-zÁÉÍÓÚáéíóúÑñÜü]", ctx.mensaje or ""):
        return Decision(RESPALDO, {}, False, ctx.mensaje, "mensaje sin palabras: pedir aclaración", "regla")

    # 2c. Alquiler del auditorio / salones para eventos: siempre al flujo de servicios (trae los números
    #     de reservas). El modelo lo mandaba a Administración, que no tiene esos datos.
    if regla_salon_eventos(ctx.mensaje):
        return Decision("servicios_mall", {"servicio": "salon_eventos"}, False, ctx.mensaje,
                        "alquiler de salón / auditorio para eventos", "regla")

    # 2c'. «¿Qué hay en la oficina 506?», «local 301»: se busca por número (el modelo decía «está vacía»)
    if not ctx.estado.flujo_activo:
        from ..conocimiento.catalogo import locales_por_numero, numero_en_texto
        numero = numero_en_texto(ctx.mensaje)
        if numero:
            en_numero = locales_por_numero(ctx.db, numero)
            n = normalizar(ctx.mensaje)
            if (en_numero and all(l.es_torre for l in en_numero)) or (not en_numero and re.search(r"oficina|consultorio", n)):
                return Decision("torre_medica", {}, False, ctx.mensaje, f"pregunta por la oficina {numero}", "regla")
            if en_numero:
                return Decision("locales", {}, False, ctx.mensaje, f"pregunta por el local {numero}", "regla")

    # 2c''. «Oficina», «¿qué oficinas tiene?»: el directorio de la Torre (el modelo lo mandaba a servicios)
    from ..flujos.locales import _SOLO_OFICINAS
    from ..conocimiento.texto import palabras
    pal = set(palabras(normalizar(ctx.mensaje or "")))
    if not ctx.estado.flujo_activo and pal & {"oficina", "oficinas", "torre"} and pal <= _SOLO_OFICINAS:
        return Decision("locales", {}, False, ctx.mensaje, "pide el listado de oficinas", "regla")

    # 2c-3. «¿Cuáles hay en el quinto piso?»: los pisos solo existen en la Torre
    piso = piso_en_texto(ctx.mensaje)
    if piso and not ctx.estado.flujo_activo and \
            re.search(r"\b(que|cuales|quienes|hay|oficinas?|consultorios?|lista|listado)\b", normalizar(ctx.mensaje)):
        return Decision("torre_medica", {"piso": piso}, False, ctx.mensaje, f"pregunta por el piso {piso}", "regla")

    # 2c-4. Áreas del centro comercial: «quiero hablar con la gerente», «número de mercadeo», «queja a la gerencia»
    if not ctx.estado.flujo_activo:
        from ..conocimiento.areas import area_para
        a = area_para(ctx.mensaje)
        n = normalizar(ctx.mensaje)
        if a and not a.get("area", "").startswith(("Parqueadero", "Punto de Información")):
            if re.search(r"\b(queja|quejas|reclamo|reclamos|inconformidad|mal servicio|pesimo)\b", n):
                return Decision("emergencia_queja", {"tipo": "queja"}, False, ctx.mensaje, f"queja para {a['area']}", "regla")
            return Decision("administracion", {}, False, ctx.mensaje, f"pide el área {a['area']}", "regla")

    # 2d. El mensaje es solo el nombre de un local ("FDS", "Enjoy"): ficha de ese local, sin adivinar
    loc = None if ctx.estado.flujo_activo else local_por_nombre_exacto(ctx)   # con un pedido a medias decide la IA
    if loc:
        return Decision("torre_medica" if loc.es_torre else "locales", {"local": loc.nombre}, False, ctx.mensaje,
                        f"el mensaje es el nombre del local «{loc.nombre}»", "regla")

    # 3. Router IA
    try:
        return await _router_ia(ctx)
    except ErrorLLM as e:
        ctx.traza.alerta(f"router IA falló: {e}")
        return Decision(RESPALDO, {}, False, ctx.mensaje, "respaldo: el router IA falló", "respaldo")


def _historial_corto(ctx: Contexto, n: int = 6) -> str:
    if not ctx.historial:
        return "(sin historial: es el primer mensaje de la sesión)"
    lineas = []
    for t in ctx.historial[-n:]:
        quien = "Cliente" if t.rol == "user" else "Any"
        # la novedad del día ("De paso: …") no es el tema de la conversación: no se le muestra al router
        texto = " ".join(l for l in t.texto.split("\n") if "de paso" not in l.lower())
        lineas.append(f"{quien}: {texto[:300]}")
    return "\n".join(lineas)


async def _router_ia(ctx: Contexto) -> Decision:
    sistema = leer_prompt("router.md").format(flujos=catalogo_para_router())
    previo = ctx.estado.ultimo_flujo or "ninguno"
    recordado = ctx.estado.ultimas_entidades or {}
    activo = ""
    if ctx.estado.flujo_activo == "domicilios":
        activo = (f"Hay un PEDIDO A DOMICILIO a medias con {ctx.estado.datos.get('local', 'un local')}: si el mensaje "
                  f"trae datos del pedido (nombre, celular, dirección, qué pedir, forma de pago) o habla del pedido, "
                  f"el especialista es domicilios.\n")
    usuario = (f"HISTORIAL:\n{_historial_corto(ctx)}\n\n{activo}"
               f"Especialista del turno anterior: {previo}\n"
               f"Entidades del turno anterior: {recordado}\n\n"
               f"MENSAJE: {ctx.mensaje}")
    r = await completar(cfg().llm_router, [{"role": "system", "content": sistema},
                                          {"role": "user", "content": usuario}],
                        json_salida=True, temperatura=0, max_tokens=400, razonamiento="low")
    ctx.traza.llm("router", r)
    j = r.json()
    flujo = str(j.get("flujo") or "").strip().lower()
    if flujo not in nombres_validos():
        ctx.traza.alerta(f"router devolvió un flujo desconocido: {flujo!r}")
        flujo = RESPALDO
    ent = j.get("entidades") or {}
    ent = {k: v for k, v in ent.items() if k in CLAVES_ENTIDADES and v not in (None, "", [], {})} \
        if isinstance(ent, dict) else {}
    nombrados = [f for f, frases in TEMA_NOMBRADO.items() if alguna_frase(frases, ctx.mensaje)]
    if len(nombrados) == 1 and nombrados[0] != flujo and flujo in TEMA_NOMBRADO:
        ctx.traza.alerta(f"el router dejó {flujo} pero el cliente nombró {nombrados[0]}: gana el tema nombrado")
        flujo = nombrados[0]
    return Decision(flujo, ent, bool(j.get("es_seguimiento")),
                    str(j.get("consulta_reescrita") or ctx.mensaje)[:500], str(j.get("razon") or "")[:300], "ia")