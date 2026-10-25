"""
Corredor del banco de pruebas de Any 2.0.

Reproduce conversaciones reales turno por turno (con su historial y con la
fecha simulada) contra el núcleo completo, y califica cada respuesta:
  - flujo:       ¿el router eligió el especialista esperado?
  - debe:        todos estos textos deben aparecer
  - debe_alguno: al menos uno debe aparecer
  - no_debe:     ninguno debe aparecer
  - adjunto:     el tipo de adjunto esperado (imagen | documento | ubicacion)
  - reglas globales (todas las respuestas): sin pisos/niveles fuera de la Torre,
    sin **negrita doble**, sin IDs ni JSON, nunca vacía, teléfonos reales,
    sin lugares inventados.
El "criterio" es para revisión humana (o, más adelante, un juez IA).

Uso (desde backend/):
    python -m any.evals.correr                        # todo, con los modelos configurados
    python -m any.evals.correr --llm simulado:x       # sin clave: prueba la plomería
    python -m any.evals.correr --flujo servicios_mall --ver
    python -m any.evals.correr --caso real-03 --reporte /ruta/reporte.md
Los teléfonos de prueba empiezan por "eval-" y se borran antes de cada conversación.
"""
from __future__ import annotations

import argparse
import asyncio
import glob
import json
import logging
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta

import yaml

AQUI = os.path.dirname(os.path.abspath(__file__))


def _norm(t: str) -> str:
    from ..conocimiento.texto import normalizar
    return normalizar(t or "")


def _aparece(esperado: str, texto: str) -> bool:
    e = str(esperado)
    if re.fullmatch(r"[\d\s\-+]{7,}", e):                 # un teléfono: se comparan solo los dígitos
        return re.sub(r"\D", "", e) in re.sub(r"\D", "", texto)
    return _norm(e) in _norm(texto)


_PISO = re.compile(r"\b(piso|nivel|planta)\s+(\d+|uno|dos|tres|cuatro|cinco|seis)\b", re.I)
_TEL = re.compile(r"(?<!\d)(?:\+?57[\s-]?)?(3\d{2}[\s-]?\d{3}[\s-]?\d{4})(?!\d)")
LUGARES_INVENTADOS = ["galeria comercial", "segundo piso", "primer piso", "tercer piso", "sotano", "mezzanine"]


def reglas_globales(texto: str, flujo: str, telefonos_reales: set) -> list[str]:
    fallas = []
    if not texto.strip():
        fallas.append("respuesta vacía")
    if flujo != "torre_medica" and _PISO.search(texto):
        fallas.append(f"menciona piso/nivel: {_PISO.search(texto).group(0)}")
    if "**" in texto:
        fallas.append("negrita doble **")
    if re.search(r"\bID:\s*\d+|\[TIENDA", texto):
        fallas.append("ID interno visible")
    if texto.strip().startswith("{") or '"flujo"' in texto:
        fallas.append("JSON o texto interno visible")
    if re.search(r"[\{\[]\s*LISTA?\s*[\}\]]", texto, re.I):
        fallas.append("marca {LISTA} visible")
    if re.search(r"(?i)\bel puente de informaci[oó]n\b", texto):
        fallas.append("«El Puente de Información» (es Punto de Información)")
    if re.search(r"\b(recib[ií]s|ten[eé]s|pod[eé]s|quer[eé]s)\b", texto):
        fallas.append("voseo (en Colombia es tuteo)")
    n = _norm(texto)
    for l in LUGARES_INVENTADOS:
        if l in n:
            fallas.append(f"lugar inventado: {l}")
    for m in _TEL.findall(texto):
        d = re.sub(r"\D", "", m)[-10:]
        if d not in telefonos_reales:
            fallas.append(f"teléfono que no existe en la base: {m}")
    if "[simulado]" in texto:
        pass  # con el modelo simulado no se califica el estilo
    return fallas


def telefonos_de_la_base(db) -> set:
    from sqlalchemy import text
    tels = {"3174320138", "123"}
    for tabla, col in (("stores", "phone"), ("mall_info", "phone")):
        try:
            for (v,) in db.execute(text(f"SELECT {col} FROM {tabla}")):
                for d in re.findall(r"3\d{9}", re.sub(r"\D", "", v or "")):
                    tels.add(d)
        except Exception:
            db.rollback()
    try:
        for (v,) in db.execute(text("SELECT parking FROM mall_info")):
            tels |= set(re.findall(r"3\d{9}", re.sub(r"[\s-]", "", v or "")))
    except Exception:
        db.rollback()
    return tels


def cargar_casos(rutas: list[str]) -> list[dict]:
    casos = []
    for r in rutas:
        with open(r, encoding="utf-8") as f:
            for c in yaml.safe_load(f) or []:
                c["_archivo"] = os.path.basename(r)
                casos.append(c)
    return casos


async def correr(args) -> dict:
    from models.database import SessionLocal
    from ..flujos import FLUJOS
    from ..nucleo.guardias import borrar_datos
    from ..nucleo.harness import procesar
    from ..config import ZONA_HORARIA

    rutas = [args.casos] if args.casos else sorted(glob.glob(os.path.join(AQUI, "casos", "*.yaml")))
    casos = cargar_casos(rutas)
    if args.caso:
        casos = [c for c in casos if c["id"] == args.caso]
    db = SessionLocal()
    tels = telefonos_de_la_base(db)
    resultados = []
    for conv in casos:
        telefono = f"eval-{conv['id']}"[:20]
        borrar_datos(db, telefono)
        fecha = datetime.fromisoformat(str(conv.get("fecha_simulada", "2026-10-21"))).replace(hour=15)
        fecha = fecha.replace(tzinfo=ZONA_HORARIA)
        for i, turno in enumerate(conv.get("turnos") or []):
            ahora = fecha + timedelta(minutes=2 * i)
            r = await procesar(db, telefono, conv.get("cliente", ""), turno["pregunta"], ahora=ahora, modo="eval")
            texto = "\n".join(r.mensajes())
            esperado = turno.get("flujo")
            evaluar = (not args.flujo or esperado == args.flujo) and \
                      (not args.solo_construidos or esperado in FLUJOS)
            if not evaluar:
                continue
            fallas = []
            if esperado and r.flujo != esperado:
                fallas.append(f"flujo {r.flujo} (esperado {esperado})")
            simulado = "[simulado]" in texto
            if not simulado:
                for x in turno.get("debe") or []:
                    if not _aparece(x, texto):
                        fallas.append(f"falta «{x}»")
                alguno = turno.get("debe_alguno") or []
                if alguno and not any(_aparece(x, texto) for x in alguno):
                    fallas.append(f"falta alguno de {alguno}")
                promo = (r.meta.get("promo") or {}).get("nombre")
                sin_promo = "\n".join(l for l in texto.split("\n") if not (promo and _norm(promo) in _norm(l)))
                for x in turno.get("no_debe") or []:   # la línea de la novedad del día no cuenta como error
                    if _aparece(x, sin_promo):
                        fallas.append(f"sobra «{x}»")
                fallas += reglas_globales(texto, r.flujo, tels)
            tipo_adj = turno.get("adjunto")
            if tipo_adj == "carta":   # la carta puede ir como foto, PDF o link
                hay = any(a.tipo in ("imagen", "documento") for a in r.adjuntos) or "http" in texto
            else:
                hay = any(a.tipo == tipo_adj for a in r.adjuntos)
            if tipo_adj and not hay:
                fallas.append(f"falta adjunto {turno['adjunto']}")
            res = {"conversacion": conv["id"], "turno": i + 1, "pregunta": turno["pregunta"],
                   "flujo_esperado": esperado, "flujo": r.flujo, "construido": esperado in FLUJOS,
                   "ok": not fallas, "fallas": fallas, "respuesta": texto, "criterio": turno.get("criterio", ""),
                   "depende_de_dato": turno.get("depende_de_dato"), "alertas": r.meta.get("traza", {}).get("alertas"),
                   "ms": r.meta.get("traza", {}).get("ms_total"), "tokens": r.meta.get("traza", {}).get("tokens")}
            resultados.append(res)
            if args.ver or not res["ok"]:
                marca = "✅" if res["ok"] else "❌"
                print(f"{marca} {conv['id']} t{i + 1} «{turno['pregunta'][:60]}» → {r.flujo}"
                      + (f" | {'; '.join(fallas)}" if fallas else ""))
                if args.ver:
                    print("   " + texto[:600].replace("\n", "\n   "))
        borrar_datos(db, telefono)
    db.close()
    return resumir(resultados)


def resumir(resultados: list[dict]) -> dict:
    por_flujo = defaultdict(lambda: {"total": 0, "ok": 0, "ruta_ok": 0})
    for r in resultados:
        f = por_flujo[r["flujo_esperado"] or "-"]
        f["total"] += 1
        f["ok"] += r["ok"]
        f["ruta_ok"] += r["flujo"] == r["flujo_esperado"]
    total = len(resultados)
    return {"total": total, "ok": sum(r["ok"] for r in resultados),
            "ruta_ok": sum(r["flujo"] == r["flujo_esperado"] for r in resultados),
            "por_flujo": dict(por_flujo), "resultados": resultados}


def reporte_md(res: dict, modelo: str) -> str:
    l = [f"# Banco de pruebas Any 2.0 — {datetime.now():%Y-%m-%d %H:%M}", "",
         f"Modelo: `{modelo}`  ", f"Turnos evaluados: {res['total']} · correctos: {res['ok']} · "
         f"router acertó: {res['ruta_ok']}", "", "| Flujo | Correctos | Router acertó |", "|---|---|---|"]
    for f, d in sorted(res["por_flujo"].items()):
        l.append(f"| {f} | {d['ok']}/{d['total']} | {d['ruta_ok']}/{d['total']} |")
    l += ["", "## Fallas", ""]
    for r in res["resultados"]:
        if r["ok"]:
            continue
        l += [f"**{r['conversacion']} · turno {r['turno']}** — «{r['pregunta']}» → `{r['flujo']}` "
              f"(esperado `{r['flujo_esperado']}`)", "", "- " + "\n- ".join(r["fallas"])]
        if r["depende_de_dato"]:
            l.append(f"- depende de un dato que debe entregar el mall: {r['depende_de_dato']}")
        if r["criterio"]:
            l.append(f"- criterio: {r['criterio']}")
        l += ["", "```", r["respuesta"][:1200], "```", ""]
    return "\n".join(l)


def main():
    p = argparse.ArgumentParser(description="Banco de pruebas de Any 2.0")
    p.add_argument("--casos", help="archivo YAML (por defecto todos los de evals/casos/)")
    p.add_argument("--caso", help="solo una conversación (id)")
    p.add_argument("--flujo", help="solo los turnos de un flujo")
    p.add_argument("--solo-construidos", action="store_true", help="solo turnos de flujos ya construidos")
    p.add_argument("--llm", help="modelo para router y flujos, ej. groq:openai/gpt-oss-120b o simulado:x")
    p.add_argument("--reporte", help="ruta del reporte .md")
    p.add_argument("--json", help="ruta del resultado .json")
    p.add_argument("--ver", action="store_true", help="imprime cada respuesta")
    args = p.parse_args()
    if args.llm:
        os.environ["ANY_LLM_ROUTER"] = args.llm
        os.environ["ANY_LLM_FLUJOS"] = args.llm
    logging.disable(logging.WARNING)
    res = asyncio.run(correr(args))
    from ..config import cfg
    modelo = f"router {cfg().llm_router} · flujos {cfg().llm_flujos}"
    print(f"\n{res['ok']}/{res['total']} turnos correctos · router acertó {res['ruta_ok']}/{res['total']}")
    for f, d in sorted(res["por_flujo"].items()):
        print(f"  {f:18} {d['ok']:>3}/{d['total']:<3}  router {d['ruta_ok']}/{d['total']}")
    if args.reporte:
        with open(args.reporte, "w", encoding="utf-8") as f:
            f.write(reporte_md(res, modelo))
        print(f"Reporte: {args.reporte}")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
    sys.exit(0)


if __name__ == "__main__":
    main()