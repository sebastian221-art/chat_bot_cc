"""Tipos que viajan por el núcleo: Contexto (entrada) → Decision (router) → Respuesta (salida)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Adjunto:
    tipo: str                       # imagen | documento | ubicacion
    url: str | None = None
    nombre_archivo: str | None = None
    leyenda: str = ""
    latitud: float | None = None
    longitud: float | None = None
    titulo: str = ""
    direccion: str = ""

    def dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v not in (None, "")}


@dataclass
class Respuesta:
    texto: str
    flujo: str = ""
    adjuntos: list[Adjunto] = field(default_factory=list)
    previos: list[str] = field(default_factory=list)   # mensajes que van ANTES (ej. aviso Ley 1581)
    entidades: dict = field(default_factory=dict)       # de qué se habló (local, evento…) para el siguiente turno
    meta: dict = field(default_factory=dict)            # datos para las guardias y la traza
    responder: bool = True                              # False = no enviar nada (bot en pausa)

    def mensajes(self) -> list[str]:
        return [m for m in self.previos + [self.texto] if m and m.strip()]


@dataclass
class Decision:
    flujo: str
    entidades: dict = field(default_factory=dict)
    es_seguimiento: bool = False
    consulta: str = ""             # la pregunta reescrita con el contexto ("¿y el horario?" → "horario de Jarris")
    razon: str = ""
    metodo: str = "ia"             # regla | ia | estado | respaldo


@dataclass
class Turno:
    rol: str                       # user | assistant
    texto: str
    cuando: datetime | None = None


@dataclass
class Contexto:
    db: Any
    telefono: str
    nombre: str
    mensaje: str
    ahora: datetime                # hora Colombia (o la simulada en pruebas)
    historial: list[Turno]
    sesion_nueva: bool
    estado: Any                    # nucleo.estado.EstadoSesion
    traza: Any                     # nucleo.trazas.Traza
    modo: str = "prueba"           # produccion | sombra | prueba | eval
    imagen: bytes | None = None
    decision: Decision | None = None
    promo: dict | None = None      # la promoción que la regla única decidió para este turno

    @property
    def nombre_real(self) -> str | None:
        """El nombre de perfil de WhatsApp solo se usa si parece un nombre de persona."""
        n = (self.nombre or "").strip()
        if not n or n.lower() in {"usuario", "user", "cliente"} or any(c.isdigit() for c in n) or len(n) > 30:
            return None
        return n.split()[0].capitalize()