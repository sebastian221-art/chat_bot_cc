"""Una sola imagen cuando la respuesta es una lista (pedido del 27/11).

«Cuando pregunten por todas (las promociones de Jumbo, las del centro comercial, los eventos, los sorteos o lo que hay
este mes), en el texto van TODAS y en foto solo la más actual. Si preguntan por una en especial, va esa con su foto.»

La «más actual» es la que el cliente tiene más cerca:
  1. un evento que es HOY;
  2. una promoción de un día de la semana que es HOY (Jueves de Juguetería, un jueves);
  3. el evento o el sorteo más próximo (por días que faltan);
  4. las promociones sin día ni fecha (la más nueva primero);
  5. lo recurrente de otro día, por los días que faltan para ese día.
A igual cercanía gana la de mayor prioridad y después la más nueva. Solo cuentan las que tienen foto.
"""
from __future__ import annotations

from ..conocimiento.fotos import foto_principal
from ..conocimiento.vigencia import dias_para, recurrencia
from ..nucleo.tipos import Adjunto


def _cercania_evento(e, hoy) -> float:
    from .eventos import _dias_del_evento
    dias = _dias_del_evento(e.date, hoy)
    if dias is not None and hoy in dias:
        return 0.0
    faltan = dias_para(e.date, hoy)
    if faltan is not None:
        return max(float(faltan), 0.6)
    rec = recurrencia(e.name, f"{e.date or ''} {e.description or ''}")
    if rec:
        return 0.0 if hoy.weekday() in rec[1] else 2.0 + min((d - hoy.weekday()) % 7 for d in rec[1])
    return 8.0


def _cercania_sorteo(s, hoy) -> float:
    faltan = dias_para(s.end_date, hoy)
    return max(float(faltan), 0.6) if faltan is not None else 9.0


def _cercania_promo(m, hoy) -> float:
    rec = recurrencia(m.title, m.description)
    if rec:
        return 0.5 if hoy.weekday() in rec[1] else 2.0 + min((d - hoy.weekday()) % 7 for d in rec[1])
    return 1.5


def elegir(db, hoy, eventos=(), sorteos=(), promos=()) -> Adjunto | None:
    """La imagen de la más actual entre eventos, sorteos y promociones (o None si ninguna tiene foto)."""
    candidatos = []
    for e in eventos:
        candidatos.append((_cercania_evento(e, hoy), -(getattr(e, "priority", None) or 3), -(e.id or 0),
                           "event", e, e.name, getattr(e, "photo_url", None), ("afiche", "otra")))
    for s in sorteos:
        candidatos.append((_cercania_sorteo(s, hoy), -(s.priority or 3), -(s.id or 0),
                           "raffle", s, s.name, s.photo_url, ("afiche", "premio", "otra")))
    for m in promos:
        candidatos.append((_cercania_promo(m, hoy), -(m.priority or 3), -(m.id or 0),
                           "marketing", m, m.title, getattr(m, "photo_url", None), ("afiche", "otra")))
    for *_, tipo, obj, nombre, respaldo, orden in sorted(candidatos, key=lambda c: c[:3]):
        foto = foto_principal(db, tipo, obj.id, respaldo=respaldo, orden=orden)
        if foto:
            return Adjunto(tipo="imagen", url=foto, leyenda=nombre)
    return None


def poner(datos, adjunto: Adjunto | None, total: int) -> None:
    """Deja solo esa imagen y le dice al redactor qué es (y que no ofrezca lo que ya va)."""
    datos.adjuntos = [a for a in datos.adjuntos if a.tipo != "imagen"]
    for k in ("imagen", "imagenes"):
        datos.hechos.pop(k, None)
    if adjunto:
        datos.adjuntos.append(adjunto)
        datos.hechos["imagen"] = (f"va adjunta UNA imagen: la de «{adjunto.leyenda}» (la más actual). No la describas, "
                                  "no digas que envías imágenes de las demás y no ofrezcas mandar esta.")
    if total > 1:
        datos.hechos["como_ofrecer_mas"] = ("Al final, en UNA línea: si quiere la información o la imagen de alguna en "
                                            "especial, que te diga cuál.")
