"""
Rutas de Any 3.0 (todas con sesión del panel, salvo /any3/estado que no muestra nada privado):

  GET  /any3/estado        ¿está activa?, qué números atiende, qué modelo usa (sin secretos)
  POST /any3/prueba        probar un mensaje con Any 3.0 (igual que /any/prueba)
  GET  /any3/chat          chat de prueba en el navegador, con Any 3.0
  POST /any3/examen        examen con respuestas completas: ?motor=any3|any2|ambos (&modelo=… para Any 3.0)
  GET  /any3/examen        resultados (?todas=true trae cada pregunta con su respuesta)
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


@router.get("/estado")
async def estado():
    n = config.numeros()
    return {"any3": "activa" if n else "apagada",
            "atiende": "todos" if n == "todos" else [f"…{x[-4:]}" for x in sorted(n)],
            "modelo": config.modelo(), "vigilante": config.modelo_vigilante() if config.vigilante_activo() else "apagado",
            "respaldo": config.respaldo() or "(ninguno)",
            "clave_anthropic": bool(os.environ.get("ANTHROPIC_API_KEY")), "clave_groq": bool(os.environ.get("GROQ_API_KEY")),
            "examenes": _resumen_examenes()}


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
               '<button id="b-exportar" type="button">Exportar examen</button>'
               '<button id="b-vacios" type="button">Datos faltantes</button>')
    html = html.replace('<button id="reiniciar" type="button">Reiniciar conversación</button>',
                        '<button id="reiniciar" type="button">Reiniciar conversación</button>' + botones, 1)
    html = html.replace("</body>", _HERRAMIENTAS + "</body>", 1)
    return HTMLResponse(html)


_HERRAMIENTAS = """<style>
#traza table { width:100%; border-collapse:collapse; font-size:13px; }
#traza td, #traza th { border-bottom:1px solid #e3e3e3; padding:5px 4px; vertical-align:top; text-align:left; }
#traza tr.fila { cursor:pointer; } #traza tr.fila:hover { background:#f3f3f3; }
#traza .det { background:#fafafa; } #traza .det pre { white-space:pre-wrap; margin:4px 0; font:12px/1.4 system-ui; }
#traza .filtros button { margin:0 4px 6px 0; padding:4px 8px; border:1px solid #ccc; border-radius:6px; background:#fff; cursor:pointer; }
#traza .resumen { display:flex; gap:10px; flex-wrap:wrap; margin-bottom:8px; }
#traza .resumen div { border:1px solid #ddd; border-radius:8px; padding:6px 10px; }
</style>
<script>
function _esc(t) { return String(t ?? "").replace(/[&<>]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;"})[c]); }
function _panel(titulo, html) { $("traza").innerHTML = "<h2>" + _esc(titulo) + "</h2>" + html; }
async function _json(ruta, opciones) {
  const r = await fetch(ruta, { ...(opciones || {}), headers: { "Content-Type": "application/json", ...(token ? { Authorization: "Bearer " + token } : {}) } });
  let j = null;
  try { j = await r.json(); } catch (e) { j = { detail: "respuesta no válida del servidor (" + r.status + ")" }; }
  if (!r.ok) {
    if (r.status === 401) { j.detail = "Tu sesión venció: recarga la página y vuelve a entrar."; }
    throw new Error(j.detail || ("error " + r.status));
  }
  return j;
}
function _fallo(titulo, e) { _panel(titulo, "<p class='error'>" + _esc(e.message || e) + "</p>"); }
$("b-groq").onclick = async () => {
  _panel("Límites de Groq", "<p>Consultando…</p>");
  let j;
  try { j = await _json("/any3/groq"); } catch (e) { return _fallo("Límites de Groq", e); }
  _panel("Límites de Groq", "<p><b>" + _esc(j.veredicto || j.error) + "</b></p><pre style='white-space:pre-wrap'>" + _esc(JSON.stringify(j, null, 1)) + "</pre>");
};
$("b-examen").onclick = async () => {
  const motor = (prompt("¿Qué examinar? Escribe: ambos, any3 o any2", "ambos") || "").trim().toLowerCase();
  if (!motor) return;
  const conjunto = (prompt("¿Qué preguntas? Escribe: todo (banco + nuevas + prueba final) o final (solo la prueba final, preguntas nuevas)", "final") || "").trim().toLowerCase();
  if (!conjunto) return;
  let j;
  try { j = await _json("/any3/examen?motor=" + encodeURIComponent(motor) + "&conjunto=" + encodeURIComponent(conjunto), { method: "POST" }); } catch (e) { return _fallo("Examen", e); }
  _panel("Examen", "<p>" + _esc(j.estado) + "</p>");
  setTimeout(_verExamen, 1500);
};
let _datos = null, _filtro = "todas";
function _celda(f) { return !f ? "—" : (f.ok === null || f.ok === undefined ? "⚪" : (f.ok ? "✅" : "❌")); }
function _detalle(nombre, f) {
  if (!f) return "<p><b>" + nombre + ":</b> sin correr</p>";
  return "<p><b>" + nombre + " " + _celda(f) + "</b> · " + _esc(f.tema || "") + (nombre === "Any 3.0" && f.respondio === "any2" ? " · (lo pasó a Any 2.0)" : "") + " · " + _esc(f.segundos) + " s" +
    (f.eligio && f.eligio.length ? "<br>locales: " + _esc(f.eligio.join(", ")) : "") +
    (f.faltan && f.faltan.length ? "<br><b>faltaron:</b> " + _esc(f.faltan.join(", ")) : "") +
    (f.sobran && f.sobran.length ? "<br><b>sobraron:</b> " + _esc(f.sobran.join(", ")) : "") +
    (f.problema ? "<br><b>" + _esc(f.problema) + "</b>" : "") + "</p><pre>" + _esc(f.respuesta || "") + "</pre>";
}
function _pintar() {
  const a3 = (_datos.any3 || {}), a2 = (_datos.any2 || {});
  const res = (n, e) => !e.estado ? "" : "<div><b>" + n + "</b>" + (e.conjunto ? " · " + _esc(e.conjunto === "final" ? "prueba final" : "todo") : "") + "<br>" + _esc(e.estado) + (["corriendo", "en espera"].includes(e.estado) ? " · <b>" + _esc(e.progreso) + " de " + _esc(e.total_casos) + "</b> preguntas (se actualiza solo)" : "") +
     (e.total ? "<br><span style='font-size:20px'><b>" + e.bien + " / " + e.total + "</b></span> (" + e.porcentaje + " %)" + (e.sin_calificar ? "<br>+ " + e.sin_calificar + " nuevas para comparar a ojo" : "") + "<br>" + _esc(JSON.stringify(e.por_tipo || {})) + "<br>" + e.segundos_promedio + " s por pregunta" : "") +
     (e.error ? "<br><span class='error'>" + _esc(e.error) + "</span>" : "") + "<br><small>" + _esc(e.modelo || "") + "</small></div>";
  let h = "<div class='resumen'>" + res("Any 3.0", a3) + res("Any 2.0", a2) + "</div>";
  if (a3.conjunto && a2.conjunto && a3.conjunto !== a2.conjunto) h += "<p class='error'>Ojo: Any 3.0 corrió «" + _esc(a3.conjunto) + "» y Any 2.0 «" + _esc(a2.conjunto) + "»: las filas no se corresponden. Córrelos con «ambos».</p>";
  h += "<div class='filtros'>" + ["todas", "fallas any3", "fallas any2", "diferencias", "nuevas (a ojo)"].map(x => "<button data-f='" + x + "'" + (x === _filtro ? " style='background:#eee'" : "") + ">" + x + "</button>").join("") + "</div>";
  const f3 = {}, f2 = {}; (a3.todas || []).forEach(f => f3[f.n] = f); (a2.todas || []).forEach(f => f2[f.n] = f);
  const ns = [...new Set([...Object.keys(f3), ...Object.keys(f2)].map(Number))].sort((x, y) => x - y);
  h += "<table><tr><th>#</th><th>Pregunta</th><th>3.0</th><th>2.0</th></tr>";
  for (const n of ns) {
    const x = f3[n], y = f2[n];
    if (_filtro === "fallas any3" && !(x && !x.ok)) continue;
    if (_filtro === "fallas any2" && !(y && !y.ok)) continue;
    if (_filtro === "diferencias" && !(x && y && x.ok !== y.ok)) continue;
    if (_filtro === "nuevas (a ojo)" && (x || y).tipo !== "nueva") continue;
    const p = (x || y).pregunta;
    h += "<tr class='fila' data-n='" + n + "'><td>" + n + "</td><td>" + _esc(p) + "</td><td>" + _celda(x) + "</td><td>" + _celda(y) + "</td></tr>" +
         "<tr class='det' id='det-" + n + "' hidden><td colspan='4'>" + _detalle("Any 3.0", x) + _detalle("Any 2.0", y) + "</td></tr>";
  }
  h += "</table>";
  _panel("Examen", h);
  document.querySelectorAll("#traza .filtros button").forEach(b => b.onclick = () => { _filtro = b.dataset.f; _pintar(); });
  document.querySelectorAll("#traza tr.fila").forEach(tr => tr.onclick = () => { const d = $("det-" + tr.dataset.n); d.hidden = !d.hidden; });
}
let _reloj = null;
async function _verExamen() {
  clearTimeout(_reloj);
  try { _datos = await _json("/any3/examen?todas=true"); } catch (e) { return _fallo("Examen", e); }
  if (!_datos.any3 && !_datos.any2) { _panel("Examen", "<p>Todavía no hay ningún examen guardado. Toca «Correr examen».</p>"); return; }
  _pintar();
  const vivo = ["any3", "any2"].some(m => _datos[m] && ["corriendo", "en espera"].includes(_datos[m].estado));
  if (vivo) _reloj = setTimeout(() => { if ($("traza").querySelector(".resumen")) _verExamen(); }, 5000);   // se actualiza solo
}
$("b-ver").onclick = _verExamen;
$("b-exportar").onclick = async () => {
  let d;
  try { d = await _json("/any3/examen?todas=true"); } catch (e) { return _fallo("Exportar", e); }
  const f3 = {}, f2 = {}; ((d.any3 || {}).todas || []).forEach(f => f3[f.n] = f); ((d.any2 || {}).todas || []).forEach(f => f2[f.n] = f);
  const ns = [...new Set([...Object.keys(f3), ...Object.keys(f2)].map(Number))].sort((x, y) => x - y);
  const col = (f, k) => f ? (Array.isArray(f[k]) ? f[k].join(", ") : (k === "ok" ? (f.ok === null || f.ok === undefined ? "A OJO" : (f.ok ? "BIEN" : "MAL")) : (f[k] ?? ""))) : "";
  const cab = ["#", "tipo", "pregunta", "any3_resultado", "any3_locales", "any3_faltaron", "any3_sobraron", "any3_problema", "any3_respuesta",
               "any2_resultado", "any2_locales", "any2_faltaron", "any2_sobraron", "any2_problema", "any2_respuesta"];
  const filas = [cab].concat(ns.map(n => { const x = f3[n], y = f2[n], b = x || y;
    return [n, b.tipo, b.pregunta].concat(["ok", "eligio", "faltan", "sobran", "problema", "respuesta"].map(k => col(x, k)))
                                  .concat(["ok", "eligio", "faltan", "sobran", "problema", "respuesta"].map(k => col(y, k))); }));
  const csv = "\\ufeff" + filas.map(r => r.map(v => '"' + String(v).replace(/"/g, '""') + '"').join(";")).join("\\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  a.download = "examen_any3_vs_any2.csv"; a.click();
};
$("b-vacios").onclick = async () => {
  let j;
  try { j = await _json("/any3/vacios"); } catch (e) { return _fallo("Datos faltantes", e); }
  const lista = (xs) => (xs || []).map(x => "<li>" + _esc(x.fecha) + " — " + _esc(x.mensaje) + "</li>").join("") || "<li>nada</li>";
  _panel("Datos faltantes", "<p>Revisadas: " + _esc(j.revisadas) + "</p><h2>No estaba en la base</h2><ul>" + lista(j.no_estaba_en_la_base) +
    "</ul><h2>Solo «probablemente»</h2><ul>" + lista(j.solo_probable) + "</ul><h2>El vigilante corrigió</h2><ul>" + lista(j.el_vigilante_corrigio) + "</ul>");
};
</script>
"""


def _resumen_examenes() -> dict:
    try:
        from .almacen import leer
        return {m: {k: v for k, v in e.items() if k in ("estado", "modelo", "bien", "total", "porcentaje", "progreso")}
                for m, e in leer().items()}
    except Exception as e:
        return {"error": repr(e)[:200]}


@router.post("/examen")
async def correr_examen(motor: str = "ambos", modelo: str = "", conjunto: str = "todo", _u=Depends(_usuario_panel)):
    """Corre el examen con Any 3.0, con Any 2.0 o con los dos (uno detrás del otro), en segundo plano.
    El avance y los resultados se guardan en la base (sobreviven a reinicios y a varios procesos)."""
    from .almacen import guardar, leer
    from .examen import correr, total_casos
    if conjunto not in ("todo", "final"):
        raise HTTPException(400, "conjunto debe ser todo o final")
    motores = ["any3", "any2"] if motor == "ambos" else [motor]
    if any(m not in ("any3", "any2") for m in motores):
        raise HTTPException(400, "motor debe ser any3, any2 o ambos")
    actuales = leer()
    if any(actuales.get(m, {}).get("estado") in ("corriendo", "en espera") for m in motores):
        return {"estado": "ya hay un examen corriendo: toca «Ver examen»"}
    estados = {}
    for m in motores:
        estados[m] = {"estado": "en espera", "progreso": 0, "total_casos": total_casos(conjunto), "todas": [],
                      "conjunto": conjunto,
                      "modelo": (modelo or config.modelo()) if m == "any3" else "Any 2.0 (sus modelos)"}
        guardar(m, estados[m])

    async def tarea():
        for m in motores:
            e = estados[m]
            e.update(estado="corriendo", inicio=datetime.now(ZONA_HORARIA).isoformat())
            guardar(m, e)

            def progreso(fila, e=e, m=m):
                e["progreso"] = e.get("progreso", 0) + 1
                e["todas"].append(fila)
                try:
                    guardar(m, e)          # cada pregunta queda guardada apenas termina
                except Exception:
                    pass
            try:
                res = await correr(m, progreso=progreso, modelo=modelo if m == "any3" else "", conjunto=conjunto)
                e.update(res, estado="terminado")
            except Exception as ex:
                e.update(estado="falló", error=repr(ex)[:500])
            guardar(m, e)
    asyncio.create_task(tarea())
    return {"estado": "corriendo: " + " y luego ".join("Any 3.0" if m == "any3" else "Any 2.0" for m in motores)}


@router.get("/examen")
async def ver_examen(todas: bool = False, _u=Depends(_usuario_panel)):
    from .almacen import leer
    datos = leer()
    if todas:
        return datos
    return {m: {k: v for k, v in e.items() if k != "todas"} for m, e in datos.items()}


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
