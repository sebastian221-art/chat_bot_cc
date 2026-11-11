"""
Flujo cine (Cinelandia Múltiplex): cartelera, una película, boletas, tarifas y confitería.
Todo sale de la base (cine_funciones + bloques de tarifas/confitería del local del cine).
Compra: siempre el link oficial y la taquilla; nunca se inventan pasos.
"""
from __future__ import annotations

import re

from ..conocimiento import cine_datos as cd
from ..conocimiento.fotos import foto_principal
from ..conocimiento.texto import normalizar
from ..nucleo import mensajes
from ..nucleo.tipos import Adjunto, Contexto
from .base import Datos, Flujo


def _tema(texto: str) -> set:
    t = normalizar(texto)
    temas = set()
    if re.search(r"\b(precio|precios|vale|valen|cuesta|cuestan|cuanto|tarifa|tarifas|boleta|boletas|entrada|entradas|promocion|promociones|descuento|descuentos|2x1|tarjeta|informacion|info)\b", t):
        temas.add("tarifas")
    if re.search(r"\b(comprar|compro|reservar|reserva|boleta|boletas|en linea|online|taquilla)\b", t):
        temas.add("compra")
    if re.search(r"\b(crispetas|palomitas|combo|combos|confiteria|nachos|gaseosa|comida|promocion|promociones)\b", t):
        temas.add("confiteria")
    return temas


class Cine(Flujo):
    nombre = "cine"
    descripcion = "cartelera, horarios de funciones, películas, boletas, tarifas y confitería de Cinelandia"
    temperatura = 0.5
    max_tokens = 700

    async def reunir(self, ctx: Contexto) -> Datos:
        db = ctx.db
        d = ctx.decision
        consulta = (d.consulta if d and d.consulta else ctx.mensaje)
        texto = f"{ctx.mensaje} {consulta} {(d.entidades.get('pelicula') if d else '') or ''}"
        temas = _tema(texto)
        funciones = cd.cartelera(db)
        cine = cd.local_cine(db)
        hechos: dict = {
            "cine": {"nombre": cine.nombre if cine else "Cinelandia Múltiplex", "zona": cine.zona if cine else None,
                     "whatsapp": cine.whatsapp if cine else None},
            "compra_de_boletas": {"link_oficial": mensajes.valor("cine_compra_url"), "tambien": "en la taquilla del cine"},
        }
        datos = Datos(hechos=hechos, entidades={"tema": "cine"})
        peli = cd.pelicula_mencionada(funciones, texto)
        recordada = ctx.estado.ultimas_entidades.get("pelicula")
        if not peli and recordada and d and d.es_seguimiento:
            peli = next((f for f in funciones if f.title == recordada), None)
        if peli:
            hechos["pelicula"] = {"titulo": peli.title, "funciones_hoy": peli.showtimes or "sin horarios cargados",
                                  "estreno": bool(peli.is_premiere), "sinopsis": (peli.description or "")[:400]}
            datos.entidades["pelicula"] = peli.title
            poster = foto_principal(db, "cine_funcion", peli.id, orden=("poster", "otra"))
            if poster:
                datos.adjuntos.append(Adjunto(tipo="imagen", url=poster, leyenda=peli.title))
        elif not temas or "cartelera" in normalizar(texto) or re.search(r"pel[ií]cula", texto, re.I):
            hechos["cartelera_es_de"] = f"hoy, {ctx.ahora:%d/%m/%Y} (los horarios de otros días no están cargados)"
            hechos["cartelera"] = [{"titulo": f.title, "funciones": f.showtimes or "", "estreno": bool(f.is_premiere)}
                                   for f in funciones] or "la cartelera no está cargada en este momento"
            # UN póster de referencia (el primer estreno, si hay), no uno por película (pedido 11/11)
            for f in sorted(funciones, key=lambda x: not x.is_premiere):
                poster = foto_principal(db, "cine_funcion", f.id, orden=("poster", "otra"))
                if poster:
                    datos.adjuntos.append(Adjunto(tipo="imagen", url=poster, leyenda=f.title))
                    hechos["imagen"] = (f"se adjunta UN póster de referencia: el de «{f.title}». No digas que envías "
                                        f"los pósters de las demás.")
                    break
        nombre_peli = d.entidades.get("pelicula") if d else None
        if nombre_peli and not peli:
            hechos["pelicula_pedida_no_esta_en_cartelera"] = nombre_peli
        if "tarifas" in temas or "compra" in temas:
            hoy = cd.tarifas_del_dia(db, ctx.ahora)
            hechos["tarifas_de_hoy"] = hoy or "no tengo las tarifas cargadas"
            hechos["nota_tarifas"] = "precios de compra en la web; en taquilla pueden variar"
        if "confiteria" in temas:
            hechos["confiteria"] = cd.confiteria(db) or "no tengo la confitería cargada"
        # Promociones del cine cargadas en el panel (2x1…): antes decía «no hay promociones» y el «De paso» sí la traía
        try:
            from .sorteos_promos import ficha_promo, promos_vigentes
            from ..conocimiento.texto import normalizar as _n
            cine = hechos.get("cine", {}).get("nombre", "")
            promos = [ficha_promo(db, m) for m in promos_vigentes(db, ctx.ahora.date())
                      if re.search(r"\bcine|cinelandia|pelicula", _n(f"{m.title} {m.description or ''}"))
                      or (cine and ficha_promo(db, m).get("local") == cine)]
            if promos:
                hechos["promociones_del_cine"] = promos
        except Exception:
            pass
        return datos

    def respaldo(self, ctx, datos):
        return (f"Las boletas de Cinelandia se compran en taquilla o en 👉 {mensajes.valor('cine_compra_url')}")