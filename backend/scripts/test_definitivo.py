"""

scripts/test_definitivo.py



════════════════════════════════════════════════════════════════════

  TEST DEFINITIVO — la prueba máxima de Any

════════════════════════════════════════════════════════════════════



Prueba ABSOLUTAMENTE TODO lo que Any puede hacer, de todos los ángulos:



  NIVEL 1 — Transaccional (buscar datos concretos)

  NIVEL 2 — Contenido con FOTOS (locales, cine, sorteos, eventos, marketing)

  NIVEL 3 — Asesoría (acotar, recomendar, comparar)

  NIVEL 4 — Emergencias, quejas, piloteo (fuera de tema, social)

  NIVEL 5 — Casos borde (ambiguo, vacío, largo, grosero, con errores)

  NIVEL 6 — Torre médica / servicios de salud

  NIVEL 7 — Domicilio, ubicación, navegación, base de conocimiento

  NIVEL 8 — Coherencia en conversación (memoria de contexto)



Verifica automáticamente: respuestas vacías, marcas internas, IDs,

etiquetas <think>, cortes, fotos donde se esperan, ubicación donde se

espera, y contenido que NO debería estar (ej. hamburguesa en radiografía).



AJUSTA los nombres reales de tu panel abajo (TIENDA_CON_FOTO, etc.).



Cómo correrlo (Railway → backend → Console):

    python scripts/test_definitivo.py

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



# ─── AJUSTA A LO QUE TENGAS CARGADO EN EL PANEL ────────────────────

TIENDA_CON_FOTO    = "12B Burguer"    # tienda con Portada/Galería cargada

PELICULA_CARTELERA = "Zootopia 2"     # película activa con Póster

# ───────────────────────────────────────────────────────────────────



RESULTADOS = []





def enviar(mensaje, telefono):

    try:

        r = requests.post(f"{BASE}/webhook/test", json={"message": mensaje, "phone": telefono}, timeout=60)

        return r.json()

    except Exception as e:

        return {"bot": None, "error": str(e), "image_urls": []}





def limpiar(telefono):

    try:

        requests.delete(f"{BASE}/webhook/history/{telefono}", timeout=30)

    except Exception:

        pass





def probar(nivel, mensaje, telefono, espera_foto=False, espera_ubicacion=False,

           no_foto=False, no_ubicacion=False, no_debe_contener=None, pausa=0.5):

    """

    espera_foto / espera_ubicacion → DEBE traerlos

    no_foto / no_ubicacion → NO debe traerlos (ej. radiografía no debe traer hamburguesa)

    no_debe_contener → lista de textos que NO deben aparecer

    """

    resultado = enviar(mensaje, telefono)

    bot = (resultado.get("bot") or "").strip()

    error = resultado.get("error")

    imgs = resultado.get("image_urls") or []

    loc = resultado.get("location")



    problemas = []

    if error:

        problemas.append(f"ERROR: {error}")

    if not bot and not error:

        problemas.append("RESPUESTA VACÍA")

    if bot:

        for marca in ("[TIENDA:", "[EVENTO:", "[SORTEO:", "[MARKETING:"):

            if marca in bot:

                problemas.append(f"MARCA INTERNA: {marca}")

        if re.search(r'\(?\bID:?\s*\d+\)?', bot):

            problemas.append("ID INTERNO VISIBLE")

        if "<think" in bot.lower():

            problemas.append("ETIQUETA <think>")

        if len(bot) > 1400:

            problemas.append(f"MUY LARGA ({len(bot)} car.)")



    if espera_foto and not imgs:

        problemas.append("❗ FALTA FOTO (se esperaba)")

    if espera_ubicacion and not loc:

        problemas.append("❗ FALTA UBICACIÓN (se esperaba)")

    if no_foto and imgs:

        problemas.append("❗ FOTO DE RELLENO (no debía traer foto)")

    if no_ubicacion and loc:

        problemas.append("❗ UBICACIÓN DE RELLENO (no debía traer pin)")

    if no_debe_contener:

        for txt in no_debe_contener:

            if txt.lower() in bot.lower():

                problemas.append(f"NO DEBÍA DECIR: '{txt}'")



    RESULTADOS.append({

        "nivel": nivel, "mensaje": mensaje, "bot": bot,

        "problemas": problemas, "imgs": len(imgs), "loc": bool(loc),

    })



    estado = "❌" if problemas else "✅"

    print(f"\n{estado} [{nivel}] {mensaje}")

    print(f"   → {bot[:160]}{'...' if len(bot) > 160 else ''}")

    print(f"   📷{len(imgs)} 📍{'sí' if loc else 'no'}")

    for p in problemas:

        print(f"   ⚠️  {p}")

    time.sleep(pausa)





def seccion(t):

    print("\n" + "═" * 70)

    print(f"  {t}")

    print("═" * 70)





# ══════════════════════════════════════════════════════════════════

# NIVEL 1 — TRANSACCIONAL

# ══════════════════════════════════════════════════════════════════

seccion("NIVEL 1 — TRANSACCIONAL (datos concretos)")

t = PREFIX + "n1"; limpiar(t)

probar("Saludo", "Hola", t)

probar("Horario mall", "¿Cuál es el horario del centro comercial?", t)

probar("Ubicación mall", "¿Dónde queda el centro comercial?", t, espera_ubicacion=True)

probar("Parqueadero", "¿Tienen parqueadero?", t)

probar("Número tienda", f"Dame el número de {TIENDA_CON_FOTO}", t)



# ══════════════════════════════════════════════════════════════════

# NIVEL 2 — CONTENIDO CON FOTOS

# ══════════════════════════════════════════════════════════════════

seccion("NIVEL 2 — CONTENIDO CON FOTOS")

t = PREFIX + "n2"; limpiar(t)

probar("Ficha tienda", f"Cuéntame de {TIENDA_CON_FOTO}", t, espera_foto=True)

probar("Foto portada", "¿Tienes una foto de ese local?", t, espera_foto=True)

probar("Carta del local", f"¿Tienes la carta de {TIENDA_CON_FOTO}?", t)

t = PREFIX + "n2b"; limpiar(t)

probar("Cartelera cine", "¿Qué películas hay en cartelera?", t, espera_foto=True)

probar("Película puntual", f"¿A qué hora dan {PELICULA_CARTELERA}?", t, espera_foto=True)

t = PREFIX + "n2c"; limpiar(t)

probar("Sorteos", "¿Qué están sorteando?", t)

probar("Foto sorteo", "¿Tienes foto del premio?", t, espera_foto=True)

probar("Eventos", "¿Qué eventos hay?", t)

probar("Promociones", "¿Hay promociones ahora?", t)



# ══════════════════════════════════════════════════════════════════

# NIVEL 3 — ASESORÍA (acotar / recomendar)

# ══════════════════════════════════════════════════════════════════

seccion("NIVEL 3 — ASESORÍA")

t = PREFIX + "n3"; limpiar(t)

probar("Acotar zapatos", "Busco zapatos", t, no_debe_contener=["• *"])  # no debe soltar lista larga

probar("Acotar ropa", "Quiero comprar ropa", t, no_debe_contener=["• *"])

probar("Categoría específica", "¿Dónde comer hamburguesas?", t)

probar("Recomendación", "¿Qué me recomiendas para almorzar?", t)

probar("Búsqueda vaga", "Busco un regalo", t)



# ══════════════════════════════════════════════════════════════════

# NIVEL 4 — EMERGENCIAS, QUEJAS, PILOTEO

# ══════════════════════════════════════════════════════════════════

seccion("NIVEL 4 — EMERGENCIAS, QUEJAS, PILOTEO")

t = PREFIX + "n4"; limpiar(t)

probar("Emergencia niño", "Se perdió mi hijo", t, no_foto=True)

probar("Emergencia robo", "Me acaban de robar el celular", t, no_foto=True)

probar("Queja", "Un empleado me trató muy mal", t, no_foto=True,

       no_debe_contener=["• *"])

probar("Fuera de tema", "¿Cuál es la capital de Francia?", t,

       no_debe_contener=["París", "Paris"])

probar("Hora actual", "¿Qué hora es?", t, no_debe_contener=["son las"])

probar("Social", "¿Cómo estás?", t)

probar("Agradecimiento", "Muchas gracias 😊", t)



# ══════════════════════════════════════════════════════════════════

# NIVEL 5 — CASOS BORDE

# ══════════════════════════════════════════════════════════════════

seccion("NIVEL 5 — CASOS BORDE")

t = PREFIX + "n5"; limpiar(t)

probar("Solo emoji", "🍔", t)

probar("Mensaje ambiguo", "eso", t)

probar("Grosería", "esta porquería no sirve", t)

probar("Errores escritura", "dnd kda la tienda d zapatos", t)

probar("Multi-intención", "¿Dónde comer y a qué hora cierran?", t)

probar("Mensaje larguísimo", "hola buenas quiero comer con mi familia de 6 personas algo economico con opciones para los niños que llevo dos pequeños y postres cerca del parqueadero", t,

       no_debe_contener=["ropa infantil"])



# ══════════════════════════════════════════════════════════════════

# NIVEL 6 — TORRE MÉDICA (sin foto/pin de relleno)

# ══════════════════════════════════════════════════════════════════

seccion("NIVEL 6 — TORRE MÉDICA")

t = PREFIX + "n6"; limpiar(t)

# Primero menciona una tienda, para verificar que NO pegue su foto después

probar("(contexto) hamburguesas", "¿Dónde comer hamburguesas?", t)

probar("Radiografía", "¿Dónde puedo sacar mi radiografía?", t, no_foto=True, no_ubicacion=True)

probar("Radiografía otra vez", "¿Dónde puedo sacar mi radiografía?", t, no_foto=True, no_ubicacion=True)

probar("Especialista", "¿Hay algún cardiólogo?", t, no_foto=True)



# ══════════════════════════════════════════════════════════════════

# NIVEL 7 — DOMICILIO, NAVEGACIÓN, BASE DE CONOCIMIENTO

# ══════════════════════════════════════════════════════════════════

seccion("NIVEL 7 — DOMICILIO Y BASE DE CONOCIMIENTO")

t = PREFIX + "n7"; limpiar(t)

probar("Domicilio", f"Quiero pedir a domicilio de {TIENDA_CON_FOTO}", t)

probar("Registro factura", "¿Cómo registro mi factura?", t)

probar("Baños", "¿Dónde están los baños?", t)



# ══════════════════════════════════════════════════════════════════

# NIVEL 8 — COHERENCIA EN CONVERSACIÓN (memoria de contexto)

# ══════════════════════════════════════════════════════════════════

seccion("NIVEL 8 — COHERENCIA / MEMORIA DE CONTEXTO")

t = PREFIX + "n8"; limpiar(t)

probar("Pregunta 1", f"¿Dónde queda {TIENDA_CON_FOTO}?", t)

probar("Seguimiento (¿y el horario?)", "¿y a qué hora abre?", t)  # debe entender que sigue siendo de esa tienda

probar("Seguimiento (¿tienen carta?)", "¿tienen carta?", t)



# ══════════════════════════════════════════════════════════════════

# REPORTE FINAL

# ══════════════════════════════════════════════════════════════════

print("\n\n" + "█" * 70)

print("  REPORTE — TEST DEFINITIVO")

print("█" * 70)



total = len(RESULTADOS)

ok = sum(1 for r in RESULTADOS if not r["problemas"])

con_foto = sum(1 for r in RESULTADOS if r["imgs"] > 0)



print(f"\n  RESULTADO: {ok}/{total} sin problemas | {total - ok} con algo que revisar")

print(f"  {con_foto} respuestas trajeron foto\n")



# Agrupar problemas por nivel

por_nivel = {}

for r in RESULTADOS:

    n = r["nivel"]

    por_nivel.setdefault(n, {"ok": 0, "fail": 0})

    if r["problemas"]:

        por_nivel[n]["fail"] += 1

    else:

        por_nivel[n]["ok"] += 1



print("  CASOS CON PROBLEMAS:")

print("  " + "-" * 66)

hay = False

for r in RESULTADOS:

    if r["problemas"]:

        hay = True

        print(f"\n  ❌ [{r['nivel']}] \"{r['mensaje']}\"")

        for p in r["problemas"]:

            print(f"       → {p}")

        print(f"       Respondió: {r['bot'][:120]}")

if not hay:

    print("  🎉 ¡NINGUNO! Todo pasó los chequeos automáticos.")



print("\n\n  MAPA DE FOTOS Y UBICACIÓN (revisa a ojo que sea correcto):")

print("  " + "-" * 66)

for r in RESULTADOS:

    m = []

    if r["imgs"]:

        m.append(f"📷x{r['imgs']}")

    if r["loc"]:

        m.append("📍")

    if m:

        print(f"  {' '.join(m):10} [{r['nivel']}] {r['mensaje'][:42]}")



print("\n" + "█" * 70)

print("  NOTA: los ❗ FOTO/UBICACIÓN DE RELLENO son los más importantes —")

print("  significan que mandó algo que no venía al caso. Revisa esos primero.")

print("█" * 70)