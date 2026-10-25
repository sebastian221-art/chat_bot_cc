"""
Entrada propia de Any 2.0 (no toca el webhook viejo):

  GET  /any/webhook   verificación de Meta (hub.challenge)
  POST /any/webhook   mensajes de WhatsApp → se responde 200 al instante y se procesa aparte
  POST /any/prueba    probar un mensaje sin WhatsApp (devuelve respuesta + traza). Exige sesión del panel.
  GET  /any/chat      chat de prueba en el navegador

Para pasar de sistema basta cambiar la URL del webhook en Meta de /webhook a /any/webhook.

Seguridad:
  - Si existe META_APP_SECRET, se valida la firma X-Hub-Signature-256 de cada petición.
  - Cada mensaje se procesa una sola vez (Meta reintenta: se deduplica por message_id).
  - Los mensajes de un mismo cliente se atienden en orden (un candado por teléfono).
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import os
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .config import ZONA_HORARIA, cfg
from .nucleo import estado as est
from .nucleo.harness import procesar

log = logging.getLogger("any.entrada")
router = APIRouter(prefix="/any", tags=["any2"])
_candados: dict[str, asyncio.Lock] = {}


def _sesion():
    from models.database import SessionLocal
    return SessionLocal()


# ── Webhook de Meta ───────────────────────────────────────────────

@router.get("/webhook")
async def verificar(request: Request):
    p = request.query_params
    if p.get("hub.mode") == "subscribe" and cfg().verify_token and p.get("hub.verify_token") == cfg().verify_token:
        return Response(content=p.get("hub.challenge", ""), media_type="text/plain")
    raise HTTPException(status_code=403, detail="Token de verificación inválido")


def _firma_valida(cuerpo: bytes, firma: str) -> bool:
    secreto = os.environ.get("META_APP_SECRET", "")
    if not secreto:
        return True   # sin secreto configurado no se puede validar (se advierte en el log al arrancar)
    esperado = "sha256=" + hmac.new(secreto.encode(), cuerpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, firma or "")


def extraer_mensajes(datos: dict) -> list[dict]:
    """TODOS los mensajes del lote (el parser viejo solo leía el primero)."""
    salida = []
    for entry in datos.get("entry") or []:
        for change in entry.get("changes") or []:
            v = change.get("value") or {}
            nombres = {c.get("wa_id"): (c.get("profile") or {}).get("name", "") for c in v.get("contacts") or []}
            for m in v.get("messages") or []:
                base = {"telefono": m.get("from", ""), "nombre": nombres.get(m.get("from"), ""),
                        "message_id": m.get("id", ""), "tipo": m.get("type")}
                if m.get("type") == "text":
                    base["texto"] = (m.get("text") or {}).get("body", "")
                elif m.get("type") == "image":
                    img = m.get("image") or {}
                    base.update(media_id=img.get("id"), texto=img.get("caption", ""))
                elif m.get("type") == "interactive":
                    it = m.get("interactive") or {}
                    sel = it.get("button_reply") or it.get("list_reply") or {}
                    base.update(tipo="text", texto=sel.get("title", ""))
                elif m.get("type") == "button":
                    base.update(tipo="text", texto=(m.get("button") or {}).get("text", ""))
                salida.append(base)
    return salida


@router.post("/webhook")
async def recibir(request: Request, tareas: BackgroundTasks, x_hub_signature_256: str = Header(default="")):
    cuerpo = await request.body()
    if not _firma_valida(cuerpo, x_hub_signature_256):
        log.warning("Webhook de Any 2.0 con firma inválida: descartado")
        raise HTTPException(status_code=403, detail="Firma inválida")
    try:
        datos = await request.json()
    except Exception:
        return {"status": "ignorado"}
    for m in extraer_mensajes(datos):
        tareas.add_task(atender_mensaje, m)
    return {"status": "ok"}


async def atender_mensaje(m: dict):
    telefono = m.get("telefono") or ""
    if not telefono:
        return
    candado = _candados.setdefault(telefono, asyncio.Lock())
    async with candado:
        db = _sesion()
        procesado = False
        try:
            est.asegurar_tablas(db)
            if est.ya_visto(db, m.get("message_id", ""), telefono):
                return
            from services import whatsapp
            imagen = None
            if m.get("tipo") == "image" and m.get("media_id"):
                imagen = await whatsapp.download_media(m["media_id"])
            elif m.get("tipo") != "text":
                await whatsapp.send_text_message(
                    telefono, "Por ahora solo puedo leer mensajes de texto y fotos 🙏. ¿Me lo escribes?")
                return
            r = await procesar(db, telefono, m.get("nombre", ""), m.get("texto", ""), modo="produccion",
                               imagen=imagen)
            procesado = True
            await enviar(telefono, r)
        except Exception:
            log.exception("Error atendiendo mensaje en Any 2.0")
            if not procesado:      # el cliente nunca se queda sin respuesta
                try:
                    from services import whatsapp
                    await whatsapp.send_text_message(
                        telefono, "Uy, algo salió mal de mi parte 😅 ¿Me lo escribes de nuevo, por favor?")
                except Exception:
                    log.exception("Tampoco se pudo enviar el mensaje de disculpa")
        finally:
            db.close()


async def enviar(telefono: str, r):
    if not r.responder:
        return
    from services import whatsapp
    for texto in r.mensajes():
        await whatsapp.send_text_message(telefono, texto)
    for a in r.adjuntos:
        try:
            if a.tipo == "imagen" and a.url:
                await whatsapp.send_image_message(telefono, a.url, a.leyenda or "")
            elif a.tipo == "documento" and a.url:
                await whatsapp.send_document_message(telefono, a.url, a.nombre_archivo or "documento.pdf",
                                                     a.leyenda or "")
            elif a.tipo == "ubicacion" and a.latitud is not None:
                await whatsapp.send_location_message(telefono, a.latitud, a.longitud, a.titulo, a.direccion)
        except Exception:
            log.exception("No se pudo enviar un adjunto")


# ── Chat de prueba ────────────────────────────────────────────────

def _usuario_panel(authorization: str = Header(default="")):
    if cfg().prueba_abierta:
        return None
    from models.database import SessionLocal
    from routers.auth import get_current_user
    db = SessionLocal()
    try:
        return get_current_user(authorization=authorization, db=db)
    finally:
        db.close()


class Prueba(BaseModel):
    mensaje: str
    telefono: str = "prueba-any2"
    nombre: str = "Prueba"
    fecha: str | None = None     # "2026-10-21 15:30" para simular otro día
    imagen_base64: str | None = None   # foto de prueba (como si el cliente la mandara por WhatsApp)


@router.post("/prueba")
async def probar(p: Prueba, _u=Depends(_usuario_panel)):
    ahora = None
    if p.fecha:
        try:
            ahora = datetime.fromisoformat(p.fecha).replace(tzinfo=ZONA_HORARIA)
        except ValueError:
            raise HTTPException(400, "fecha inválida (usa AAAA-MM-DD HH:MM)")
    db = _sesion()
    try:
        imagen = None
        if p.imagen_base64:
            import base64
            try:
                imagen = base64.b64decode(p.imagen_base64.split(",", 1)[-1])
            except Exception:
                raise HTTPException(400, "imagen inválida")
        r = await procesar(db, p.telefono, p.nombre, p.mensaje, ahora=ahora, modo="prueba", imagen=imagen)
        return {"mensajes": r.mensajes(), "flujo": r.flujo, "adjuntos": [a.dict() for a in r.adjuntos],
                "traza": r.meta.get("traza"), "traza_id": r.meta.get("traza_id")}
    finally:
        db.close()


@router.delete("/prueba/{telefono}")
async def reiniciar_prueba(telefono: str, _u=Depends(_usuario_panel)):
    """Borra la conversación de un teléfono de prueba (solo los que empiezan por 'prueba')."""
    if not telefono.startswith("prueba"):
        raise HTTPException(400, "Solo se pueden reiniciar teléfonos de prueba")
    from .nucleo.guardias import borrar_datos
    db = _sesion()
    try:
        return {"borrado": borrar_datos(db, telefono)}
    finally:
        db.close()


@router.get("/chat")
async def chat():
    return FileResponse(os.path.join(os.path.dirname(__file__), "static", "chat.html"))


if not os.environ.get("META_APP_SECRET"):
    log.warning("Any 2.0: META_APP_SECRET no está configurado; el webhook /any/webhook no valida la firma de Meta")


# ── Any 2.0 como sistema principal ────────────────────────────────
# Con ANY_PRINCIPAL=1 (variable en Railway), el mismo /webhook que Meta ya usa lo atiende Any 2.0.
# No hay que tocar nada en Meta. Para volver al bot viejo: quitar la variable (o ponerla en 0).
# main.py incluye este router ANTES del webhook viejo, por eso gana.

def es_principal() -> bool:
    return os.environ.get("ANY_PRINCIPAL", "").strip().strip("'\"").strip().lower() in {"1", "true", "si", "sí", "on"}


principal = APIRouter(tags=["any2-principal"])


@router.get("/estado")
async def estado_del_cambio():
    """Para confirmar desde el navegador si Any 2.0 es la que responde (no muestra secretos)."""
    solo = numeros_de_prueba()
    return {
        "any2_desplegada": True,
        "any2_responde_whatsapp": es_principal(),
        "modo": ("solo números de prueba" if solo else "todos los clientes") if es_principal() else "responde el bot viejo",
        "numeros_de_prueba": [f"…{n[-4:]}" for n in sorted(solo)],
        "modelo": cfg().llm_flujos,
        "respaldo": cfg().llm_respaldo or "ninguno",
        "groq_configurado": bool(os.environ.get("GROQ_API_KEY", "").strip() not in ("", "PENDIENTE")),
    }


def _numero(n: str) -> str:
    d = "".join(c for c in (n or "") if c.isdigit())
    return "57" + d if len(d) == 10 else d


def numeros_de_prueba() -> set[str]:
    """ANY_NUMEROS_PRUEBA="3154559242, 3001234567": solo esos números los atiende Any 2.0 (el resto, el bot viejo).
    Vacía = Any 2.0 atiende a TODOS."""
    crudo = os.environ.get("ANY_NUMEROS_PRUEBA", "")
    return {_numero(x) for x in crudo.replace(";", ",").replace(" ", ",").split(",") if _numero(x)}


@principal.post("/webhook")
async def recibir_principal(request: Request, tareas: BackgroundTasks, x_hub_signature_256: str = Header(default="")):
    solo = numeros_de_prueba()
    if solo:
        try:
            datos = await request.json()
        except Exception:
            datos = {}
        remitentes = [_numero(m.get("telefono", "")) for m in extraer_mensajes(datos)]
        if not remitentes or not all(r in solo for r in remitentes):
            from routers.webhook import receive_message      # no es un número de prueba: bot viejo
            return await receive_message(request, tareas)
    return await recibir(request, tareas, x_hub_signature_256)