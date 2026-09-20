"""
scripts/test_final.py

PRUEBA FINAL COMPLETA — verifica TODO el sistema con los datos reales ya
cargados (los 47 locales, cartas, eventos, sorteos, etc.).

Cubre todos los ángulos:
  - Búsqueda por categoría (ropa, zapatos, bolsos, comida, belleza...)
  - Locales específicos (info, horario, teléfono, carta)
  - Eventos / sorteos / promociones (con rotación)
  - Cine, ubicación, base de conocimiento, torre médica
  - Emergencias, quejas, piloteo (fuera de tema)
  - Casos borde y coherencia

Marca automáticamente: respuestas vacías, IDs visibles, marcas internas,
etiquetas <think>, y verifica fotos/ubicación donde se esperan.

Cómo correrlo (Railway → backend → Console):
    python scripts/test_final.py
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


def probar(categoria, mensaje, telefono, espera_foto=False, espera_ubicacion=False,
           no_foto=False, no_ubicacion=False, no_debe=None, pausa=0.4):
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
            problemas.append("ID VISIBLE")
        if "<think" in bot.lower():
            problemas.append("<think> VISIBLE")
    if espera_foto and not imgs:
        problemas.append("❗ FALTA FOTO")
    if espera_ubicacion and not loc:
        problemas.append("❗ FALTA UBICACIÓN")
    if no_foto and imgs:
        problemas.append("❗ FOTO DE RELLENO (no debía)")
    if no_ubicacion and loc:
        problemas.append("❗ UBICACIÓN DE RELLENO (no debía)")
    if no_debe:
        for txt in no_debe:
            if txt.lower() in bot.lower():
                problemas.append(f"NO DEBÍA DECIR: '{txt}'")

    RESULTADOS.append({"cat": categoria, "msg": mensaje, "bot": bot,
                       "prob": problemas, "imgs": len(imgs), "loc": bool(loc)})
    estado = "❌" if problemas else "✅"
    print(f"\n{estado} [{categoria}] {mensaje}")
    print(f"   → {bot[:150]}{'...' if len(bot) > 150 else ''}")
    print(f"   📷{len(imgs)} 📍{'sí' if loc else 'no'}")
    for p in problemas:
        print(f"   ⚠️  {p}")
    time.sleep(pausa)


def seccion(t):
    print("\n" + "═" * 68)
    print(f"  {t}")
    print("═" * 68)


# ══════════════════════════════════════════════════════════════════
# 1. BÚSQUEDA POR CATEGORÍA (los datos nuevos que cargaste)
# ══════════════════════════════════════════════════════════════════
seccion("1. BÚSQUEDA POR CATEGORÍA")
t = PREFIX + "cat"; limpiar(t)
probar("Bolsos", "¿Dónde venden bolsos?", t)
probar("Zapatos mujer", "Busco zapatos de mujer", t)
probar("Maquillaje", "¿Dónde hay maquillaje?", t)
probar("Ropa", "Quiero comprar ropa", t)
probar("Zapatos", "Busco zapatos", t)
probar("Comida", "¿Dónde comer hamburguesas?", t)
probar("Muebles", "¿Venden muebles?", t)
probar("Tenis deportivos", "¿Dónde venden tenis Nike?", t)

# ══════════════════════════════════════════════════════════════════
# 2. LOCALES ESPECÍFICOS (info, horario, teléfono, carta)
# ══════════════════════════════════════════════════════════════════
seccion("2. LOCALES ESPECÍFICOS")
t = PREFIX + "loc"; limpiar(t)
probar("Info local", "Cuéntame de Mercagán Parrilla", t)
probar("Horario", "¿A qué hora abre Mercagán?", t)
probar("Teléfono", "Dame el número de Offcorss", t)
probar("Carta", "¿Tienen carta de Mercagán?", t)
probar("Ubicación local", "¿Dónde queda Cromantic?", t)

# ══════════════════════════════════════════════════════════════════
# 3. EVENTOS / SORTEOS / PROMOCIONES (rotación)
# ══════════════════════════════════════════════════════════════════
seccion("3. EVENTOS / SORTEOS / PROMOCIONES")
t = PREFIX + "esp"; limpiar(t)
probar("Eventos", "¿Qué eventos hay?", t)
probar("Sorteos", "¿Qué están sorteando?", t)
probar("Promociones", "¿Hay promociones?", t)

# ══════════════════════════════════════════════════════════════════
# 4. CINE / UBICACIÓN / KB / TORRE MÉDICA
# ══════════════════════════════════════════════════════════════════
seccion("4. CINE / UBICACIÓN / CONOCIMIENTO / TORRE MÉDICA")
t = PREFIX + "srv"; limpiar(t)
probar("Cine", "¿Qué películas hay?", t)
probar("Ubicación mall", "¿Dónde queda el centro comercial?", t, espera_ubicacion=True)
probar("Baños", "¿Dónde están los baños?", t, no_ubicacion=True)
probar("Parqueadero", "¿Tienen parqueadero?", t)
probar("Factura", "¿Cómo registro mi factura?", t)
probar("Mascotas (sinónimo)", "¿Puedo llevar mi perro?", t)
probar("Wifi (sinónimo)", "¿Tienen internet?", t)
probar("Radiografía", "¿Dónde saco una radiografía?", t, no_foto=True, no_ubicacion=True)
probar("Zona comidas", "¿Dónde está la zona de comidas?", t)

# ══════════════════════════════════════════════════════════════════
# 5. EMERGENCIAS / QUEJAS / PILOTEO
# ══════════════════════════════════════════════════════════════════
seccion("5. EMERGENCIAS / QUEJAS / PILOTEO")
t = PREFIX + "emg"; limpiar(t)
probar("Niño perdido", "Se perdió mi hijo", t, no_foto=True)
probar("Robo", "Me acaban de robar", t, no_foto=True)
probar("Queja", "Un empleado me trató muy mal", t, no_foto=True, no_debe=["• *"])
probar("Fuera de tema", "¿Cuál es la capital de Francia?", t, no_debe=["París", "Paris"])
probar("Hora", "¿Qué hora es?", t)
probar("Social", "¿Cómo estás?", t)
probar("Gracias", "Muchas gracias 😊", t)

# ══════════════════════════════════════════════════════════════════
# 6. CASOS BORDE
# ══════════════════════════════════════════════════════════════════
seccion("6. CASOS BORDE")
t = PREFIX + "bor"; limpiar(t)
probar("Emoji", "🍔", t)
probar("Ambiguo", "eso", t)
probar("Grosería", "esta porquería no sirve", t)
probar("Con errores", "dnd kda la tienda d zapatos", t)
probar("Familia+niños", "busco comer con mi familia y llevo 2 niños", t, no_debe=["ropa infantil"])

# ══════════════════════════════════════════════════════════════════
# 7. COHERENCIA (seguidas, mismo teléfono)
# ══════════════════════════════════════════════════════════════════
seccion("7. COHERENCIA / MEMORIA")
t = PREFIX + "coh"; limpiar(t)
probar("Pregunta 1", "¿Dónde queda Mercagán?", t)
probar("Seguimiento horario", "¿y a qué hora abre?", t)
probar("Seguimiento carta", "¿tienen carta?", t)

# ══════════════════════════════════════════════════════════════════
# REPORTE FINAL
# ══════════════════════════════════════════════════════════════════
print("\n\n" + "█" * 68)
print("  REPORTE — PRUEBA FINAL COMPLETA")
print("█" * 68)
total = len(RESULTADOS)
ok = sum(1 for r in RESULTADOS if not r["prob"])
con_foto = sum(1 for r in RESULTADOS if r["imgs"] > 0)
print(f"\n  RESULTADO: {ok}/{total} sin problemas | {total - ok} para revisar")
print(f"  {con_foto} respuestas trajeron foto\n")

print("  CASOS CON PROBLEMAS:")
print("  " + "-" * 64)
hay = False
for r in RESULTADOS:
    if r["prob"]:
        hay = True
        print(f"\n  ❌ [{r['cat']}] \"{r['msg']}\"")
        for p in r["prob"]:
            print(f"       → {p}")
        print(f"       Respondió: {r['bot'][:110]}")
if not hay:
    print("  🎉 ¡NINGUNO! Todo pasó los chequeos automáticos.")

print("\n\n  MAPA DE FOTOS Y UBICACIÓN (revisa a ojo que sea correcto):")
print("  " + "-" * 64)
for r in RESULTADOS:
    m = []
    if r["imgs"]:
        m.append(f"📷x{r['imgs']}")
    if r["loc"]:
        m.append("📍")
    if m:
        print(f"  {' '.join(m):10} [{r['cat']}] {r['msg'][:42]}")

print("\n" + "█" * 68)
print("  Revisa especialmente: fotos correctas (carta, local, evento),")
print("  que emergencias NO traigan foto, y que las búsquedas listen bien.")
print("█" * 68)