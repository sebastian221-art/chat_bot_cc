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
    c_carta    = _col(ws, hg, "anexa carta", "catálogo", "catalogo")

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

        # Primer teléfono si hay varios separados por coma/;/ /
        telefono = contacto
        for sep in [",", ";", "/", " y "]:
            if sep in telefono:
                telefono = telefono.split(sep)[0].strip()
                break

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
            "responsable": f"{resp} ({cargo})".strip() if resp else "",
        }
        locales[idloc] = local
        orden.append(idloc)

    # ── Hoja 2: catálogo de productos/servicios ───────────────────
    if HOJA_CATALOGO in wb.sheetnames:
        ws2 = wb[HOJA_CATALOGO]
        hc = _headers(ws2)
        c2_id     = _col(ws2, hc, "id", "número de local", "numero de local")
        c2_subcat = _col(ws2, hc, "subcategoría", "subcategoria")
        c2_pub    = _col(ws2, hc, "público", "publico")
        c2_ocas   = _col(ws2, hc, "ocasión", "ocasion", "plan")
        c2_keys   = _col(ws2, hc, "palabras clave", "búsqueda", "busqueda")
        c2_marcas = _col(ws2, hc, "marcas")
        c2_info   = _col(ws2, hc, "información detallada", "informacion detallada", "detalle")

        for row in range(2, ws2.max_row + 1):
            idloc = _txt(ws2.cell(row, c2_id).value) if c2_id else ""
            if not idloc or idloc not in locales:
                continue
            L = locales[idloc]

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
            "_anexa_carta": L["_anexa_carta"],
        })

    return resultado