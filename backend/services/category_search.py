# 📄 ARCHIVO: backend/services/category_search.py
"""
Búsqueda JUSTA por categoría — para garantizar equidad comercial.

Cuando un cliente pregunta por un TIPO de producto/comida ("¿dónde comer
hamburguesas?", "¿zapatos formales?"), el bot debe listar TODOS los
locales de ese tipo, no una selección — porque mostrar solo algunos
parecería favoritismo y los demás locales podrían reclamar con razón.

Este módulo:
1. Detecta si el mensaje es una búsqueda por categoría/tipo.
2. Mapea la pregunta a los términos con los que buscar en la base.
3. (La búsqueda en sí vive en rag.py → find_all_stores_by_category, que
   trae TODOS los coincidentes, en orden alfabético neutral.)

IMPORTANTE: la calidad de esto depende de qué tan completas estén las
palabras clave de cada local (las columnas del Excel). Si un local de
hamburguesas no tiene "hamburguesa" en su categoría/tags/descripción,
no aparecerá — eso se resuelve con datos, no con código.
"""

# Cada entrada: los términos que, si aparecen en el mensaje del cliente,
# disparan una búsqueda por categoría — y con qué palabras buscar en la
# base de datos (para cubrir sinónimos y variantes de escritura).
CATEGORIAS_BUSQUEDA = {
    # ── Comida ──
    "hamburguesas": ["hamburgues", "burger"],
    "pizza": ["pizza", "pizzas"],
    "tacos": ["taco", "tacos", "mexicana"],
    "pollo": ["pollo", "asadero"],
    "comida rápida": ["comida rápida", "comida rapida", "fast food"],
    "almuerzos": ["almuerzo", "almuerzos", "corrientazo", "menú del día"],
    "postres": ["postre", "postres", "dulce", "repostería"],
    "helados": ["helado", "helados", "heladería"],
    "café": ["café", "cafetería", "cafeteria", "tinto"],
    "sushi": ["sushi", "japonesa", "oriental"],
    "comida": ["restaurante", "comida", "comer", "almorzar", "almuerzo", "cenar", "cena", "desayunar", "desayuno", "hambre"],  # genérico — usar solo si no hubo match más específico

    # ── Ropa ──
    "ropa": ["ropa", "vestuario", "prendas"],
    "vestidos": ["vestido", "vestidos"],
    "jeans": ["jean", "jeans", "pantalón", "pantalones"],
    "camisas": ["camisa", "camisas", "blusa"],
    "ropa deportiva": ["ropa deportiva", "deportiva"],
    "ropa infantil": ["ropa infantil", "ropa para niños", "ropa de niños", "ropa bebé", "ropa de bebe"],
    "ropa interior": ["ropa interior", "interior", "lencería"],

    # ── Calzado ──
    "zapatos": ["zapato", "zapatos", "calzado"],
    # Tenis/deportivos: en la base casi ninguna zapatería tiene la palabra
    # "deportivo" (D'Italy TENNIS y TENNIS van con doble n, otras solo
    # dicen "calzado"). Para no dejar locales por fuera, se lista todo el
    # calzado + los que digan tennis.
    "zapatos deportivos": ["deportivo", "tenis", "tennis", "zapatilla"],
    "tenis": ["tenis", "tennis", "zapatilla", "deportivo"],
    "zapatos formales": ["formal", "vestir", "tacón", "tacon"],
    "sandalias": ["sandalia", "sandalias"],

    # ── Accesorios ──
    "gafas": ["gafas", "lentes", "óptica", "optica"],
    "relojes": ["reloj", "relojes", "relojería"],
    "joyería": ["joyer", "joya", "anillo", "cadena"],
    "bolsos": ["bolso", "bolsos", "cartera", "carteras", "morral", "morrales", "billetera", "riñonera", "maletín", "maleta"],
    "accesorios": ["accesorio", "accesorios"],

    # ── Belleza ──
    "maquillaje": ["maquillaje", "cosmético", "cosmetico", "cosméticos", "labial", "base"],
    "cuidado capilar": ["cabello", "capilar", "shampoo", "champú", "champu", "tratamiento capilar"],

    # ── Tecnología ──
    "tecnología": ["tecnolog", "celular", "computador", "electrónica"],
    "celulares": ["celular", "celulares", "móvil", "smartphone"],

    # ── Entretenimiento ──
    "juegos": ["juego", "juegos", "arcade", "diversión", "diversion", "recreación", "recreacion", "juegos de niños", "juegos para niños", "zona de juegos", "cumpleaños", "entretenimiento"],

    # ── Otros ──
    "droguerías": ["farmacia", "drogueria", "medicamento", "drogas "],
    "juguetes": ["juguete", "juguetería", "jugueteria"],
    "colchones": ["colchón", "colchon", "colchones"],
    "muebles": ["mueble", "muebles", "decoración", "decoracion"],
    "belleza": ["belleza", "peluquería", "peluqueria", "estética", "estetica", "salón de belleza", "salon de belleza", "spa", "barbería", "barberia"],
    "gimnasio": ["gimnasio", "gym", "fitness"],
    "bancos": ["banco", "cajero", "financiera"],
    "supermercado": ["supermercado", "mercado", "mercar", "viveres", "víveres", "abarrotes"],
}

# Para algunas categorías, las palabras que DETECTAN la intención en el
# mensaje no sirven para BUSCAR en la base: "comer" está dentro de
# "Local COMERcial" y traía 76 locales (todo el mall) cuando alguien
# preguntaba por "dónde comer". Aquí van los términos que sí se usan
# contra la base de datos para esas categorías.
TERMINOS_DB = {
    "comida": ["restaurante", "comida", "almuerzo", "plazoleta de comidas", "cocina"],
    # tenis/deportivos: se busca TODO el calzado (ver nota arriba)
    "zapatos deportivos": ["deportivo", "tenis", "tennis", "zapatilla", "zapato", "calzado"],
    "tenis": ["deportivo", "tenis", "tennis", "zapatilla", "zapato", "calzado"],
    # "tiendas deportivas": People Plays dice "accesorios deportivos" y
    # "tienda deportiva"; se busca la raíz, no solo "ropa deportiva".
    "ropa deportiva": ["ropa deportiva", "deportiva", "deportivo", "deporte"],
    # La búsqueda en base exige todas las palabras de una frase (ver
    # rag._coincide_frase): "ropa para niños" = ropa + niños.
    "ropa infantil": ["ropa infantil", "ropa niños", "ropa bebés"],
    "supermercado": ["supermercado", "mercado"],
    # "electrónica" coincidía con "pago electrónico" (Gopass, un TAG de peajes).
    "tecnología": ["tecnolog", "celular", "computador", "portatil", "audifono", "tablet"],
    "celulares": ["celular", "smartphone", "tecnolog"],
    # "mexicana" traía un puesto de micheladas; se exige comida mexicana.
    "tacos": ["taco", "burrito", "comida mexicana"],
}


def _plano(t: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFD", (t or "").lower().strip())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _terminos_db(nombre_cat: str, terminos: list[str]) -> list[str]:
    return TERMINOS_DB.get(nombre_cat, terminos)


def _en_palabra(termino: str, msg: str) -> bool:
    """
    ¿El término aparece en el mensaje como PALABRA (no como pedazo de otra)?
    Debe empezar donde empieza una palabra, y la palabra solo puede seguir
    hasta 3 letras más (plural, género, "hamburgues" → "hamburguesas").
    Antes era `termino in msg`: "comer" coincidía con "centro COMERcial"
    y una pregunta por supermercados terminaba listando restaurantes.
    """
    import re
    termino = termino.strip()
    if not termino:
        return False
    return re.search(rf"(?<![a-z0-9ñ]){re.escape(termino)}[a-z0-9ñ]{{0,3}}(?![a-z0-9ñ])", msg) is not None


def _coincide_termino(termino: str, msg: str) -> bool:
    """
    ¿El término aparece en el mensaje? Como palabra (ver _en_palabra), o
    con un error de tecleo pequeño en palabras largas ("hambuirguesas" ≈
    "hamburgues"). Solo se tolera el error en términos de 6+ letras, para
    no confundir palabras cortas distintas.
    """
    if _en_palabra(termino, msg):
        return True
    if len(termino) < 6 or " " in termino:
        return False
    import difflib
    for palabra in msg.split():
        if len(palabra) < 5:
            continue
        trozo = palabra[:len(termino) + 1]
        if difflib.SequenceMatcher(None, termino, trozo).ratio() >= 0.85 or \
           difflib.SequenceMatcher(None, termino, palabra).ratio() >= 0.85:
            return True
    return False


# Palabras que indican intención de BUSCAR un tipo (no una tienda puntual)
INTENCION_BUSQUEDA = [
    "dónde", "donde", "qué locales", "que locales", "qué tiendas", "que tiendas",
    "cuáles", "cuales", "hay", "venden", "vende", "puedo comprar", "puedo comer",
    "consigo", "encuentro", "busco", "quiero", "necesito", "tienen",
    "recomienda", "recomiéndame", "recomiendame", "opciones de",
    # "tiendas de ropa", "locales de zapatos", "almacenes de ropa", "sitios de comida"
    "tiendas de", "tienda de", "locales de", "local de", "almacenes de", "almacén de",
    "almacen de", "sitios de", "lugares de", "lugar de", "lista de", "todos los", "todas las",
]

# Mensajes MUY cortos ("ropa", "droguerías", "juguetería", "zapatos") son
# una búsqueda aunque no traigan verbo: el cliente escribió solo lo que busca.
MAX_PALABRAS_MENSAJE_CORTO = 3


def detectar_categoria(mensaje: str, exigir_intencion: bool = True) -> tuple[str, list[str]] | None:
    """
    Si el mensaje es una búsqueda por categoría, devuelve
    (nombre_categoria, terminos_para_buscar). Si no, devuelve None.

    Prefiere la coincidencia MÁS ESPECÍFICA — "zapatos formales" gana
    sobre "zapatos", "hamburguesas" gana sobre "comida" — para no
    responder de más ni de menos.

    exigir_intencion=False: se usa cuando OTRO ya decidió que es una
    búsqueda (ej. la IA del orquestador eligió 'busqueda_categoria'); ahí
    solo hace falta saber QUÉ categoría es, sin pedir un verbo como
    "dónde"/"quiero". Antes "tiendas de ropa" o "droguerías" devolvían
    None por no traer esas palabras y el bot terminaba inventando.
    """
    msg = _plano(mensaje)  # minúsculas y sin tildes: "jugueteria" = "juguetería"

    # EXCEPCIÓN: si preguntan por la UBICACIÓN de la zona de comidas /
    # plazoleta (no por comida en sí), NO es una búsqueda de categoría —
    # es una consulta de ubicación/zona que maneja la conversación
    # general. Ej: "¿dónde está la zona de comidas?", "¿dónde queda la
    # plazoleta?". Sin esto, "comidas" activaba la lista de restaurantes.
    if any(z in msg for z in ["zona de comida", "zona de comidas", "plazoleta de comida",
                               "plazoleta de comidas", "zona de restaurante"]):
        return None
    # Alquilar/arrendar un salón, local o espacio es un tema de ADMINISTRACIÓN
    # del mall, no una búsqueda de locales ("salón" disparaba peluquerías).
    if any(z in msg for z in ["alquil", "arrend", "arriendo", "salon de eventos", "salón de eventos"]):
        return None

    # ¿Hay al menos una señal de que quieren BUSCAR algo?
    hay_intencion = any(_plano(p) in msg for p in INTENCION_BUSQUEDA)
    if not hay_intencion and len(msg.replace("?", " ").replace("¿", " ").split()) <= MAX_PALABRAS_MENSAJE_CORTO:
        hay_intencion = True  # mensaje corto tipo "droguerías" / "tiendas de ropa"
    if not hay_intencion and not exigir_intencion:
        hay_intencion = True
    if not hay_intencion:
        return None

    # Buscamos todas las categorías cuyo NOMBRE aparezca en el mensaje,
    # y nos quedamos con la más específica (la de nombre más largo, que
    # típicamente es la más precisa: "zapatos formales" > "zapatos").
    coincidencias = []
    for nombre_cat, terminos in CATEGORIAS_BUSQUEDA.items():
        # Coincide si el nombre de la categoría, o cualquiera de sus
        # términos de búsqueda, aparece en el mensaje.
        if _en_palabra(_plano(nombre_cat), msg) or any(_coincide_termino(_plano(t), msg) for t in terminos):
            coincidencias.append((nombre_cat, _terminos_db(nombre_cat, terminos)))

    if not coincidencias:
        return None

    # PRIORIDAD DE COMIDA: si el mensaje tiene señales claras de que el
    # cliente quiere COMER (no comprar ropa), la comida gana — aunque
    # también mencione "niños"/"familia" (que dispararían "ropa
    # infantil"). Evita el error de mandar a alguien que busca almorzar
    # con la familia a tiendas de ropa infantil.
    SEÑALES_COMER = ["comer", "comida", "almorzar", "almuerzo", "cenar", "desayunar",
                     "hambre", "restaurante", "plazoleta", "comidas"]
    if any(_en_palabra(s, msg) for s in SEÑALES_COMER):
        comida_cats = [c for c in coincidencias if c[0] in (
            "comida", "hamburguesas", "pizza", "tacos", "pollo", "comida rápida",
            "almuerzos", "postres", "helados", "café", "sushi",
        )]
        if comida_cats:
            # devolvemos la categoría de comida más específica
            comida_cats.sort(key=lambda c: -len(c[0]))
            return comida_cats[0]

    # La más específica = la de nombre más largo
    coincidencias.sort(key=lambda c: -len(c[0]))
    return coincidencias[0]


def ubicacion_mostrable(store) -> str:
    """
    Cómo se le dice al cliente dónde queda un local: SOLO la zona
    ("Pasillo Vélez", "Plaza Principal", "Paseo de la Cruz"). El Centro
    Comercial pidió NO hablar de niveles (confunden al cliente). La Torre
    Médica es la excepción: ahí sí se dice el piso ("Torre Médica, Piso 4").
    """
    piso = (getattr(store, "floor", "") or "").strip()
    zona = (getattr(store, "location_hint", "") or "").strip()
    if piso.lower() == "por confirmar":
        piso = ""
    if zona.lower().startswith("torre"):
        return ", ".join(x for x in [zona, piso] if x)
    return zona


def construir_lista_locales(stores: list, nombre_categoria: str) -> str:
    """
    Arma el texto con TODOS los locales de la categoría — orden
    alfabético neutral, sin destacar a ninguno. Cada uno con lo
    esencial para que el cliente sepa a dónde ir.
    """
    if not stores:
        return ""

    lineas = [f"Estos son los locales donde puedes encontrar {nombre_categoria} en el Centro Comercial El Puente:\n"]
    for s in stores:
        partes = [f"• *{s.name}*"]
        ubic = ubicacion_mostrable(s)
        if ubic:
            partes.append(f" — {ubic}")
        if s.phone:
            partes.append(f" · Tel: {s.phone}")
        lineas.append("".join(partes))

    return "\n".join(lineas)