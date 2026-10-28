"""
Flujo emergencia y queja. La emergencia la detecta una regla dura en el router
(por palabra completa) para no depender del modelo; aquí se marca la
conversación para atención humana en el panel y se redacta la respuesta.
Si el modelo falla, sale el mensaje fijo de emergencia. Una guardia verifica
después que vayan el Punto de Información, el personal de seguridad y la línea.
"""
from __future__ import annotations

from ..nucleo import mensajes
from ..nucleo.tipos import Contexto
from .base import Datos, Flujo


def marcar_para_humano(db, telefono: str, motivo: str):
    from models.conversation_flag import ConversationFlag
    try:
        f = db.get(ConversationFlag, telefono) or ConversationFlag(phone_number=telefono)
        f.needs_human = True
        f.reason = motivo[:200]
        db.merge(f)
        db.commit()
        return True
    except Exception:
        db.rollback()
        return False


class EmergenciaQueja(Flujo):
    nombre = "emergencia_queja"
    descripcion = "emergencias (robo, herido, incendio, niño perdido, acoso) y quejas o reclamos de un cliente molesto"
    temperatura = 0.3
    max_tokens = 350

    async def reunir(self, ctx: Contexto) -> Datos:
        d = ctx.decision
        tipo = "emergencia" if (d and (d.metodo == "regla" or d.entidades.get("tipo") == "emergencia")) else \
            (d.entidades.get("tipo") if d and d.entidades.get("tipo") else "queja_o_emergencia")
        avisado = marcar_para_humano(ctx.db, ctx.telefono, f"Any 2.0 · {tipo}: {ctx.mensaje[:150]}")
        hechos = {
            "tipo_detectado": tipo,
            "punto_de_informacion": "Pasillo Barichara",
            "personal_de_seguridad": "recorre todo el centro comercial",
            "linea_centro_comercial": "317 432 0138 · https://wa.me/573174320138",
            "linea_nacional_emergencias": "123",
            "equipo_notificado": avisado,
        }
        if d and d.entidades.get("local"):
            hechos["local_mencionado"] = d.entidades["local"]
        if tipo != "emergencia":
            from ..conocimiento.areas import area_para, areas, ficha_area
            a = area_para(ctx.mensaje) or next((x for x in areas() if x.get("area", "").startswith("Punto de Información")), None)
            if a:
                hechos["area_que_atiende"] = ficha_area(a)     # «queja a la gerencia» → Gerencia (Delis González)
        return Datos(hechos=hechos, meta={"tipo": tipo, "sin_promo": True}, entidades={"tema": tipo})

    def respaldo(self, ctx, datos):
        return mensajes.texto("emergencia")