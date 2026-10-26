"""
Pruebas por secciones de Any 2.0 (sin clave de IA y sin WhatsApp).
Cada sección se prueba sola: texto, búsqueda, adaptadores de modelos,
router, guardias, privacidad, entrada de Meta y el recorrido completo.

Uso (desde backend/, con DATABASE_URL apuntando a una copia de la base):
    python -m any.evals.pruebas            # todas
    python -m any.evals.pruebas guardias   # solo las que contienen "guardias" en el nombre
También funcionan con pytest si está instalado.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import traceback

os.environ.setdefault("ANY_LLM_ROUTER", "simulado:x")
os.environ.setdefault("ANY_LLM_FLUJOS", "simulado:x")
os.environ.setdefault("ANY_LLM_VISION", "simulado:x")


def _db():
    from models.database import SessionLocal
    import models.store, models.store_photo, models.cine_funcion, models.marketing  # noqa: F401,E401
    return SessionLocal()


def _correr(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ── Texto ─────────────────────────────────────────────────────────

def test_ajustes_prueba_jefe():
    """Lo que falló en la prueba del 26/10: cancélalo, De paso repetido, salón, nombre solo, Benítez."""
    from any.flujos.domicilios import _quiere_cancelar
    assert _quiere_cancelar("cancelalo") and _quiere_cancelar("Cancélalo por favor") and _quiere_cancelar("anúlalo")
    assert _quiere_cancelar("cancelar") and not _quiere_cancelar("no lo canceles") and not _quiere_cancelar("una pizza")
    from any.nucleo import promociones
    class _C:  # contexto mínimo para asegurar()
        telefono, ahora = "prueba-promo", __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        db = _db()
    texto, agregada = promociones.asegurar(_C, {"entity_type": "marketing", "entity_id": 0,
                                                "datos": {"tipo": "promocion", "nombre": "20% OFF"}},
                                           "Precios...\n\nDe paso: aprovecha el 20 % OFF hasta el 31/10")
    assert not agregada and texto.count("De paso") == 1
    from any.nucleo.router import regla_salon_eventos
    assert regla_salon_eventos("quiero alquilar un salón para una graduación")
    assert regla_salon_eventos("Quiero hacer una capacitacion en el centro comercial")
    assert regla_salon_eventos("cuanto vale el auditorio")
    assert not regla_salon_eventos("qué eventos hay") and not regla_salon_eventos("quiero hacer un pedido")
    from any.conocimiento.buscador import encontrar_local
    from any.conocimiento.catalogo import locales
    db = _db()
    nombres = {l.nombre for l in locales(db)}
    if "Benítez y Bravo Abogados" in nombres:
        assert encontrar_local(db, "Benítez abogados").nombre == "Benítez y Bravo Abogados"


def test_fijo_no_tiene_whatsapp():
    from any.conocimiento.texto import link_whatsapp, telefono_fijo
    assert link_whatsapp("315 694 5386") == "https://wa.me/573156945386"
    assert link_whatsapp("7244097") is None and telefono_fijo("7244097") == "(607) 724 4097"
    assert link_whatsapp("6077245818") is None and telefono_fijo("6077245818") == "(607) 724 5818"
    assert telefono_fijo("018000971903") == "01 8000 971 903"
    assert link_whatsapp("31051117207") is None and telefono_fijo("31051117207") is None   # celular mal escrito
    assert telefono_fijo("3156945386") is None


def test_texto_palabra_completa():
    from any.conocimiento.texto import contiene_frase, raiz
    assert not contiene_frase("comer", "centro comercial")          # grieta del sistema viejo
    assert not contiene_frase("niño", "Americanino")
    assert not contiene_frase("bar", "barbería")
    assert contiene_frase("zapatos", "venta de zapato deportivo")
    assert raiz("niñas") == raiz("niño") and raiz("bebés") == raiz("bebé") and raiz("tenis") == "tenis"


def test_texto_link_whatsapp():
    from any.conocimiento.texto import link_whatsapp
    assert link_whatsapp("321 918 1497") == "https://wa.me/573219181497"
    assert link_whatsapp("+57 321-918-1497") == "https://wa.me/573219181497"
    assert link_whatsapp("Teléfono:") is None and link_whatsapp("") is None


# ── Catálogo y búsqueda ───────────────────────────────────────────

def test_catalogo_sin_basura():
    from any.conocimiento.catalogo import invalidar, locales
    invalidar()
    db = _db()
    nombres = [l.nombre for l in locales(db)]
    assert nombres, "la base de prueba no tiene locales"
    assert not any(n.strip().lower().startswith("teléfono") for n in nombres)
    torre = [l for l in locales(db) if l.es_torre]
    assert all(l.piso is None or l.piso.lower().startswith("piso") for l in torre)
    assert all(not l.zona.lower().startswith(("nivel", "piso")) for l in locales(db))


def test_busqueda_locales():
    from any.conocimiento.buscador import buscar_locales
    db = _db()
    r = buscar_locales(db, "Me regalas el número de Jarris")
    assert r and r[0].local.nombre == "Jarris" and r[0].nombre_exacto
    tenis = [x.local.nombre for x in buscar_locales(db, "tenis para correr")[:5]]
    assert "people plays" in tenis and "D'ITALY tennis" in tenis
    comer = [x.local.nombre for x in buscar_locales(db, "quiero comer")]
    assert "Administración" not in comer                           # "comer" ≠ "comercial"
    assert all(not x.local.es_torre for x in buscar_locales(db, "pediatra"))


def test_busqueda_conocimiento():
    from any.conocimiento.buscador import buscar_conocimiento
    db = _db()
    assert buscar_conocimiento(db, "dónde hay baños")[0].titulo == "Baños"
    assert buscar_conocimiento(db, "puedo entrar con mi perro")[0].titulo == "Mascotas"
    assert buscar_conocimiento(db, "hay wifi")[0].titulo == "WiFi"
    assert buscar_conocimiento(db, "xyzzy qwerty") == []


# ── Adaptadores de modelos (con un servidor falso) ────────────────

def _falso_httpx(modulo, respuesta: dict, capturado: dict):
    import httpx

    def manejar(request):
        capturado["url"] = str(request.url)
        capturado["cuerpo"] = json.loads(request.content)
        capturado["cabeceras"] = dict(request.headers)
        return httpx.Response(200, json=respuesta)

    original = httpx.AsyncClient

    class Cliente(original):
        def __init__(self, *a, **k):
            k["transport"] = httpx.MockTransport(manejar)
            super().__init__(*a, **k)
    modulo.httpx.AsyncClient = Cliente
    return lambda: setattr(modulo.httpx, "AsyncClient", original)


def test_llm_openai_compat_herramientas():
    from any.llm import openai_compat as oc
    from any.llm.base import Herramienta
    os.environ["GROQ_API_KEY"] = "clave-falsa"
    cap = {}
    restaurar = _falso_httpx(oc, {"choices": [{"message": {"content": None, "tool_calls": [
        {"id": "c1", "type": "function", "function": {"name": "buscar", "arguments": "{\"q\": \"tenis\"}"}}]}}],
        "usage": {"prompt_tokens": 50, "completion_tokens": 7}}, cap)
    try:
        h = Herramienta("buscar", "busca", {"type": "object", "properties": {"q": {"type": "string"}}}, lambda q: q)
        r = _correr(oc.ClienteOpenAICompat("groq", "openai/gpt-oss-120b").completar(
            [{"role": "user", "content": "hola"}], [h], razonamiento="low"))
    finally:
        restaurar()
        os.environ["GROQ_API_KEY"] = ""
    assert cap["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert cap["cuerpo"]["tools"][0]["function"]["name"] == "buscar"
    assert cap["cuerpo"]["reasoning_effort"] == "low"
    assert cap["cabeceras"]["authorization"] == "Bearer clave-falsa"
    assert r.llamadas[0].argumentos == {"q": "tenis"} and r.tokens_entrada == 50


def test_llm_openai_gpt5_sin_temperatura():
    from any.llm.openai_compat import ClienteOpenAICompat
    os.environ["OPENAI_API_KEY"] = "x"
    c = ClienteOpenAICompat("openai", "gpt-5-mini")
    cuerpo = c._cuerpo([{"role": "user", "content": "hola"}], None, True, 0.3, 500, None)
    os.environ["OPENAI_API_KEY"] = ""
    assert "temperature" not in cuerpo and cuerpo["max_completion_tokens"] == 500
    assert cuerpo["response_format"] == {"type": "json_object"}


def test_llm_anthropic_traduccion():
    from any.llm import anthropic as an
    sistema, msgs = an._traducir([
        {"role": "system", "content": "eres Any"},
        {"role": "user", "content": "tenis"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "t1", "type": "function", "function": {"name": "buscar", "arguments": "{\"q\":\"tenis\"}"}}]},
        {"role": "tool", "tool_call_id": "t1", "content": "{\"locales\": []}"},
    ])
    assert sistema == "eres Any"
    assert msgs[1]["content"][0]["type"] == "tool_use" and msgs[1]["content"][0]["input"] == {"q": "tenis"}
    assert msgs[2]["role"] == "user" and msgs[2]["content"][0]["type"] == "tool_result"


def test_llm_json_tolerante():
    from any.llm.base import LLMRespuesta
    assert LLMRespuesta(texto='```json\n{"flujo": "cine"}\n```').json() == {"flujo": "cine"}
    assert LLMRespuesta(texto='Claro: {"flujo": "locales"} listo').json() == {"flujo": "locales"}


def test_llm_respaldo():
    from any.llm import registro
    os.environ["ANY_LLM_RESPALDO"] = "simulado:respaldo"
    os.environ["GROQ_API_KEY"] = ""
    try:
        r = _correr(registro.completar("groq:openai/gpt-oss-120b", [{"role": "user", "content": "hola"}]))
    finally:
        os.environ["ANY_LLM_RESPALDO"] = ""
    assert r.modelo == "simulado:respaldo"


# ── Router ────────────────────────────────────────────────────────

def test_router_emergencia_por_regla():
    from any.nucleo.router import regla_emergencia
    assert regla_emergencia("me robaron el celular en el baño")
    assert regla_emergencia("perdí a mi hijo")
    assert regla_emergencia("hay una persona herida")
    assert not regla_emergencia("quiero comprar un robot de juguete")
    assert not regla_emergencia("dónde venden ropa")


def test_router_tema_nombrado_gana():
    from any.llm import simulado
    from any.llm.base import LLMRespuesta
    from any.nucleo.router import decidir
    from any.nucleo.trazas import Traza

    class E:
        flujo_activo, ultimo_flujo, ultimas_entidades = None, "cine", {}

    class C:
        pass
    c = C()
    c.mensaje, c.historial, c.estado, c.traza = "Hay promociones", [], E(), Traza("x", "x", "prueba")
    c.imagen, c.db = None, _db()
    simulado.MANEJADOR = lambda m, h, j: LLMRespuesta(texto=json.dumps({"flujo": "cine", "es_seguimiento": True}),
                                                      modelo="simulado:x")
    try:
        d = _correr(decidir(c))
    finally:
        simulado.MANEJADOR = None
    assert d.flujo == "sorteos_promos"


# ── Guardias ──────────────────────────────────────────────────────

class _TrazaFalsa:
    def __init__(self, detalle=None):
        self.pasos = [{"paso": "datos_reunidos", "detalle": detalle or {}}]
        self.alertas = []

    def alerta(self, t):
        self.alertas.append(t)

    def paso(self, *a):
        pass


class _Ctx:
    def __init__(self, detalle=None):
        self.traza = _TrazaFalsa(detalle)


def test_guardias_formato():
    from any.nucleo.guardias import formato_whatsapp
    t = formato_whatsapp("## Locales\n**Jarris** está aquí\n---\n| Local | Zona |\n|---|---|\n| Jarris | Vélez |\n- uno")
    assert "#" not in t and "**" not in t and "---" not in t and "|" not in t
    assert "*Jarris*" in t and "• Jarris — Vélez" in t and "• uno" in t


def test_guardias_pisos_y_telefonos():
    from any.nucleo.guardias import revisar_salida
    from any.nucleo.tipos import Respuesta
    ctx = _Ctx({"telefono": "3219181497"})
    r = revisar_salida(ctx, Respuesta("Queda en el Piso 1, Pasillo Barichara.\nLlama al 3219181497\n"
                                      "O al 3009998877", "locales"))
    assert "Piso 1" not in r.texto and "Pasillo Barichara" in r.texto
    assert "3219181497" in r.texto and "3009998877" not in r.texto
    assert len(ctx.traza.alertas) == 2
    torre = revisar_salida(_Ctx(), Respuesta("El consultorio queda en el piso 3.", "torre_medica"))
    assert "piso 3" in torre.texto


def test_guardias_emergencia_y_vacio():
    from any.nucleo.guardias import revisar_salida
    from any.nucleo.tipos import Respuesta
    r = revisar_salida(_Ctx(), Respuesta("Tranquilo, te ayudo.", "emergencia_queja", meta={"tipo": "emergencia"}))
    assert "Barichara" in r.texto and "317 432 0138" in r.texto and "seguridad" in r.texto
    assert revisar_salida(_Ctx(), Respuesta("", "conversacion")).texto


def test_guardias_equidad():
    from any.nucleo.guardias import revisar_salida
    from any.nucleo.tipos import Respuesta
    r = revisar_salida(_Ctx(), Respuesta("• *Badelei* — Plaza Principal", "locales",
                                         meta={"lista_equidad": ["Badelei", "Popsy"],
                                               "lineas_equidad": {"Popsy": "• *Popsy* — Paseo de la Cruz"}}))
    assert "Popsy" in r.texto


def test_guardias_nombres_mal_copiados():
    from any.nucleo.guardias import revisar_salida
    from any.nucleo.tipos import Respuesta
    ctx = _Ctx({"hechos": {"eventos": [{"nombre": "Concurso de Disfraces", "lugar": "Plazoleta Guanentá"}],
                           "locales": [{"nombre": "La Poporra  Burger"}, {"nombre": "LA POPORRA DRINKS"}]}})
    r = revisar_salida(ctx, Respuesta("El concurso es en la Plazaleta Guamerá. También LA POPORRA DRINKS.", "eventos"))
    assert "Plazoleta Guanentá" in r.texto and "LA POPORRA DRINKS" in r.texto


def test_guardias_precios_inventados():
    from any.nucleo.guardias import revisar_salida
    from any.nucleo.tipos import Respuesta
    ctx = _Ctx({"hechos": {"tarifas_de_hoy": [{"general": "$18.000", "vip": "$25.000"}], "promo": "20% OFF"}})
    r = revisar_salida(ctx, Respuesta("• General: $18.000 · VIP $ 25.000\n• Combo Popcorn: $8.000\n"
                                      "• Con tarjeta: 10 % de descuento\nAfiliados: 20% OFF", "cine"))
    assert "$18.000" in r.texto and "25.000" in r.texto and "20% OFF" in r.texto
    assert "Popcorn" not in r.texto and "10 %" not in r.texto


def test_guardias_pulido_25_10():
    """Errores vistos en producción el 25/10."""
    from any.nucleo.guardias import revisar_salida
    from any.nucleo.tipos import Respuesta
    ctx = _Ctx({"hechos": {"sorteo": {"nombre": "El Latido Millonario", "premio": "$13.000.000"},
                           "lugar": {"nombre": "El Puente"}, "parqueadero": "Carro $3.000 la hora"}})
    # "el Punto de Información" no se "corrige" a "El Puente"
    r = revisar_salida(ctx, Respuesta("Regístrala en el Punto de Información (Pasillo Barichara).", "sorteos_promos"))
    assert "Punto de Información" in r.texto and "Puente de" not in r.texto
    # "$13 millones" es el mismo premio que "$13.000.000"
    r = revisar_salida(ctx, Respuesta("De paso: El Latido Millonario, premio de $13 millones.", "locales"))
    assert "13 millones" in r.texto
    r = revisar_salida(ctx, Respuesta("De paso: El Latido Millonario, premio de $13\u202f000\u202f000.", "locales"))
    assert "Latido" in r.texto
    # piso con ordinal, voseo y la marca del pasillo partida
    r = revisar_salida(ctx, Respuesta("Pagas en los módulos del 2.º piso. Recibís un número. Ve al *Pasillo Barichar*a.",
                                      "servicios_mall"))
    assert "piso" not in r.texto and "recibes" in r.texto.lower() and "Barichara*." in r.texto
    # si se quita la línea de un precio inventado, no queda la frase de entrada colgando
    r = revisar_salida(ctx, Respuesta("El parqueadero cuesta:\nMoto $9.999 la hora.\nCarro $3.000 la hora.", "servicios_mall"))
    assert "cuesta:" not in r.texto or "•" in r.texto


def test_guardias_ronda_3():
    from any.nucleo.guardias import revisar_salida
    from any.nucleo.tipos import Respuesta
    ctx = _Ctx({"hechos": {"evento": {"nombre": "La Santa Misa"}}})
    r = revisar_salida(ctx, Respuesta("*La Santa Misa* es a las 11:30 a.m.", "eventos"))
    assert r.texto.startswith("*La Santa Misa*")                         # los asteriscos no se rompen
    r = revisar_salida(ctx, Respuesta("Hay vacunación. {Lista: Piso ?, Consultorio X}\n• *FOSCAL*", "torre_medica"))
    assert "{" not in r.texto and "FOSCAL" in r.texto


def test_servicio_sin_datos_no_lo_inventa():
    from any.flujos.servicios_mall import ServiciosMall
    from any.nucleo.tipos import Decision
    from any.nucleo.trazas import Traza

    class E:
        flujo_activo, ultimo_flujo, ultimas_entidades = None, None, {}

    class C:
        pass
    c = C()
    c.mensaje, c.historial, c.estado, c.traza = "hay wifi?", [], E(), Traza("x", "x", "prueba")
    c.db = _db()
    c.decision = Decision("servicios_mall", {"servicio": "wifi"}, False, "hay wifi?")
    d = _correr(ServiciosMall().reunir(c))
    from any.conocimiento.servicios import info_mall
    if not info_mall(c.db).get("wifi") and not d.hechos.get("fragmentos_relevantes"):
        assert d.respuesta_directa and "No tengo información de el wifi" not in d.respuesta_directa
        assert "wifi" in d.respuesta_directa


def test_lista_con_marca_mal_escrita():
    from any.flujos.locales import poner_lista
    lista = "• *A*\n• *B*"
    t = poner_lista("Te paso los locales:\n{LIST}\nDe paso: algo.", lista)
    assert "{LIST" not in t and t.index("• *A*") < t.index("De paso")
    t = poner_lista("Te paso los locales.\nDe paso: algo.", lista)
    assert t.index("• *A*") < t.index("De paso")
    t = poner_lista("Aquí tienes:\n• *A* — Pasillo X\n• *B* — Pasillo Y\n\nDe paso: algo.", lista)
    assert t.count("*A*") == 1 and t.count("*B*") == 1      # el modelo escribió la lista: no sale doble


def test_promo_sin_mayusculas_sostenidas():
    from any.nucleo.promociones import suavizar
    t = suavizar("POR CADA $100.000 en marcas o $300.000 acumulados en JUMBO reciba 1 NÚMERO", ["Jumbo"])
    assert t.startswith("Por cada") and "Jumbo" in t and "número" in t


def test_torre_solo_salud_cuando_buscan_doctor():
    from any.flujos.torre_medica import busca_salud, es_de_salud

    class L:
        def __init__(self, n, d):
            self.nombre, self.descripcion, self.productos, self.rubro = n, d, [], ""
    assert busca_salud("hay un doctor cerca de Mercagan?")
    assert es_de_salud(L("FOSCAL", "Citología / Vacunación / Atención por enfermería"))
    assert not es_de_salud(L("Benitez Abogados", "Abogados | Torre Médica y Empresarial"))


def test_eventos_fin_de_semana_lo_calcula_el_codigo():
    from datetime import date
    from any.flujos.eventos import ficha_evento

    class E:
        name, time, location, description = "x", "", "", ""
    e = E(); e.date = "31/10/2026"
    assert ficha_evento(e, date(2026, 10, 20))["es_este_fin_de_semana"] is False
    e.date = "23/10/2026 al 25/10/2026"
    assert ficha_evento(e, date(2026, 10, 20))["es_este_fin_de_semana"] is True


# ── Entrada de Meta ───────────────────────────────────────────────

def test_entrada_lote_completo():
    from any.entrada import _firma_valida, extraer_mensajes
    lote = {"entry": [{"changes": [{"value": {
        "contacts": [{"wa_id": "573001", "profile": {"name": "Ana"}}],
        "messages": [{"from": "573001", "id": "a", "type": "text", "text": {"body": "hola"}},
                     {"from": "573001", "id": "b", "type": "image", "image": {"id": "m1", "caption": "así"}},
                     {"from": "573001", "id": "c", "type": "interactive",
                      "interactive": {"button_reply": {"title": "Sí"}}}]}}]}]}
    ms = extraer_mensajes(lote)
    assert [m["message_id"] for m in ms] == ["a", "b", "c"] and ms[0]["nombre"] == "Ana"
    assert ms[1]["media_id"] == "m1" and ms[2]["texto"] == "Sí"
    import hashlib, hmac  # noqa: E401
    os.environ["META_APP_SECRET"] = "s"
    firma = "sha256=" + hmac.new(b"s", b"{}", hashlib.sha256).hexdigest()
    assert _firma_valida(b"{}", firma) and not _firma_valida(b"{}", "sha256=mala")
    os.environ["META_APP_SECRET"] = ""


# ── Recorrido completo (núcleo con modelo simulado) ───────────────

def test_recorrido_privacidad_y_traza():
    from any.nucleo.guardias import borrar_datos
    from any.nucleo.harness import procesar
    db = _db()
    tel = "prueba-unidad"
    borrar_datos(db, tel)
    r1 = _correr(procesar(db, tel, "Ana", "hola"))
    assert len(r1.mensajes()) == 2 and "Ley 1581" in r1.mensajes()[0]      # aviso + respuesta
    r2 = _correr(procesar(db, tel, "Ana", "hay wifi?"))
    assert len(r2.mensajes()) == 1 and r2.flujo == "servicios_mall"         # el aviso no se repite
    assert r2.meta["traza_id"]
    r3 = _correr(procesar(db, tel, "Ana", "me robaron la billetera"))
    assert r3.flujo == "emergencia_queja" and "barichara" in r3.texto.lower()
    _correr(procesar(db, tel, "Ana", "eliminar mis datos"))
    r5 = _correr(procesar(db, tel, "Ana", "sí, eliminar"))
    assert "eliminados" in r5.texto and r5.meta["borrado"].get("conversations")
    from models.conversation import Conversation
    assert db.query(Conversation).filter(Conversation.phone_number == tel).count() == 0


def test_recorrido_pausa_humana():
    from datetime import datetime, timedelta, timezone
    from models.conversation_flag import ConversationFlag
    from any.nucleo.guardias import borrar_datos
    from any.nucleo.harness import procesar
    db = _db()
    tel = "prueba-pausa"
    borrar_datos(db, tel)
    db.merge(ConversationFlag(phone_number=tel, needs_human=True,
                              bot_paused_until=datetime.now(timezone.utc) + timedelta(minutes=30)))
    db.commit()
    r = _correr(procesar(db, tel, "Ana", "hola?"))
    assert not r.responder and not r.mensajes()
    borrar_datos(db, tel)


def test_recorrido_ubicacion_con_pin():
    from any.llm import simulado
    from any.nucleo.guardias import borrar_datos
    from any.nucleo.harness import procesar
    from any.llm.base import LLMRespuesta
    db = _db()
    tel = "prueba-pin"
    borrar_datos(db, tel)
    simulado.MANEJADOR = lambda m, h, j: LLMRespuesta(
        texto=json.dumps({"flujo": "servicios_mall", "entidades": {"servicio": "ubicación"},
                          "consulta_reescrita": "dirección del centro comercial"}) if j else "Te dejo la ubicación 📍",
        modelo="simulado:x")
    try:
        r = _correr(procesar(db, tel, "Ana", "cómo llego al centro comercial"))
    finally:
        simulado.MANEJADOR = None
    assert any(a.tipo == "ubicacion" for a in r.adjuntos)
    borrar_datos(db, tel)


def test_recorrido_modelo_caido():
    from any.nucleo.guardias import borrar_datos
    from any.nucleo.harness import procesar
    db = _db()
    tel = "prueba-caido"
    borrar_datos(db, tel)
    os.environ["ANY_LLM_ROUTER"] = os.environ["ANY_LLM_FLUJOS"] = "groq:modelo-sin-clave"
    os.environ["GROQ_API_KEY"] = ""
    try:
        r = _correr(procesar(db, tel, "Ana", "hola"))
        e = _correr(procesar(db, tel, "Ana", "hay un incendio"))
    finally:
        os.environ["ANY_LLM_ROUTER"] = os.environ["ANY_LLM_FLUJOS"] = "simulado:x"
    assert r.texto.startswith("¡Hola, Ana!")                                         # saludo de respaldo, nunca vacío
    assert "317 432 0138" in e.texto and "Barichara" in e.texto                     # emergencia sin IA
    borrar_datos(db, tel)


# ── Flujo locales ─────────────────────────────────────────────────

def test_locales_que_pide():
    from any.flujos.locales import que_pide
    assert que_pide(None, "Me regalas el número de Jarris") == "telefono"
    assert que_pide(None, "La carta de Mercagan por fa") == "carta"
    assert que_pide(None, "Tienes el instagram de Chevignon?") == "instagram"
    assert que_pide("horario", "y a qué hora?") == "horario"


def test_locales_seleccion_sin_ruido():
    from any.conocimiento.buscador import buscar_locales, seleccionar_relevantes, encontrar_local
    db = _db()
    ninos = [r.local.nombre for r in seleccionar_relevantes(buscar_locales(db, "almacen de ropa para niños"))]
    assert "Offcorss" in ninos and "Tomaticos" in ninos and "Americanino" not in ninos
    zapatos = [r.local.nombre for r in seleccionar_relevantes(buscar_locales(db, "dime todos los almacenes de zapatos"))]
    assert {"VILLA SHOES", "RIVANO", "Tennis"} <= set(zapatos)
    assert seleccionar_relevantes(buscar_locales(db, "Q supermercados hay"))[0].local.nombre == "Jumbo"
    assert encontrar_local(db, "la barra").nombre == "La Barra 1516"
    assert encontrar_local(db, "12b").nombre == "12B Burger Angus"


def test_locales_lista_la_pone_el_codigo():
    from any.llm import simulado
    from any.llm.base import LLMRespuesta
    from any.nucleo.guardias import borrar_datos
    from any.nucleo.harness import procesar

    def m(msgs, h, j):
        u = msgs[-1]["content"]
        if j and "MENSAJE:" in u:
            return LLMRespuesta(texto=json.dumps({"flujo": "locales", "entidades": {"categoria": "helado"}}),
                                modelo="simulado:x")
        if j:   # el juez intenta colar un local que no está en los candidatos: se ignora
            return LLMRespuesta(texto=json.dumps({"incluir": ["popsy", "Badelei", "Heladería Inventada"]}),
                                modelo="simulado:x")
        return LLMRespuesta(texto="¡Claro! Estos venden helado:\n{LISTA}\n¿Te paso la carta de alguno?",
                            modelo="simulado:x")
    db = _db()
    borrar_datos(db, "prueba-helado")
    simulado.MANEJADOR = m
    try:
        r = _correr(procesar(db, "prueba-helado", "Ana", "dónde venden helado"))
    finally:
        simulado.MANEJADOR = None
    t = r.texto
    assert "{LISTA}" not in t and "Inventada" not in t
    assert t.index("*Badelei*") < t.index("*popsy*")                      # orden alfabético
    assert "wa.me/57" in t and "¿Te paso la carta de alguno?" in t   # al final puede ir la novedad del día
    borrar_datos(db, "prueba-helado")


def test_pendiente_no_usa_ia():
    """Un tema sin especialista (si se agrega uno nuevo al router antes de construirlo) responde sin IA."""
    from any.llm import simulado
    from any.llm.base import LLMRespuesta
    from any.nucleo.harness import FlujoPendiente
    llamadas = []
    simulado.MANEJADOR = lambda m, h, j: (llamadas.append(j), LLMRespuesta(texto="Estilo & Corte", modelo="s"))[1]

    class C:
        pass
    c = C()
    c.decision, c.traza = None, type("T", (), {"paso": lambda *a: None, "alerta": lambda *a: None})()
    try:
        r = _correr(FlujoPendiente("tema_nuevo").ejecutar(c))
    finally:
        simulado.MANEJADOR = None
    assert llamadas == [] and "317 432 0138" in r.texto


def test_cine_tarifas_del_dia():
    from datetime import datetime
    from any.conocimiento import cine_datos as cd
    db = _db()
    if not cd.bloque(db, "tarifa"):
        return   # la base no tiene tarifas cargadas
    jueves = cd.tarifas_del_dia(db, datetime(2026, 10, 22, 18, 0))
    assert jueves and all(t["dia"] == "Jueves" for t in jueves)
    assert any(t["general"].startswith("$") for t in jueves)


def test_promo_regla_unica():
    from datetime import datetime, timedelta
    from any.config import ZONA_HORARIA
    from any.nucleo import promociones
    from any.nucleo.guardias import borrar_datos
    from any.nucleo.tipos import Turno

    class C:  # contexto mínimo
        pass
    c = C()
    c.db, c.telefono, c.sesion_nueva = _db(), "prueba-promo", True
    c.ahora = datetime(2026, 10, 21, 15, 0, tzinfo=ZONA_HORARIA)
    c.historial = [Turno("user", "hola", c.ahora - timedelta(minutes=5))]
    borrar_datos(c.db, c.telefono)
    assert promociones.elegir(c, "emergencia_queja") is None and promociones.elegir(c, "eventos") is None
    vig = promociones.vigentes(c.db, c.ahora.date())
    if not vig:
        return   # la base no tiene nada vigente
    vistas = set()
    for _ in range(len(vig)):                      # rota: cada novedad vigente sale una vez antes de repetir
        p = promociones.elegir(c, "locales")
        assert p and (p["entity_type"], p["entity_id"]) not in vistas
        vistas.add((p["entity_type"], p["entity_id"]))
        texto, agregada = promociones.asegurar(c, p, "Te paso la lista.")
        assert agregada and p["datos"]["nombre"] in texto      # si la IA no la mencionó, va igual
        c.ahora += timedelta(minutes=1)
    assert promociones.elegir(c, "locales") is not None        # se acabaron: vuelve a empezar
    borrar_datos(c.db, c.telefono)


# ── Fase 4: domicilios, QR, foto ─────────────────────────────────

def _sim_domicilio(m, h, j):
    from any.llm.base import LLMRespuesta
    u = m[-1]["content"] if isinstance(m[-1]["content"], str) else ""
    if j and "MENSAJE:" in u:
        return LLMRespuesta(texto=json.dumps({"flujo": "domicilios", "entidades": {"local": "12B Burger Angus"}}),
                            modelo="simulado:x")
    if j and "MENSAJE DEL CLIENTE" in u:
        msg = u.split("MENSAJE DEL CLIENTE:", 1)[1].lower()
        datos = {"nombre": None, "celular": None, "direccion": None, "pedido": None, "pago": None}
        if "ana" in msg:
            datos.update(nombre="Ana", direccion="Calle 10 # 5-20, barrio Centro", pedido="2 hamburguesas sencillas",
                         pago="efectivo")
        return LLMRespuesta(texto=json.dumps(datos), modelo="simulado:x")
    return LLMRespuesta(texto="Con gusto te ayudo con eso.", modelo="simulado:x")


def test_domicilio_completo_con_confirmacion():
    from any.llm import simulado
    from any.nucleo.guardias import borrar_datos
    from any.nucleo.harness import procesar
    from models.delivery_management import DeliveryManagement
    db = _db()
    tel = "573001234567"
    borrar_datos(db, tel)
    simulado.MANEJADOR = _sim_domicilio
    try:
        r1 = _correr(procesar(db, tel, "Ana", "quiero pedir un domicilio de 12b"))
        assert r1.flujo == "domicilios"
        r2 = _correr(procesar(db, tel, "Ana", "soy Ana, calle 10 # 5-20 barrio Centro, 2 hamburguesas, efectivo"))
        assert "¿Lo confirmas?" in r2.texto and "2 hamburguesas" in r2.texto and "300 123 4567" in r2.texto
        r3 = _correr(procesar(db, tel, "Ana", "sí"))
    finally:
        simulado.MANEJADOR = None
    assert "wa.me/573219181497?text=" in r3.texto
    g = db.query(DeliveryManagement).filter(DeliveryManagement.phone_number == tel).first()
    assert g and g.status == "completed" and g.payment_method == "Efectivo"
    borrar_datos(db, tel)


def test_domicilio_pago_y_celular_sin_ia():
    from any.flujos.domicilios import celular_en_texto, pago_en_texto
    assert pago_en_texto("una hamburguesa y pago por nequi") == "Transferencia"
    assert pago_en_texto("pago con Daviplata") == "Transferencia"
    assert pago_en_texto("en efectivo") == "Efectivo"
    assert pago_en_texto("contraentrega") == "Efectivo"
    assert pago_en_texto("calle 15 # 9-30") is None
    assert celular_en_texto("mi cel 300 111 2233, calle 15") == "300 111 2233"
    assert celular_en_texto("+57 3001112233") == "300 111 2233"
    assert celular_en_texto("calle 15 # 9-30") is None
    from any.flujos.domicilios import _no_es_pedido
    assert _no_es_pedido("domicilio de 12B Burger Angus", "12B Burger Angus")
    assert not _no_es_pedido("2 hamburguesas clásicas", "12B Burger Angus")


def test_router_mensaje_sin_palabras():
    from any.llm import simulado
    from any.llm.base import LLMRespuesta
    from any.nucleo.router import decidir
    from any.nucleo.trazas import Traza

    class E:
        flujo_activo, ultimo_flujo, ultimas_entidades = None, "servicios_mall", {}

    class C:
        pass
    simulado.MANEJADOR = lambda m, h, j: LLMRespuesta(texto=json.dumps({"flujo": "servicios_mall"}), modelo="simulado:x")
    try:
        for m in ["?", "...", "👍", "¿?"]:
            c = C()
            c.mensaje, c.historial, c.estado, c.traza = m, [], E(), Traza("x", "x", "prueba")
            c.imagen, c.db = None, _db()
            d = _correr(decidir(c))
            assert d.flujo == "conversacion", m
        c.mensaje = "¿y el horario?"
        assert _correr(decidir(c)).flujo == "servicios_mall"      # con palabras sí decide el router
    finally:
        simulado.MANEJADOR = None


def test_domicilio_cancelar_y_recordatorio():
    from any.llm import simulado
    from any.llm.base import LLMRespuesta
    from any.nucleo.guardias import borrar_datos
    from any.nucleo.harness import procesar
    db = _db()
    tel = "prueba-dom2"
    borrar_datos(db, tel)
    simulado.MANEJADOR = _sim_domicilio
    try:
        _correr(procesar(db, tel, "Ana", "quiero un domicilio de 12b"))
        simulado.MANEJADOR = lambda m, h, j: LLMRespuesta(
            texto=json.dumps({"flujo": "servicios_mall"}) if j else "Hay wifi gratis.", modelo="simulado:x")
        r = _correr(procesar(db, tel, "Ana", "hay wifi?"))
        assert "sigue abierto" in r.texto                                 # pregunta otra cosa: se le recuerda
        simulado.MANEJADOR = _sim_domicilio
        r = _correr(procesar(db, tel, "Ana", "cancelar"))
        assert r.flujo == "domicilios"
        r = _correr(procesar(db, tel, "Ana", "hay wifi?"))
    finally:
        simulado.MANEJADOR = None
    assert "sigue abierto" not in r.texto
    borrar_datos(db, tel)


def test_qr_estricto_y_escaneo():
    from models.zone import Zone
    from models.zone_scan import ZoneScan
    from any.flujos.navegacion_qr import codigo_qr
    from any.nucleo.guardias import borrar_datos
    from any.nucleo.harness import procesar
    db = _db()
    if not db.query(Zone).filter(Zone.code == "T9").first():
        db.add(Zone(code="T9", floor="Nivel 1", description="Pasillo Vélez, frente a la fuente"))
        db.commit()
    try:
        assert codigo_qr(db, "Estoy en Zona T9") == "T9"
        assert codigo_qr(db, "dónde queda la zona de comidas") is None      # el sistema viejo leía "DE"
        assert codigo_qr(db, "estoy por la zona t9 cerca") == "T9"          # existe en la tabla
        tel = "prueba-qr"
        borrar_datos(db, tel)
        r = _correr(procesar(db, tel, "Ana", "Estoy en Zona T9"))
        assert r.flujo == "navegacion_qr"
        assert db.query(ZoneScan).filter(ZoneScan.phone_number == tel, ZoneScan.zone_code == "T9").count() == 1
        assert "nivel" not in r.texto.lower()
        borrar_datos(db, tel)
    finally:
        db.query(Zone).filter(Zone.code == "T9").delete()
        db.commit()


def test_imagen_usa_la_busqueda_de_locales():
    from any.llm import simulado
    from any.llm.base import LLMRespuesta
    from any.nucleo.guardias import borrar_datos
    from any.nucleo.harness import procesar

    def m(msgs, h, j):
        c = msgs[-1]["content"]
        if isinstance(c, list):   # la llamada de visión trae la foto
            return LLMRespuesta(texto=json.dumps({"es_producto": True, "que_es": "tenis deportivos",
                                                  "busqueda": "tenis", "color": "blanco"}), modelo="simulado:x")
        if j:
            return LLMRespuesta(texto='{"excluir": [], "agregar": []}', modelo="simulado:x")
        return LLMRespuesta(texto="Parecen unos tenis deportivos blancos. Estos locales venden algo así:\n{LISTA}",
                            modelo="simulado:x")
    db = _db()
    borrar_datos(db, "prueba-foto")
    simulado.MANEJADOR = m
    try:
        r = _correr(procesar(db, "prueba-foto", "Ana", "", imagen=b"\xff\xd8\xff\xe0 foto falsa"))
    finally:
        simulado.MANEJADOR = None
    assert r.flujo == "imagen" and "*Tennis*" in r.texto and "{LISTA}" not in r.texto
    borrar_datos(db, "prueba-foto")


# ── Mini corredor ─────────────────────────────────────────────────

def main():
    import logging
    logging.disable(logging.WARNING)
    filtro = sys.argv[1] if len(sys.argv) > 1 else ""
    pruebas = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and filtro in n]
    ok = 0
    for n, f in pruebas:
        try:
            f()
            ok += 1
            print(f"✅ {n}")
        except Exception:
            print(f"❌ {n}")
            traceback.print_exc(limit=3)
    print(f"\n{ok}/{len(pruebas)} pruebas bien")
    sys.exit(0 if ok == len(pruebas) else 1)


if __name__ == "__main__":
    main()