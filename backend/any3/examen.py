"""
Examen del cerebro de Any 3.0 con preguntas REALES de clientes (las mismas del banco de Any 2.0 y más).
Mide lo que importa: ¿eligió los locales correctos y ninguno que no sea?

  python -m any3.examen                     (necesita la clave del modelo en el entorno)
  POST /any3/examen  y luego  GET /any3/examen   (desde el panel, en Railway, donde está la clave)

Para comparar modelos: ANY3_LLM=anthropic:claude-haiku-5-5 / anthropic:claude-sonnet-5-5 / groq:openai/gpt-oss-120b
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime

from any.evals.banco_busqueda import CASOS, NOMBRES

# (pregunta, acción esperada, palabra que debe estar en el título de algún K elegido o None)
INFO: list[tuple[str, str, str | None]] = [
    ("¿Cuánto vale el parqueadero?", "info", "parqueadero"),
    ("¿El parqueadero es gratis si compro en Jumbo?", "info", "parqueadero"),
    ("¿Cuánto vale la mensualidad de moto?", "info", "parqueadero"),
    ("¿A qué hora cierran hoy?", "info", "horario"),
    ("¿Puedo entrar con mi perro?", "info", "mascotas"),
    ("¿Cómo registro mis facturas para el sorteo?", None, None),
    ("¿Dónde compro una tarjeta de regalo?", "info", "bono"),
    ("¿Hay enfermería?", "info", "enfermeria"),
    ("Necesito el correo de la gerente", "info", "gerencia"),
    ("¿Cuál es la dirección del centro comercial?", "info", "direccion"),
    ("¿Qué eventos hay este fin de semana?", "eventos", None),
    ("¿Qué sorteos hay?", "sorteos_promos", None),
    ("¿Qué películas hay en cine?", "cine", None),
    ("Quiero pedir un domicilio de Zirus Pizza", "domicilios", None),
    ("Me robaron el celular en el baño", "emergencia_queja", None),
    ("Quiero arrendar un local", "administracion", None),
    ("Hola", "conversacion", None),
    ("Gracias, muy amable", "conversacion", None),
]


def _ctx(db, mensaje: str):
    from any.config import ZONA_HORARIA
    from any.nucleo.estado import EstadoSesion
    from any.nucleo.tipos import Contexto
    from any.nucleo.trazas import Traza
    return Contexto(db=db, telefono="examen-any3", nombre="", mensaje=mensaje, ahora=datetime.now(ZONA_HORARIA),
                    historial=[], sesion_nueva=True, estado=EstadoSesion("examen-any3"),
                    traza=Traza("examen-any3", mensaje, "eval"), modo="eval")


async def _uno(db, d, pregunta: str):
    from any3 import cerebro
    t0 = time.perf_counter()
    ctx = _ctx(db, pregunta)
    try:
        el = await cerebro.elegir(ctx, d)
    except Exception as e:
        return None, f"error: {e}"[:200], time.perf_counter() - t0, ctx.traza.tokens
    return el, "", time.perf_counter() - t0, ctx.traza.tokens


async def correr(db, paralelo: int = 4, progreso=None, modelo: str = "") -> dict:
    from any.nucleo.harness import _cargar_modelos
    from any3 import config
    if modelo:
        config.MODELO_FORZADO.set(modelo)
    from any3.directorio import construir
    _cargar_modelos()
    d = construir(db)
    existentes = {l.nombre for l in d.locales.values()}
    sem = asyncio.Semaphore(paralelo)
    casos = ([("producto", p, deben, nunca) for p, deben, nunca in CASOS]
             + [("nombre", p, {esperado}, set()) for p, esperado in NOMBRES]
             + [("info", p, acc, k) for p, acc, k in INFO])

    async def evaluar(caso):
        tipo, pregunta, a, b = caso
        async with sem:
            el, error, seg, tokens = await _uno(db, d, pregunta)
        fila = {"tipo": tipo, "pregunta": pregunta, "segundos": round(seg, 1), "tokens": tokens}
        if el is None:
            fila.update(ok=False, problema=error)
        else:
            nombres = [d.nombre(i) for i in el.ids]
            fila.update(accion=el.accion, eligio=nombres, info=[d.nombre(i) for i in el.info_ids], razon=el.razon)
            if tipo in ("producto", "nombre"):
                faltan = sorted({n for n in a if n in existentes} - set(nombres))
                sobran = sorted(set(nombres) & b)
                if tipo == "nombre" and set(nombres) != a & existentes and a & existentes:
                    sobran = sorted(set(nombres) - a)
                fila.update(ok=not faltan and not sobran, faltan=faltan, sobran=sobran)
            else:
                ok = a is None or el.accion == a
                if ok and b:
                    from any.conocimiento.texto import normalizar
                    ok = any(b in normalizar(d.nombre(i)) for i in el.info_ids) or \
                        any(b in normalizar(d.nombre(i)) for i in el.ids)
                fila.update(ok=ok)
        if progreso:
            progreso(fila)
        return fila

    t0 = time.perf_counter()
    filas = await asyncio.gather(*(evaluar(c) for c in casos))
    bien = sum(1 for f in filas if f.get("ok"))
    entrada = sum(f["tokens"]["entrada"] for f in filas)
    return {"modelo": config.modelo(), "total": len(filas), "bien": bien,
            "porcentaje": round(100 * bien / max(1, len(filas)), 1),
            "segundos_promedio": round(sum(f["segundos"] for f in filas) / max(1, len(filas)), 1),
            "tokens_entrada_total": entrada, "duracion_s": round(time.perf_counter() - t0, 1),
            "fallas": [f for f in filas if not f.get("ok")], "todas": filas}


if __name__ == "__main__":
    from models.database import SessionLocal
    res = asyncio.run(correr(SessionLocal()))
    for f in res["fallas"]:
        print("❌", f["pregunta"], "→", f.get("accion"), f.get("eligio"), "faltan", f.get("faltan"),
              "sobran", f.get("sobran"), f.get("problema", ""))
    print(f"\n{res['modelo']}: {res['bien']}/{res['total']} ({res['porcentaje']} %) · "
          f"{res['segundos_promedio']} s por pregunta")
