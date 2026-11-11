"""
Dónde se guarda el examen: en la BASE DE DATOS, no en la memoria del servidor.
Antes quedaba en memoria y se perdía si Railway reiniciaba (cada vez que se sube código) o si la petición de
«Ver examen» caía en otro proceso del servidor: por eso «Ver examen» salía vacío.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import text

MINUTOS_SIN_LATIDO = 6     # si un examen «corriendo» no avanza en este tiempo, se cortó (reinicio del servidor)


def _sesion():
    from models.database import SessionLocal
    return SessionLocal()


def _asegurar(db):
    db.execute(text("CREATE TABLE IF NOT EXISTS any3_examenes "
                    "(motor VARCHAR(10) PRIMARY KEY, datos TEXT, actualizado VARCHAR(40))"))
    db.commit()


def guardar(motor: str, datos: dict):
    db = _sesion()
    try:
        _asegurar(db)
        cuerpo = json.dumps(datos, ensure_ascii=False, default=str)
        ahora = datetime.now(timezone.utc).isoformat()
        r = db.execute(text("UPDATE any3_examenes SET datos = :d, actualizado = :a WHERE motor = :m"),
                       {"d": cuerpo, "a": ahora, "m": motor})
        if not r.rowcount:
            db.execute(text("INSERT INTO any3_examenes (motor, datos, actualizado) VALUES (:m, :d, :a)"),
                       {"d": cuerpo, "a": ahora, "m": motor})
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def leer() -> dict:
    db = _sesion()
    try:
        _asegurar(db)
        filas = db.execute(text("SELECT motor, datos, actualizado FROM any3_examenes")).fetchall()
    finally:
        db.close()
    out = {}
    for motor, datos, actualizado in filas:
        try:
            d = json.loads(datos or "{}")
        except ValueError:
            continue
        d["actualizado"] = actualizado
        if d.get("estado") in ("corriendo", "en espera") and actualizado:
            try:
                quieto = (datetime.now(timezone.utc) - datetime.fromisoformat(actualizado)).total_seconds() / 60
            except ValueError:
                quieto = 0
            if quieto > MINUTOS_SIN_LATIDO:
                d["estado"] = "interrumpido"
                d["error"] = ("Se cortó (el servidor se reinició, por ejemplo al subir código). "
                              "Toca «Correr examen» otra vez.")
        out[motor] = d
    return out
