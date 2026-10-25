"""
Flujo locales: buscar locales por lo que venden y dar la ficha de un local.

Dos modos, decididos en código:
  FICHA  el cliente nombró un local ("número de Jarris", "carta de 12b", "¿y People Plays?")
         → solo lo que pidió: teléfono, zona, horario, carta (foto, PDF o link), Instagram, foto.
  LISTA  el cliente busca algo ("tenis", "ropa para niños", "dónde comer hamburguesa")
         → TODOS los locales relevantes, en orden alfabético, con el mismo formato (equidad).
           La lista la arma el código; la IA solo escribe la frase de entrada y, si quiere, un cierre.

Cómo se eligen los locales de la lista:
  1. búsqueda por palabra completa con sinónimos (conocimiento/buscador.py);
  2. si hay varios candidatos, un juez IA descarta los que solo coinciden por casualidad
     (no puede agregar locales que no estén en los candidatos);
  3. si el juez falla, queda la selección determinista.
Nunca se muestran datos internos del local (responsable, notas de extra_info).
"""
from __future__ import annotations

import json
import re

from ..config import cfg
from ..conocimiento.buscador import (buscar_locales, conceptos, encontrar_local, seleccionar_relevantes,
                                     PALABRAS_DE_PEDIDO)
from ..conocimiento.catalogo import Local, locales
from ..conocimiento.texto import normalizar, palabras
from ..llm import completar
from ..nucleo.tipos import Adjunto, Contexto
from .base import Datos, Flujo, leer_prompt

MARCA_LISTA = "{LISTA}"
_MARCA_VARIANTES = re.compile(r"[\{\[]\s*(?:LISTA|LIST|lista|list)\s*[\}\]]")


def poner_lista(texto: str, lista: str) -> str:
    """Pone la lista donde el modelo escribió la marca ({LISTA}, {LIST}, [LISTA]…); si no la puso,
    después del primer párrafo y siempre ANTES de la línea "De paso"."""
    texto = _MARCA_VARIANTES.sub(MARCA_LISTA, (texto or "").strip())
    if MARCA_LISTA in texto:
        antes, despues = texto.split(MARCA_LISTA, 1)
        return (antes.rstrip() + "\n" + lista + ("\n" + despues.lstrip() if despues.strip() else "")).replace(MARCA_LISTA, "").strip()
    if not texto:
        return lista
    lineas = texto.split("\n")
    i_paso = next((i for i, l in enumerate(lineas) if "de paso" in l.lower()), None)
    if i_paso is not None:
        cuerpo, cola = "\n".join(lineas[:i_paso]).strip(), "\n".join(lineas[i_paso:]).strip()
        return "\n".join(x for x in [cuerpo, lista] if x) + "\n\n" + cola
    partes = texto.split("\n\n", 1)
    return "\n\n".join([partes[0], lista] + partes[1:])
MAX_CANDIDATOS_JUEZ = 60

_PIDE = [
    ("ubicacion", r"\bnumero (?:de|del) (?:local|almacen|tienda)\b"),
    ("telefono", r"\b(numero|telefono|celular|whatsapp|wasap|contacto|llamar|escribir)\b"),
    ("carta", r"\b(carta|menu|catalogo|precios?)\b"),
    ("instagram", r"\b(instagram|insta|redes)\b"),
    ("foto", r"\b(fotos?|imagen|imagenes)\b"),
    ("horario", r"\b(horarios?|abren?|cierran?|hora)\b"),
    ("ubicacion", r"\b(donde|queda|quedan|ubicad[oa]|ubicacion|piso|nivel|zona)\b"),
    ("todo", r"\b(todo|cuentame|informacion|info)\b"),
]


def que_pide(entidad: str | None, mensaje: str) -> str | None:
    if entidad:
        e = normalizar(str(entidad))
        for nombre, patron in _PIDE:
            if nombre in e or re.search(patron, e):
                return nombre
    m = normalizar(mensaje)
    for nombre, patron in _PIDE:
        if re.search(patron, m):
            return nombre
    return None


def instagram_de(loc: Local) -> str | None:
    for texto in (loc.carta_link or "", loc.descripcion or ""):
        m = re.search(r"(?:https?://)?(?:www\.)?instagram\.com/[A-Za-z0-9_.\-/?=&]+", texto)
        if m:
            url = m.group(0).rstrip(".,)")
            return url if url.startswith("http") else "https://" + url
    return None


def carta_de(loc: Local) -> tuple[str | None, str | None]:
    """(foto o PDF de la carta, link de la carta)."""
    archivo = loc.fotos.get("carta")
    return archivo, (loc.carta_link or None)


def linea_lista(loc: Local) -> str:
    partes = [f"• *{loc.nombre}*"]
    if loc.zona:
        partes.append(f" — {loc.zona}")
    if loc.whatsapp:
        partes.append(f" · 👉 {loc.whatsapp}")
    return "".join(partes)


def _quita_pedido(texto: str) -> str:
    return " ".join(p for p in palabras(texto) if p not in PALABRAS_DE_PEDIDO)


class Locales(Flujo):
    nombre = "locales"
    descripcion = ("buscar locales o productos (qué venden, dónde queda, teléfono, horario, carta, Instagram, "
                   "foto de un local), recomendaciones por categoría ('tenis', 'ropa para niños', 'dónde comer')")
    temperatura = 0.5
    max_tokens = 500

    # ── Reunir datos ──────────────────────────────────────────────

    async def reunir(self, ctx: Contexto) -> Datos:
        d = ctx.decision
        ent = d.entidades if d else {}
        consulta = (d.consulta if d and d.consulta else ctx.mensaje)
        pide = que_pide(ent.get("pide"), ctx.mensaje)
        loc = self._local_nombrado(ctx, ent, consulta, pide)
        if loc:
            return self._ficha(loc, pide)
        return await self._lista(ctx, ent, consulta, pide)

    def _local_nombrado(self, ctx: Contexto, ent: dict, consulta: str, pide: str | None) -> Local | None:
        db = ctx.db
        if ent.get("local"):
            loc = encontrar_local(db, str(ent["local"]), incluir_torre=False)
            if loc:
                return loc
        for texto in (() if ent.get("categoria") else (ctx.mensaje, consulta)):   # "unos tennis" ≠ el local Tennis
            exactos = [r for r in buscar_locales(db, texto) if r.nombre_exacto]
            if len(exactos) == 1:
                return exactos[0].local
        # "¿y el horario?" justo después de hablar de un local
        recordado = ctx.estado.ultimas_entidades.get("local")
        if recordado and pide and not ent.get("categoria") and ctx.decision and ctx.decision.es_seguimiento:
            return encontrar_local(db, recordado, incluir_torre=False)
        return None

    def _ficha(self, loc: Local, pide: str | None) -> Datos:
        hechos = {"modo": "ficha", "lo_que_pide": pide or "general", "local": loc.ficha(completa=True)}
        datos = Datos(hechos=hechos, entidades={"local": loc.nombre},
                      meta={"telefonos_validos": [loc.telefono] if loc.telefono else []})
        if pide == "carta":
            archivo, link = carta_de(loc)
            if archivo:
                es_pdf = archivo.lower().split("?")[0].endswith(".pdf")
                datos.adjuntos.append(Adjunto(tipo="documento" if es_pdf else "imagen", url=archivo,
                                              nombre_archivo=f"Carta {loc.nombre}.pdf" if es_pdf else None,
                                              leyenda=f"Carta de {loc.nombre}"))
                hechos["carta"] = "se adjunta la carta"
                if link:
                    hechos["carta_link"] = link
            elif link:
                hechos["carta_link"] = link
            else:
                hechos["carta"] = "este local no tiene carta cargada: dilo claro y ofrece su WhatsApp para pedirla"
        elif pide == "instagram":
            ig = instagram_de(loc)
            hechos["instagram"] = ig or "no tengo el Instagram de este local: dilo y ofrece su WhatsApp"
        elif pide == "foto":
            foto = loc.fotos.get("portada") or loc.fotos.get("otra")
            if foto:
                datos.adjuntos.append(Adjunto(tipo="imagen", url=foto, leyenda=loc.nombre))
            else:
                hechos["foto"] = "no tengo foto de este local"
        return datos

    async def _lista(self, ctx: Contexto, ent: dict, consulta: str, pide: str | None) -> Datos:
        db = ctx.db
        termino = str(ent.get("categoria") or "") or consulta
        res = buscar_locales(db, termino)
        if not res and termino != consulta:
            termino, res = consulta, buscar_locales(db, consulta)

        # "¿De qué locales tienes Instagram / carta?" sin decir de qué tipo
        if pide in ("carta", "instagram") and not conceptos(_quita_pedido(termino), "locales"):
            return self._conteo(db, pide)

        relevantes = seleccionar_relevantes(res)
        seleccion = [r.local for r in relevantes]
        # candidatos que no entraron por palabras pero son del grupo mayor ("vestido" → otras tiendas de ropa)
        ids = {l.id for l in seleccion}
        mx = max((len(r.fuertes) for r in relevantes), default=0)
        if len(seleccion) >= 3 and mx >= 2:
            extra = []   # "ropa para niños": ya cumplen las dos cosas; no se abre a toda la ropa
        else:
            extra = [r.local for r in res if r.local.id not in ids and (r.cercanos or r.fuertes)]
        if seleccion and mx == 0:
            # Nadie declara venderlo: solo lo menciona su descripción ("gimnasio" en un parque infantil).
            # No es seguro: el juez decide si de verdad lo ofrecen; si dice que ninguno, no hay.
            juzgado = await self._juez(ctx, termino, [], (seleccion + extra)[:MAX_CANDIDATOS_JUEZ])
            if juzgado is not None:
                seleccion = juzgado
        elif len(seleccion) + len(extra) >= 4:
            juzgado = await self._juez(ctx, termino, seleccion, extra[:MAX_CANDIDATOS_JUEZ])
            if juzgado:
                seleccion = juzgado
        if pide == "carta":
            seleccion = [l for l in seleccion if any(carta_de(l))]
        elif pide == "instagram":
            seleccion = [l for l in seleccion if instagram_de(l)]

        seleccion = sorted({l.id: l for l in seleccion}.values(), key=lambda l: normalizar(l.nombre))
        if not seleccion:
            rubros = sorted({l.rubro for l in locales(db, incluir_torre=False, incluir_servicios=False) if l.rubro})
            return Datos(hechos={"modo": "sin_resultados", "busqueda": termino, "rubros_del_centro_comercial": rubros},
                         entidades={"categoria": termino})
        lineas = {l.nombre: linea_lista(l) for l in seleccion}
        hechos = {
            "modo": "lista", "busqueda": termino, "cantidad": len(seleccion),
            "locales_para_tu_contexto": [{"nombre": l.nombre, "rubro": l.rubro, "que_vende": ", ".join(l.productos[:8])}
                                         for l in seleccion[:40]],
            "como_escribir": f"Escribe una frase corta de entrada; luego, en una línea sola, escribe exactamente "
                             f"{MARCA_LISTA} (ahí el sistema pone la lista completa con zona y WhatsApp); "
                             f"opcional: una línea final corta. NO escribas tú los locales.",
        }
        if pide == "carta":
            hechos["filtro"] = ("TODOS los locales de la lista TIENEN carta cargada (por eso están). Dilo así: "
                                "\"estos tienen carta\" y que te pidan la de cuál. Nunca digas que no hay cartas.")
        return Datos(hechos=hechos, entidades={"categoria": termino},
                     meta={"lista_equidad": [l.nombre for l in seleccion], "lineas_equidad": lineas,
                           "lista": "\n".join(lineas.values()),
                           "telefonos_validos": [l.telefono for l in seleccion if l.telefono]})

    def _conteo(self, db, pide: str) -> Datos:
        todos = locales(db, incluir_torre=False, incluir_servicios=False)
        con = [l.nombre for l in todos if (instagram_de(l) if pide == "instagram" else any(carta_de(l)))]
        return Datos(hechos={"modo": "conteo", "que": pide, "cantidad": len(con), "ejemplos": sorted(con)[:12],
                             "como_escribir": "Di de cuántos locales lo tienes y pregunta de cuál le interesa. "
                                              "No pegues todos los links."})

    async def _juez(self, ctx: Contexto, busqueda: str, seguros: list[Local], posibles: list[Local]) -> list[Local] | None:
        """
        La IA revisa la lista, pero la equidad manda:
          - los SEGUROS (encontrados por lo que declaran vender) se quedan, salvo que sean claramente un error;
          - de los POSIBLES (del grupo mayor) solo entran los que de verdad venden lo buscado.
        Solo puede elegir entre esos nombres: no puede agregar locales.
        """
        def fila(l: Local) -> str:
            return f"- {l.nombre} | {l.rubro} | {', '.join(l.productos[:12])} | {l.descripcion[:140]}"
        texto = (f"BUSCA: {busqueda}\n\nSEGUROS (se quedan salvo error claro):\n" + ("\n".join(map(fila, seguros)) or "(ninguno)")
                 + "\n\nPOSIBLES (entran solo si de verdad lo venden):\n" + ("\n".join(map(fila, posibles)) or "(ninguno)"))
        try:
            r = await completar(cfg().modelo_de_flujo("locales"),
                                [{"role": "system", "content": leer_prompt("flujos/locales_juez.md")},
                                 {"role": "user", "content": texto}],
                                json_salida=True, temperatura=0, max_tokens=900, razonamiento="low")
            ctx.traza.llm("juez_locales", r)
            j = r.json()
        except Exception as e:   # el juez es una mejora: si falla por lo que sea, manda la selección por palabras
            ctx.traza.alerta(f"juez de locales falló, se usa la selección por palabras: {e}")
            return None
        excluir = {normalizar(str(n)) for n in j.get("excluir") or []}
        agregar = {normalizar(str(n)) for n in j.get("agregar") or []}
        quedan = [l for l in seguros if normalizar(l.nombre) not in excluir]
        entran = [l for l in posibles if normalizar(l.nombre) in agregar]
        if seguros and len(quedan) < len(seguros) / 2:   # quitar más de la mitad de lo seguro no es una poda, es un error
            ctx.traza.alerta(f"el juez quería quitar {len(seguros) - len(quedan)} de {len(seguros)} locales: se ignora la poda")
            quedan = seguros
        ctx.traza.paso("juez_locales", {"quitados": [l.nombre for l in seguros if l not in quedan],
                                        "agregados": [l.nombre for l in entran], "razon": j.get("razon")})
        return quedan + entran   # [] = el juez revisó y ninguno sirve; None = el juez falló

    # ── Componer ──────────────────────────────────────────────────

    def componer(self, ctx: Contexto, datos: Datos, texto: str) -> str:
        lista = datos.meta.get("lista")
        if not lista:
            return texto
        return poner_lista(texto, lista)

    def respaldo(self, ctx: Contexto, datos: Datos) -> str | None:
        h = datos.hechos
        if h.get("modo") == "lista":
            return f"Estos son los locales que encontré:\n{MARCA_LISTA}"
        if h.get("modo") == "ficha":
            l = h["local"]
            partes = [f"*{l['nombre']}*" + (f" queda en {l['zona']}" if l.get("zona") else "")]
            if l.get("whatsapp"):
                partes.append(f"👉 {l['whatsapp']}")
            return "\n".join(partes)
        return None