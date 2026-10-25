from sqlalchemy import Column, Integer, String, Text, DateTime, Float
from sqlalchemy.sql import func
from models.database import Base


class OrchestratorTrace(Base):
    """
    Traza de CADA mensaje que procesa el orquestador — el corazón de la
    transparencia del sistema nuevo. Para cada mensaje guarda el
    razonamiento completo: qué herramientas consideró, cuál eligió, por
    qué, qué encontró, qué respondió, y cuánto tardó cada paso.

    Esto es lo que hace el flujo VISIBLE — en vez de adivinar por qué el
    bot respondió como respondió, se abre la traza y se ve el paso a
    paso real. Distinto a las trazas viejas (que iban a los logs de
    Railway y se perdían), estas quedan guardadas y consultables desde
    el panel.

    El campo `pasos` guarda un JSON con la secuencia de decisiones —
    formato flexible para no tener que migrar la tabla cada vez que
    agregamos un tipo de paso nuevo.
    """
    __tablename__ = "orchestrator_traces"

    id             = Column(Integer, primary_key=True, index=True)
    phone_number   = Column(String(20), nullable=False, index=True)
    mensaje_usuario = Column(Text, nullable=False)

    # Decisión principal
    herramienta_elegida = Column(String(50), nullable=True)   # ej. "buscar_tienda", "emergencia"
    metodo_decision     = Column(String(20), nullable=True)   # "reglas" | "ia" | "hibrido"
    razon_decision      = Column(Text, nullable=True)         # por qué eligió esa herramienta

    # Resultado
    respuesta_bot   = Column(Text, nullable=True)
    fotos_enviadas  = Column(Integer, default=0)
    fotos_urls      = Column(Text, nullable=True)             # JSON: lista de links de las fotos enviadas
    contenido_extra = Column(Text, nullable=True)             # JSON: qué evento/promo/sorteo/tienda se agregó
    ubicacion_enviada = Column(String(5), default="no")       # "si" | "no"

    # Detalle completo del razonamiento (JSON serializado)
    pasos          = Column(Text, nullable=True)              # JSON: [{paso, detalle, ms}, ...]

    # Rendimiento
    tiempo_total_ms = Column(Float, nullable=True)

    # Modo en que se procesó (para distinguir pruebas de producción)
    modo           = Column(String(10), default="prueba")     # "prueba" | "produccion"

    created_at     = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self):
        import json
        try:
            pasos = json.loads(self.pasos) if self.pasos else []
        except Exception:
            pasos = []
        try:
            fotos_urls = json.loads(self.fotos_urls) if self.fotos_urls else []
        except Exception:
            fotos_urls = []
        try:
            contenido_extra = json.loads(self.contenido_extra) if self.contenido_extra else []
        except Exception:
            contenido_extra = []
        # Tolerancia de formato: las trazas de Any 2.0 guardadas antes del 25/10/2026 traían
        # "pasos" como objeto y "contenido_extra" como objeto; el panel espera listas de textos.
        if isinstance(pasos, dict):
            pasos = pasos.get("pasos") or []
        if not isinstance(pasos, list):
            pasos = []
        limpios = []
        for p in pasos:
            if not isinstance(p, dict):
                p = {"paso": "", "detalle": p, "ms": 0}
            det = p.get("detalle")
            if det is not None and not isinstance(det, str):
                det = json.dumps(det, ensure_ascii=False, default=str)[:1500]
            ms = p.get("ms")
            limpios.append({"paso": str(p.get("paso") or ""), "detalle": det or "",
                            "ms": ms if isinstance(ms, (int, float)) else 0})
        pasos = limpios
        if isinstance(contenido_extra, dict):
            contenido_extra = [{"tipo": str(k), "detalle": json.dumps(v, ensure_ascii=False, default=str)[:500]}
                               for k, v in contenido_extra.items() if v]
        if not isinstance(contenido_extra, list):
            contenido_extra = []
        contenido_extra = [c if isinstance(c, dict) and isinstance(c.get("detalle", ""), str)
                           else {"tipo": str((c or {}).get("tipo", "extra")) if isinstance(c, dict) else "extra",
                                 "detalle": json.dumps(c, ensure_ascii=False, default=str)[:500]}
                           for c in contenido_extra]
        if not isinstance(fotos_urls, list):
            fotos_urls = []
        return {
            "id": self.id,
            "phone_number": self.phone_number,
            "mensaje_usuario": self.mensaje_usuario,
            "herramienta_elegida": self.herramienta_elegida,
            "metodo_decision": self.metodo_decision,
            "razon_decision": self.razon_decision,
            "respuesta_bot": self.respuesta_bot,
            "fotos_enviadas": self.fotos_enviadas,
            "fotos_urls": fotos_urls,
            "contenido_extra": contenido_extra,
            "ubicacion_enviada": self.ubicacion_enviada,
            "pasos": pasos,
            "tiempo_total_ms": self.tiempo_total_ms,
            "modo": self.modo,
            "created_at": str(self.created_at) if self.created_at else None,
        }