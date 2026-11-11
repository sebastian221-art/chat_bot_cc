"""
Pruebas de PLOMERÍA de Any 3.0 sin clave ni gasto (modelo simulado): que cada pieza haga lo que debe.
La calidad de verdad (¿elige bien?) se mide con el examen y un modelo real (any3/examen.py).

  python -m any3.pruebas
"""
from __future__ import annotations

import asyncio
import json
import os
import re

os.environ["ANY3_LLM"] = "simulado:any3"
os.environ["ANY3_LLM_RESPALDO"] = "simulado:any3"
os.environ["ANY3_NUMEROS"] = "3154559242"
os.environ.setdefault("ANY_LLM_ROUTER", "simulado:any2")
os.environ.setdefault("ANY_LLM_FLUJOS", "simulado:any2")

from any.llm import simulado                     # noqa: E402
from any.llm.base import LLMRespuesta            # noqa: E402

ESCENA: dict = {}


def _ultimo_usuario(mensajes) -> str:
    return next((m["content"] for m in reversed(mensajes) if m["role"] == "user"), "")


def manejador(mensajes, herramientas, json_salida):
    sistema = "\n".join(m["content"] for m in mensajes if m["role"] == "system")
    if "Eres el CEREBRO" in sistema:
        ESCENA["llamadas_cerebro"] = ESCENA.get("llamadas_cerebro", 0) + 1
        if ESCENA.get("cerebro_falla"):
            return LLMRespuesta(texto="esto no es json", modelo="simulado:any3")
        return LLMRespuesta(texto=json.dumps(ESCENA["cerebro"]), modelo="simulado:any3")
    if "VIGILANTE" in sistema:
        cola = ESCENA.setdefault("vigilante", [])
        v = cola.pop(0) if cola else {"ok": True, "gravedad": "ninguna"}
        ESCENA.setdefault("vistos_por_vigilante", []).append(_ultimo_usuario(mensajes))
        return LLMRespuesta(texto=json.dumps(v), modelo="simulado:any3")
    if "REVISIÓN DE CALIDAD" in sistema:
        ESCENA["correcciones"] = ESCENA.get("correcciones", 0) + 1
        return LLMRespuesta(texto=ESCENA.get("texto_corregido", "Texto corregido.\n{LISTA}"), modelo="simulado:any3")
    if json_salida:                               # router de Any 2.0 (cuando se le pasa el mensaje)
        ESCENA["any2_router"] = ESCENA.get("any2_router", 0) + 1
        return LLMRespuesta(texto=json.dumps(simulado.router_por_defecto(mensajes)), modelo="simulado:any2")
    return LLMRespuesta(texto=ESCENA.get("texto", "Claro, estos son los locales:\n{LISTA}\n¿Te ayudo con algo más?"),
                        modelo="simulado:redactor")


def _db(ruta: str):
    os.environ["DATABASE_URL"] = f"sqlite:///{ruta}"
    from models.database import SessionLocal
    return SessionLocal()


def _ids(db, *nombres) -> list[str]:
    from any.conocimiento.catalogo import locales
    por = {l.nombre: l for l in locales(db)}
    return [f"L{por[n].id}" for n in nombres if n in por]


async def correr(db) -> list[str]:
    from any.nucleo.guardias import borrar_datos
    from any3.harness import procesar
    simulado.MANEJADOR = manejador
    fallas = []

    def check(cond, que):
        print(("  ✅ " if cond else "  ❌ ") + que)
        if not cond:
            fallas.append(que)

    tel = "prueba-any3-plomeria"

    async def turno(msg, cerebro=None, **escena):
        ESCENA.clear()
        ESCENA.update(escena)
        ESCENA["cerebro"] = cerebro or {}
        return await procesar(db, tel, "Sebastián", msg)

    borrar_datos(db, tel)
    print("1. Lista por producto: el código pone la lista con contactos")
    ids = _ids(db, "D'ITALY tennis", "FootPrints", "people plays")
    r = await turno("tenis", {"accion": "locales", "ids": ids + ["L999999"], "busqueda": "tenis", "consulta": "¿dónde venden tenis?"})
    check(r.flujo == "locales" and r.meta.get("any3", {}).get("accion") == "locales", "lo respondió Any 3.0 (flujo locales)")
    check(all(n.lower() in r.texto.lower() for n in ["d'italy tennis", "footprints", "people plays"]), "están los 3 locales elegidos")
    check("{LISTA}" not in r.texto, "no quedó la marca {LISTA}")
    check(any(p["paso"] == "cerebro" and "L999999" in str(p["detalle"]) for p in r.meta["traza"]["pasos"]),
          "el ID inventado se descartó (y quedó en la traza)")

    print("2. Seguimiento: recuerda los locales mostrados")
    from any.nucleo import estado as est
    from datetime import datetime
    from any.config import ZONA_HORARIA
    e = est.cargar_estado(db, tel, datetime.now(ZONA_HORARIA))
    check(set(e.ultimas_entidades.get("any3_ids") or []) == set(ids), "guardó los IDs mostrados para el siguiente turno")

    print("3. Un local concreto: ficha con su WhatsApp")
    zid = _ids(db, "Zirus Pizza")
    r = await turno("el número de zirus", {"accion": "locales", "ids": zid, "es_local_concreto": True, "pide": "telefono"},
                    texto="Claro, el WhatsApp de Zirus Pizza es 👉 https://wa.me/573000000000")
    check(r.flujo == "locales", "flujo locales")
    check("3000000000" not in r.texto, "un número inventado por el redactor se quitó (guardias de Any 2.0)")

    print("4. El vigilante quita un local que no corresponde (sin otra llamada al redactor)")
    ids4 = _ids(db, "D'ITALY tennis", "FootPrints", "people plays", "Calzado Rich")
    r = await turno("tenis", {"accion": "locales", "ids": ids4, "busqueda": "tenis"},
                    vigilante=[{"ok": False, "gravedad": "leve", "quitar": ["Calzado Rich"]}])
    check("calzado rich" not in r.texto.lower(), "Calzado Rich salió de la lista")
    check("footprints" in r.texto.lower(), "los demás siguen")
    check(ESCENA.get("correcciones", 0) == 0, "no hizo falta reescribir")

    print("5. Vigilante: respuesta grave → se reescribe una vez")
    r = await turno("tenis", {"accion": "locales", "ids": ids, "busqueda": "tenis"},
                    vigilante=[{"ok": False, "gravedad": "grave", "problemas": ["dice que no hay"]}, {"ok": True}],
                    texto_corregido="¡Claro! Estos venden tenis:\n{LISTA}")
    check(ESCENA.get("correcciones") == 1, "se pidió una corrección")
    check(r.texto.startswith("¡Claro! Estos venden tenis"), "se envió la corregida")

    print("6. Vigilante rechaza dos veces → respuesta armada por código")
    r = await turno("tenis", {"accion": "locales", "ids": ids, "busqueda": "tenis"},
                    vigilante=[{"ok": False, "gravedad": "grave", "problemas": ["x"]},
                               {"ok": False, "gravedad": "grave", "problemas": ["y"]}])
    check("Estos son los locales que encontré" in r.texto and "footprints" in r.texto.lower(),
          "se usó el respaldo por código con la lista")

    print("7. No hay: respuesta honesta sin locales")
    r = await turno("venden helicópteros?", {"accion": "no_hay", "busqueda": "helicópteros"},
                    texto="Uy, qué pena, eso no lo tengo registrado. ¿Te ayudo con otra cosa?")
    check(r.flujo == "locales" and "•" not in r.texto, "sin lista de locales")

    print("8. Si el cerebro falla, responde Any 2.0 (el cliente nunca queda sin respuesta)")
    r = await turno("tenis", cerebro_falla=True)
    check(r.meta.get("any3", {}).get("respondio") == "any2" and r.texto, "respondió Any 2.0")

    print("9. Temas delegados (cine) → Any 2.0")
    r = await turno("qué películas hay", {"accion": "cine"})
    check(r.meta.get("any3", {}).get("respondio") == "any2", "cine lo respondió Any 2.0")

    print("10. Info del centro comercial con lo que eligió el cerebro")
    from any3.directorio import construir
    d = construir(db)
    k = next(i for i, f in d.info.items() if "parqueadero" in f["titulo"].lower())
    r = await turno("cuánto vale el parqueadero", {"accion": "info", "info_ids": [k]}, texto="El parqueadero vale $3.600 la hora para carro.")
    hechos = next(p["detalle"] for p in r.meta["traza"]["pasos"] if p["paso"] == "datos_reunidos")
    check(r.flujo == "servicios_mall" and k and "parqueadero" in str(hechos).lower(), "el fragmento elegido llegó a los datos")

    print("11. Aclarar: pregunta corta, sin inventar")
    r = await turno("eso", {"accion": "aclarar", "aclaracion": "¿Me cuentas qué estás buscando?"})
    check("¿Me cuentas qué estás buscando?" in r.texto, "hizo la pregunta del cerebro")

    print("12. Números que NO son de Any 3.0 no entran")
    from any3 import atiende
    check(atiende("573154559242") and atiende("3154559242") and not atiende("573001112233"), "solo el número de prueba")
    borrar_datos(db, tel)
    simulado.MANEJADOR = None
    return fallas


if __name__ == "__main__":
    import sys
    ruta = sys.argv[1] if len(sys.argv) > 1 else "local.db"
    db = _db(ruta)
    f = asyncio.run(correr(db))
    print(f"\n{'TODO BIEN' if not f else f'{len(f)} FALLAS'}")
    sys.exit(1 if f else 0)
