"""
Traza de cada mensaje: por dónde pasó, qué decidió el router y por qué,
qué datos reunió el flujo, qué herramientas pidió el modelo, cuánto tardó y
cuánto costó en tokens. Se guarda en la tabla existente `orchestrator_traces`
(la que ya lee el panel) con metodo_decision="any2" y herramienta "any:<flujo>".
La fase 7 construye sobre esto la página "Recorrido de cada mensaje".
"""
from __future__ import annotations

import json
import logging
import time

log = logging.getLogger("any.trazas")


class Traza:
    def __init__(self, telefono: str, mensaje: str, modo: str):
        self.telefono, self.mensaje, self.modo = telefono, mensaje, modo
        self.t0 = time.perf_counter()
        self._ultimo = self.t0
        self.pasos: list[dict] = []
        self.alertas: list[str] = []
        self.tokens = {"entrada": 0, "salida": 0}
        self.modelos: set = set()

    def paso(self, nombre: str, detalle=None):
        ahora = time.perf_counter()
        self.pasos.append({"paso": nombre, "detalle": detalle, "ms": round((ahora - self._ultimo) * 1000, 1)})
        self._ultimo = ahora

    def alerta(self, texto: str):
        """Algo que una guardia corrigió o que merece revisión (lo leerá Emilia en la fase 8)."""
        self.alertas.append(texto)
        self.paso("alerta", texto)

    def llm(self, rol: str, r):
        self.tokens["entrada"] += r.tokens_entrada
        self.tokens["salida"] += r.tokens_salida
        self.modelos.add(r.modelo)
        self.paso(f"llm_{rol}", {"modelo": r.modelo, "ms": round(r.ms), "tokens": [r.tokens_entrada, r.tokens_salida],
                                 "herramientas_pedidas": [c.nombre for c in r.llamadas]})

    @property
    def ms_total(self) -> float:
        return round((time.perf_counter() - self.t0) * 1000, 1)

    def resumen(self) -> dict:
        return {"pasos": self.pasos, "alertas": self.alertas, "tokens": self.tokens,
                "modelos": sorted(self.modelos), "ms_total": self.ms_total}

    def guardar(self, db, decision, respuesta):
        """Escribe la traza. Nunca rompe la respuesta si falla."""
        try:
            from models.orchestrator_trace import OrchestratorTrace
            fotos = [a.url for a in respuesta.adjuntos if a.tipo == "imagen" and a.url]
            fila = OrchestratorTrace(
                phone_number=self.telefono[:20],
                mensaje_usuario=self.mensaje,
                herramienta_elegida=f"any:{decision.flujo if decision else respuesta.flujo}"[:50],
                metodo_decision="any2",
                razon_decision=(f"[{decision.metodo}] {decision.razon}" if decision else "")[:2000],
                respuesta_bot="\n\n".join(respuesta.mensajes()),
                fotos_enviadas=len(fotos),
                fotos_urls=json.dumps(fotos),
                contenido_extra=json.dumps({"entidades": respuesta.entidades, "meta": respuesta.meta,
                                            "adjuntos": [a.dict() for a in respuesta.adjuntos]},
                                           ensure_ascii=False, default=str),
                ubicacion_enviada="si" if any(a.tipo == "ubicacion" for a in respuesta.adjuntos) else "no",
                pasos=json.dumps(self.resumen(), ensure_ascii=False, default=str),
                tiempo_total_ms=self.ms_total,
                modo=self.modo[:10],
            )
            db.add(fila)
            db.commit()
            return fila.id
        except Exception as e:  # la traza es importante, pero nunca más que responderle al cliente
            log.error("No se pudo guardar la traza: %s", e)
            try:
                db.rollback()
            except Exception:
                pass
            return None
