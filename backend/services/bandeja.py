"""
Bandeja de entrada a prueba de reinicios (ver models/mensaje_entrante.py).

  guardar(msg)        → lo guarda ANTES de responderle «OK» a Meta. Si Meta reenvía el mismo mensaje, no se repite.
  procesar(id, msg)   → lo responde y lo marca «hecho».
  vigilante()         → corre siempre: al arrancar y cada minuto responde lo que haya quedado sin responder
                        (por un reinicio o una caída), si no tiene más de BANDEJA_MAX_MINUTOS (30 por defecto).

Nunca tumba nada: si la tabla falla, el mensaje se procesa igual que antes.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone

from models.database import SessionLocal
from models.mensaje_entrante import MensajeEntrante

logger = logging.getLogger("mall_bot")

MAX_MINUTOS = float(os.environ.get("BANDEJA_MAX_MINUTOS", "30"))   # más viejo que esto ya no se responde
MAX_INTENTOS = 3
ARRANQUE = datetime.now(timezone.utc)
EN_CURSO: set[int] = set()        # ids que ESTE proceso está respondiendo ahora mismo


def _utc(d: datetime | None) -> datetime | None:
    if d is None:
        return None
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d


def guardar(msg: dict) -> tuple[str, int | None]:
    """→ ("nuevo", id) | ("repetido", None) | ("sin_bandeja", None)."""
    wamid = msg.get("message_id")
    if not wamid:
        return "sin_bandeja", None
    db = SessionLocal()
    try:
        if db.query(MensajeEntrante.id).filter(MensajeEntrante.wamid == wamid).first():
            return "repetido", None
        fila = MensajeEntrante(wamid=wamid, telefono=str(msg.get("phone_number") or msg.get("telefono") or "")[:40],
                               datos=json.dumps(msg, ensure_ascii=False), estado="pendiente", intentos=0)
        db.add(fila)
        db.commit()
        return "nuevo", fila.id
    except Exception as e:
        db.rollback()
        # Si dos copias del mismo mensaje llegan a la vez, la segunda choca con el `unique`: es repetido.
        try:
            if db.query(MensajeEntrante.id).filter(MensajeEntrante.wamid == wamid).first():
                return "repetido", None
        except Exception:
            pass
        logger.error(f"Bandeja: no se pudo guardar el mensaje {wamid}: {e}")
        return "sin_bandeja", None
    finally:
        db.close()


def _marcar(mid: int, estado: str, sumar_intento: bool = False) -> None:
    db = SessionLocal()
    try:
        fila = db.query(MensajeEntrante).filter(MensajeEntrante.id == mid).first()
        if fila:
            fila.estado = estado
            fila.actualizado = datetime.now(timezone.utc)
            if sumar_intento:
                fila.intentos = (fila.intentos or 0) + 1
            db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Bandeja: no se pudo marcar {mid} como {estado}: {e}")
    finally:
        db.close()


async def procesar(mid: int, msg: dict, procesar_mensaje) -> None:
    if mid in EN_CURSO:
        return
    EN_CURSO.add(mid)
    try:
        _marcar(mid, "procesando", sumar_intento=True)
        try:
            await procesar_mensaje(msg)
            _marcar(mid, "hecho")
        except Exception as e:
            logger.error(f"Bandeja: error respondiendo el mensaje {mid}: {e}", exc_info=True)
            _marcar(mid, "error")
    finally:
        EN_CURSO.discard(mid)


def _ya_respondido(db, telefono: str, recibido: datetime) -> bool:
    """¿Any ya le escribió a ese número después de que llegó el mensaje? (p. ej. respondió uno posterior)."""
    from models.conversation import Conversation
    ultimo = (db.query(Conversation.timestamp)
              .filter(Conversation.phone_number == telefono, Conversation.role == "assistant")
              .order_by(Conversation.timestamp.desc()).first())
    return bool(ultimo and ultimo[0] and _utc(ultimo[0]) >= recibido)


def _sin_responder() -> list[tuple[int, dict]]:
    """Mensajes que quedaron a medias (el proceso que los tenía se murió) y aún vale la pena responder."""
    ahora = datetime.now(timezone.utc)
    db = SessionLocal()
    salida = []
    try:
        filas = (db.query(MensajeEntrante)
                 .filter(MensajeEntrante.estado.in_(("pendiente", "procesando")))
                 .order_by(MensajeEntrante.id).limit(200).all())
        for f in filas:
            if f.id in EN_CURSO:
                continue
            recibido = _utc(f.recibido) or ahora
            if ahora - recibido < timedelta(seconds=45) and recibido > ARRANQUE:
                continue                      # recién llegado: su propia tarea lo está respondiendo
            if ahora - recibido > timedelta(minutes=MAX_MINUTOS) or (f.intentos or 0) >= MAX_INTENTOS:
                f.estado = "vencido"
                continue
            if _ya_respondido(db, f.telefono, recibido):
                f.estado = "hecho"
                continue
            try:
                salida.append((f.id, json.loads(f.datos)))
            except Exception:
                f.estado = "error"
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Bandeja: no se pudo revisar pendientes: {e}")
    finally:
        db.close()
    return salida


def resumen() -> dict:
    """Para /any/estado: ¿están llegando mensajes de WhatsApp? ¿quedó alguno sin responder?"""
    db = SessionLocal()
    try:
        ult = db.query(MensajeEntrante.recibido).order_by(MensajeEntrante.id.desc()).first()
        ult_hecho = (db.query(MensajeEntrante.actualizado).filter(MensajeEntrante.estado == "hecho")
                     .order_by(MensajeEntrante.id.desc()).first())
        abiertos = db.query(MensajeEntrante.id).filter(MensajeEntrante.estado.in_(("pendiente", "procesando"))).count()
        def _col(d):
            d = _utc(d[0]) if d and d[0] else None
            return d.astimezone(timezone(timedelta(hours=-5))).strftime("%d/%m/%Y %I:%M:%S %p") if d else None
        return {"ultimo_mensaje_recibido_de_whatsapp": _col(ult), "ultimo_respondido": _col(ult_hecho),
                "sin_responder_ahora": abiertos, "respondiendo_en_este_momento": len(EN_CURSO)}
    except Exception as e:
        return {"error": str(e)[:200]}
    finally:
        db.close()


def _limpiar_viejos() -> None:
    db = SessionLocal()
    try:
        limite = datetime.now(timezone.utc) - timedelta(days=7)
        viejos = [f.id for f in db.query(MensajeEntrante.id, MensajeEntrante.recibido)
                  .filter(MensajeEntrante.estado.in_(("hecho", "vencido", "error"))).limit(5000).all()
                  if _utc(f.recibido) and _utc(f.recibido) < limite]
        if viejos:
            db.query(MensajeEntrante).filter(MensajeEntrante.id.in_(viejos)).delete(synchronize_session=False)
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


async def revisar_una_vez(procesar_mensaje) -> int:
    pendientes = await asyncio.to_thread(_sin_responder)
    for mid, msg in pendientes:
        quien = msg.get("phone_number") or msg.get("telefono")
        que = msg.get("message_text") or msg.get("texto") or msg.get("message_type") or msg.get("tipo")
        print(f"  ♻️   Bandeja: respondiendo mensaje que había quedado sin respuesta ({quien}: {str(que)[:60]})", flush=True)
        await procesar(mid, msg, procesar_mensaje)
    return len(pendientes)


async def vigilante(procesar_mensaje) -> None:
    await asyncio.sleep(5)                     # que termine de arrancar
    vueltas = 0
    while True:
        try:
            await revisar_una_vez(procesar_mensaje)
            vueltas += 1
            if vueltas % 60 == 1:
                await asyncio.to_thread(_limpiar_viejos)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Bandeja: el vigilante falló (sigue): {e}")
        await asyncio.sleep(60)
