"""
Banco de pruebas REAL de búsqueda de locales por producto o categoría.

Cada caso es una pregunta que un cliente hizo de verdad (sacada de las trazas de producción, oct–nov 2026),
con los locales que DEBEN salir y los que NO pueden salir. Si un local de «debe» no está en la base de pruebas,
ese local no se exige (la base de pruebas puede ser más vieja que la de producción).

  python -m any.evals.banco_busqueda          → imprime aciertos y fallas
  test_banco_busqueda (pruebas.py)            → falla si algún caso falla

Cuando aparezca una falla nueva en producción: se agrega aquí el caso ANTES de arreglarla.
"""
from __future__ import annotations

import asyncio
import types

# (pregunta, deben_salir, no_pueden_salir)
CASOS: list[tuple[str, set, set]] = [
    # ── 11/11: palabras como «mujer», «niños», «colegio» no pueden traer locales por sí solas ──
    ("Shampoo para mujer", {"MILAGROS", "Menta Hair"},
     {"Alucinada", "Americanino", "Calzado Rich", "Chevignon", "Dra. Alejandra Téllez", "ESPRIT"}),
    ("Estoy buscando como cremas para mujer si así", {"Senthia", "Tienda Piel"},
     {"Alucinada", "Americanino", "Calzado Rich", "Chevignon", "Chivo Loco", "Dra. Alejandra Téllez"}),
    ("Ropa deportiva", {"people plays", "D'ITALY tennis", "FootPrints"},
     {"Alucinada", "Americanino", "Chevignon", "Drogas La Principal del Fonce", "CROMANTIC"}),
    ("Y deportivo", {"people plays", "D'ITALY tennis", "FootPrints"}, {"Alucinada"}),
    ("Carrito para niños", {"Super kars", "ROAD TRIP"},
     {"Calzado Rich", "CASA DEL LIBRO", "Club House Pádel", "RAMONA FLOWERS", "Offcorss", "Tomaticos", "TOTTO"}),
    ("Quiero bolsos para el colegio", {"TOTTO"}, {"Artesanias Pueblito viejo"}),
    ("Bolso para dama", {"RIVANO", "MANTRA", "Moma"}, {"Drogas La Principal del Fonce"}),
    ("dónde venden bolsos", {"RIVANO", "MANTRA", "Moma", "TOTTO"}, set()),
    ("Jeans para mujer", {"STOP JEANS", "Americanino", "Levis"}, {"Artesanias Pueblito viejo", "Calzado Rich"}),
    ("Vestidos para mujer", {"Alucinada", "ESPRIT", "First class store"}, {"D'ITALY tennis", "Calzado Rich"}),
    ("Quiero zapatos para dama", {"Calzado Rich", "RAMONA FLOWERS"}, {"Drogas La Principal del Fonce", "Offcorss"}),
    ("Ropa elegante", {"First class store", "Alucinada"}, {"Artesanias Pueblito viejo", "D'ITALY tennis", "Calzado Rich"}),
    ("Ropa para dama", set(), {"Artesanias Pueblito viejo", "D'ITALY tennis", "Calzado Rich", "Dra. Alejandra Téllez"}),
    ("Ropa para niñas", {"Offcorss", "Tomaticos"}, {"RAMONA FLOWERS", "Alucinada", "ESPRIT", "Chevignon"}),
    ("quisiera saber que locales de ropa infantil puedo encontrar", {"Offcorss", "Tomaticos"}, {"Alucinada", "ESPRIT"}),
    ("Accesorios para mujer", {"ACCESORIOS J&A", "Manhattan Accesorios"}, {"CLARO", "Sanautos Renault", "King Helmets"}),
    ("Ropa casual para mujer", set(), {"Calzado Rich", "Dra. Alejandra Téllez"}),
    ("Cobijas para mi casa", {"Tru"}, {"CASA DEL LIBRO"}),
    ("Quiero cobijas", {"Tru"}, set()),
    # ── dulces, gomitas, comida y bebida ──
    ("Gomitas", {"popsy", "ROAD TRIP"}, {"Calzado Rich"}),
    ("Venden gomitas?", {"popsy", "ROAD TRIP"}, set()),
    ("Gomistas", {"popsy", "ROAD TRIP"}, set()),
    ("Dulces gomistas caramelos", {"popsy", "ROAD TRIP", "Dulceria cocoa"}, set()),
    ("Café", {"Juan Valdez", "Dotos", "Loma Verde"}, {"Calzado Rich"}),
    ("Tea", {"TAROKO"}, set()),
    ("Quiero naranja", set(), {"Calzado Rich", "Americanino"}),
    ("Quiero un jugó", set(), {"Calzado Rich"}),
    ("Quiero malteada", {"Nativos", "Pololos"}, set()),
    ("Quiero obleas", {"Obleas Floridablanca"}, set()),
    ("Quiero waffles", {"Waffles"}, set()),
    ("Hay algún restaurante de comida mexicana?", {"Mero Merito"}, {"Alucinada", "RIVANO", "MANTRA"}),
    ("Quiero ir a tomarme una cerveza", {"CULTO CERVECERO"}, {"Ortopedicos y mas"}),
    ("qué bares hay", {"CULTO CERVECERO", "GITANO ENTRE HIELOS"}, {"Ortopedicos y mas"}),
    ("Quiero una hamburguesa económica", {"12B Burger Angus", "HAMBURGO 1718"}, set()),
    ("Hay supermercado?", {"Jumbo"}, {"Colchones Happy Sleep", "Vivero El Edén"}),
    # ── belleza y accesorios ──
    ("Maquillaje", {"CROMANTIC", "MAKILLA BEAUTY"}, set()),
    ("Labiales", {"CROMANTIC", "MAKILLA BEAUTY"}, set()),
    ("Quiero una manilla", {"ACCESORIOS J&A"}, {"Koaj", "STOP JEANS", "YOYO jeans", "First class store"}),
    ("Joyería", {"Yugen Joyería"}, set()),
    # ── otros rubros ──
    ("Tenis", {"D'ITALY tennis", "FootPrints", "people plays"}, {"Calzado Rich"}),
    ("Cascos para moto", {"King Helmets"}, set()),
    ("¿Dónde puedo pagar el SOAT?", {"Gopass"}, set()),
    ("¿Venden plantas?", {"Vivero El Edén"}, set()),
    ("Hay juegos infantiles?", {"Happylandia", "Maxiland Kids"}, set()),
    ("¿Hay discoteca?", {"Ibiza Social Club"}, set()),
    ("Quiero saber en donde puedo conseguir colchones", {"Colchones Happy Sleep", "Colchones Wonder"}, set()),
    ("Hay gimnasio?", {"Gimnasio Cajasan"}, set()),
    ("Cuál es el horario del lavadero?", {"Speed Clean Car"}, {"King Helmets", "Gopass"}),
    # ── comprobados al comparar con el sistema anterior (11/11) ──
    ("Sura", {"EPS Sura"}, {"Fenalco Sur de Santander"}),
    ("Ropa casual", {"Americanino", "ESPRIT", "Koaj"}, {"Havana Cocina Casual"}),
    ("Cascos para moto", {"King Helmets"}, {"Parqueaderos", "ROAD TRIP"}),
    ("me puedes recomendar tiendas de calzado", {"Calzado Rich", "VILLA SHOES", "RAMONA FLOWERS"}, set()),
    ("Quiero una chaqueta negra", {"OXFORD", "ESPRIT"}, {"King Helmets", "TAROKO"}),
    ("Ropa", {"Alucinada", "Koaj"}, {"Artesanias Pueblito viejo", "Tru"}),
    ("Shentia", {"Senthia"}, set()),
    ("Bolsos y zapatos", {"TOTTO", "RIVANO", "Calzado Rich", "VILLA SHOES"}, {"Drogas La Principal del Fonce"}),
    ("Quiero comer tacos", {"Mero Merito"}, {"Zirus Pizza", "Gari Sushi", "Wokland"}),
    ("Toallas", {"Tru"}, {"Colchones Happy Sleep", "Colchones Wonder"}),
    ("Hay pádel", {"Club House Pádel"}, set()),
    ("me regalas por favor el numero de contacto de obleas", {"Obleas Floridablanca"}, set()),
    ("Donde consigo taloneras para espolon", {"Ortopedicos y mas"}, set()),
    # ── cosas que no hay: no pueden salir locales al azar ──
    ("Masajes", set(), {"ACCESORIOS J&A", "ESPRIT", "Koaj", "MAKILLA BEAUTY", "STOP JEANS"}),
    ("¿venden helicópteros?", set(), {"Calzado Rich", "Alucinada"}),
]

# Nombres escritos distinto (11/11: «JyA», «Manhata»): debe salir ESE local
NOMBRES: list[tuple[str, str]] = [
    ("JyA", "ACCESORIOS J&A"),
    ("J&A", "ACCESORIOS J&A"),
    ("Manhata", "Manhattan Accesorios"),
    ("Manhatan", "Manhattan Accesorios"),
    ("Firts Clases Store", "First class store"),
    ("Root+co", "ROOTT+CO"),
    ("Stop jean", "STOP JEANS"),
    ("Yugen", "Yugen Joyería"),
]


class _Traza:
    def alerta(self, *_): pass
    def paso(self, *_): pass
    def llm(self, *_): pass


def _ctx(db, mensaje: str):
    from any.nucleo.tipos import Decision
    return types.SimpleNamespace(db=db, mensaje=mensaje, traza=_Traza(),
                                 decision=Decision("locales", {}, False, mensaje, "", "prueba"),
                                 estado=types.SimpleNamespace(ultimas_entidades={}))


def resultado(db, pregunta: str) -> list[str]:
    """Los locales que Any mostraría (sin la IA: el juez falla sin conexión y queda la selección del código)."""
    from any.flujos.locales import Locales
    d = asyncio.run(Locales()._reunir(_ctx(db, pregunta)))
    h = d.hechos
    if h.get("modo") == "ficha":
        return [h["local"]["nombre"]]
    return list(d.meta.get("lista_equidad") or [])


def evaluar(db) -> tuple[int, list[str]]:
    from any.conocimiento.catalogo import locales
    existentes = {l.nombre for l in locales(db, incluir_torre=True)}
    fallas, total = [], 0
    for pregunta, deben, prohibidos in CASOS:
        total += 1
        salio = set(resultado(db, pregunta))
        faltan = {n for n in deben if n in existentes} - salio
        sobran = salio & prohibidos
        if faltan or sobran:
            fallas.append(f"«{pregunta}»: faltan {sorted(faltan)} · sobran {sorted(sobran)} · salió {sorted(salio)}")
    for pregunta, esperado in NOMBRES:
        if esperado not in existentes:
            continue
        total += 1
        salio = resultado(db, pregunta)
        if salio != [esperado]:
            fallas.append(f"«{pregunta}»: debía ser {esperado} · salió {salio}")
    return total, fallas


if __name__ == "__main__":
    from models.database import SessionLocal
    total, fallas = evaluar(SessionLocal())
    for f in fallas:
        print("❌", f)
    print(f"\n{total - len(fallas)}/{total} casos bien")
