"""
Flujo navegación QR (con estado). Cada QR pegado en el centro comercial abre WhatsApp con
"Estoy en Zona A5". Any:
  1. reconoce el código (regla estricta: el texto del QR, o un código que SÍ existe en la tabla
     de zonas — el sistema viejo leía "en la zona de comidas" como el código "DE");
  2. registra el escaneo (zone_scans, para el mapa de tráfico del panel) aunque la zona no exista;
  3. confirma dónde está el cliente y le pregunta a qué local quiere ir;
  4. cuando dice el local, le dice en qué zona queda respecto a donde está.
No inventa giros ni distancias: la base no tiene rutas. Cuando el panel tenga "indicaciones" por
zona (fase 7), se usan aquí.
"""
from __future__ import annotations

import re

from ..conocimiento.buscador import buscar_locales, encontrar_local
from ..conocimiento.texto import normalizar
from ..nucleo.tipos import Adjunto, Contexto
from .base import Datos, Flujo

QR = re.compile(r"^\s*estoy\s+en\s+(?:la\s+)?zona\s+([a-z0-9][a-z0-9\-]{0,9})\s*[.!]?\s*$", re.I)
CODIGO_SUELTO = re.compile(r"\bzona\s+([a-z]?\d{1,3}[a-z]?|[a-z]\d?)\b", re.I)


def codigo_qr(db, mensaje: str) -> str | None:
    """Código de zona si el mensaje es el texto del QR, o si menciona un código que existe."""
    m = QR.match(mensaje or "")
    if m:
        return m.group(1).upper()
    m = CODIGO_SUELTO.search(mensaje or "")
    if m:
        from models.zone import Zone
        cod = m.group(1).upper()
        if db.query(Zone).filter(Zone.code == cod).first():
            return cod
    return None


def _registrar_escaneo(db, telefono: str, codigo: str):
    try:
        from models.zone_scan import ZoneScan
        db.add(ZoneScan(phone_number=telefono[:20], zone_code=codigo[:20]))
        db.commit()
    except Exception:
        db.rollback()


class NavegacionQR(Flujo):
    nombre = "navegacion_qr"
    descripcion = ("el cliente escaneó un QR de zona ('Estoy en Zona A5') o pide indicaciones para llegar a un local "
                   "desde donde está dentro del centro comercial")
    con_estado = True
    temperatura = 0.4
    max_tokens = 350

    def sigue_en_flujo(self, ctx: Contexto) -> bool:
        """Después del QR, el siguiente mensaje que nombra un local es la pregunta de a dónde va."""
        if codigo_qr(ctx.db, ctx.mensaje):
            return True
        from .locales import que_pide
        if que_pide(None, ctx.mensaje) not in (None, "ubicacion"):   # "el número de Jarris" no es navegación
            return False
        return any(r.nombre_exacto for r in buscar_locales(ctx.db, ctx.mensaje, incluir_torre=True))

    async def reunir(self, ctx: Contexto) -> Datos:
        from models.zone import Zone
        db, e = ctx.db, ctx.estado
        codigo = codigo_qr(db, ctx.mensaje)
        if codigo:
            _registrar_escaneo(db, ctx.telefono, codigo)
            z = db.query(Zone).filter(Zone.code == codigo).first()
            if not z:
                e.terminar_flujo()
                return Datos(hechos={"situacion": "el cliente escaneó un QR con un código que todavía no está "
                                                  "configurado; dilo con naturalidad y pregúntale a qué local quiere ir "
                                                  "para darle la zona", "codigo": codigo})
            e.activar(self.nombre, {"zona": z.code, "zona_descripcion": z.description})
            datos = Datos(hechos={"situacion": "el cliente acaba de escanear el QR de esta zona; confirma dónde está y "
                                               "pregúntale a qué local quiere llegar",
                                  "cliente_esta_en": z.description},
                          entidades={"zona_qr": z.description})
            return datos
        # ¿a qué local va?
        dec = ctx.decision
        loc = None
        if dec and dec.entidades.get("local"):
            loc = encontrar_local(db, str(dec.entidades["local"]))
        if not loc:
            exactos = [r for r in buscar_locales(db, ctx.mensaje, incluir_torre=True) if r.nombre_exacto]
            loc = exactos[0].local if len(exactos) == 1 else None
        donde = e.datos.get("zona_descripcion") if e.flujo_activo == self.nombre else \
            ctx.estado.ultimas_entidades.get("zona_qr")
        if not loc:
            return Datos(hechos={"situacion": "el cliente quiere llegar a un lugar pero no se entiende a qué local; "
                                              "pregúntale el nombre", "cliente_esta_en": donde or "no se sabe"})
        e.terminar_flujo()
        destino = {"nombre": loc.nombre, "zona": loc.zona}
        if loc.es_torre:
            destino.update(piso=loc.piso, consultorio=loc.numero, nota="queda en la Torre Médica y Empresarial")
        if loc.whatsapp:
            destino["whatsapp"] = loc.whatsapp
        misma = bool(donde and loc.zona and normalizar(loc.zona) in normalizar(donde))
        hechos = {"situacion": "dile en qué zona queda el local respecto a donde está el cliente. NO inventes giros, "
                               "metros ni puntos de referencia que no estén en los datos.",
                  "cliente_esta_en": donde or "no se sabe (no escaneó un QR)", "destino": destino,
                  "misma_zona": misma}
        datos = Datos(hechos=hechos, entidades={"local": loc.nombre})
        foto = loc.fotos.get("portada")
        if foto:
            datos.adjuntos.append(Adjunto(tipo="imagen", url=foto, leyenda=loc.nombre))
        return datos