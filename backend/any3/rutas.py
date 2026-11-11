"""
Rutas de Any 3.0 (todas con sesión del panel, salvo /any3/estado que no muestra nada privado):

  GET  /any3/estado        ¿está activa?, qué números atiende, qué modelo usa (sin secretos)
  POST /any3/prueba        probar un mensaje con Any 3.0 (igual que /any/prueba)
  GET  /any3/chat          chat de prueba en el navegador, con Any 3.0
  POST /any3/examen        corre el examen del cerebro en segundo plano (?modelo=anthropic:claude-sonnet-5-5)
  GET  /any3/examen        resultado del último examen
  GET  /any3/vacios        lo que preguntaron y no estaba en la base (datos por completar)
  GET  /any3/groq          límites de tokens de tu cuenta de Groq y si Any 3.0 cabe
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
    botones = ('<button id="b-groq" type="button">Límites Groq</button>'
               '<button id="b-examen" type="button">Correr examen</button>'
               '<button id="b-ver" type="button">Ver examen</button>'
               '<button id="b-vacios" type="button">Datos faltantes</button>')
    html = html.replace('<button id="reiniciar" type="button">Reiniciar conversación</button>',
                        '<button id="reiniciar" type="button">Reiniciar conversación</button>' + botones, 1)
    html = html.replace("</body>", _HERRAMIENTAS + "</body>", 1)
    return HTMLResponse(html)


_HERRAMIENTAS = """<script>
function _esc(t) { return String(t ?? "").replace(/[&<>]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;"})[c]); }
function _panel(titulo, html) { $("traza").innerHTML = "<h2>" + _esc(titulo) + "</h2>" + html; }
async function _json(ruta, opciones) {
  const r = await fetch(ruta, { ...(opciones || {}), headers: { "Content-Type": "application/json", ...(token ? { Authorization: "Bearer " + token } : {}) } });
  return r.json();
}
$("b-groq").onclick = async () => {
  _panel("Límites de Groq", "<p>Consultando…</p>");
  const j = await _json("/any3/groq");
  _panel("Límites de Groq", "<p><b>" + _esc(j.veredicto || j.error) + "</b></p><pre style='white-space:pre-wrap'>" + _esc(JSON.stringify(j, null, 1)) + "</pre>");
};
$("b-examen").onclick = async () => {
  const modelo = prompt("Modelo (vacío = el configurado). Ej: groq:openai/gpt-oss-120b", "") || "";
  const j = await _json("/any3/examen" + (modelo ? "?modelo=" + encodeURIComponent(modelo) : ""), { method: "POST" });
  _panel("Examen", "<p>" + _esc(j.estado) + " · " + _esc(j.modelo || "") + "</p><p>Con Groq va de a una pregunta: puede tardar 10–20 minutos. Toca «Ver examen» para ver el avance.</p>");
};
$("b-ver").onclick = async () => {
  const j = await _json("/any3/examen");
  let h = "<p><b>" + _esc(j.estado) + "</b> · " + _esc(j.modelo || "") + " · directorio " + _esc(j.directorio || "") + "</p>";
  if (j.estado === "corriendo") h += "<p>Van " + _esc(j.progreso) + " de 97 preguntas…</p>";
  if (j.total) h += "<p style='font-size:20px'><b>" + j.bien + " / " + j.total + "</b> (" + j.porcentaje + " %) · " + j.segundos_promedio + " s por pregunta</p>";
  if (j.error) h += "<p class='error'>" + _esc(j.error) + "</p>";
  for (const f of (j.fallas || [])) {
    h += "<div style='border-top:1px solid #ddd;padding:6px 0'><b>❌ " + _esc(f.pregunta) + "</b><br>eligió: " + _esc((f.eligio || []).join(", ") || f.accion || "") +
         (f.faltan && f.faltan.length ? "<br>faltaron: " + _esc(f.faltan.join(", ")) : "") +
         (f.sobran && f.sobran.length ? "<br>sobraron: " + _esc(f.sobran.join(", ")) : "") +
         (f.problema ? "<br>" + _esc(f.problema) : "") + "<br><small>" + _esc(f.razon || "") + "</small></div>";
  }
  _panel("Examen", h);
};
$("b-vacios").onclick = async () => {
  const j = await _json("/any3/vacios");
  const lista = (xs) => (xs || []).map(x => "<li>" + _esc(x.fecha) + " — " + _esc(x.mensaje) + "</li>").join("") || "<li>nada</li>";
  _panel("Datos faltantes", "<p>Revisadas: " + _esc(j.revisadas) + "</p><h2>No estaba en la base</h2><ul>" + lista(j.no_estaba_en_la_base) +
    "</ul><h2>Solo «probablemente»</h2><ul>" + lista(j.solo_probable) + "</ul><h2>El vigilante corrigió</h2><ul>" + lista(j.el_vigilante_corrigio) + "</ul>");
};
</script>
"""


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


@router.get("/groq")
async def limites_groq(_u=Depends(_usuario_panel)):
    """Pregunta a Groq cuántos tokens por minuto permite TU cuenta (con una llamada mínima) y si el directorio
    completo de Any 3.0 cabe. Sin mostrar la clave."""
    import httpx
    from .cerebro import _prompt
    from .directorio import construir
    clave = os.environ.get("GROQ_API_KEY", "")
    if not clave:
        return {"error": "No hay GROQ_API_KEY en las variables"}
    modelo = config.GROQ.split(":", 1)[1]
    async with httpx.AsyncClient(timeout=20) as http:
        r = await http.post("https://api.groq.com/openai/v1/chat/completions",
                            headers={"Authorization": f"Bearer {clave}"},
                            json={"model": modelo, "messages": [{"role": "user", "content": "hola"}], "max_tokens": 5})
    h = {k: v for k, v in r.headers.items() if k.lower().startswith("x-ratelimit")}
    db = _sesion()
    try:
        base = len(_prompt("cerebro.md")) + 1200
        completo = (len(construir(db).texto) + base) // 3.5
        compacto = (len(construir(db, compacto=True).texto) + base) // 3.5
    finally:
        db.close()
    tpm = int(h.get("x-ratelimit-limit-tokens") or 0)
    if not tpm:
        veredicto = "Groq no informó el límite (mira la respuesta)"
    elif tpm >= completo * 3 + 15000:
        veredicto = "Cabe el directorio COMPLETO con margen: Any 3.0 funciona a su máxima calidad con Groq."
    elif tpm >= compacto * 2 + 10000:
        veredicto = ("El completo no cabe con margen: Any 3.0 usará el directorio CORTO (funciona, un poco menos "
                     "preciso). Pon ANY3_DIRECTORIO=compacto para no perder tiempo intentando el completo.")
    else:
        veredicto = ("Tu límite de tokens por minuto es muy bajo para Any 3.0 (y aprieta también a Any 2.0). "
                     "Sube de plan en console.groq.com/settings/billing o usa la clave de Claude.")
    return {"estado_http": r.status_code, "limites": h, "tokens_por_mensaje_aprox": {
        "cerebro_completo": int(completo), "cerebro_corto": int(compacto), "redactor_y_vigilante": 9000},
        "veredicto": veredicto, "error": r.text[:300] if r.status_code != 200 else ""}
