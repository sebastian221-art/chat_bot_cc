"""
Guardias: lo que se revisa SIEMPRE, antes y después del flujo, en código.

Entrada
  - pausa_humana: si un asesor tomó la conversación desde el panel, Any no responde.
  - privacidad:   "eliminar mis datos" con confirmación (Ley 1581) y aviso la primera vez.
Salida
  - formato:   WhatsApp (*negrita simple*, sin #, ---, tablas), sin IDs internos.
  - pisos:     fuera de la Torre Médica no se habla de pisos/niveles; nunca "Piso 1".
  - teléfonos: un número que no está en los datos se marca y se quita (no se inventa).
  - equidad:   si el flujo entregó una lista que debe ir completa, se completa.
  - emergencia: siempre Punto de Información + seguridad + línea del mall.
  - nunca vacía.
Cada corrección queda como alerta en la traza.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from ..conocimiento.texto import alguna_frase, normalizar, solo_digitos
from . import estado as est
from . import mensajes
from .tipos import Contexto, Respuesta

# ── Entrada ───────────────────────────────────────────────────────


def bot_en_pausa(db: Session, telefono: str, ahora: datetime) -> bool:
    from models.conversation_flag import ConversationFlag
    f = db.get(ConversationFlag, telefono)
    if not f or not f.bot_paused_until:
        return False
    hasta = f.bot_paused_until
    hasta = hasta.replace(tzinfo=timezone.utc) if hasta.tzinfo is None else hasta
    return hasta > ahora.astimezone(timezone.utc)


def privacidad(ctx: Contexto) -> Respuesta | None:
    """Pedido de borrado y su confirmación. Devuelve la respuesta si el mensaje era de privacidad."""
    e = ctx.estado
    if e.datos.get("borrado_pendiente") and e.flujo_activo == "privacidad":
        if alguna_frase(mensajes.frases("frases_confirmar_borrado"), ctx.mensaje) and \
                not re.search(r"\bno\b", normalizar(ctx.mensaje)):
            tablas = borrar_datos(ctx.db, ctx.telefono)
            ctx.traza.paso("privacidad_borrado", {"tablas": tablas})
            e.terminar_flujo()
            e.ultimas_entidades = {}
            return Respuesta(mensajes.texto("borrado_hecho"), "privacidad", meta={"borrado": tablas, "sin_promo": True})
        e.terminar_flujo()
        ctx.traza.paso("privacidad_cancelado")
        return None if len(ctx.mensaje.split()) > 3 else \
            Respuesta(mensajes.texto("borrado_cancelado"), "privacidad", meta={"sin_promo": True})
    if alguna_frase(mensajes.frases("frases_borrado"), ctx.mensaje):
        e.activar("privacidad", {"borrado_pendiente": True})
        return Respuesta(mensajes.texto("borrado_confirmar"), "privacidad", meta={"sin_promo": True})
    return None


# Tablas con datos del cliente: se borra toda fila de su teléfono.
COLUMNAS_TELEFONO = ("phone_number", "telefono", "customer_phone", "phone")
TABLAS_EXCLUIDAS = {"stores", "mall_info", "info_points", "users", "store_users"}


def borrar_datos(db: Session, telefono: str) -> dict:
    """Derecho de supresión completo: busca en TODAS las tablas una columna de teléfono del cliente."""
    insp = inspect(db.get_bind())
    hecho = {}
    for tabla in insp.get_table_names():
        if tabla in TABLAS_EXCLUIDAS:
            continue
        cols = {c["name"] for c in insp.get_columns(tabla)}
        col = next((c for c in COLUMNAS_TELEFONO if c in cols), None)
        if not col:
            continue
        try:
            r = db.execute(text(f'DELETE FROM "{tabla}" WHERE "{col}" = :t'), {"t": telefono})
            if r.rowcount:
                hecho[tabla] = r.rowcount
        except Exception:
            db.rollback()
    db.commit()
    return hecho


def aviso_privacidad(ctx: Contexto, respuesta: Respuesta):
    """La primera vez, el aviso va como mensaje previo; la respuesta a la pregunta igual sale."""
    if ctx.modo == "eval" or est.aviso_ya_mostrado(ctx.db, ctx.telefono):
        return
    av = mensajes.valor("aviso_privacidad") or {}
    respuesta.previos.insert(0, mensajes.texto("aviso_privacidad"))
    est.marcar_aviso(ctx.db, ctx.telefono, str(av.get("version", "")), ctx.ahora)
    ctx.traza.paso("aviso_privacidad", "mostrado")


# ── Salida ────────────────────────────────────────────────────────

LINEA_MALL = "3174320138"
# Pasos de la traza cuyos datos cuentan como "verificados" (lo que escribió el cliente en su pedido también)
PASOS_CON_DATOS = ("datos_reunidos", "herramienta", "promocion_elegida", "domicilio_datos", "vision")
_PISO = re.compile(r"\s*\(?\b(?:en el |en |del )?(?:piso|nivel|planta)\s+(?:\d+|uno|dos|tres|cuatro|cinco|seis)\b\)?",
                   re.IGNORECASE)
_PISO_ORDINAL = re.compile(r"\s*\(?\b(?:en el |en |del |el )?(?:\d+\s?(?:\.?\s?[º°o]|er|do|ro|to)|primer|primero|segundo|"
                          r"tercer|tercero|cuarto|quinto|sexto)\s+(?:piso|nivel|planta)\b\)?", re.IGNORECASE)
_ID_INTERNO = re.compile(r"\[(?:TIENDA|ID|LOCAL)[^\]]*\]|\bID:\s*\d+\b", re.IGNORECASE)
_TELEFONO = re.compile(r"(?<!\d)(?:\+?57[\s-]?)?3\d{2}[\s-]?\d{3}[\s-]?\d{4}(?!\d)")


_VOSEO = {"recibís": "recibes", "tenés": "tienes", "podés": "puedes", "querés": "quieres", "sabés": "sabes",
          "registrálas": "regístralas", "registralas": "regístralas", "mirá": "mira", "fijate": "fíjate",
          "escribí": "escribe", "acercate": "acércate", "participá": "participa", "aprovechá": "aprovecha"}


def formato_whatsapp(t: str) -> str:
    t = re.sub(r"[\u200b\u200c\u200e\u200f\u2060\ufeff\u00ad]", "", t)   # invisibles ("Barichar\u200ba"); el \u200d une emojis
    t = re.sub(r"(\b[Pp]asillo\s+\*?[A-Za-zÁÉÍÓÚáéíóúÑñ]+)\*([a-záéíóúñ]{1,3})\b", r"\1\2*", t)   # "*Pasillo Barichar*a"
    for vos, tu in _VOSEO.items():                                 # "recibís" → "recibes" (tuteo colombiano)
        t = re.sub(rf"(?i)\b{vos}\b", lambda m, tu=tu: tu.capitalize() if m.group(0)[0].isupper() else tu, t)
    t = re.sub(r"\*\*(.+?)\*\*", r"*\1*", t)                     # **x** → *x*
    t = re.sub(r"__(.+?)__", r"*\1*", t)
    t = re.sub(r"^\s{0,3}#{1,6}\s*", "", t, flags=re.MULTILINE)   # títulos
    t = re.sub(r"^\s*[-*_]{3,}\s*$", "", t, flags=re.MULTILINE)   # ---
    lineas = []
    for l in t.split("\n"):
        if re.match(r"^\s*\|?\s*:?-{2,}", l):                     # separador de tabla
            continue
        if l.count("|") >= 2:                                      # fila de tabla → viñeta
            celdas = [c.strip() for c in l.strip().strip("|").split("|") if c.strip()]
            l = "• " + " — ".join(celdas)
        lineas.append(l)
    t = "\n".join(lineas)
    t = re.sub(r"^\s*[-*]\s+", "• ", t, flags=re.MULTILINE)       # viñetas uniformes
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


_DINERO = re.compile(r"\$\s?\d[\d.,]*(?:\s?(?:millones|millón|millon|mil)\b)?|\b\d{1,3}(?:[.,]\d{3})+\b|"
                     r"\b\d+(?:[.,]\d+)?\s?%")


def _cifra(x: str) -> str:
    """'$ 18.000' → '18000' · '20 %' → '20%' · '$47,500' → '47500' · '$13 millones' → '13000000' · '$2 mil' → '2000'."""
    pct = "%" if "%" in x else ""
    base = x.split("%")[0]
    m = re.search(r"(millones|millón|millon|mil)\b", base, re.I)
    if m:
        num = re.search(r"\d+(?:[.,]\d+)?", base)
        if num:
            n = num.group(0)
            if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", n):     # "$1.500 millones": el punto es de miles
                v = float(re.sub(r"[.,]", "", n))
            else:
                v = float(n.replace(",", "."))
            return str(int(round(v * (1_000 if m.group(1).lower() == "mil" else 1_000_000))))
    d = re.sub(r"[^\d]", "", base)
    return d + pct


def _cifras_validas(ctx: Contexto) -> set[str]:
    validas = set()
    for p in ctx.traza.pasos:
        if p["paso"] in PASOS_CON_DATOS:
            for m in _DINERO.findall(str(p["detalle"])):
                validas.add(_cifra(m))
    return validas


_MESES = {m: i + 1 for i, m in enumerate(["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
                                          "septiembre", "octubre", "noviembre", "diciembre"])}
_FECHA_NUM = re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})\b")
_FECHA_TXT = re.compile(r"\b(\d{1,2})\s+de\s+(" + "|".join(_MESES) + r")(?:\s+de(?:l)?\s+(\d{4}))?\b", re.I)


def _fechas(texto: str) -> set[tuple]:
    """Fechas completas (día, mes, año) y parciales (día, mes) escritas en el texto."""
    out = set()
    for d, m, a in _FECHA_NUM.findall(texto):
        out.add((int(d), int(m), int(a)))
    for d, m, a in _FECHA_TXT.findall(normalizar(texto)):
        out.add((int(d), _MESES[m.lower()], int(a)) if a else (int(d), _MESES[m.lower()]))
    return out


def _fechas_validas(ctx: Contexto) -> set[tuple]:
    validas = set()
    a = ctx.ahora if hasattr(ctx, "ahora") else None
    if a:
        for k in range(0, 8):   # hoy y la semana que viene ("este domingo 26 de octubre")
            from datetime import timedelta
            f = (a + timedelta(days=k)).date()
            validas |= {(f.day, f.month, f.year), (f.day, f.month)}
    for p in ctx.traza.pasos:
        if p["paso"] in PASOS_CON_DATOS:
            for t in _fechas(str(p["detalle"])):
                validas.add(t)
                validas.add(t[:2])
    return validas


def _telefonos_validos(respuesta: Respuesta, ctx: Contexto) -> set[str]:
    validos = {LINEA_MALL, "123"}
    validos |= {solo_digitos(x)[-10:] for x in respuesta.meta.get("telefonos_validos", [])}
    # todo número que haya llegado en los datos del flujo o de herramientas es válido
    for p in ctx.traza.pasos:
        if p["paso"] in PASOS_CON_DATOS:
            for m in _TELEFONO.findall(str(p["detalle"])):
                validos.add(solo_digitos(m)[-10:])
            for m in re.findall(r"wa\.me/57(\d{10})", str(p["detalle"])):
                validos.add(m)
    return validos


PASILLOS = ["Barichara", "Vélez", "Socorro", "Charalá", "Páramo", "Curití"]


def _corregir_pasillos(ctx: Contexto, t: str) -> str:
    """'Pasillo Barichra' → 'Pasillo Barichara'. Un pasillo que no existe se marca para revisión."""
    import difflib
    oficiales = {normalizar(p): p for p in PASILLOS}

    def cambiar(m):
        nombre = m.group(1)
        n = normalizar(nombre)
        if n in oficiales:
            return f"{m.group(0)[:-len(nombre)]}{oficiales[n]}" if nombre != oficiales[n] else m.group(0)
        cerca = difflib.get_close_matches(n, list(oficiales), n=1, cutoff=0.75)
        if cerca:
            ctx.traza.alerta(f"pasillo mal escrito «{nombre}» → {oficiales[cerca[0]]}")
            return f"{m.group(0)[:-len(nombre)]}{oficiales[cerca[0]]}"
        ctx.traza.alerta(f"pasillo que no existe: «{nombre}» (revisar)")
        return m.group(0)
    return re.sub(r"\b[Pp]asillo\s+\*?([A-Za-zÁÉÍÓÚáéíóúÑñ]+)", cambiar, t)


NOMBRES_FIJOS = {"Punto de Información", "Torre Médica", "Plazoleta de Comidas La Ceiba", "Plaza Principal",
                 "Zona Terrazas", "Paseo de la Cruz", "Cinelandia Múltiplex"}
CLAVES_NOMBRES = {"nombre", "lugar", "zona", "titulo", "local", "location", "donde_registrar"}


def _nombres_de_los_datos(ctx: Contexto) -> set[str]:
    """Nombres propios que llegaron en los datos del turno (eventos, lugares, locales, películas)."""
    out: set[str] = set()

    def recorrer(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k in CLAVES_NOMBRES and isinstance(v, str) and 6 <= len(v) <= 60:
                    out.add(v.strip())
                recorrer(v)
        elif isinstance(x, list):
            for v in x:
                recorrer(v)
    for p in ctx.traza.pasos:
        if p["paso"] == "datos_reunidos" and isinstance(p["detalle"], dict):
            recorrer(p["detalle"].get("hechos"))
    return out


def _corregir_nombres(ctx: Contexto, t: str) -> str:
    """'Plazaleta Guamerá' → 'Plazoleta Guanentá': un nombre de los datos mal copiado se devuelve a como es."""
    import difflib
    if re.search(r"(?i)\bel puente de informaci[oó]n\b", t):     # confusión conocida del modelo
        ctx.traza.alerta("nombre mal copiado «El Puente de Información» → Punto de Información")
        t = re.sub(r"(?i)\bel puente de informaci[oó]n\b", "Punto de Información", t)
    nombres = _nombres_de_los_datos(ctx) | NOMBRES_FIJOS
    exactos = {normalizar(n) for n in nombres}
    protegidos: list[str] = []

    def _proteger(m):
        protegidos.append(m.group(0))
        return f"⟦N{len(protegidos) - 1}⟧"
    for nombre in sorted(nombres, key=len, reverse=True):
        if len(nombre) >= 6:
            t = re.sub(re.escape(nombre), _proteger, t, flags=re.IGNORECASE)
    for nombre in sorted(nombres, key=len, reverse=True):
        if nombre in t:
            continue
        n = len(nombre.split())
        palabras_t = re.findall(r"\S+", t)
        for i in range(len(palabras_t) - n + 1):
            trozo = " ".join(palabras_t[i:i + n]).strip("*.,;:()¡!¿?")
            if len(trozo) < 6 or trozo == nombre or normalizar(trozo) in exactos:
                continue   # otro nombre real de los datos no se toca
            a, b = normalizar(trozo), normalizar(nombre)
            # parecido en conjunto Y palabra por palabra ("no tengo información" no es "Punto de Información")
            if a != b and difflib.SequenceMatcher(None, a, b).ratio() >= 0.8 and all(
                    difflib.SequenceMatcher(None, x, y).ratio() >= 0.6 for x, y in zip(a.split(), b.split())):
                ctx.traza.alerta(f"nombre mal copiado «{trozo}» → {nombre}")
                t = t.replace(trozo, nombre)
    return re.sub(r"⟦N(\d+)⟧", lambda m: protegidos[int(m.group(1))], t)


def _sin_entradas_colgando(t: str) -> str:
    """Quita una línea que termina en ':' si lo que la seguía (la lista) fue retirado por una guardia."""
    lineas = t.split("\n")
    out = []
    for i, l in enumerate(lineas):
        if l.rstrip().endswith(":"):
            siguiente = next((x for x in lineas[i + 1:] if x.strip()), "")
            if not siguiente.lstrip().startswith(("•", "-", "*", "1", "2", "3", "4", "5", "6", "7", "8", "9")):
                continue
        out.append(l)
    return "\n".join(out).strip()


def revisar_salida(ctx: Contexto, r: Respuesta) -> Respuesta:
    t = r.texto or ""
    t = _ID_INTERNO.sub("", t)
    t = formato_whatsapp(t)

    if r.flujo != "torre_medica" and (_PISO.search(t) or _PISO_ORDINAL.search(t)):
        ctx.traza.alerta(f"se quitó mención de piso/nivel: {_PISO.findall(t) + _PISO_ORDINAL.findall(t)}")
        t = _PISO_ORDINAL.sub("", _PISO.sub("", t))

    # links de WhatsApp de mentira (el modelo copió un ejemplo "57XXXXXXXXXX")
    if re.search(r"wa\.me/\S*[xX]{3,}", t):
        ctx.traza.alerta("link de WhatsApp de relleno (XXXX): se quitó la línea")
        t = "\n".join(l for l in t.split("\n") if not re.search(r"wa\.me/\S*[xX]{3,}", l)).strip()

    # los links se apartan mientras se revisa el texto: un link con el pedido escrito (?text=…%20…)
    # no debe confundirse con precios, fechas o teléfonos
    numeros_wa = re.findall(r"wa\.me/57(\d{10})", t)
    links: list[str] = []

    def _apartar(m):
        links.append(m.group(0))
        return f"⟦L{len(links) - 1}⟧"
    t = re.sub(r"https?://\S+", _apartar, t)

    t = _corregir_pasillos(ctx, t)
    t = _corregir_nombres(ctx, t)

    validos = _telefonos_validos(r, ctx)
    inventados = set()
    for m in _TELEFONO.findall(t):
        if solo_digitos(m)[-10:] not in validos:
            inventados.add(m)
    for m in numeros_wa:
        if m not in validos:
            inventados.add(m)
    if inventados:
        ctx.traza.alerta(f"número que no está en los datos (se quitó la línea): {sorted(inventados)}")
        def _con_link(l):   # la línea con sus links reales, para buscar el número dentro
            return re.sub(r"⟦L(\d+)⟧", lambda m: links[int(m.group(1))], l)
        lineas = [l for l in t.split("\n") if not any(n in _con_link(l) for n in inventados)]
        t = "\n".join(lineas).strip()

    # precios y porcentajes que no vienen en los datos: el modelo los inventó
    cifras = _cifras_validas(ctx)
    malas = {m for m in _DINERO.findall(t) if _cifra(m) not in cifras}
    if malas:
        ctx.traza.alerta(f"precio o porcentaje que no está en los datos (se quitó la línea): {sorted(malas)}")
        t = "\n".join(l for l in t.split("\n") if not any(m in l for m in malas)).strip()

    # fechas que no vienen en los datos ("hasta el 31 de enero de 2027" sin que la base lo diga)
    validas_f = _fechas_validas(ctx)
    malas_f = [f for f in _fechas(t) if f not in validas_f]
    if malas_f:
        ctx.traza.alerta(f"fecha que no está en los datos (se quitó la línea): {malas_f}")
        lineas = []
        for l in t.split("\n"):
            if not any(f not in validas_f for f in _fechas(l)):
                lineas.append(l)
        t = "\n".join(lineas).strip()

    t = re.sub(r"⟦L(\d+)⟧", lambda m: links[int(m.group(1))], t)   # se devuelven los links
    if malas or malas_f or inventados:
        t = _sin_entradas_colgando(t)

    faltantes = [n for n in r.meta.get("lista_equidad", []) if normalizar(n) not in normalizar(t)]
    if faltantes:
        ctx.traza.alerta(f"equidad: faltaban {len(faltantes)} locales en la lista; se agregaron")
        extra = r.meta.get("lineas_equidad", {})
        t += "\n" + "\n".join(extra.get(n, f"• *{n}*") for n in faltantes)

    if r.flujo == "emergencia_queja" and r.meta.get("tipo") == "emergencia":
        n = normalizar(t)
        if "barichara" not in n or LINEA_MALL not in solo_digitos(t) or "seguridad" not in n:
            ctx.traza.alerta("emergencia sin los tres contactos obligatorios: se agregó el bloque fijo")
            t = (t + "\n\n" + mensajes.texto("emergencia")).strip()

    if not t.strip():
        ctx.traza.alerta("respuesta vacía: se usó el mensaje de error técnico")
        t = mensajes.texto("error_tecnico")
    r.texto = t
    return r