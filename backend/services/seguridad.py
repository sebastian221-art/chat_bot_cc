# 📄 ARCHIVO: backend/services/seguridad.py
"""
Capa de SEGURIDAD del sistema — protege el panel y la API contra
ataques comunes, sin afectar el funcionamiento normal ni bloquear los
mensajes legítimos de clientes que llegan por el webhook de WhatsApp.

Incluye:

1. RATE LIMITING (límite de peticiones por IP):
   Si una IP hace demasiadas peticiones en poco tiempo (típico de un
   ataque o un bot malicioso), se le bloquea temporalmente. Los límites
   son normales — no molestan a un usuario real del panel, pero frenan
   a quien intente saturar el servidor con miles de peticiones.

2. PROTECCIÓN DE FUERZA BRUTA en el login:
   Si desde una IP se fallan varios intentos de login seguidos (alguien
   probando contraseñas), se bloquea temporalmente esa IP para el login.

3. Utilidades para respuestas de error seguras (que no filtran detalles
   técnicos al atacante).

Todo se maneja en memoria (sin base de datos), con limpieza automática.
Es simple, rápido y suficiente para el tamaño de este sistema.
"""
import time
import logging
from collections import defaultdict, deque
from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("mall_bot")

# ── CONFIGURACIÓN (límites normales, ajustables) ──────────────────
# Peticiones generales al panel/API: máximo N por ventana de tiempo.
RATE_LIMIT_PETICIONES = 120      # 120 peticiones
RATE_LIMIT_VENTANA    = 60       # por cada 60 segundos (2 por segundo en promedio)

# Login: máximo N intentos fallidos antes de bloquear esa IP.
LOGIN_MAX_INTENTOS    = 6        # 6 intentos fallidos
LOGIN_BLOQUEO_SEG     = 300      # bloqueo de 5 minutos

# Rutas que NO se limitan (el webhook de WhatsApp recibe muchos mensajes
# legítimos de Meta; y los archivos estáticos/imágenes son inofensivos).
RUTAS_EXENTAS = ("/webhook", "/uploads", "/static", "/health")


# ── Estado en memoria ─────────────────────────────────────────────
_peticiones_por_ip = defaultdict(deque)     # ip → timestamps recientes
_login_fallidos    = defaultdict(list)      # ip → timestamps de fallos
_login_bloqueado   = {}                     # ip → hasta_cuando (timestamp)


def _ip_de(request: Request) -> str:
    """Obtiene la IP real del cliente, considerando el proxy de Railway."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "desconocida"


# ── 1. Rate limiting general ──────────────────────────────────────
def esta_limitado(request: Request) -> bool:
    """True si esta IP superó el límite de peticiones (hay que bloquearla)."""
    ruta = request.url.path
    if any(ruta.startswith(r) for r in RUTAS_EXENTAS):
        return False

    ip = _ip_de(request)
    ahora = time.time()
    cola = _peticiones_por_ip[ip]

    # Quitar las peticiones viejas (fuera de la ventana)
    while cola and cola[0] < ahora - RATE_LIMIT_VENTANA:
        cola.popleft()

    cola.append(ahora)
    if len(cola) > RATE_LIMIT_PETICIONES:
        logger.warning(f"Rate limit superado por IP {ip} ({len(cola)} peticiones en {RATE_LIMIT_VENTANA}s)")
        return True
    return False


# ── 2. Fuerza bruta en login ──────────────────────────────────────
def login_bloqueado(request: Request) -> bool:
    """True si esta IP está bloqueada por demasiados intentos fallidos."""
    ip = _ip_de(request)
    hasta = _login_bloqueado.get(ip)
    if hasta and time.time() < hasta:
        return True
    if hasta and time.time() >= hasta:
        # Ya pasó el bloqueo — limpiar
        _login_bloqueado.pop(ip, None)
        _login_fallidos.pop(ip, None)
    return False


def registrar_login_fallido(request: Request):
    """Cuenta un intento de login fallido; bloquea la IP si se pasa."""
    ip = _ip_de(request)
    ahora = time.time()
    fallos = _login_fallidos[ip]
    # Solo contar los fallos recientes (última ventana de bloqueo)
    fallos = [t for t in fallos if t > ahora - LOGIN_BLOQUEO_SEG]
    fallos.append(ahora)
    _login_fallidos[ip] = fallos
    if len(fallos) >= LOGIN_MAX_INTENTOS:
        _login_bloqueado[ip] = ahora + LOGIN_BLOQUEO_SEG
        logger.warning(f"IP {ip} bloqueada para login por {LOGIN_MAX_INTENTOS} intentos fallidos")


def registrar_login_exitoso(request: Request):
    """Limpia el contador de fallos tras un login exitoso."""
    ip = _ip_de(request)
    _login_fallidos.pop(ip, None)
    _login_bloqueado.pop(ip, None)


# ── Respuestas de error seguras ───────────────────────────────────
def respuesta_muchas_peticiones() -> JSONResponse:
    return JSONResponse(status_code=429, content={"detail": "Demasiadas peticiones. Espera un momento e intenta de nuevo."})


def respuesta_login_bloqueado() -> JSONResponse:
    return JSONResponse(status_code=429, content={"detail": "Demasiados intentos. Por seguridad, espera unos minutos antes de intentar de nuevo."})