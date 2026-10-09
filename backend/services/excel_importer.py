# 📄 ARCHIVO: backend/services/excel_importer.py
"""
Importador de la PLANTILLA EXCEL de locales "ANY El Puente".

Lee el archivo .xlsx tal como se lo entregan al Centro Comercial, con sus
dos hojas:
  - "01_Informacion_General": los datos de cada local (nombre, piso,
    zona, horario, contacto, etc.)
  - "02_Catalogo_Productos_Servicios": qué vende cada local, con las
    palabras clave de búsqueda que Any usa para las categorías.

Combina ambas hojas en cada local y las mapea a los campos del sistema
(modelo Store), aprovechando TODA la información de la plantilla:

  Hoja 1                          → Campo del sistema
  ─────────────────────────────────────────────────────
  ID / Número de Local            → local_number
  Nombre del Local                → name
  Tipo de Establecimiento         → category (base)
  Pasillo / Zona                  → location_hint (+ zona)
  Nivel                           → floor
  Horario de Atención             → schedule
  Número(s) de Contacto/WhatsApp  → phone
  Métodos de Pago, Responsable    → se suman a description
  ¿Anexa Carta?                   → se recuerda para la carta

  Hoja 2 (catálogo)               → Campo del sistema
  ─────────────────────────────────────────────────────
  Subcategoría, Público, Ocasión  → description (enriquecida)
  Palabras Clave de Búsqueda      → tags (¡clave para las búsquedas!)
  Info Detallada del Producto     → description
  Marcas                          → tags

Es tolerante: si un local no está en la hoja 2, igual se importa con lo
de la hoja 1. Si una fila no tiene nombre, se salta. Nunca revienta por
un dato faltante.
"""
import io
import logging

import openpyxl

logger = logging.getLogger("mall_bot")

HOJA_GENERAL = "01_Informacion_General"
HOJA_CATALOGO = "02_Catalogo_Productos_Servicios"


def _txt(v) -> str:
    """Convierte cualquier celda a texto limpio. Quita el '.0' que Excel
    le pone a los números (ej. teléfonos: 6077237070.0 → 6077237070)."""
    if v is None:
        return ""
    s = str(v).strip()
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return s


def _headers(ws) -> dict:
    """Mapa {texto_encabezado_normalizado: numero_columna} de la fila 1."""
    h = {}
    for c in range(1, ws.max_column + 1):
        val = ws.cell(1, c).value
        if val:
            clave = str(val).lower().strip()
            h[clave] = c
    return h


def _col(ws, headers, *nombres_posibles):
    """Devuelve el número de columna que coincide con alguno de los
    nombres dados (búsqueda flexible por 'contiene')."""
    for nombre in nombres_posibles:
        n = nombre.lower()
        for clave, col in headers.items():
            if n in clave:
                return col
    return None


def parse_plantilla(file_bytes: bytes) -> list[dict]:
    """
    Lee el Excel y devuelve una lista de locales listos para importar,
    cada uno como un dict con los campos del modelo Store.
    """
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)

    # ── Hoja 1: información general ────────────────────────────────
    if HOJA_GENERAL in wb.sheetnames:
        ws = wb[HOJA_GENERAL]
    else:
        ws = wb.worksheets[0]  # si renombraron la hoja, usar la primera
    hg = _headers(ws)

    c_id       = _col(ws, hg, "id", "número de local", "numero de local")
    c_nombre   = _col(ws, hg, "nombre del local", "nombre")
    c_tipo     = _col(ws, hg, "tipo de establecimiento", "tipo")
    c_zona     = _col(ws, hg, "pasillo", "zona")
    c_nivel    = _col(ws, hg, "nivel")
    c_parq     = _col(ws, hg, "parqueadero", "cercanía")
    c_horario  = _col(ws, hg, "horario")
    c_contacto = _col(ws, hg, "contacto", "whatsapp", "número")
    c_resp     = _col(ws, hg, "responsable")
    c_cargo    = _col(ws, hg, "cargo")
    c_pago     = _col(ws, hg, "métodos de pago", "metodos de pago", "pago")
    # OJO: "anexa carta" y "catalogos o link" son DOS columnas distintas.
    # c_carta = la de "¿Anexa Carta / Catálogo? (Sí/No)".
    # c_link  = la de "Catalogos o link" (el PDF o el enlace del catálogo).
    c_carta    = _col(ws, hg, "anexa carta", "¿anexa")
    c_link     = _col(ws, hg, "catalogos o link", "catálogos o link", "catalogo o link", "link")

    locales = {}  # clave: id_local (str) → dict del local
    orden = []

    for row in range(2, ws.max_row + 1):
        nombre = _txt(ws.cell(row, c_nombre).value) if c_nombre else ""
        if not nombre:
            continue  # fila sin nombre → se salta

        idloc = _txt(ws.cell(row, c_id).value) if c_id else ""
        tipo = _txt(ws.cell(row, c_tipo).value) if c_tipo else ""
        zona = _txt(ws.cell(row, c_zona).value) if c_zona else ""
        nivel = _txt(ws.cell(row, c_nivel).value) if c_nivel else ""
        parq = _txt(ws.cell(row, c_parq).value) if c_parq else ""
        horario = _txt(ws.cell(row, c_horario).value) if c_horario else ""
        contacto = _txt(ws.cell(row, c_contacto).value) if c_contacto else ""
        resp = _txt(ws.cell(row, c_resp).value) if c_resp else ""
        cargo = _txt(ws.cell(row, c_cargo).value) if c_cargo else ""
        pago = _txt(ws.cell(row, c_pago).value) if c_pago else ""
        carta = _txt(ws.cell(row, c_carta).value) if c_carta else ""
        link_raw = _txt(ws.cell(row, c_link).value) if c_link else ""

        # ¿Lo que pusieron en "Catalogos o link" es un ENLACE o un archivo
        # PDF/foto que se subirá manual? Si es un enlace (http, www, wa.me,
        # instagram, un dominio .com/.co, etc.) lo guardamos como catálogo
        # digital → Any lo manda como "la carta". Si es un nombre de archivo
        # (termina en .pdf/.jpg/.png) NO es link: esa carta la sube el admin
        # como foto desde el panel.
        catalogo_link = ""
        if link_raw:
            low = link_raw.lower()
            es_archivo = low.endswith((".pdf", ".jpg", ".jpeg", ".png", ".webp"))
            es_enlace = (
                low.startswith(("http://", "https://", "www."))
                or "wa.me" in low or "wa.link" in low
                or "instagram" in low or "linktr" in low or "facebook" in low
                or (("." in low) and (" " not in link_raw.strip()) and not es_archivo
                    and any(d in low for d in (".com", ".co", ".net", ".org", ".io", ".shop", ".store")))
            )
            if es_enlace and not es_archivo:
                catalogo_link = link_raw

        # Primer teléfono si vienen varios. Los separadores pueden ser
        # coma, punto y coma, barra, " y ", o guiones. Extraemos el PRIMER
        # número de 7 a 12 dígitos seguidos (un teléfono válido), ignorando
        # separadores y espacios entre números distintos.
        import re as _re
        # Primero normalizamos separadores a un espacio, luego buscamos el
        # primer grupo de dígitos consecutivos (sin mezclar dos números).
        _limpio = _re.sub(r"[^\d]+", " ", contacto).strip()
        _numeros = [n for n in _limpio.split() if len(n) >= 7]
        if _numeros:
            telefono = _numeros[0]  # el primer teléfono válido
        else:
            telefono = _re.sub(r"[^\d]", "", contacto)  # lo que haya
        telefono = telefono[:20]  # seguridad: nunca superar el límite de la BD

        # Info extra que el sistema no tiene en campos propios → a description
        extras = []
        if pago:
            extras.append(f"Métodos de pago: {pago}")
        if parq:
            extras.append(f"Cercanía a parqueadero: {parq}")

        local = {
            "local_number": idloc or "S/N",
            "name": nombre,
            "category": tipo or "Por confirmar",
            "floor": nivel or "Por confirmar",
            "location_hint": zona,
            "schedule": horario,
            "phone": telefono,
            "_descripcion_extras": extras,       # se une abajo
            "_catalogo_desc": [],                 # se llena con hoja 2
            "_tags": [],                          # se llena con hoja 2
            "_anexa_carta": carta.lower().startswith("s"),  # "Sí" → True
            "_catalogo_link": catalogo_link,               # enlace de carta/catálogo (o "")
            "responsable": f"{resp} ({cargo})".strip() if resp else "",
        }
        # LLAVE ÚNICA = ID + nombre. Algunos locales REUSAN el mismo número
        # (ej. el 204 lo usan "Gari Sushi" y "FOSCAL odontología", que están
        # en torres distintas). Si usáramos solo el ID como llave, el segundo
        # pisaría al primero y se perdería un local. El nombre los distingue.
        clave = f"{idloc}#{nombre.strip().lower()}"
        locales[clave] = local
        orden.append(clave)

    # ── Hoja 2: catálogo de productos/servicios ───────────────────
    if HOJA_CATALOGO in wb.sheetnames:
        ws2 = wb[HOJA_CATALOGO]
        hc = _headers(ws2)
        c2_id     = _col(ws2, hc, "id", "número de local", "numero de local")
        c2_nombre = _col(ws2, hc, "nombre del local", "nombre")
        c2_subcat = _col(ws2, hc, "subcategoría", "subcategoria")
        c2_pub    = _col(ws2, hc, "público", "publico")
        c2_ocas   = _col(ws2, hc, "ocasión", "ocasion", "plan")
        c2_keys   = _col(ws2, hc, "palabras clave", "búsqueda", "busqueda")
        c2_marcas = _col(ws2, hc, "marcas")
        c2_info   = _col(ws2, hc, "información detallada", "informacion detallada", "detalle")

        # Índice de respaldo por ID solo cuando ese ID es ÚNICO (no reusado),
        # para emparejar aunque el nombre del catálogo difiera un poco.
        from collections import Counter
        _ids = [k.split("#", 1)[0] for k in locales]
        _ids_unicos = {i for i, n in Counter(_ids).items() if n == 1}
        _por_id = {k.split("#", 1)[0]: k for k in locales}

        for row in range(2, ws2.max_row + 1):
            idloc = _txt(ws2.cell(row, c2_id).value) if c2_id else ""
            nom2  = _txt(ws2.cell(row, c2_nombre).value) if c2_nombre else ""
            if not idloc:
                continue
            clave = f"{idloc}#{nom2.strip().lower()}"
            if clave in locales:
                L = locales[clave]
            elif idloc in _ids_unicos:
                L = locales[_por_id[idloc]]   # mismo ID único, nombre con otra variante
            else:
                continue

            subcat = _txt(ws2.cell(row, c2_subcat).value) if c2_subcat else ""
            pub    = _txt(ws2.cell(row, c2_pub).value) if c2_pub else ""
            ocas   = _txt(ws2.cell(row, c2_ocas).value) if c2_ocas else ""
            keys   = _txt(ws2.cell(row, c2_keys).value) if c2_keys else ""
            marcas = _txt(ws2.cell(row, c2_marcas).value) if c2_marcas else ""
            info   = _txt(ws2.cell(row, c2_info).value) if c2_info else ""

            if info:
                L["_catalogo_desc"].append(info)
            if subcat:
                L["_tags"].append(subcat)
            if keys:
                L["_tags"].append(keys)
            if marcas:
                L["_tags"].append(marcas)
            if pub and pub not in L["_catalogo_desc"]:
                L["_catalogo_desc"].append(f"Para: {pub}")
            if ocas:
                L["_catalogo_desc"].append(f"Ideal para: {ocas}")

    # ── Armar los locales finales (unir todo en description y tags) ─
    resultado = []
    for idloc in orden:
        L = locales[idloc]
        # Descripción = catálogo + extras (pago, parqueadero)
        desc_partes = L["_catalogo_desc"] + L["_descripcion_extras"]
        descripcion = ". ".join(p for p in desc_partes if p).strip()
        # Tags = subcategorías + palabras clave + marcas (para búsquedas)
        tags = ", ".join(dict.fromkeys([t for t in L["_tags"] if t]))  # sin duplicados

        resultado.append({
            "local_number": L["local_number"][:60],
            "name": L["name"][:150],
            "category": L["category"][:80],
            "floor": L["floor"][:20],
            "location_hint": L["location_hint"][:200],
            "schedule": L["schedule"][:200],
            "phone": L["phone"][:20],
            "description": descripcion[:4000] if descripcion else "",
            "tags": tags[:300],
            "extra_info": f"Responsable: {L['responsable']}" if L["responsable"] else "",
            "catalogo_link": L["_catalogo_link"][:500] if L.get("_catalogo_link") else "",
            "_anexa_carta": L["_anexa_carta"],
        })

    return resultado