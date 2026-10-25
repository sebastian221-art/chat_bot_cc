"""
Banco de pruebas contra el servidor REAL (Railway), sin WhatsApp.

Manda todas las preguntas de evals/casos/*.yaml al endpoint /any/prueba del servidor en
producción —el mismo Any 2.0, la misma base de datos y el mismo Groq que atienden a los
clientes— y arma un reporte con TODAS las respuestas (no solo las fallas), para revisarlas.

No toca a ningún cliente: usa teléfonos de prueba "prueba-banco-…" que se borran antes y
después de cada conversación. Las respuestas no se envían por WhatsApp.

Uso (desde backend/, con el venv activo):
    python -m any.evals.produccion
    python -m any.evals.produccion --caso real-04
    python -m any.evals.produccion --url https://chatbotcc-production.up.railway.app --reporte produccion.md

Pide el usuario y la contraseña del panel (o léelos de ANY_PANEL_USUARIO / ANY_PANEL_CLAVE).
"""
from __future__ import annotations

import argparse
import getpass
import glob
import os
import sys
import time
from datetime import datetime

import httpx

from .correr import AQUI, _aparece, _norm, cargar_casos, reglas_globales, resumir

URL_POR_DEFECTO = "https://chatbotcc-production.up.railway.app"


def _login(cliente: httpx.Client, url: str) -> str:
    usuario = os.environ.get("ANY_PANEL_USUARIO") or input("Usuario del panel: ").strip()
    clave = os.environ.get("ANY_PANEL_CLAVE") or getpass.getpass("Contraseña del panel: ")
    r = cliente.post(f"{url}/auth/login", json={"username": usuario, "password": clave})
    if r.status_code != 200:
        sys.exit(f"No se pudo entrar al panel ({r.status_code}): {r.text[:200]}")
    token = (r.json() or {}).get("token")
    if not token:
        sys.exit("El login no devolvió token.")
    return token


def _promo_de(traza: dict) -> str | None:
    for p in (traza or {}).get("pasos") or []:
        if p.get("paso") == "promocion_mostrada" and isinstance(p.get("detalle"), dict):
            return p["detalle"].get("nombre")
    return None


def correr(args) -> dict:
    rutas = sorted(glob.glob(os.path.join(AQUI, "casos", "*.yaml")))
    casos = cargar_casos(rutas)
    if args.caso:
        casos = [c for c in casos if c["id"] == args.caso]
    url = args.url.rstrip("/")
    cliente = httpx.Client(timeout=120)
    try:
        estado = cliente.get(f"{url}/any/estado").json()
        print(f"Servidor: {url} · Any 2.0 responde WhatsApp: {estado.get('any2_responde_whatsapp')} · "
              f"modo: {estado.get('modo')} · modelo: {estado.get('modelo')}")
    except Exception:
        print(f"Servidor: {url} (no respondió /any/estado; sigo igual)")
    token = _login(cliente, url)
    cab = {"Authorization": f"Bearer {token}"}
    resultados = []
    total_turnos = sum(len(c.get("turnos") or []) for c in casos)
    n = 0
    for conv in casos:
        telefono = f"prueba-banco-{conv['id']}"[:20]
        cliente.delete(f"{url}/any/prueba/{telefono}", headers=cab)
        base = str(conv.get("fecha_simulada", "2026-10-21"))
        for i, turno in enumerate(conv.get("turnos") or []):
            n += 1
            fecha = f"{base} 15:{2 * i:02d}"
            t0 = time.time()
            try:
                r = cliente.post(f"{url}/any/prueba", headers=cab, json={
                    "mensaje": turno["pregunta"], "telefono": telefono, "nombre": conv.get("cliente", "Juan"),
                    "fecha": fecha})
                datos = r.json() if r.status_code == 200 else {"mensajes": [], "flujo": f"ERROR {r.status_code}",
                                                                 "error": r.text[:300]}
            except Exception as e:
                datos = {"mensajes": [], "flujo": "ERROR", "error": str(e)[:300]}
            texto = "\n".join(datos.get("mensajes") or [])
            flujo = datos.get("flujo") or ""
            traza = datos.get("traza") or {}
            esperado = turno.get("flujo")
            fallas = []
            if datos.get("error"):
                fallas.append(f"error del servidor: {datos['error']}")
            if esperado and flujo != esperado:
                fallas.append(f"flujo {flujo} (esperado {esperado})")
            for x in turno.get("debe") or []:
                if not _aparece(x, texto):
                    fallas.append(f"falta «{x}»")
            alguno = turno.get("debe_alguno") or []
            if alguno and not any(_aparece(x, texto) for x in alguno):
                fallas.append(f"falta alguno de {alguno}")
            promo = _promo_de(traza)
            sin_promo = "\n".join(l for l in texto.split("\n") if not (promo and _norm(promo) in _norm(l)))
            for x in turno.get("no_debe") or []:
                if _aparece(x, sin_promo):
                    fallas.append(f"sobra «{x}»")
            # sin acceso a la base desde aquí: el chequeo de teléfonos lo hacen las guardias del servidor
            fallas += [f for f in reglas_globales(texto, flujo, set()) if not f.startswith("teléfono")]
            tipo_adj = turno.get("adjunto")
            adj = datos.get("adjuntos") or []
            if tipo_adj == "carta":
                hay = any(a.get("tipo") in ("imagen", "documento") for a in adj) or "http" in texto
            else:
                hay = any(a.get("tipo") == tipo_adj for a in adj)
            if tipo_adj and not hay:
                fallas.append(f"falta adjunto {tipo_adj}")
            res = {"conversacion": conv["id"], "turno": i + 1, "pregunta": turno["pregunta"],
                   "flujo_esperado": esperado, "flujo": flujo, "construido": True, "ok": not fallas,
                   "fallas": fallas, "respuesta": texto, "criterio": turno.get("criterio", ""),
                   "adjuntos": [a.get("tipo") for a in adj], "promo": promo,
                   "alertas": traza.get("alertas"), "ms": round((time.time() - t0) * 1000),
                   "tokens": traza.get("tokens")}
            resultados.append(res)
            marca = "✅" if res["ok"] else "❌"
            print(f"[{n}/{total_turnos}] {marca} {conv['id']} t{i + 1} «{turno['pregunta'][:55]}» → {flujo}"
                  + (f" | {'; '.join(fallas)}" if fallas else ""))
        cliente.delete(f"{url}/any/prueba/{telefono}", headers=cab)
    cliente.close()
    return resumir(resultados)


def reporte(res: dict, url: str) -> str:
    l = [f"# Any 2.0 en producción — {datetime.now():%Y-%m-%d %H:%M}", "",
         f"Servidor: `{url}`  ", f"Turnos: {res['total']} · correctos: {res['ok']} · router acertó: {res['ruta_ok']}",
         "", "| Flujo | Correctos | Router acertó |", "|---|---|---|"]
    for f, d in sorted(res["por_flujo"].items()):
        l.append(f"| {f} | {d['ok']}/{d['total']} | {d['ruta_ok']}/{d['total']} |")
    l += ["", "## Todas las respuestas", ""]
    previo = None
    for r in res["resultados"]:
        if r["conversacion"] != previo:
            l += ["", f"### {r['conversacion']}", ""]
            previo = r["conversacion"]
        marca = "✅" if r["ok"] else "❌"
        l.append(f"**{marca} t{r['turno']}** — «{r['pregunta']}» → `{r['flujo']}`"
                 + (f" (esperado `{r['flujo_esperado']}`)" if r['flujo_esperado'] and r['flujo'] != r['flujo_esperado'] else "")
                 + f" · {r['ms']} ms")
        l.append("")
        for f in r["fallas"]:
            l.append(f"- ❌ {f}")
        if r["criterio"]:
            l.append(f"- criterio: {r['criterio']}")
        if r["adjuntos"]:
            l.append(f"- adjuntos: {', '.join(r['adjuntos'])}")
        if r["alertas"]:
            l.append(f"- correcciones de las guardias: {'; '.join(map(str, r['alertas']))}")
        l += ["", "```", r["respuesta"] or "(sin respuesta)", "```", ""]
    return "\n".join(l)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.environ.get("ANY_URL_PRODUCCION", URL_POR_DEFECTO))
    ap.add_argument("--caso")
    ap.add_argument("--reporte", default="reporte_produccion.md")
    args = ap.parse_args()
    res = correr(args)
    print(f"\n{res['ok']}/{res['total']} turnos correctos · router acertó {res['ruta_ok']}/{res['total']}")
    for f, d in sorted(res["por_flujo"].items()):
        print(f"  {f:<20} {d['ok']}/{d['total']}")
    with open(args.reporte, "w", encoding="utf-8") as fh:
        fh.write(reporte(res, args.url))
    print(f"Reporte con todas las respuestas: {args.reporte}")


if __name__ == "__main__":
    main()