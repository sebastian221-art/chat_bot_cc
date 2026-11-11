"""
Examen con preguntas REALES de clientes. Corre la respuesta COMPLETA (lo que le llegaría al cliente) con el motor
que se elija, para comparar Any 3.0 contra Any 2.0 con exactamente las mismas preguntas.

  python -m any3.examen [any3|any2]          (necesita la clave del modelo en el entorno)
  Desde /any3/chat: botones «Correr examen» y «Ver examen» (en Railway, donde está la clave)

Qué se califica:
  - productos: que salgan los locales que DEBEN y ninguno de los que NO pueden salir;
  - nombres: que salga exactamente ese local;
  - información: que lo atienda el tema correcto y que la respuesta traiga el dato clave (precio, correo…);
  - seguimientos: conversaciones de 2 mensajes («háblame de X» → «¿y el teléfono?»);
  - nuevas: preguntas reales que no se usaron para afinar a ninguno, sin nota: se comparan a ojo.
Cada pregunta usa un teléfono de prueba nuevo y al final se borra todo lo que dejó (conversación y trazas).
"""
from __future__ import annotations

import asyncio
import time

from any.evals.banco_busqueda import CASOS, NOMBRES

# (pregunta, tema esperado, textos de los que AL MENOS UNO debe estar en la respuesta)
INFO: list[tuple[str, str, list[str]]] = [
    ("¿Cuánto vale el parqueadero?", "info", ["3.600", "3600"]),
    ("¿El parqueadero es gratis si compro en Jumbo?", "info", ["35.000", "35000"]),
    ("¿Cuánto vale la mensualidad de moto?", "info", ["60.000", "60000"]),
    ("¿A qué hora cierran hoy?", "info", ["pm", "p. m", "p.m"]),
    ("¿Puedo entrar con mi perro?", "info", ["mascota"]),
    ("¿Cómo registro mis facturas para el sorteo?", "", ["registro-de-facturas", "punto de informacion"]),
    ("¿Dónde compro una tarjeta de regalo?", "info", ["punto de informacion"]),
    ("¿Hay enfermería?", "info", ["enfermer"]),
    ("Necesito el correo de la gerente", "info", ["gerencia@elpuente.com.co"]),
    ("¿Cuál es la dirección del centro comercial?", "info", ["calle 10"]),
    ("¿Qué eventos hay este fin de semana?", "eventos", []),
    ("¿Qué sorteos hay?", "sorteos_promos", []),
    ("¿Qué películas hay en cine?", "cine", []),
    ("Quiero pedir un domicilio de Zirus Pizza", "domicilios", []),
    ("Me robaron el celular en el baño", "emergencia_queja", []),
    ("Quiero arrendar un local", "administracion", []),
    ("Hola", "conversacion", []),
    ("Gracias, muy amable", "conversacion", []),
]

# Conversaciones de varios mensajes: (mensajes, local que debe estar en la ÚLTIMA respuesta)
SEGUIMIENTOS: list[tuple[list[str], str]] = [
    (["Háblame de Zirus Pizza", "¿y el teléfono?"], "Zirus Pizza"),
    (["¿Dónde queda Juan Valdez?", "¿y a qué hora abren?"], "Juan Valdez"),
    (["Quiero comida mexicana", "¿tienen carta?"], "Mero Merito"),
    (["Hola", "busco cascos para moto"], "King Helmets"),
]

# Preguntas reales de las trazas de noviembre que NO se usaron para afinar a ninguno de los dos: no tienen
# calificación automática; están para comparar a ojo cómo responde cada motor (lo justo: Any 2.0 se afinó con
# las preguntas del banco de arriba, así que ahí juega de local).
NUEVAS: list[str] = [
    "En cuál almacén del centro comercial el puente puedo conseguir calzado de la mejor calidad",
    "Quiero dar un regalo para mujer", "Ropa casual para hombre por favor", "Ropa para jóvenes",
    "Chaquetas de jeans dama", "Quiero comer una hamburguesa", "Dónde puedo comprar un helado",
    "Quiero un vaso de mango", "Qué postres o snack de frutas puedo encontrar en el Cc",
    "Quiero comida santandereana, qué me recomiendas?", "Almuerzos tipo bufete",
    "que restaurante puedo encontrar abierto a esta hora", "Quiero plan de internet", "necesito un ortodoncista",
    "Estoy buscando consultorio de dermatología cual es ?", "Hay servicio de oncologo", "Endoscopia digestiva",
    "tienes servicio de vacunación?", "Hay una oficina de contadores públicos?",
    "Existe una oficina de asesoria tributaria", "hay algun local que vende seguros?",
    "Oye, qué bancos hay en el centro comercial.", "¿Dónde hago un giro?", "¿Dónde queda Paga Fácil?",
    "hay cargador para carro eléctrico?", "dónde hay baños", "hay wifi?", "Si voy a cine, ¿me dan parqueadero?",
    "Si compré en People Plays, ¿me dan parqueadero?",
    "Si soy empleado del centro comercial tengo descuento en el parqueadero ?",
    "Quiero saber sobre la zona de entretenimiento para adultos, cuales hay?", "Que planes puedo hacer con los niños?",
    "Hay algún lugar para reuniones o algo así", "hay clases de yoga?", "cajasan tiene clases de zumbaterapia?",
    "Cuántos años tiene de fundado el centro comercial el puente", "Cuántos locales tiene el centro comercial",
    "en donde estan ubicadas las canchas de PADEL del centro comercial?",
    "Buenos días, en que nivel de parqueadero esta ubicada la zona de motos",
    "Quiero hablar con la gerente, dame su número", "Cómo se llama la administradora del centro comercial y el contacto",
    "número de mercadeo", "hay vacantes de trabajo?", "Tienes promos en bolsos", "cual es el local 167",
    "Ramona flowers", "Isem", "Que ofrece sanitas", "Me regalas el número de la barra",
    "Tienes el instagram de Chevignon?", "Me puedes enviar la foto de la tienda people plays ?", "Dame la carta de 12b",
]

# Tema de la respuesta → acción del examen
_ACCION = {"servicios_mall": "info", "locales": "locales", "torre_medica": "locales"}


def _nombres(r) -> list[str]:
    lista = r.meta.get("lista_equidad")
    if lista:
        return list(lista)
    loc = (r.entidades or {}).get("local")
    if isinstance(loc, list):
        return [str(x) for x in loc]
    return [loc] if loc else []


async def _conversar(motor: str, mensajes: list[str], tel: str):
    from models.database import SessionLocal
    from any.nucleo.guardias import borrar_datos
    db = SessionLocal()
    try:
        borrar_datos(db, tel)
        r = None
        for m in mensajes:
            if motor == "any3":
                from any3.harness import procesar
            else:
                from any.nucleo.harness import procesar
            r = await procesar(db, tel, "", m, modo="eval")
        return r
    finally:
        try:
            borrar_datos(db, tel)
        except Exception:
            db.rollback()
        db.close()


async def correr(motor: str = "any3", paralelo: int = 3, progreso=None, modelo: str = "") -> dict:
    from any.conocimiento.texto import normalizar
    from any.nucleo.harness import _cargar_modelos
    from models.database import SessionLocal
    from any3 import config
    from any3.directorio import construir
    if modelo:
        config.MODELO_FORZADO.set(modelo)
    _cargar_modelos()
    db = SessionLocal()
    try:
        existentes = {l.nombre for l in construir(db).locales.values()}
    finally:
        db.close()
    sem = asyncio.Semaphore(paralelo)
    casos = ([("producto", [p], deben, nunca) for p, deben, nunca in CASOS]
             + [("nombre", [p], {esperado}, set()) for p, esperado in NOMBRES if esperado in existentes]
             + [("info", [p], acc, textos) for p, acc, textos in INFO]
             + [("seguimiento", msgs, {local}, set()) for msgs, local in SEGUIMIENTOS if local in existentes]
             + [("nueva", [p], None, None) for p in NUEVAS])

    async def evaluar(i, caso):
        tipo, msgs, a, b = caso
        t0 = time.perf_counter()
        fila = {"n": i + 1, "tipo": tipo, "pregunta": " → ".join(msgs)}
        async with sem:
            try:
                r = await asyncio.wait_for(_conversar(motor, msgs, f"prueba-ex{motor[-1]}-{i}"), timeout=150)
            except Exception as e:
                r = None
                fila.update(ok=False, problema=f"error: {e!r}"[:300])
        fila["segundos"] = round(time.perf_counter() - t0, 1)
        if r is not None:
            nombres = _nombres(r)
            accion = _ACCION.get(r.flujo, r.flujo)
            m3 = r.meta.get("any3") or {}
            fila.update(tema=r.flujo, eligio=nombres, respuesta=r.texto,
                        respondio=m3.get("respondio") or ("any3" if motor == "any3" else "any2"),
                        revision=(m3.get("revision") or {}).get("intentos"))
            if tipo == "nueva":
                fila["ok"] = None          # se compara a ojo
            elif tipo in ("producto", "nombre"):
                faltan = sorted({n for n in a if n in existentes} - set(nombres))
                sobran = sorted(set(nombres) & b)
                if tipo == "nombre" and set(nombres) != a:
                    sobran = sorted(set(nombres) - a)
                fila.update(ok=not faltan and not sobran, faltan=faltan, sobran=sobran)
            elif tipo == "seguimiento":
                local = next(iter(a))
                ok = local in nombres or normalizar(local) in normalizar(r.texto)
                fila.update(ok=ok, faltan=[] if ok else [local])
            else:
                ok = not a or accion == a
                texto = normalizar(r.texto).replace(" ", "")
                if ok and b:
                    ok = any(normalizar(x).replace(" ", "") in texto for x in b)
                    if not ok:
                        fila["problema"] = f"la respuesta no trae: {' / '.join(b)}"
                elif not ok:
                    fila["problema"] = f"lo atendió «{r.flujo}» y debía ser «{a}»"
                fila["ok"] = ok
        if progreso:
            progreso(fila)
        return fila

    t0 = time.perf_counter()
    filas = await asyncio.gather(*(evaluar(i, c) for i, c in enumerate(casos)))
    calificadas = [f for f in filas if f["tipo"] != "nueva"]
    bien = sum(1 for f in calificadas if f.get("ok"))
    por_tipo = {}
    for f in calificadas:
        t = por_tipo.setdefault(f["tipo"], [0, 0])
        t[0] += 1 if f.get("ok") else 0
        t[1] += 1
    return {"motor": motor, "modelo": config.modelo() if motor == "any3" else "Any 2.0 (sus modelos)",
            "total": len(calificadas), "bien": bien, "porcentaje": round(100 * bien / max(1, len(calificadas)), 1),
            "sin_calificar": len(filas) - len(calificadas),
            "por_tipo": {k: f"{v[0]}/{v[1]}" for k, v in por_tipo.items()},
            "segundos_promedio": round(sum(f["segundos"] for f in filas) / max(1, len(filas)), 1),
            "duracion_s": round(time.perf_counter() - t0, 1),
            "fallas": [f for f in calificadas if not f.get("ok")], "todas": filas}


if __name__ == "__main__":
    import sys
    motor = sys.argv[1] if len(sys.argv) > 1 else "any3"
    res = asyncio.run(correr(motor))
    for f in res["fallas"]:
        print("❌", f["pregunta"], "→", f.get("eligio"), "faltan", f.get("faltan"), "sobran", f.get("sobran"),
              f.get("problema", ""))
    print(f"\n{res['motor']}: {res['bien']}/{res['total']} ({res['porcentaje']} %) · {res['por_tipo']}")


def total_casos() -> int:
    return len(CASOS) + len(NOMBRES) + len(INFO) + len(SEGUIMIENTOS) + len(NUEVAS)
