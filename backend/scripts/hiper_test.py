"""
scripts/hiper_test.py

HÍPER-TEST — batería completa de tipos de conversación.

A diferencia de pruebas_completas.py (que prueba funciones puntuales),
este script está diseñado para encontrar los LÍMITES de Any: la prepara
para todos los tipos de conversación que un cliente real puede tener, y
detecta automáticamente dónde responde mal, feo o peligroso.

El objetivo NO es que todo pase — es tener un MAPA HONESTO de hasta
dónde llega bien el bot hoy, para saber qué construir después.

Cómo correrlo (Railway → backend → Console):
    python scripts/hiper_test.py

Al final imprime un REPORTE DE LÍMITES agrupado por tipo de conversación.
"""
import sys
import time
import re
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import get_settings

settings = get_settings()
BASE = settings.PUBLIC_BASE_URL
PREFIX = "htest_"

# Guardamos todo para el reporte final
RESULTADOS = []


def enviar(mensaje, telefono):
    try:
        r = requests.post(f"{BASE}/webhook/test", json={"message": mensaje, "phone": telefono}, timeout=60)
        return r.json()
    except Exception as e:
        return {"bot": None, "error": str(e)}


def limpiar(telefono):
    try:
        requests.delete(f"{BASE}/webhook/history/{telefono}", timeout=30)
    except Exception:
        pass


def revisar(tipo, mensaje, resultado, señales_malas=None, señales_buenas=None):
    """
    Registra el resultado y hace chequeos automáticos de calidad.
    señales_malas: lista de textos que, si aparecen, indican problema.
    señales_buenas: lista de textos que DEBERÍAN aparecer.
    """
    bot = (resultado.get("bot") or "").strip()
    error = resultado.get("error")
    imgs = resultado.get("image_urls", [])

    problemas = []

    # Chequeos automáticos universales
    if error:
        problemas.append(f"ERROR TÉCNICO: {error}")
    if not bot and not error:
        problemas.append("RESPUESTA VACÍA (el cliente no recibiría nada)")
    if bot:
        # Marcas internas filtradas
        for marca in ("[TIENDA:", "[EVENTO:", "[SORTEO:", "[MARKETING:"):
            if marca in bot:
                problemas.append(f"MARCA INTERNA VISIBLE: {marca}")
        if re.search(r'\(?\bID:?\s*\d+\)?', bot):
            problemas.append("ID INTERNO VISIBLE en el texto")
        # Etiquetas de razonamiento filtradas
        if "<think" in bot.lower() or "</think" in bot.lower():
            problemas.append("ETIQUETA <think> VISIBLE")
        # Respuesta cortada (termina abruptamente sin puntuación)
        if len(bot) > 40 and bot[-1] not in ".!?)😊👋🎉📍🎬🍔🛍️":
            problemas.append("POSIBLE CORTE (termina sin puntuación final)")
        # Demasiado larga para WhatsApp
        if len(bot) > 1200:
            problemas.append(f"MUY LARGA ({len(bot)} caracteres)")

    # Chequeos específicos de esta prueba
    if señales_malas:
        for s in señales_malas:
            if s.lower() in bot.lower():
                problemas.append(f"CONTIENE algo que NO debería: '{s}'")
    if señales_buenas:
        falta = [s for s in señales_buenas if s.lower() not in bot.lower()]
        if falta:
            problemas.append(f"FALTA algo que debería tener: {falta}")

    RESULTADOS.append({
        "tipo": tipo, "mensaje": mensaje, "bot": bot,
        "problemas": problemas, "imgs": len(imgs),
    })

    estado = "❌" if problemas else "✅"
    print(f"\n{estado} [{tipo}] Cliente: {mensaje}")
    print(f"   Bot: {bot[:150]}{'...' if len(bot) > 150 else ''}")
    if imgs:
        print(f"   📷 {len(imgs)} foto(s)")
    for p in problemas:
        print(f"   ⚠️  {p}")


def seccion(titulo):
    print("\n" + "═" * 70)
    print(f"  {titulo}")
    print("═" * 70)


# ══════════════════════════════════════════════════════════════════
# NIVEL 1 — CONVERSACIONES TRANSACCIONALES (información concreta)
# ══════════════════════════════════════════════════════════════════
seccion("NIVEL 1 — TRANSACCIONALES (buscar datos concretos)")

t = PREFIX + "n1"
limpiar(t)
casos_n1 = [
    ("Buscar local puntual", "¿Dónde queda Zirus Pizza?"),
    ("Número de tienda", "Me pasas el número de Zirus Pizza"),
    ("Horario del mall", "¿Cuál es el horario del centro comercial?"),
    ("Ubicación del mall", "¿Dónde queda el centro comercial?"),
    ("Parqueadero", "¿Tienen parqueadero?"),
    ("Categoría (todos)", "¿Dónde puedo comer hamburguesas?"),
    ("Categoría zapatos", "¿Dónde venden zapatos?"),
    ("Baños", "¿Dónde están los baños?"),
    ("Cajero", "¿Hay cajeros automáticos?"),
    ("WiFi", "¿Tienen wifi?"),
]
for tipo, msg in casos_n1:
    revisar(tipo, msg, enviar(msg, t))
    time.sleep(0.5)

# ══════════════════════════════════════════════════════════════════
# NIVEL 2 — CONVERSACIONES DE ASESORÍA (no sabe qué quiere)
# ══════════════════════════════════════════════════════════════════
seccion("NIVEL 2 — ASESORÍA (el cliente necesita ser guiado)")

t = PREFIX + "n2"
limpiar(t)
casos_n2 = [
    ("Búsqueda vaga", "Busco un regalo"),
    ("Búsqueda vaga 2", "Necesito algo para mi mamá"),
    ("Acotar zapatos", "Busco zapatos"),
    ("Acotar ropa", "Quiero comprar ropa"),
    ("Por ocasión", "Voy a salir a cenar esta noche, ¿alguna recomendación?"),
    ("Comparar precio", "¿Dónde es más barato comer?"),
    ("Producto específico", "¿Venden tenis Nike?"),
    ("Pedir recomendación", "¿Qué me recomiendas para almorzar?"),
]
for tipo, msg in casos_n2:
    revisar(tipo, msg, enviar(msg, t))
    time.sleep(0.5)

# ══════════════════════════════════════════════════════════════════
# NIVEL 3 — ACCIÓN, RELACIÓN Y LO INESPERADO (lo que hoy no cubre)
# ══════════════════════════════════════════════════════════════════
seccion("NIVEL 3 — QUEJAS, EMERGENCIAS, FUERA DE TEMA, SOCIAL")

t = PREFIX + "n3"
limpiar(t)
casos_n3 = [
    # Quejas — no debe responder con lista de tiendas
    ("Queja de trato", "Un empleado de una tienda me trató muy mal",
     ["¿de qué tienda quieres información", "aquí están las tiendas"], None),
    ("Queja de producto", "Compré algo y salió defectuoso, quiero reclamar", None, None),
    # Emergencias — delicado
    ("Emergencia niño", "Se perdió mi hijo aquí en el centro comercial", None, None),
    ("Emergencia salud", "Alguien se desmayó, necesito ayuda", None, None),
    ("Robo", "Me acaban de robar el celular en el mall", None, None),
    # Fuera de tema — debe redirigir con gracia
    ("Fuera de tema", "¿Cuál es la capital de Francia?", None, None),
    ("Fuera de tema 2", "¿Me prestas plata?", None, None),
    ("Fuera de tema 3", "¿Qué hora es?", None, None),
    # Social / casual
    ("Social saludo", "¿Cómo estás?", None, None),
    ("Social gracias", "Muchas gracias, muy amable 😊", None, None),
    ("Social broma", "jajaja eres un robot muy inteligente", None, None),
]
for caso in casos_n3:
    tipo, msg = caso[0], caso[1]
    malas = caso[2] if len(caso) > 2 else None
    buenas = caso[3] if len(caso) > 3 else None
    revisar(tipo, msg, enviar(msg, t), señales_malas=malas, señales_buenas=buenas)
    time.sleep(0.5)

# ══════════════════════════════════════════════════════════════════
# NIVEL 4 — CASOS BORDE (lo que rompe bots mal hechos)
# ══════════════════════════════════════════════════════════════════
seccion("NIVEL 4 — CASOS BORDE (ambiguo, vacío, largo, grosero)")

t = PREFIX + "n4"
limpiar(t)
casos_n4 = [
    ("Multi-intención", "¿Dónde puedo comer y a qué hora cierran?"),
    ("Mensaje muy corto", "hola"),
    ("Solo emoji", "🍔"),
    ("Mensaje ambiguo", "eso"),
    ("Grosería", "esta porquería no sirve para nada"),
    ("Mensaje larguísimo", "hola buenas tardes mira resulta que estoy buscando un lugar para comer algo rico con mi familia somos como 6 personas y queremos algo que no sea muy caro pero que tenga buen sabor y que tengan opciones para niños porque llevo dos pequeños y también si tienen postres mejor y que quede cerca del parqueadero"),
    ("Pregunta repetida", "¿horario?"),
    ("Escrito con errores", "dnd kda la tienda d zapatos"),
]
for tipo, msg in casos_n4:
    revisar(tipo, msg, enviar(msg, t))
    time.sleep(0.5)

# ══════════════════════════════════════════════════════════════════
# NIVEL 5 — TORRE MÉDICA (información nueva, si ya se cargó)
# ══════════════════════════════════════════════════════════════════
seccion("NIVEL 5 — TORRE MÉDICA (probar solo si ya cargaste el Excel)")

t = PREFIX + "n5"
limpiar(t)
casos_n5 = [
    ("Servicio médico", "¿Hay algún cirujano en el centro comercial?"),
    ("Servicio médico 2", "¿Dónde queda la unidad renal?"),
    ("Servicio médico 3", "¿Dónde puedo sacarme una radiografía?"),
    ("Especialista", "¿Tienen algún médico internista?"),
    ("Torre médica general", "¿Qué hay en la torre médica?"),
]
for tipo, msg in casos_n5:
    revisar(tipo, msg, enviar(msg, t))
    time.sleep(0.5)

# ══════════════════════════════════════════════════════════════════
# REPORTE FINAL DE LÍMITES
# ══════════════════════════════════════════════════════════════════
print("\n\n")
print("█" * 70)
print("  REPORTE DE LÍMITES — hasta dónde responde bien Any hoy")
print("█" * 70)

por_tipo = {}
for r in RESULTADOS:
    nivel = r["tipo"]
    if nivel not in por_tipo:
        por_tipo[nivel] = {"ok": 0, "fail": 0, "problemas": []}
    if r["problemas"]:
        por_tipo[nivel]["fail"] += 1
        por_tipo[nivel]["problemas"].extend(r["problemas"])
    else:
        por_tipo[nivel]["ok"] += 1

total_ok = sum(1 for r in RESULTADOS if not r["problemas"])
total = len(RESULTADOS)

print(f"\n  RESUMEN GLOBAL: {total_ok}/{total} respuestas sin problemas detectados")
print(f"  ({total - total_ok} con algún problema que revisar)\n")

print("  DETALLE POR CASO CON PROBLEMAS:")
print("  " + "-" * 66)
for r in RESULTADOS:
    if r["problemas"]:
        print(f"\n  ❌ [{r['tipo']}] \"{r['mensaje']}\"")
        for p in r["problemas"]:
            print(f"       → {p}")

print("\n\n  ✅ CASOS SIN PROBLEMAS DETECTADOS:")
print("  " + "-" * 66)
sin_problemas = [r for r in RESULTADOS if not r["problemas"]]
for r in sin_problemas:
    print(f"  ✅ [{r['tipo']}] \"{r['mensaje']}\"")

print("\n")
print("█" * 70)
print("  NOTA HONESTA: 'sin problemas detectados' significa que pasó los")
print("  chequeos automáticos — pero la CALIDAD real (si la respuesta es")
print("  útil, cálida, propositiva) hay que leerla a ojo arriba. Este")
print("  reporte detecta errores técnicos y de forma, no de criterio.")
print("█" * 70)