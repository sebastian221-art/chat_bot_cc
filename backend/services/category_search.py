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
    "hamburguesas": ["hamburgues"],
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
    "ropa infantil": ["infantil", "niños", "bebé", "bebe"],
    "ropa interior": ["ropa interior", "interior", "lencería"],

    # ── Calzado ──
    "zapatos": ["zapato", "zapatos", "calzado"],
    "zapatos deportivos": ["deportivo", "tenis", "zapatilla"],
    "tenis": ["tenis", "zapatilla", "deportivo"],
    "zapatos formales": ["formal", "vestir", "tacón", "tacon"],
    "sandalias": ["sandalia", "sandalias"],

    # ── Accesorios ──
    "gafas": ["gafas", "lentes", "óptica", "optica"],
    "relojes": ["reloj", "relojes", "relojería"],
    "joyería": ["joyer", "joya", "anillo", "cadena"],
    "bolsos": ["bolso", "bolsos", "cartera", "maletín"],

    # ── Tecnología ──
    "tecnología": ["tecnolog", "celular", "computador", "electrónica"],
    "celulares": ["celular", "celulares", "móvil", "smartphone"],

    # ── Otros ──
    "farmacias": ["farmacia", "droguería", "drogueria", "medicamento"],
    "juguetes": ["juguete", "juguetería", "jugueteria"],
    "colchones": ["colchón", "colchon", "colchones"],
    "muebles": ["mueble", "muebles", "hogar"],
    "belleza": ["belleza", "peluquería", "peluqueria", "estética", "salón"],
    "gimnasio": ["gimnasio", "gym", "fitness"],
    "bancos": ["banco", "cajero", "financiera"],
}

# Palabras que indican intención de BUSCAR un tipo (no una tienda puntual)
INTENCION_BUSQUEDA = [
    "dónde", "donde", "qué locales", "que locales", "qué tiendas", "que tiendas",
    "cuáles", "cuales", "hay", "venden", "vende", "puedo comprar", "puedo comer",
    "consigo", "encuentro", "busco", "quiero", "necesito", "tienen",
    "recomienda", "recomiéndame", "recomiendame", "opciones de",
]


def detectar_categoria(mensaje: str) -> tuple[str, list[str]] | None:
    """
    Si el mensaje es una búsqueda por categoría, devuelve
    (nombre_categoria, terminos_para_buscar). Si no, devuelve None.

    Prefiere la coincidencia MÁS ESPECÍFICA — "zapatos formales" gana
    sobre "zapatos", "hamburguesas" gana sobre "comida" — para no
    responder de más ni de menos.
    """
    msg = msg_limpio = mensaje.lower()

    # ¿Hay al menos una señal de que quieren BUSCAR algo?
    hay_intencion = any(p in msg for p in INTENCION_BUSQUEDA)
    if not hay_intencion:
        return None

    # Buscamos todas las categorías cuyo NOMBRE aparezca en el mensaje,
    # y nos quedamos con la más específica (la de nombre más largo, que
    # típicamente es la más precisa: "zapatos formales" > "zapatos").
    coincidencias = []
    for nombre_cat, terminos in CATEGORIAS_BUSQUEDA.items():
        # Coincide si el nombre de la categoría, o cualquiera de sus
        # términos de búsqueda, aparece en el mensaje.
        if nombre_cat in msg or any(t in msg for t in terminos):
            coincidencias.append((nombre_cat, terminos))

    if not coincidencias:
        return None

    # PRIORIDAD DE COMIDA: si el mensaje tiene señales claras de que el
    # cliente quiere COMER (no comprar ropa), la comida gana — aunque
    # también mencione "niños"/"familia" (que dispararían "ropa
    # infantil"). Evita el error de mandar a alguien que busca almorzar
    # con la familia a tiendas de ropa infantil.
    SEÑALES_COMER = ["comer", "comida", "almorzar", "almuerzo", "cenar", "desayunar",
                     "hambre", "restaurante", "plazoleta", "comidas"]
    if any(s in msg for s in SEÑALES_COMER):
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
        ubic = []
        if s.floor:
            ubic.append(s.floor)
        if s.location_hint:
            ubic.append(s.location_hint)
        if ubic:
            partes.append(f" — {', '.join(ubic)}")
        if s.phone:
            partes.append(f". Tel: {s.phone}")
        lineas.append("".join(partes))

    return "\n".join(lineas)