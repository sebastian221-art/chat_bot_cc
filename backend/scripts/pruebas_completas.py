# 📄 ARCHIVO: backend/scripts/pruebas_completas.py
"""
Script de pruebas automáticas — corre TODOS los escenarios importantes
del bot de una sola vez y muestra un reporte claro de qué respondió,
si mandó foto (y cuál), si mandó ubicación, y cuánto tardó cada una.

CÓMO CORRERLO:
    Railway → servicio backend → pestaña "Console"
    python scripts/pruebas_completas.py

Mientras corre, abre también la pestaña "Deploy Logs" en otra ventana —
ahí vas a ver en tiempo real todo el detalle interno: qué tienda
encontró, qué consultas hizo a la base de datos, qué foto eligió y
por qué, etc. Este script te da el resumen; los Deploy Logs te dan
el detalle completo.
"""
import httpx
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import get_settings

settings = get_settings()
BASE = settings.PUBLIC_BASE_URL
PHONE_PREFIX = "test_"  # corto a propósito — la columna phone_number solo acepta 20 caracteres

# ── Ayudantes ────────────────────────────────────────────────────

def enviar(mensaje: str, telefono: str, nombre: str = "Tester") -> dict:
    try:
        r = httpx.post(
            f"{BASE}/webhook/test",
            json={"message": mensaje, "phone": telefono, "name": nombre},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def limpiar_historial(telefono: str):
    try:
        httpx.delete(f"{BASE}/webhook/history/{telefono}", timeout=15)
    except Exception:
        pass


def imprimir_resultado(mensaje: str, resultado: dict, esperado: str = ""):
    print(f"  📨 Mensaje: {mensaje}")
    if "traceback" in resultado and resultado.get("traceback"):
        print(f"  💥 ERROR INTERNO DEL SERVIDOR ({resultado.get('error_type', '?')}): {resultado.get('error')}")
        print(f"  📋 Traceback completo:")
        for linea in resultado["traceback"].splitlines():
            print(f"     {linea}")
        print()
        return
    if "error" in resultado:
        print(f"  ❌ ERROR DE CONEXIÓN: {resultado['error']}")
        print()
        return
    bot = resultado.get("bot", "(sin respuesta)")
    img = resultado.get("image_url")
    loc = resultado.get("location")
    tiempo = resultado.get("time_seconds", "?")
    print(f"  🤖 Respuesta: {bot}")
    print(f"  🖼️  Foto adjunta: {img if img else '(ninguna)'}")
    if loc:
        print(f"  📍 Ubicación adjunta: {loc}")
    print(f"  ⏱️  Tiempo: {tiempo}s")
    if esperado:
        print(f"  🎯 Se esperaba: {esperado}")
    print()


def seccion(titulo: str):
    print()
    print("=" * 70)
    print(f"  {titulo}")
    print("=" * 70)


# ══════════════════════════════════════════════════════════════════
# BLOQUE 1 — Básicos
# ══════════════════════════════════════════════════════════════════
seccion("BLOQUE 1 — Básicos (saludo, horario, ubicación, parqueadero)")
tel = PHONE_PREFIX + "basicos"
limpiar_historial(tel)

for msg, esperado in [
    ("Hola", "Saludo normal"),
    ("Cuál es el horario del CC?", "Debe dar el horario real, no 'no tengo ese dato'"),
    ("Donde queda el centro comercial?", "Texto + pin de ubicación real (location != null)"),
    ("Tienen parqueadero?", "Debe mencionar 24 horas"),
    ("Hay tiendas de zapatos deportivos?", "Debe preguntar qué tipo antes de listar"),
]:
    imprimir_resultado(msg, enviar(msg, tel), esperado)

# ══════════════════════════════════════════════════════════════════
# BLOQUE 2 — Sinónimos
# ══════════════════════════════════════════════════════════════════
seccion("BLOQUE 2 — Sinónimos (no deben activar domicilio por error)")
tel = PHONE_PREFIX + "sinonimos"
limpiar_historial(tel)

for msg, esperado in [
    ("Se permiten mascotas?", "Política real de mascotas"),
    ("Puedo llevar a mi perro?", "MISMA respuesta que la anterior — NO debe activar domicilio"),
    ("Y puedo llevar mi gato?", "MISMA respuesta — NO debe activar domicilio"),
]:
    imprimir_resultado(msg, enviar(msg, tel), esperado)

# ══════════════════════════════════════════════════════════════════
# BLOQUE 3 — Número de tienda
# ══════════════════════════════════════════════════════════════════
seccion("BLOQUE 3 — Petición directa del número de una tienda")
tel = PHONE_PREFIX + "numero"
limpiar_historial(tel)

for msg, esperado in [
    ("Me pasas el número de Zirus Pizza", "Número + link de WhatsApp + pregunta de seguimiento"),
]:
    imprimir_resultado(msg, enviar(msg, tel), esperado)

# ══════════════════════════════════════════════════════════════════
# BLOQUE 4 — Domicilio simple
# ══════════════════════════════════════════════════════════════════
seccion("BLOQUE 4 — Domicilio: mención simple")
tel = PHONE_PREFIX + "dom_simple"
limpiar_historial(tel)

for msg, esperado in [
    ("Quiero pedir de Zirus Pizza", "Solo el link directo, rápido, sin pedir datos"),
]:
    imprimir_resultado(msg, enviar(msg, tel), esperado)

# ══════════════════════════════════════════════════════════════════
# BLOQUE 5 — Domicilio: gestión completa (flujo de varios mensajes)
# ══════════════════════════════════════════════════════════════════
seccion("BLOQUE 5 — Domicilio: gestión completa de principio a fin")
tel = PHONE_PREFIX + "gestion"
limpiar_historial(tel)

pasos = [
    ("Ayúdame a gestionar mi pedido a Mero Mérito", "Carta (o aviso de que no hay) + pide los 5 datos"),
    ("Juan, 3001234567, Calle 5 #10-20, 2 hamburguesas, efectivo", "Debe armar el link con todos los datos"),
]
for msg, esperado in pasos:
    imprimir_resultado(msg, enviar(msg, tel), esperado)

# ══════════════════════════════════════════════════════════════════
# BLOQUE 6 — Gestión: cancelación y pregunta fuera de tema
# ══════════════════════════════════════════════════════════════════
seccion("BLOQUE 6 — Gestión: pregunta fuera de tema + cancelación")
tel = PHONE_PREFIX + "gest_cancela"
limpiar_historial(tel)

pasos = [
    ("Ayúdame a gestionar mi pedido a Zirus Pizza", "Pide los datos"),
    ("Se permiten mascotas?", "Debe responder la pregunta real Y recordar que el pedido sigue pendiente"),
    ("No ya no quiero hacer el domicilio", "Debe cancelar limpiamente"),
    ("Cual es el horario del CC?", "Debe responder normal — ya no debe estar 'atrapado'"),
]
for msg, esperado in pasos:
    imprimir_resultado(msg, enviar(msg, tel), esperado)

# ══════════════════════════════════════════════════════════════════
# BLOQUE 7 — Seguimiento de gestión (nombrar tienda después de preguntar)
# ══════════════════════════════════════════════════════════════════
seccion("BLOQUE 7 — Gestión iniciada sin nombrar tienda, luego solo el nombre")
tel = PHONE_PREFIX + "gest_seguim"
limpiar_historial(tel)

pasos = [
    ("Me puedes ayudar a gestionar mi domicilio", "Debe preguntar de qué tienda (versión de gestión)"),
    ("A Mero Merito", "Debe CONTINUAR con gestión completa (carta + datos), NO dar solo el link"),
]
for msg, esperado in pasos:
    imprimir_resultado(msg, enviar(msg, tel), esperado)

# ══════════════════════════════════════════════════════════════════
# BLOQUE 8 — Fotos de tienda (portada y carta)
# ══════════════════════════════════════════════════════════════════
seccion("BLOQUE 8 — Fotos de tienda con etiqueta correcta")
tel = PHONE_PREFIX + "fotos"
limpiar_historial(tel)

for msg, esperado in [
    ("Dame información de 12B Burguer", "Puede o no traer foto de portada, según lo que tengas cargado"),
    ("Tienes una foto de portada?", "Debe recordar la tienda del mensaje anterior y mandar la foto de portada si existe"),
    ("Tienen carta?", "Debe mandar la foto de CARTA si existe, distinta a la de portada"),
]:
    imprimir_resultado(msg, enviar(msg, tel), esperado)

# ══════════════════════════════════════════════════════════════════
# BLOQUE 9 — Sorteos (afiche vs premio)
# ══════════════════════════════════════════════════════════════════
seccion("BLOQUE 9 — Sorteos: afiche vs foto del premio")
tel = PHONE_PREFIX + "sorteos"
limpiar_historial(tel)

for msg, esperado in [
    ("Tienen sorteos?", "Debe mandar el AFICHE del sorteo si existe"),
    ("Qué premio tiene el sorteo?", "Debe mandar la foto del PREMIO si existe, distinta al afiche"),
]:
    imprimir_resultado(msg, enviar(msg, tel), esperado)

# ══════════════════════════════════════════════════════════════════
# BLOQUE 10 — Base de conocimiento
# ══════════════════════════════════════════════════════════════════
seccion("BLOQUE 10 — Base de Conocimiento")
tel = PHONE_PREFIX + "conocim"
limpiar_historial(tel)

for msg, esperado in [
    ("Como registro mi factura?", "Debe dar la ubicación real de registro de facturas"),
    ("Como participo en las campañas?", "Debe dar la info real de campañas/sorteos"),
]:
    imprimir_resultado(msg, enviar(msg, tel), esperado)

print()
print("=" * 70)
print("  ✅ TODAS LAS PRUEBAS TERMINARON")
print("  Revisa arriba cuáles NO coincidieron con lo esperado.")
print("  Revisa los Deploy Logs (en otra pestaña) para ver el detalle")
print("  interno de cada una (consultas SQL, decisiones de ruteo, etc.)")
print("=" * 70)