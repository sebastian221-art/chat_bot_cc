"""
scripts/test_masivo.py

PRUEBA MASIVA TOTAL — ejercita TODO lo que el bot puede responder y
enviar, desde todos los ángulos: locales con fotos, cine con póster,
eventos/sorteos/marketing con sus afiches, domicilio, ubicación,
navegación, base de conocimiento, y todos los tipos de conversación.

A diferencia del hiper_test (que mide límites de conversación), este
verifica que el CONTENIDO se mande completo: texto + fotos + ubicación,
bien diseñado, sin fugas técnicas.

IMPORTANTE: prueba cosas REALES de la base de datos. Ajusta los nombres
de abajo (TIENDA_CON_FOTO, etc.) si en tu panel se llaman distinto.

Cómo correrlo (Railway → backend → Console):
    python scripts/test_masivo.py
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

# ─── AJUSTA ESTOS NOMBRES A LO QUE TENGAS CARGADO EN EL PANEL ───────
TIENDA_CON_FOTO   = "12B Burguer"     # una tienda que tenga Portada + Galería
PELICULA_CARTELERA = "Spiderman Brand New Day"      # película activa con Póster
# (eventos, sorteos, marketing se detectan solos si tienen prioridad alta)

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


def revisar(categoria, mensaje, resultado, espera_foto=False, espera_ubicacion=False):
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
                problemas.append(f"MARCA INTERNA VISIBLE: {marca}")
        if re.search(r'\(?\bID:?\s*\d+\)?', bot):
            problemas.append("ID INTERNO VISIBLE")
        if "<think" in bot.lower():
            problemas.append("ETIQUETA <think> VISIBLE")
        if len(bot) > 1400:
            problemas.append(f"MUY LARGA ({len(bot)} car.)")

    # Verificaciones de contenido esperado
    if espera_foto and not imgs:
        problemas.append("❗ NO envió FOTO (se esperaba una)")
    if espera_ubicacion and not loc:
        problemas.append("❗ NO envió UBICACIÓN (se esperaba)")

    RESULTADOS.append({
        "categoria": categoria, "mensaje": mensaje, "bot": bot,
        "problemas": problemas, "imgs": len(imgs), "loc": bool(loc),
    })

    estado = "❌" if problemas else "✅"
    print(f"\n{estado} [{categoria}] Cliente: {mensaje}")
    print(f"   Bot: {bot[:180]}{'...' if len(bot) > 180 else ''}")
    print(f"   📷 {len(imgs)} foto(s) | 📍 {'sí' if loc else 'no'}")
    for p in problemas:
        print(f"   ⚠️  {p}")


def seccion(t):
    print("\n" + "═" * 70)
    print(f"  {t}")
    print("═" * 70)


# ══════════════════════════════════════════════════════════════════
# 1. LOCALES — con fotos (portada + galería)
# ══════════════════════════════════════════════════════════════════
seccion("1. LOCALES Y FOTOS")
t = PREFIX + "loc"
limpiar(t)
revisar("Info de tienda", f"Cuéntame de {TIENDA_CON_FOTO}", enviar(f"Cuéntame de {TIENDA_CON_FOTO}", t), espera_foto=True)
time.sleep(0.5)
revisar("Foto de portada", "¿Tienes una foto de ese local?", enviar("¿Tienes una foto de ese local?", t), espera_foto=True)
time.sleep(0.5)
revisar("Número de tienda", f"Dame el número de {TIENDA_CON_FOTO}", enviar(f"Dame el número de {TIENDA_CON_FOTO}", t))
time.sleep(0.5)

# ══════════════════════════════════════════════════════════════════
# 2. CINE — cartelera + película con póster
# ══════════════════════════════════════════════════════════════════
seccion("2. CINE")
t = PREFIX + "cine"
limpiar(t)
revisar("Cartelera completa", "¿Qué películas hay en cartelera?", enviar("¿Qué películas hay en cartelera?", t), espera_foto=True)
time.sleep(0.5)
revisar("Película puntual", f"¿A qué hora dan {PELICULA_CARTELERA}?", enviar(f"¿A qué hora dan {PELICULA_CARTELERA}?", t), espera_foto=True)
time.sleep(0.5)

# ══════════════════════════════════════════════════════════════════
# 3. EVENTOS / SORTEOS / MARKETING — con sus fotos
# ══════════════════════════════════════════════════════════════════
seccion("3. EVENTOS, SORTEOS Y MARKETING")
t = PREFIX + "mkt"
limpiar(t)
revisar("Eventos", "¿Qué eventos hay?", enviar("¿Qué eventos hay?", t))
time.sleep(0.5)
revisar("Sorteos", "¿Qué están sorteando?", enviar("¿Qué están sorteando?", t))
time.sleep(0.5)
revisar("Foto del sorteo", "¿Tienes una foto del premio del sorteo?", enviar("¿Tienes una foto del premio del sorteo?", t), espera_foto=True)
time.sleep(0.5)
revisar("Promociones", "¿Hay alguna promoción u oferta ahora?", enviar("¿Hay alguna promoción u oferta ahora?", t))
time.sleep(0.5)

# ══════════════════════════════════════════════════════════════════
# 4. DOMICILIO — flujo completo
# ══════════════════════════════════════════════════════════════════
seccion("4. DOMICILIO")
t = PREFIX + "dom"
limpiar(t)
revisar("Pedir domicilio", f"Quiero pedir a domicilio de {TIENDA_CON_FOTO}", enviar(f"Quiero pedir a domicilio de {TIENDA_CON_FOTO}", t))
time.sleep(0.5)

# ══════════════════════════════════════════════════════════════════
# 5. UBICACIÓN Y NAVEGACIÓN
# ══════════════════════════════════════════════════════════════════
seccion("5. UBICACIÓN")
t = PREFIX + "ubi"
limpiar(t)
revisar("Ubicación del mall", "¿Dónde queda el centro comercial?", enviar("¿Dónde queda el centro comercial?", t), espera_ubicacion=True)
time.sleep(0.5)

# ══════════════════════════════════════════════════════════════════
# 6. BASE DE CONOCIMIENTO
# ══════════════════════════════════════════════════════════════════
seccion("6. BASE DE CONOCIMIENTO")
t = PREFIX + "kb"
limpiar(t)
revisar("Registro de facturas", "¿Cómo registro mi factura?", enviar("¿Cómo registro mi factura?", t))
time.sleep(0.5)
revisar("Baños", "¿Dónde están los baños?", enviar("¿Dónde están los baños?", t))
time.sleep(0.5)
revisar("Parqueadero", "¿Tienen parqueadero?", enviar("¿Tienen parqueadero?", t))
time.sleep(0.5)

# ══════════════════════════════════════════════════════════════════
# 7. BÚSQUEDA POR CATEGORÍA vs ACOTAR (el punto de calidad que viste)
# ══════════════════════════════════════════════════════════════════
seccion("7. BÚSQUEDA / ACOTAR (calidad)")
t = PREFIX + "cat"
limpiar(t)
revisar("Categoría amplia (ropa)", "Quiero comprar ropa", enviar("Quiero comprar ropa", t))
time.sleep(0.5)
revisar("Categoría amplia (zapatos)", "Busco zapatos", enviar("Busco zapatos", t))
time.sleep(0.5)
revisar("Búsqueda específica", "¿Dónde comer hamburguesas?", enviar("¿Dónde comer hamburguesas?", t))
time.sleep(0.5)

# ══════════════════════════════════════════════════════════════════
# REPORTE
# ══════════════════════════════════════════════════════════════════
print("\n\n" + "█" * 70)
print("  REPORTE — PRUEBA MASIVA TOTAL")
print("█" * 70)

total = len(RESULTADOS)
ok = sum(1 for r in RESULTADOS if not r["problemas"])
con_foto = sum(1 for r in RESULTADOS if r["imgs"] > 0)

print(f"\n  {ok}/{total} sin problemas | {con_foto} respuestas trajeron foto\n")

print("  CASOS CON PROBLEMAS:")
print("  " + "-" * 66)
hay = False
for r in RESULTADOS:
    if r["problemas"]:
        hay = True
        print(f"\n  ❌ [{r['categoria']}] \"{r['mensaje']}\"")
        for p in r["problemas"]:
            print(f"       → {p}")
if not hay:
    print("  ✅ Ninguno — todo pasó los chequeos automáticos")

print("\n\n  RESUMEN DE FOTOS Y UBICACIÓN (verifica a ojo si es correcto):")
print("  " + "-" * 66)
for r in RESULTADOS:
    marca = []
    if r["imgs"] > 0:
        marca.append(f"📷x{r['imgs']}")
    if r["loc"]:
        marca.append("📍")
    if marca:
        print(f"  {' '.join(marca):12} [{r['categoria']}] {r['mensaje'][:45]}")

print("\n" + "█" * 70)
print("  NOTA: revisa a ojo el DISEÑO de las respuestas de eventos/")
print("  sorteos/marketing arriba — cómo se ve el formato de promoción.")
print("█" * 70)