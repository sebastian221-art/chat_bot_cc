"""
Rutas de Any 3.0 (todas con sesión del panel, salvo /any3/estado que no muestra nada privado):

  GET  /any3/estado        ¿está activa?, qué números atiende, qué modelo usa (sin secretos)
  POST /any3/prueba        probar un mensaje con Any 3.0 (igual que /any/prueba)
  GET  /any3/chat          chat de prueba en el navegador, con Any 3.0
  POST /any3/examen        corre el examen del cerebro en segundo plano (?modelo=anthropic:claude-sonnet-5-5)
  GET  /any3/examen        resultado del último examen
  GET  /any3/vacios        lo que preguntaron y no estaba en la base (datos por completar)
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse

from any.config import ZONA_HORARIA
from any.entrada import Prueba, _sesion, _usuario_panel

from . import config

router = APIRouter(prefix="/any3", tags=["any3"])
_examen: dict = {"estado": "sin correr"}


@router.get("/estado")
async def estado():
    n = config.numeros()
    return {"any3": "activa" if n else "apagada",
            "atiende": "todos" if n == "todos" else [f"…{x[-4:]}" for x in sorted(n)],
            "modelo": config.modelo(), "vigilante": config.modelo_vigilante() if config.vigilante_activo() else "apagado",
            "respaldo": config.respaldo() or "(ninguno)",
            "clave_anthropic": bool(os.environ.get("ANTHROPIC_API_KEY")), "clave_groq": bool(os.environ.get("GROQ_API_KEY")),
            "examen": {k: v for k, v in _examen.items() if k in ("estado", "modelo", "bien", "total", "porcentaje")}}


@router.post("/prueba")
async def probar(p: Prueba, _u=Depends(_usuario_panel)):
    from .harness import procesar
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
            imagen = base64.b64decode(p.imagen_base64.split(",", 1)[-1])
        telefono = p.telefono if p.telefono != "prueba-any2" else "prueba-any3"
        r = await procesar(db, telefono, p.nombre, p.mensaje, ahora=ahora, modo="prueba", imagen=imagen)
        return {"mensajes": r.mensajes(), "flujo": r.flujo, "adjuntos": [a.dict() for a in r.adjuntos],
                "any3": r.meta.get("any3"), "traza": r.meta.get("traza"), "traza_id": r.meta.get("traza_id")}
    finally:
        db.close()


@router.get("/chat", response_class=HTMLResponse)
async def chat():
    ruta = os.path.join(os.path.dirname(__file__), "..", "any", "static", "chat.html")
    with open(ruta, encoding="utf-8") as f:
        html = f.read()
    html = (html.replace('"/any/prueba"', '"/any3/prueba"').replace("Any 2.0", "Any 3.0")
            .replace('value="prueba-any2"', 'value="prueba-any3"').replace('|| "prueba-any2"', '|| "prueba-any3"'))
    return HTMLResponse(html)


@router.post("/examen")
async def correr_examen(modelo: str = "", _u=Depends(_usuario_panel)):
    if _examen.get("estado") == "corriendo":
        return {"estado": "ya hay un examen corriendo", "progreso": _examen.get("progreso")}
    _examen.clear()
    _examen.update(estado="corriendo", modelo=modelo or config.modelo(), progreso=0, inicio=datetime.now(ZONA_HORARIA).isoformat())

    async def tarea():
        from .examen import correr
        db = _sesion()
        try:
            def progreso(_f):
                _examen["progreso"] = _examen.get("progreso", 0) + 1
            res = await correr(db, progreso=progreso, modelo=modelo)
            _examen.update(res, estado="terminado")
        except Exception as e:
            _examen.update(estado="falló", error=repr(e)[:500])
        finally:
            db.close()
    asyncio.create_task(tarea())
    return {"estado": "corriendo", "modelo": _examen["modelo"], "ver": "GET /any3/examen"}


@router.get("/examen")
async def ver_examen(todas: bool = False, _u=Depends(_usuario_panel)):
    if todas:
        return _examen
    return {k: v for k, v in _examen.items() if k != "todas"}


@router.get("/vacios")
async def vacios(limite: int = 300, _u=Depends(_usuario_panel)):
    """Lo que preguntaron y NO estaba en la base (o solo «probablemente»), y lo que el vigilante tuvo que corregir.
    Es la lista de datos que faltan por completar: así las fallas solo pueden ser por falta de información."""
    import json
    from models.orchestrator_trace import OrchestratorTrace
    db = _sesion()
    try:
        filas = (db.query(OrchestratorTrace).filter(OrchestratorTrace.razon_decision.like("[any3]%"))
                 .order_by(OrchestratorTrace.id.desc()).limit(max(1, min(limite, 2000))).all())
        no_hay, probables, corregidas = [], [], []
        for f in filas:
            try:
                pasos = json.loads(f.pasos or "[]")
            except ValueError:
                continue
            cerebro = next((p.get("detalle", "") for p in pasos if p.get("paso") == "cerebro"), "")
            fila = {"id": f.id, "fecha": str(f.created_at)[:16], "mensaje": f.mensaje_usuario}
            if '"accion": "no_hay"' in cerebro:
                no_hay.append(fila)
            elif '"certeza": "probable"' in cerebro:
                probables.append(fila)
            if any(p.get("paso") == "vigilante_2" for p in pasos) or \
                    any(p.get("paso") == "alerta" and "vigilante" in str(p.get("detalle")) for p in pasos):
                corregidas.append({**fila, "respuesta": (f.respuesta_bot or "")[:300]})
        return {"revisadas": len(filas), "no_estaba_en_la_base": no_hay, "solo_probable": probables,
                "el_vigilante_corrigio": corregidas}
    finally:
        db.close()
