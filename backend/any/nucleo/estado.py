"""
Memoria de la conversación.

- Historial: la tabla compartida `conversations` (la misma que muestra el
  panel). Any 2.0 escribe ahí con session_id="any2".
- Estado de sesión: tabla propia `any_estado`, una fila por teléfono:
  flujo activo (domicilios, QR…), sus datos, y de qué se habló por última
  vez (local, evento…) para entender "¿y el horario?".
- Mensajes vistos: tabla `any_mensajes_vistos` para no procesar dos veces
  el mismo mensaje cuando Meta reintenta.
- Aviso de privacidad: tabla `any_aviso_privacidad` (y se respeta la vieja
  `aviso_privacidad_mostrado`, para no repetirle el aviso a quien ya lo vio).

Las tablas propias usan su propia Base para no mezclarse con las del sistema
viejo; se crean solas la primera vez (asegurar_tablas).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import Column, DateTime, String, Text, inspect, text
from sqlalchemy.orm import Session, declarative_base

from ..config import ZONA_HORARIA, cfg
from .tipos import Turno

BaseAny = declarative_base()
SESION_ID = "any2"


class AnyEstado(BaseAny):
    __tablename__ = "any_estado"
    telefono = Column(String(30), primary_key=True)
    flujo_activo = Column(String(40), nullable=True)
    datos = Column(Text, nullable=True)            # JSON del flujo activo
    ultimas_entidades = Column(Text, nullable=True)  # JSON: {"local": "...", "evento": "..."}
    ultimo_flujo = Column(String(40), nullable=True)
    actualizado = Column(DateTime(timezone=True), nullable=True)


class AnyMensajeVisto(BaseAny):
    __tablename__ = "any_mensajes_vistos"
    message_id = Column(String(120), primary_key=True)
    telefono = Column(String(30), nullable=True)
    visto = Column(DateTime(timezone=True), nullable=True)


class AnyAviso(BaseAny):
    __tablename__ = "any_aviso_privacidad"
    telefono = Column(String(30), primary_key=True)
    version = Column(String(20), nullable=True)
    mostrado = Column(DateTime(timezone=True), nullable=True)


class AnyUsuarioMeta(BaseAny):
    """Clientes que escriben con nombre de usuario de WhatsApp y sin número visible: Meta manda un ID propio
    (BSUID, ej. «CO.1234567890123456789»), más largo que las columnas de teléfono (20). Se guarda una clave
    corta y aquí queda el ID completo para poder responderle."""
    __tablename__ = "any_usuarios_meta"
    clave = Column(String(20), primary_key=True)
    bsuid = Column(String(120), nullable=False)
    creado = Column(DateTime(timezone=True), nullable=True)


_tablas_listas: set = set()
_bsuid_cache: dict = {}


def es_bsuid(identificador: str) -> bool:
    """Un BSUID trae letras o un punto («CO.1349…»); un teléfono son solo dígitos."""
    t = (identificador or "").strip()
    return bool(t) and not t.isdigit()


def clave_de_bsuid(db: Session, bsuid: str) -> str:
    """Clave de 20 caracteres para guardar al cliente en las tablas de siempre (conversaciones, trazas…)."""
    import hashlib
    clave = "u" + hashlib.sha1(bsuid.encode()).hexdigest()[:19]
    if _bsuid_cache.get(clave) != bsuid:
        asegurar_tablas(db)
        try:
            if not db.get(AnyUsuarioMeta, clave):
                db.add(AnyUsuarioMeta(clave=clave, bsuid=bsuid, creado=datetime.now(timezone.utc)))
                db.commit()
        except Exception:
            db.rollback()
        _bsuid_cache[clave] = bsuid
    return clave


def bsuid_de_clave(clave: str) -> str | None:
    """El ID de Meta detrás de una clave «u…» (para enviarle el mensaje). None si es un teléfono normal."""
    if not clave or not clave.startswith("u") or len(clave) != 20:
        return None
    if clave in _bsuid_cache:
        return _bsuid_cache[clave]
    from models.database import SessionLocal
    db = SessionLocal()
    try:
        asegurar_tablas(db)
        fila = db.get(AnyUsuarioMeta, clave)
        if fila:
            _bsuid_cache[clave] = fila.bsuid
            return fila.bsuid
    except Exception:
        db.rollback()
    finally:
        db.close()
    return None


def asegurar_tablas(db: Session):
    url = str(db.get_bind().url)
    if url in _tablas_listas:
        return
    BaseAny.metadata.create_all(bind=db.get_bind(), checkfirst=True)
    _tablas_listas.add(url)


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


# ── Estado de sesión ──────────────────────────────────────────────

@dataclass
class EstadoSesion:
    telefono: str
    flujo_activo: str | None = None
    datos: dict = field(default_factory=dict)
    ultimas_entidades: dict = field(default_factory=dict)
    ultimo_flujo: str | None = None
    actualizado: datetime | None = None
    edad: dict = field(default_factory=dict)        # turnos que lleva cada dato recordado sin mencionarse
    tocadas: set = field(default_factory=set)       # datos recordados que se mencionaron en ESTE turno

    def recordar(self, nuevas: dict):
        """Suma lo que se habló en este turno a lo recordado (y marca esas claves como recientes)."""
        from .router import limpiar_entidades
        nuevas = limpiar_entidades(nuevas or {})
        self.ultimas_entidades = limpiar_entidades({**self.ultimas_entidades, **nuevas})
        self.tocadas |= set(nuevas)

    def activar(self, flujo: str, datos: dict | None = None):
        self.flujo_activo, self.datos = flujo, (datos or {})

    def terminar_flujo(self):
        self.flujo_activo, self.datos = None, {}


def cargar_estado(db: Session, telefono: str, ahora: datetime) -> EstadoSesion:
    fila = db.get(AnyEstado, telefono)
    if not fila:
        return EstadoSesion(telefono)
    ent = json.loads(fila.ultimas_entidades or "{}")
    edad = ent.pop("_edad", {}) if isinstance(ent.get("_edad"), dict) else {}
    e = EstadoSesion(telefono, fila.flujo_activo, json.loads(fila.datos or "{}"),
                     ent, fila.ultimo_flujo, _utc(fila.actualizado), edad)
    pausa = _utc(ahora) - e.actualizado if e.actualizado else None
    # Un flujo con estado (p. ej. un domicilio a medias) caduca con la sesión
    if pausa and pausa > timedelta(hours=cfg().sesion_horas):
        e.terminar_flujo()
        e.ultimas_entidades, e.edad = {}, {}
    # Hilo nuevo: lo recordado del tema anterior ya no aplica (26/11: preguntaban por Cajasan y Any seguía
    # «recordando» Ápice y la Casa del Libro de horas antes)
    elif pausa and pausa > timedelta(minutes=cfg().hilo_minutos):
        e.ultimas_entidades, e.edad = {}, {}
        e.ultimo_flujo = None
    return e


def guardar_estado(db: Session, e: EstadoSesion, ahora: datetime):
    fila = db.get(AnyEstado, e.telefono) or AnyEstado(telefono=e.telefono)
    fila.flujo_activo = e.flujo_activo
    fila.datos = json.dumps(e.datos, ensure_ascii=False)
    # Lo recordado envejece: lo que no se menciona en N turnos se olvida solo (el hilo se «resetea» por partes)
    edad = {}
    for k in list(e.ultimas_entidades):
        edad[k] = 0 if k in e.tocadas else int(e.edad.get(k, 0)) + 1
        if edad[k] >= cfg().entidades_turnos:
            e.ultimas_entidades.pop(k, None)
            edad.pop(k)
    e.edad, e.tocadas = edad, set()
    fila.ultimas_entidades = json.dumps({**e.ultimas_entidades, "_edad": edad} if edad else e.ultimas_entidades,
                                        ensure_ascii=False)
    fila.ultimo_flujo = e.ultimo_flujo
    fila.actualizado = _utc(ahora)
    db.merge(fila)
    db.commit()


# ── Historial ─────────────────────────────────────────────────────

def cargar_historial(db: Session, telefono: str, ahora: datetime) -> tuple[list[Turno], bool]:
    """Mensajes del HILO actual y si la sesión es nueva (más de N horas sin hablar).
    El hilo son los mensajes seguidos: si entre dos mensajes pasaron más de «hilo_minutos», lo anterior es otra
    conversación y no se usa como contexto (sigue guardado para las trazas y el panel)."""
    from models.conversation import Conversation
    filas = (db.query(Conversation).filter(Conversation.phone_number == telefono)
             .order_by(Conversation.timestamp.desc(), Conversation.id.desc())
             .limit(cfg().historial_mensajes).all())
    filas.reverse()
    limite = _utc(ahora) - timedelta(hours=cfg().sesion_horas)
    from . import mensajes
    aviso = mensajes.texto("aviso_privacidad")[:40]
    turnos = [Turno("assistant" if f.role == "assistant" else "user", f.message, _utc(f.timestamp))
              for f in filas if (f.timestamp is None or _utc(f.timestamp) >= limite)
              and not (aviso and (f.message or "").startswith(aviso))]   # el aviso legal no es conversación
    sesion_nueva = not turnos
    hilo = timedelta(minutes=cfg().hilo_minutos)
    corte, siguiente = 0, _utc(ahora)
    for i in range(len(turnos) - 1, -1, -1):
        cuando = turnos[i].cuando
        if cuando is not None and siguiente - cuando > hilo:
            corte = i + 1
            break
        if cuando is not None:
            siguiente = cuando
    return turnos[corte:], sesion_nueva


def guardar_turno(db: Session, telefono: str, nombre: str, rol: str, texto: str, ahora: datetime):
    from models.conversation import Conversation
    db.add(Conversation(phone_number=telefono[:20], user_name=(nombre or "")[:100], role=rol,
                        message=texto, timestamp=_utc(ahora), session_id=SESION_ID))
    db.commit()


# ── Mensajes duplicados ───────────────────────────────────────────

def ya_visto(db: Session, message_id: str, telefono: str) -> bool:
    """Marca el mensaje como visto; devuelve True si ya se había procesado."""
    if not message_id:
        return False
    if db.get(AnyMensajeVisto, message_id):
        return True
    db.add(AnyMensajeVisto(message_id=message_id, telefono=telefono, visto=datetime.now(timezone.utc)))
    try:
        db.commit()
    except Exception:
        db.rollback()
        return True
    return False


# ── Aviso de privacidad ───────────────────────────────────────────

def aviso_ya_mostrado(db: Session, telefono: str) -> bool:
    if db.get(AnyAviso, telefono):
        return True
    try:  # respeta el registro del sistema viejo
        if inspect(db.get_bind()).has_table("aviso_privacidad_mostrado"):
            r = db.execute(text("SELECT 1 FROM aviso_privacidad_mostrado WHERE phone_number = :t"),
                           {"t": telefono}).first()
            return r is not None
    except Exception:
        db.rollback()
    return False


def marcar_aviso(db: Session, telefono: str, version: str, ahora: datetime):
    db.merge(AnyAviso(telefono=telefono, version=version, mostrado=_utc(ahora)))
    db.commit()


def ahora_colombia() -> datetime:
    return datetime.now(ZONA_HORARIA)