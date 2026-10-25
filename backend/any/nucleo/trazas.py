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

    @staticmethod
    def _texto(detalle, limite: int = 1500) -> str:
        if detalle is None:
            return ""
        t = detalle if isinstance(detalle, str) else json.dumps(detalle, ensure_ascii=False, default=str)
        return t if len(t) <= limite else t[:limite] + " …"

    def pasos_para_panel(self) -> list[dict]:
        """Formato que lee la página de trazas del panel: [{paso, detalle (texto), ms (acumulado)}]."""
        salida, acumulado = [], 0.0
        for p in self.pasos:
            acumulado += float(p.get("ms") or 0)
            salida.append({"paso": str(p.get("paso", "")), "detalle": self._texto(p.get("detalle")),
                           "ms": round(acumulado, 1)})
        salida.append({"paso": "costo", "ms": self.ms_total,
                       "detalle": f"tokens entrada {self.tokens['entrada']} · salida {self.tokens['salida']} · "
                                  f"modelos: {', '.join(sorted(self.modelos)) or 'ninguno'}"})
        return salida

    @staticmethod
    def contenido_para_panel(respuesta) -> list[dict]:
        """Lo que se agregó a la respuesta, como lista [{tipo, detalle}] (formato del panel)."""
        extra = []
        for a in respuesta.adjuntos:
            tipo = {"imagen": "foto", "documento": "documento", "ubicacion": "ubicacion"}.get(a.tipo, a.tipo)
            extra.append({"tipo": tipo, "detalle": a.url or a.titulo or a.direccion or a.leyenda or ""})
        promo = respuesta.meta.get("promo")
        if isinstance(promo, dict):
            extra.append({"tipo": str(promo.get("tipo") or "promocion"),
                          "detalle": str(promo.get("nombre") or promo.get("titulo") or Traza._texto(promo, 300))})
        if respuesta.entidades:
            extra.append({"tipo": "entidades", "detalle": Traza._texto(respuesta.entidades, 500)})
        return extra

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
                contenido_extra=json.dumps(self.contenido_para_panel(respuesta), ensure_ascii=False, default=str),
                ubicacion_enviada="si" if any(a.tipo == "ubicacion" for a in respuesta.adjuntos) else "no",
                pasos=json.dumps(self.pasos_para_panel(), ensure_ascii=False, default=str),
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