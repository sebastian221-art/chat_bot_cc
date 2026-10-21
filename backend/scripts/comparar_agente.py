# 📄 ARCHIVO: backend/scripts/comparar_agente.py  ← ARCHIVO NUEVO
"""
REGRESIÓN LADO A LADO: las 40 preguntas reales de las trazas del 20-21/10
se le hacen al AGENTE (services/agente.py) y al ORQUESTADOR actual, contra
la MISMA base de datos, y se genera un reporte con verificaciones
automáticas de las reglas del mall. Así se decide con datos, no con
sensaciones, y antes de cada entrega se comprueba que nada se rompió.

CÓMO CORRERLO (desde backend/, con tu clave real de Groq):

  1) Base de prueba a partir del export del panel (recomendado):
     - Panel → Tiendas → Exportar  → locales.csv
     - Panel → Eventos → Exportar  → eventos.csv
     (sorteos/promos/cine/info del mall se copian de la BD con --desde-bd)

     DATABASE_URL='sqlite:////tmp/comparar.db' GROQ_API_KEY='TU_CLAVE' \
     JWT_SECRET=x WHATSAPP_TOKEN=x WHATSAPP_PHONE_ID=x VERIFY_TOKEN=x SYNC_AUTOMATICO=0 DEBUG=0 \
     python3 scripts/comparar_agente.py --locales locales.csv --eventos eventos.csv

  2) O directamente contra una COPIA de la base (nunca la de producción):
     DATABASE_URL='postgresql+pg8000://...copia...' GROQ_API_KEY='TU_CLAVE' ... \
     python3 scripts/comparar_agente.py

  Opciones:
     --solo agente|orquestador   corre solo uno
     --preguntas archivo.txt     una pregunta por línea (por defecto las 40 de las trazas)
     --salida reporte.md         ruta del reporte (por defecto comparacion_agente.md)

Usa un teléfono ficticio por "conversación" para que los seguimientos
("y de ropa?", "ese descuento en qué es?") tengan historial, igual que en
WhatsApp. No envía nada por WhatsApp ni toca el switch.
"""
import argparse, asyncio, csv, io, json, os, re, sys, time, unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import logging
logging.disable(logging.WARNING)

import main  # noqa: registra modelos
from models.database import SessionLocal, create_tables
from models.conversation import Conversation
from models.orchestrator_trace import OrchestratorTrace

# ── Las 40 preguntas reales, agrupadas por conversación (mismo cliente) ──
CONVERSACIONES = {
    "Juan": [
        "Quiero comprar unos tenis para correr",
        "Dime todos los almacenes de zapatos",
        "Qué significa nivel 2",
        "Quiero comprar una boleta para ir a cine",
        "Quiero reservar en línea",
        "Cuánto vale la boleta",
        "Mero Mérito tiene instagram?",
        "Tienes el instagram de Chevignon?",
        "De qué locales tienes instagram?",
        "Quiero inscribir a mis hijos en run run kids",
        "Cómo participo en el concurso de disfraces",
        "Quiero alquilar un salón de eventos para una fiesta",
        "Quiero poner publicidad en el centro comercial",
        "Qué eventos hay",
        "Me puedes decir la dirección del CC",
        "Necesito una peluquería",
        "Dónde puedo comer hamburguesas",
        "Qué películas hay",
        "Hay promociones",
    ],
    "Contabilidad": [
        "POR FAVOR ME DICES QUE PLANES FAMILIARES PUEDO HACER ESTE FIN DE SEMANA EN EL CENTRO COMERCIAL EL PUENTE",
        "sabes de alguna promoción en productos ?",
        "promociones en los locales por favor",
    ],
    "Tatiana": [
        "Holaaaa",
        "Quiero saber donde quedan las oficinas de la administracion",
        "Cual es el siguiente evento en el cc",
        "Y de promociones? Cuales locales tiene promociones?",
        "Ese descuento en que es?",
        "Y de ropa?",
        "La misa a que hora es?",
    ],
    "Delis": [
        "Me regalas el número de Jarris",
        "Me regalas el número de la barra",
        "Tienes la carta de la barra",
        "La carta de Mercagan por fa",
        "Me puedes decir q locales venden hamburguesas",
        "Y cuales venden cerveza",
        "Cuáles locales venden ropa",
        "Tengo un grado en q marcas puedo comprar algo para el grado",
        "Vestido",
        "Valor del parqueadero",
        "Hay hora de parqueadero gratis",
    ],
    "Extra (no preparadas)": [
        "Como registro mis facturas para el sorteo",
        "Puedo entrar con mi perro?",
        "Cuál me recomiendas para comer rico?",
        "Hay cajero de Bancolombia?",
        "A qué hora cierran hoy?",
        "Qué dan hoy en el cine después de las 7?",
    ],
}


def _plano(t):
    t = (t or "").lower()
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")


# ── Verificaciones automáticas de las reglas del mall ──
def verificar(pregunta: str, respuesta: str, traza: OrchestratorTrace | None, db) -> list[str]:
    fallas = []
    r = respuesta or ""
    p = _plano(r)
    if not r.strip():
        fallas.append("respuesta vacía")
    if re.search(r"\b(nivel|piso)\s*\d", p) and "torre" not in p:
        fallas.append("menciona nivel/piso")
    if "**" in r:
        fallas.append("negrita markdown (**)")
    if "<think" in p or "tool_call" in p or '{"' in r:
        fallas.append("se coló razonamiento/JSON")
    if re.search(r"comparto lo que tengo de su carta|te la comparto 👇|aquí tienes la carta 👇", p) and "http" not in p and (not traza or traza.fotos_enviadas == 0):
        fallas.append("dice que comparte carta pero no manda nada")
    if "punto de informacion" in p and any(k in _plano(pregunta) for k in ("carta", "numero", "instagram", "venden", "comer", "zapatos", "ropa")):
        fallas.append("manda al Punto de Información en una pregunta resoluble")
    # Equidad: si la traza dice cuántos locales devolvió la búsqueda, todos deben estar
    try:
        if traza:
            for paso in json.loads(traza.pasos or "[]"):
                m = re.search(r"→ (\d+) locales|\"total\": (\d+)", paso.get("detalle", ""))
                if m and "buscar_locales" in paso.get("detalle", "") or (m and "Categoría" in paso.get("detalle", "")):
                    n = int(m.group(1) or m.group(2))
                    if n and r.count("•") < n:
                        fallas.append(f"equidad: devolvió {n} locales y la respuesta lista {r.count('•')}")
                    break
    except Exception:
        pass
    if len(r) > 1800:
        fallas.append(f"muy larga ({len(r)} chars)")
    return fallas


async def correr(flujo: str, db, phone: str, nombre: str, pregunta: str) -> tuple[str, float, OrchestratorTrace | None]:
    db.add(Conversation(phone_number=phone, user_name=nombre, role="user", message=pregunta)); db.commit()
    t0 = time.time()
    try:
        if flujo == "agente":
            from services.agente import procesar_con_agente
            res = await procesar_con_agente(db, phone, pregunta, modo="prueba", user_name=nombre)
        else:
            from services.orchestrator import procesar_con_orquestador
            res = await procesar_con_orquestador(db, phone, pregunta, modo="prueba", user_name=nombre)
        texto = res.get("text", "")
    except Exception as e:
        texto = f"[EXCEPCIÓN: {e}]"
    dt = time.time() - t0
    db.add(Conversation(phone_number=phone, user_name=nombre, role="assistant", message=texto)); db.commit()
    tr = (db.query(OrchestratorTrace).filter(OrchestratorTrace.phone_number == phone)
          .order_by(OrchestratorTrace.id.desc()).first())
    return texto, dt, tr


def cargar_csvs(db, locales_csv: str | None, eventos_csv: str | None):
    from models.store import Store
    from models.event import Event
    if locales_csv:
        with open(locales_csv, encoding="utf-8-sig") as f:
            filas = list(csv.DictReader(f))
        db.query(Store).delete()
        for r in filas:
            db.add(Store(name=r.get("name", "").strip(), local_number=r.get("local_number") or None, floor=r.get("floor") or "Por confirmar",
                         category=r.get("category") or "Por confirmar", description=r.get("description") or None,
                         schedule=r.get("schedule") or None, phone=r.get("phone") or None, location_hint=r.get("location_hint") or None,
                         tags=r.get("tags") or None, photo_url=r.get("photo_url") or None, extra_info=r.get("extra_info") or None,
                         catalogo_link=r.get("catalogo_link") or None, active=True))
        db.commit()
        print(f"  ✓ {len(filas)} locales cargados de {locales_csv}")
    if eventos_csv:
        with open(eventos_csv, encoding="utf-8-sig") as f:
            filas = list(csv.DictReader(f))
        db.query(Event).delete()
        for r in filas:
            db.add(Event(name=r["name"], date=r.get("date") or "", time=r.get("time") or None, location=r.get("location") or "",
                         description=r.get("description") or None, priority=int(r.get("priority") or 3)))
        db.commit()
        print(f"  ✓ {len(filas)} eventos cargados de {eventos_csv}")


async def main_():
    ap = argparse.ArgumentParser()
    ap.add_argument("--locales"); ap.add_argument("--eventos")
    ap.add_argument("--solo", choices=["agente", "orquestador"])
    ap.add_argument("--preguntas"); ap.add_argument("--salida", default="comparacion_agente.md")
    a = ap.parse_args()

    create_tables()
    db = SessionLocal()
    cargar_csvs(db, a.locales, a.eventos)

    convs = CONVERSACIONES
    if a.preguntas:
        convs = {"Personalizadas": [l.strip() for l in open(a.preguntas, encoding="utf-8") if l.strip()]}
    flujos = [a.solo] if a.solo else ["agente", "orquestador"]

    resultados = []  # (cliente, pregunta, {flujo: (texto, seg, fallas)})
    total = sum(len(v) for v in convs.values())
    i = 0
    for cliente, preguntas in convs.items():
        phones = {f: f"test_{f}_{_plano(cliente)[:6]}" for f in flujos}
        for ph in phones.values():
            db.query(Conversation).filter(Conversation.phone_number == ph).delete()
            db.query(OrchestratorTrace).filter(OrchestratorTrace.phone_number == ph).delete()
        db.commit()
        for preg in preguntas:
            i += 1
            fila = {}
            for f in flujos:
                texto, seg, tr = await correr(f, db, phones[f], cliente.split(" ")[0], preg)
                fila[f] = (texto, seg, verificar(preg, texto, tr, db), tr)
            resultados.append((cliente, preg, fila))
            marca = " | ".join(f"{f}: {'✅' if not fila[f][2] else '⚠️ ' + ', '.join(fila[f][2])} ({fila[f][1]:.1f}s)" for f in flujos)
            print(f"[{i}/{total}] {preg[:55]:55} → {marca}")

    # ── Reporte ──
    out = io.StringIO()
    out.write(f"# Comparación agente vs orquestador — {time.strftime('%d/%m/%Y %H:%M')}\n\n")
    for f in flujos:
        n_ok = sum(1 for _, _, fila in resultados if not fila[f][2])
        prom = sum(fila[f][1] for _, _, fila in resultados) / max(1, len(resultados))
        out.write(f"- **{f}**: {n_ok}/{len(resultados)} sin fallas automáticas · {prom:.1f}s promedio\n")
    out.write("\n> Las verificaciones automáticas solo detectan violaciones de reglas (niveles, equidad, vacío, markdown, Punto de Información como salida fácil). La CALIDAD de la respuesta hay que leerla.\n\n")
    for cliente, preg, fila in resultados:
        out.write(f"---\n### 👤 {cliente}: «{preg}»\n\n")
        for f in flujos:
            texto, seg, fallas, tr = fila[f]
            herr = tr.herramienta_elegida if tr else "?"
            out.write(f"**{f.upper()}** · {seg:.1f}s · `{herr}`" + (f" · ⚠️ {', '.join(fallas)}" if fallas else " · ✅") + "\n\n")
            out.write("```\n" + (texto or "").strip() + "\n```\n\n")
    Path(a.salida).write_text(out.getvalue(), encoding="utf-8")
    print(f"\n📄 Reporte: {a.salida}")


if __name__ == "__main__":
    asyncio.run(main_())