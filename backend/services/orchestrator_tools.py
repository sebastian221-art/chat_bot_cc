# 📄 ARCHIVO: backend/services/orchestrator_tools.py
"""
Registro central de HERRAMIENTAS del orquestador.

Este es el punto ÚNICO y VISIBLE donde se define todo lo que el bot
sabe hacer. Cada herramienta tiene:
  - nombre: identificador corto
  - descripcion: qué hace, en lenguaje natural (esto es lo que la IA
    lee para decidir cuándo usarla)
  - palabras_clave: para la decisión RÁPIDA por reglas (sin gastar IA)
  - categoria: para agrupar en el panel visual

La función real que ejecuta cada herramienta se conecta en
orchestrator.py — aquí solo se DECLARAN, para que "ver qué sabe hacer
el bot" sea leer esta lista, y para que el panel visual la muestre.

Agregar una herramienta nueva = agregar una entrada aquí + conectar su
función en orchestrator.py. Nada más regado por el código.
"""

# El orden importa para la decisión por reglas: las más específicas y
# urgentes van primero (ej. emergencia antes que búsqueda general).
HERRAMIENTAS = [
    {
        "nombre": "emergencia",
        "categoria": "Seguridad",
        "descripcion": "Cuando el cliente reporta una emergencia real: niño perdido, robo, alguien herido o desmayado, incendio, o cualquier situación de peligro. Máxima prioridad.",
        "palabras_clave": [
            "se perdió", "se me perdió", "perdí a mi", "no encuentro a mi", "perdí mi hijo",
            "me robaron", "me robó", "me robo", "acaban de robar", "me atracaron", "atraco", "atraco",
            "ladrón", "ladron", "asalto", "asaltaron", "me hurtaron", "hurto",
            "desmayó", "desmayo", "se cayó", "accidente", "herido", "sangre", "convulsion",
            "incendio", "fuego", "humo", "emergencia", "ayuda urgente", "auxilio", "socorro",
        ],
    },
    {
        "nombre": "queja",
        "categoria": "Atención",
        "descripcion": "Cuando el cliente expresa una queja, reclamo o inconformidad: mal trato de un empleado, producto defectuoso, mal servicio, algo que le molestó del mall o una tienda.",
        "palabras_clave": [
            "queja", "reclamo", "reclamar", "me trataron mal", "me trató mal", "me trato mal",
            "trató mal", "trato mal", "grosero", "grosera", "defectuoso", "mal servicio", "pésimo",
            "inconforme", "molesto", "indignado", "denunciar", "denuncia",
        ],
    },
    {
        "nombre": "gestion_domicilio",
        "categoria": "Acción",
        "descripcion": "Cuando el cliente quiere hacer un pedido a domicilio o ya está en medio de una gestión de pedido.",
        "palabras_clave": [
            "domicilio", "pedir a", "hacer un pedido", "quiero pedir",
            "gestionar mi pedido", "gestionar un pedido", "a domicilio",
        ],
    },
    {
        "nombre": "cartelera_cine",
        "categoria": "Información",
        "descripcion": "Cuando preguntan por películas, cartelera, funciones o estrenos del cine.",
        "palabras_clave": [
            "cartelera", "película", "pelicula", "peliculas", "películas",
            "estreno", "estrenos", "función de cine", "funciones de cine",
            "que dan en el cine", "qué dan en el cine",
        ],
    },
    {
        "nombre": "numero_tienda",
        "categoria": "Información",
        "descripcion": "Cuando el cliente pide el número de teléfono o el contacto de una tienda específica.",
        "palabras_clave": [
            "número de", "numero de", "teléfono de", "telefono de",
            "contacto de", "me pasas el número", "me pasas el numero",
        ],
    },
    {
        "nombre": "busqueda_categoria",
        "categoria": "Información",
        "descripcion": "Cuando preguntan por un TIPO de PRODUCTO o COMIDA que quieren comprar/comer y qué locales lo tienen (ej. 'dónde comer hamburguesas', 'tiendas de zapatos', 'quiero comprar ropa'). El foco es el producto/comida que el cliente quiere obtener. IMPORTANTE: si alguien busca 'dónde comer' o 'un lugar para comer', es COMIDA, aunque mencione que va con niños o familia — nunca lo confundas con ropa infantil.",
        "palabras_clave": [],  # se detecta con category_search.detectar_categoria (más preciso)
    },
    {
        "nombre": "ubicacion_mall",
        "categoria": "Información",
        "descripcion": "Cuando preguntan dónde queda el CENTRO COMERCIAL en sí (no una tienda). Manda el pin de ubicación real.",
        "palabras_clave": [],  # se detecta con lógica especial (ubicación del mall vs búsqueda)
    },
    {
        "nombre": "torre_medica",
        "categoria": "Información",
        "descripcion": "Cuando preguntan por servicios médicos, consultorios, especialistas o la torre médica (ej. 'dónde saco una radiografía', 'hay algún cardiólogo').",
        "palabras_clave": [
            "médico", "medico", "doctor", "doctora", "consultorio", "especialista",
            "torre médica", "torre medica", "radiografía", "radiografia", "cita médica",
            "cardiólogo", "cardiologo", "cirujano", "unidad renal", "diálisis", "dialisis",
        ],
    },
    {
        "nombre": "conversacion_general",
        "categoria": "Conversación",
        "descripcion": "El caso por defecto: consultas generales sobre tiendas, horarios, servicios, o cualquier cosa que no encaje en las herramientas anteriores. Aquí vive el comportamiento propositivo y el piloteo de lo inesperado (redirige con gracia lo que no es del mall).",
        "palabras_clave": [],  # es el fallback — se usa cuando nada más aplica
    },
]


def herramienta_por_nombre(nombre: str) -> dict | None:
    for h in HERRAMIENTAS:
        if h["nombre"] == nombre:
            return h
    return None