"""
La ÚNICA regla de promociones de Any 2.0 (en el sistema viejo había cuatro que se pisaban).

Pedido del centro comercial: cada respuesta promociona una novedad vigente (evento, sorteo
o promoción), rotando para que TODAS se muestren. Los parámetros están en datos/reglas.yaml
(temas sin promo, tope por sesión, espaciado, primer mensaje).

Cómo funciona:
  1. elegir(): antes del flujo, decide en código SI va promo y CUÁL:
     la de mayor prioridad entre las vigentes que aún no se mostraron en la sesión
     (a igual prioridad, la más próxima). Si ya se mostraron todas, la que se mostró hace más.
  2. La IA la menciona "de pasada", en una línea al final, con los datos que recibe.
  3. asegurar(): después del flujo, si la IA no la mencionó, se agrega una línea con sus datos
     reales. Así se cumple SIEMPRE, sin inventar nada. Se registra en promotions_shown.
"""
from __future__ import annotations

import os
from datetime import date, timedelta, timezone

import yaml

from ..config import cfg
from ..conocimiento.texto import normalizar
from ..conocimiento.vigencia import fecha_inicio, vigente

_RUTA = os.path.join(os.path.dirname(__file__), "..", "datos", "reglas.yaml")
_reglas: dict | None = None


def reglas() -> dict:
    global _reglas
    if _reglas is None:
        with open(_RUTA, encoding="utf-8") as f:
            _reglas = (yaml.safe_load(f) or {}).get("promociones", {})
    return _reglas


def recargar():
    global _reglas
    _reglas = None


def _utc(dt):
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


FIJOS = ["Punto de Información", "Centro Comercial El Puente", "El Puente", "Plazoleta de Comidas La Ceiba"]


def suavizar(texto: str, nombres: list[str]) -> str:
    """Palabras escritas EN MAYÚSCULAS en el panel → minúscula normal, respetando nombres de locales
    ("JUMBO" → "Jumbo") y siglas cortas (VIP, EPS, 2D)."""
    if not texto:
        return texto
    import re
    propios = {n.lower(): (n.capitalize() if n.isupper() else n) for n in nombres if len(n) >= 3}

    siglas = {"VIP", "EPS", "PSE", "SOAT", "ATM", "IVA", "NIT", "QR", "CC"}
    todas = re.findall(r"[A-Za-zÁÉÍÓÚÑÜáéíóúñü]{2,}", texto)
    gritado = bool(todas) and sum(w.isupper() for w in todas) / len(todas) >= 0.3

    def palabra(m):
        w = m.group(0)
        if not w.isupper() or w in siglas or (len(w) <= 3 and not gritado):
            return w
        return propios.get(w.lower(), w.lower())
    t = re.sub(r"[A-Za-zÁÉÍÓÚÑÜáéíóúñü]+", palabra, texto)
    for f in FIJOS + [n for n in nombres if " " in n]:
        t = re.sub(rf"(?i)\b{re.escape(f)}\b", f, t)
    t = re.sub(r"(^|[.!?¡¿]\s*)([a-záéíóúñ])", lambda m: m.group(1) + m.group(2).upper(), t)
    return t.replace("!.", "!").replace("?.", "?")


def vigentes(db, hoy: date) -> list[tuple]:
    """[(entity_type, id, prioridad, fecha_orden, datos)] de todo lo que se puede promocionar hoy."""
    from models.event import Event
    from models.marketing import Marketing
    from models.raffle import Raffle
    out = []
    try:
        from ..conocimiento.catalogo import locales
        nombres = [l.nombre for l in locales(db)]
    except Exception:
        nombres = []
    for e in db.query(Event).all():
        if vigente(e.date, hoy):
            out.append(("event", e.id, e.priority or 3, fecha_inicio(e.date) or hoy + timedelta(days=365),
                        {"tipo": "evento", "nombre": e.name, "fecha": e.date, "hora": e.time, "lugar": e.location}))
    for r in db.query(Raffle).filter(Raffle.active.is_(True)).all():
        if vigente(r.end_date, hoy):
            out.append(("raffle", r.id, r.priority or 3, hoy,
                        {"tipo": "sorteo", "nombre": r.name, "premio": suavizar(r.prize, nombres), "hasta": r.end_date}))
    for m in db.query(Marketing).filter(Marketing.active.is_(True)).all():
        if vigente(m.valid_until, hoy):
            out.append(("marketing", m.id, m.priority or 3, hoy,
                        {"tipo": "promocion", "nombre": m.title, "detalle": suavizar((m.description or "")[:160], nombres),
                         "hasta": m.valid_until}))
    return out


def elegir(ctx, flujo: str) -> dict | None:
    rg = reglas()
    if flujo in set(rg.get("flujos_sin_promo") or []):
        return None
    if ctx.sesion_nueva and not rg.get("en_primer_mensaje", True):
        return None
    from models.promotion_shown import PromotionShown
    db = ctx.db
    inicio = _utc(ctx.ahora) - timedelta(hours=cfg().sesion_horas)
    mostradas = [m for m in db.query(PromotionShown).filter(PromotionShown.phone_number == ctx.telefono[:20]).all()
                 if m.shown_at and _utc(m.shown_at) >= inicio]
    if len(mostradas) >= int(rg.get("tope_por_sesion", 12)):
        return None
    espaciado = int(rg.get("espaciado_mensajes", 0))
    if espaciado and mostradas:
        ultima = max(_utc(m.shown_at) for m in mostradas)
        turnos = [t for t in ctx.historial if t.rol == "user" and t.cuando][-espaciado:]
        if turnos and ultima >= _utc(turnos[0].cuando):
            return None
    candidatos = vigentes(db, ctx.ahora.date())
    if not candidatos:
        return None
    vistas = {}
    for m in mostradas:
        clave = (m.entity_type, m.entity_id)
        vistas[clave] = max(vistas.get(clave, _utc(m.shown_at)), _utc(m.shown_at))
    nuevas = [c for c in candidatos if (c[0], c[1]) not in vistas]
    if nuevas:
        elegida = sorted(nuevas, key=lambda c: (-c[2], c[3]))[0]
    elif rg.get("repetir_cuando_se_acaben", True):
        elegida = sorted(candidatos, key=lambda c: vistas[(c[0], c[1])])[0]
    else:
        return None
    tipo, id_, _, _, datos = elegida
    return {"entity_type": tipo, "entity_id": id_, "datos": {k: v for k, v in datos.items() if v}}


def linea(datos: dict) -> str:
    """Línea de respaldo con los datos reales (solo si la IA no la mencionó)."""
    n = datos.get("nombre", "")
    if datos.get("tipo") == "evento":
        detalle = " · ".join(x for x in [datos.get("fecha"), datos.get("hora"), datos.get("lugar")] if x)
        return f"🎉 De paso: *{n}*" + (f" — {detalle}" if detalle else "")
    if datos.get("tipo") == "sorteo":
        premio = datos.get("premio") or ""
        etiqueta = "" if premio.lower().startswith(("por cada", "cada ", "por compras")) else "premio: "
        partes = [f"{etiqueta}{premio}" if premio else "", f"hasta el {datos['hasta']}" if datos.get("hasta") else ""]
        detalle = ", ".join(p for p in partes if p)
        return f"🎁 De paso: participa en *{n}*" + (f" — {detalle}" if detalle else "")
    detalle = datos.get("detalle", "")
    hasta = f" (hasta el {datos['hasta']})" if datos.get("hasta") else ""
    return f"🛍️ De paso: *{n}*" + (f" — {detalle}" if detalle else "") + hasta


def asegurar(ctx, promo: dict, texto: str) -> tuple[str, bool]:
    """Garantiza que la novedad aparezca y la registra. Devuelve (texto, agregada_por_codigo)."""
    nombre = normalizar(promo["datos"].get("nombre", ""))
    agregada = False
    if nombre and nombre not in normalizar(texto):
        texto = (texto.rstrip() + "\n\n" + linea(promo["datos"])).strip()
        agregada = True
    from models.promotion_shown import PromotionShown
    try:
        ctx.db.add(PromotionShown(phone_number=ctx.telefono[:20], entity_type=promo["entity_type"],
                                  entity_id=promo["entity_id"], shown_at=_utc(ctx.ahora)))
        ctx.db.commit()
    except Exception:
        ctx.db.rollback()
    return texto, agregada