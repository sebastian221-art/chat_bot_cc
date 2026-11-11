"""
PRUEBA FINAL de Any 3.0: preguntas NUEVAS, parecidas a las de los clientes, que NO se usaron para afinar a
ninguno de los dos motores (se escribieron a partir del directorio, el 11/11, después de los ajustes).
Sirve para saber si de verdad entiende, y no solo si aprendió el banco de memoria.

Regla: si una de estas falla, se arregla la CAUSA general (prompt, datos, regla), nunca agregando ese caso a
mano en el código. Si se arreglan casos uno por uno, esta prueba deja de medir.

Formato:
  PRODUCTOS:    (pregunta, deben salir, no pueden salir)
  NOMBRES:      (como lo escribe el cliente, local exacto)
  INFO:         (pregunta, tema(s) aceptados separados por |, textos de los que al menos uno debe aparecer)
  SEGUIMIENTOS: (mensajes, locales de los que al menos uno debe estar en la última respuesta)
  NO_HAY:       (pregunta, locales que NO pueden salir) — cosas que nadie vende: debe decirlo, no inventar
"""
from __future__ import annotations

PRODUCTOS: list[tuple[str, set, set]] = [
    ("¿Dónde venden perfumes?", {"Senthia", "MAKILLA BEAUTY"}, {"Calzado Rich", "Koaj", "Jarris"}),
    ("Necesito unas gafas de sol", {"ACCESORIOS J&A"}, {"Casino Diamonds", "Jarris"}),
    ("Busco un colchón doble", {"Colchones Happy Sleep", "Colchones Spring", "Colchones Wonder", "comodisimos"},
     {"Drops", "Calzado Rich"}),
    ("¿Dónde compro un celular?", {"Mega Store", "moviles garcia"}, {"Mega Store Motos", "Jarris"}),
    ("Se me dañó el celular, ¿dónde lo arreglan?", {"moviles garcia", "Mega Store"}, {"Mega Store Motos", "Speed Clean Car"}),
    ("Quiero sushi", {"Gari Sushi", "Miyaki Sushi pez"}, {"Zirus Pizza", "Jarris"}),
    ("Antojo de pollo frito", {"Jarris", "Pollo Árabe"}, {"Gari Sushi", "Juan Valdez"}),
    ("¿Dónde puedo comer pizza?", {"Zirus Pizza"}, {"Gari Sushi", "Mero Merito"}),
    ("Quiero arroz chino", {"Wokland"}, {"Mero Merito", "Chivo Loco"}),
    ("Un tinto o un capuchino", {"Juan Valdez", "Loma Verde", "Dotos"}, {"Jarris", "Casino Diamonds"}),
    ("Quiero tomarme unos cócteles", {"GITANO ENTRE HIELOS", "LA POPORRA DRINKS"}, {"Juan Valdez", "Pololos", "Nativos"}),
    ("Micheladas", {"Enjoy Cheladas", "NAMPA DRINKS"}, {"Pololos", "Juan Valdez"}),
    ("Busco un smoothie", {"Nativos", "TAROKO"}, {"Jarris"}),
    ("Empanadas", {"Densa"}, {"Gari Sushi"}),
    ("Busco ropa interior para mujer", {"Maca Intima"}, {"Calzado Rich", "D'ITALY tennis"}),
    ("Necesito un vestido de baño", {"Maca Intima"}, {"Drops", "Speed Clean Car"}),
    ("Traje formal para hombre", {"Gino Pascalli"}, {"Alucinada", "Maca Intima", "First class store"}),
    ("Camisetas para hombre", {"ROOTT+CO", "vo5"}, {"Maca Intima", "First class store", "Alucinada", "Fuera de Serie (FDS)"}),
    ("Ropa para bebé", {"Offcorss"}, {"Maca Intima", "Alucinada", "Gino Pascalli"}),
    ("Morral para el colegio", {"TOTTO"}, {"Casino Diamonds", "Jarris"}),
    ("Una maleta para viajar", {"TOTTO"}, {"Jarris", "Drops"}),
    ("Billetera para hombre", {"RIVANO", "VILLA SHOES"}, {"Maca Intima", "Jarris"}),
    ("Correa de cuero", {"Calzado Rich", "VILLA SHOES", "RIVANO"}, {"Jarris"}),
    ("Busco un peluche para regalar", {"Dulceria cocoa", "Jugueteria cocoa kids"}, {"Calzado Rich", "Jarris"}),
    ("Juguetes para un niño de 5 años", {"Jugueteria cocoa kids"}, {"Casino Diamonds", "Ibiza Social Club"}),
    ("Aretes de oro", {"Yugen Joyería", "ACCESORIOS J&A"}, {"Calzado Rich"}),
    ("Protector solar para la cara", {"Tienda Piel"}, {"Calzado Rich", "Drops"}),
    ("¿Dónde me arreglo las uñas?", {"Apice Peluqueria"}, {"Yugen Joyería"}),
    ("Barbería para cortarme el pelo", {"Apice Peluqueria"}, {"Gino Pascalli"}),
    ("Necesito una droguería", {"Drogas La Principal del Fonce"}, {"Jarris"}),
    ("Necesito unas muletas", {"Ortopedicos y mas"}, {"Drops"}),
    ("Examen de la vista para gafas formuladas", {"Optica americana"}, {"ACCESORIOS J&A", "Casino Diamonds"}),
    ("Productos de limpieza para la casa", {"Drops"}, {"Speed Clean Car", "King Helmets"}),
    ("Sábanas para cama doble", {"Tru"}, {"Calzado Rich"}),
    ("Una planta para mi apartamento", {"Vivero El Edén"}, {"Pintemos"}),
    ("Figuras religiosas y novenas", {"Pintemos"}, {"Casino Diamonds"}),
    ("Quiero comprar un carro nuevo", {"Nissan", "Sanautos Renault"}, {"Super kars", "Speed Clean Car"}),
    ("Moto eléctrica", {"Mega Store Motos"}, {"Mega Store"}),
    ("Tag para pagar peajes", {"Gopass"}, {"Nissan"}),
    ("Lavar el casco de la moto", {"King Helmets"}, {"Speed Clean Car"}),
    ("Paquete de viaje a Cartagena", {"Jottatravel"}, {"TOTTO"}),
    ("Afiliarme a la caja de compensación", {"Parque Cajasan"}, {"Jottatravel"}),
    ("Crédito de una cooperativa", {"Comuldesa"}, {"Casino Diamonds"}),
    ("Retirar plata de Nequi", {"Paga Facil"}, {"Casino Diamonds"}),
    ("Jugar ruleta o tragamonedas", {"Casino Diamonds"}, {"Happylandia"}),
    ("Ir a bailar esta noche", {"Ibiza Social Club"}, {"Maxiland Kids", "Happylandia"}),
    ("Trampolines para niños", {"Happylandia"}, {"Casino Diamonds"}),
    ("Carritos eléctricos para que maneje mi hijo", {"Super kars", "ROAD TRIP"}, {"Nissan", "Sanautos Renault"}),
    ("Venden libros?", {"CASA DEL LIBRO"}, {"Jarris"}),
    ("Cursos técnicos para estudiar", {"Instituto Técnico Laboral Cajasan"}, {"Casino Diamonds"}),
    ("Veterinario para mi perro", {"Santiago Herrera Arango (Médico Veterinario)"}, {"Dermato integral"}),
    ("Abogado de familia", {"Benítez y Bravo Abogados"}, {"Cala Asociados"}),
    ("Hemodiálisis", {"Unidad Renal RTS"}, {"Daniel Villareal"}),
    ("Ecografía", {"ISEM"}, {"Cala Asociados"}),
    ("Pruebas de alergia y espirometría", {"Cuidados respiratorios integrales"}, {"Dermato integral"}),
    ("Botox", {"Dermato integral"}, {"CROMANTIC"}),
    ("Sacarme las cordales", {"Edgar Espinosa"}, {"Dermato integral"}),
    ("Un postre con nutella", {"Waffles"}, {"Jarris"}),
    ("Bubble tea", {"TAROKO"}, {"Jarris"}),
    ("Chicharrón y comida típica", {"Chivo Loco"}, {"Gari Sushi"}),
    ("Carne a la parrilla", {"Mercagan", "La Barra 1516"}, {"Gari Sushi", "popsy"}),
    ("Ramen", {"Gari Sushi", "Miyaki Sushi pez"}, {"Zirus Pizza"}),
    ("Cerveza artesanal", {"CULTO CERVECERO"}, {"Juan Valdez"}),
]

NOMBRES: list[tuple[str, str]] = [
    ("Wok land", "Wokland"),
    ("Pollo arabe", "Pollo Árabe"),
    ("Kasino diamons", "Casino Diamonds"),
    ("Merecido bufet", "Merecido Buffet"),
    ("moviles garsia", "moviles garcia"),
    ("Jotta travel", "Jottatravel"),
    ("Optica Americana", "Optica americana"),
    ("la poporra burguer", "La Poporra  Burger"),
    ("Comodisimos", "comodisimos"),
    ("Maca íntima", "Maca Intima"),
]

INFO: list[tuple[str, str, list[str]]] = [
    ("¿Hasta qué hora está abierto el parqueadero?", "info", ["11"]),
    ("¿Cuánto cobran la hora de carro en el parqueo?", "info", ["3.600", "3600"]),
    ("¿Cuánto vale la tarjeta para la mensualidad del parqueadero?", "info", ["20.000", "20000"]),
    ("¿Los primeros minutos del parqueadero son gratis?", "info", ["10 minutos", "10 min"]),
    ("¿Me dan parqueadero gratis si compro en Koaj?", "info", ["jumbo", "cine"]),
    ("¿A qué hora abre la plazoleta de comidas?", "info", ["11:30", "11.30"]),
    ("¿Dónde queda el Punto de Información?", "info|locales", ["barichara"]),
    ("¿Venden bonos de regalo?", "info|locales", ["punto de informacion"]),
    ("Correo de mercadeo", "info|administracion", ["mercadeo@elpuente.com.co"]),
    ("¿Con quién hablo para pautar en las pantallas?", "info|administracion", ["3176574494", "317 657 4494"]),
    ("Teléfono del centro comercial", "info|conversacion", ["3174320138", "317 432 0138"]),
    ("¿Puedo llevar a mi gato?", "info", ["mascota", "gato", "bolsa"]),
    ("¿Hay misa el domingo?", "eventos", ["11:30"]),
    ("¿Cuándo prenden las luces de navidad?", "eventos", ["22"]),
    ("¿Cuál es el premio del sorteo más grande?", "sorteos_promos", ["13.000.000", "13000000"]),
]

SEGUIMIENTOS: list[tuple[list[str], set]] = [
    (["Busco una pizzería", "¿me pasas el WhatsApp?"], {"Zirus Pizza"}),
    (["¿Qué hay de Mercagan?", "¿tienen carta?"], {"Mercagan"}),
    (["Hola, buenas tardes", "¿dónde queda la droguería?"], {"Drogas La Principal del Fonce"}),
    (["Cuéntame de King Helmets", "¿a qué hora cierran?"], {"King Helmets"}),
    (["Necesito un abogado", "¿y su teléfono?"], {"Benítez y Bravo Abogados", "Corporación Q&N Asociados"}),
    (["Quiero unos tenis", "¿cuál tiene Nike?"], {"D'ITALY tennis", "people plays"}),
]

NO_HAY: list[tuple[str, set]] = [
    ("¿Venden bicicletas?", {"Mega Store Motos", "Super kars", "Nissan"}),
    ("¿Dónde venden armas?", {"Casino Diamonds", "King Helmets"}),
    ("¿Venden llantas para carro?", {"Speed Clean Car", "King Helmets"}),
    ("¿Hay tienda de mascotas con concentrado?", {"Drops", "Jumbo"}),
]


def casos(existentes: set) -> list[tuple]:
    out = [("final_producto", [p], deben, nunca) for p, deben, nunca in PRODUCTOS]
    out += [("final_nombre", [p], {e}, set()) for p, e in NOMBRES if e in existentes]
    out += [("final_info", [p], acc, textos) for p, acc, textos in INFO]
    out += [("final_seguimiento", msgs, locs, set()) for msgs, locs in SEGUIMIENTOS if locs & existentes]
    out += [("final_no_hay", [p], set(), nunca) for p, nunca in NO_HAY]
    return out


def total() -> int:
    return len(PRODUCTOS) + len(NOMBRES) + len(INFO) + len(SEGUIMIENTOS) + len(NO_HAY)
