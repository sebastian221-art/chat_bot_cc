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
from ..conocimiento.catalogo import Local, locales, locales_por_numero, numero_en_texto
from ..conocimiento.texto import normalizar, palabras
from ..llm import completar
from ..nucleo.tipos import Adjunto, Contexto
from .base import Datos, Flujo, leer_prompt

MARCA_LISTA = "{LISTA}"
_MARCA_VARIANTES = re.compile(r"[\{\[][^\}\]\n]{0,60}?\b(?:LISTA|LIST|lista|list|Lista|List)\b[^\}\]\n]{0,80}[\}\]]")


def poner_lista(texto: str, lista: str) -> str:
    """Pone la lista donde el modelo escribió la marca ({LISTA}, {LIST}, [LISTA]…); si no la puso,
    después del primer párrafo y siempre ANTES de la línea "De paso"."""
    texto = _MARCA_VARIANTES.sub(MARCA_LISTA, (texto or "").strip())
    nombres = [normalizar(m) for m in re.findall(r"^• \*([^*]+)\*", lista, flags=re.M)]
    if nombres:   # el modelo no debe escribir la lista: sus viñetas con nombres de la lista se quitan
        texto = "\n".join(l for l in texto.split("\n")
                          if not (l.lstrip().startswith(("•", "-", "*")) and any(n in normalizar(l) for n in nombres)))
        texto = re.sub(r"\n{3,}", "\n\n", texto).strip()
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
            url = m.group(0).rstrip(".,)").split("?")[0]          # sin ?hl=es ni rastreadores
            return url if url.startswith("http") else "https://" + url
    return None


def carta_de(loc: Local) -> tuple[str | None, str | None]:
    """(foto o PDF de la carta, link de la carta)."""
    archivo = loc.fotos.get("carta")
    link = loc.carta_link or None
    if link and re.search(r"instagram\.com|wa\.me/|whatsapp", link, re.I):
        link = None       # un Instagram o un WhatsApp no es la carta (el Instagram ya va aparte)
    return archivo, link


def _es_imagen(url: str | None) -> bool:
    return bool(url) and not url.lower().split("?")[0].endswith(".pdf")


# "Oficina", "¿qué oficinas tiene?", "dame el listado de oficinas y locales": todo el directorio de la Torre
_SOLO_OFICINAS = set("""
oficina oficinas y que cuales cual dame listado lista de las los hay tiene tienen el la en centro comercial locales
me puedes regalar pasame quiero ver todas todos directorio torre empresarial hola por favor
medica conocer sobre saber pues entonces bueno ok y empresas negocios hay
""".split())


# Lo que se pregunta DE un local (no otro producto): con estas palabras se sigue hablando del mismo local
_ATRIBUTOS = set("""
domicilio domicilios envio envios precio precios vale valen cuesta cuestan costo costos pago pagos pagar tarjeta
tarjetas nequi daviplata efectivo transferencia parqueadero abierto abierta cerrado hoy manana lunes martes
miercoles jueves viernes sabado sabados domingo domingos festivo festivos y el la los las de del en a que
tienen tiene tienes hay dan da ofrecen ofrece hacen hace manejan maneja aceptan acepta reciben recibe venden vende
puedo puede quiero necesito busco me te se lo le por favor si no tambien ustedes alli ahi
""".split())


def linea_lista(loc: Local) -> str:
    """• *Nombre* — Zona
         👉 WhatsApp · 📸 Instagram   (los dos contactos, siempre que existan)"""
    if loc.es_torre:     # oficinas de la Torre: piso y oficina, que es como las encuentran
        lugar = ", ".join(x for x in [loc.piso, f"oficina {loc.numero}" if loc.numero and loc.numero.upper() != "S/N" else ""] if x)
        linea = f"• *{loc.nombre}* — Torre Médica" + (f", {lugar}" if lugar else "")
    else:
        linea = f"• *{loc.nombre}*" + (f" — {loc.zona}" if loc.zona else "")
    contactos = []
    if loc.whatsapp:
        contactos.append(f"👉 {loc.whatsapp}")
    elif loc.fijo:
        contactos.append(f"☎️ solo fijo: {loc.fijo}")
    ig = instagram_de(loc)
    if ig:
        contactos.append(f"📸 {ig}")
    return linea + ("\n   " + " · ".join(contactos) if contactos else "")


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
        datos = await self._reunir(ctx)
        # "¿qué restaurante está abierto a esta hora?", "horario de los almacenes de ropa": con datos reales
        if re.search(r"horario|abiert|abren|cierran|a esta hora|ahora mismo|todavia|aun estan", normalizar(ctx.mensaje)):
            try:
                from ..conocimiento.servicios import info_mall
                hg = info_mall(ctx.db).get("horario_general")
                if hg:
                    datos.hechos["horario_general_del_centro_comercial"] = hg
                dia = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"][ctx.ahora.weekday()]
                datos.hechos["hora_actual"] = f"{dia} {ctx.ahora.strftime('%I:%M %p')}"
            except Exception:
                pass
        return datos

    async def _reunir(self, ctx: Contexto) -> Datos:
        d = ctx.decision
        ent = d.entidades if d else {}
        consulta = (d.consulta if d and d.consulta else ctx.mensaje)
        pide = que_pide(ent.get("pide"), ctx.mensaje)
        numero = numero_en_texto(ctx.mensaje)
        if numero:
            en_numero = locales_por_numero(ctx.db, numero)
            if len(en_numero) == 1:
                return self._ficha(en_numero[0], pide)
            if en_numero:
                return self._datos_lista(en_numero, f"local {numero}", pide)
        pal = set(palabras(normalizar(ctx.mensaje)))
        if pal & {"oficina", "oficinas", "torre"} and pal <= _SOLO_OFICINAS:
            # "Oficina", "¿qué oficinas tiene?": el directorio de la Torre Médica y Empresarial
            return self._datos_lista([l for l in locales(ctx.db) if l.es_torre], "oficinas de la Torre", pide)
        loc = self._local_nombrado(ctx, ent, consulta, pide)
        if loc:
            return self._ficha(loc, pide)
        if getattr(ctx, "buscar_lo_que_escribio", False):
            consulta, ent = ctx.mensaje, {k: v for k, v in ent.items() if k != "local"}
        return await self._lista(ctx, ent, consulta, pide)

    def _local_nombrado(self, ctx: Contexto, ent: dict, consulta: str, pide: str | None) -> Local | None:
        db = ctx.db
        recordado = ctx.estado.ultimas_entidades.get("local")
        # Lo que el cliente escribió manda: si nombra un local exacto ("FDS dame información"), es ese,
        # aunque el modelo haya creído que seguía hablando del anterior.
        if not ent.get("categoria"):
            exactos = [r for r in buscar_locales(db, ctx.mensaje) if r.nombre_exacto]
            if len(exactos) == 1:
                return exactos[0].local
        if ent.get("local"):
            loc = encontrar_local(db, str(ent["local"]), incluir_torre=False) or \
                encontrar_local(db, str(ent["local"]), incluir_torre=True)       # "Benítez abogados" es de la Torre
            if loc and recordado and normalizar(loc.nombre) == normalizar(recordado):
                otro = self._otro_local_por_producto(db, ctx.mensaje, loc)
                if otro is not False:
                    if otro is None:
                        ctx.buscar_lo_que_escribio = True     # la lista sale de SUS palabras, no de la reescritura
                    return otro         # "¿dan clases de zumba?" después del gimnasio → RUMBATERAPIA, no el gimnasio
            if loc:
                return loc
        for texto in (() if ent.get("categoria") else (consulta,)):   # "unos tennis" ≠ el local Tennis
            exactos = [r for r in buscar_locales(db, texto) if r.nombre_exacto]
            if len(exactos) == 1:
                return exactos[0].local
        # "¿y el horario?" justo después de hablar de un local (pero no si el cliente nombró OTRO local)
        nombro_otro = ent.get("local") and recordado and normalizar(str(ent["local"])) != normalizar(recordado)
        plural = re.search(r"\b(locales|tiendas|restaurantes|almacenes|negocios|cuales|cuantos)\b", normalizar(ctx.mensaje))
        if recordado and pide and not plural and not nombro_otro and not ent.get("categoria") and \
                ctx.decision and ctx.decision.es_seguimiento:
            return encontrar_local(db, recordado, incluir_torre=False)
        return None

    def _otro_local_por_producto(self, db, mensaje: str, actual: Local):
        """El modelo suele pegarle al mensaje el local del que se venía hablando. Si lo que el cliente pide
        (zumba, yoga…) lo declara OTRO local y no este, se responde con ese otro. False = seguir con el actual;
        un Local = ese; None = varios (va la lista)."""
        if normalizar(actual.nombre) in normalizar(mensaje):
            return False
        palabras_msg = [w for w in palabras(normalizar(mensaje)) if w not in _ATRIBUTOS]
        if not palabras_msg:
            return False
        res = [r for r in buscar_locales(db, " ".join(palabras_msg), incluir_servicios=False) if r.fuertes]
        if not res:
            return False
        mx = max(len(r.fuertes) for r in res)
        tops = [r.local for r in res if len(r.fuertes) == mx]
        if any(l.id == actual.id for l in tops):
            return False
        return tops[0] if len(tops) == 1 else None

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
                hechos["carta"] = ("este local no tiene carta cargada: dilo claro; si tiene Instagram, dile que ahí "
                                   "puede ver sus productos, y ofrece su WhatsApp para pedirla")
        elif pide == "instagram":
            ig = instagram_de(loc)
            hechos["instagram"] = ig or "no tengo el Instagram de este local: dilo y ofrece su WhatsApp"
        elif pide == "foto":
            foto = next((f for f in (loc.fotos.get("portada"), loc.fotos.get("otra")) if _es_imagen(f)), None)
            if foto:
                datos.adjuntos.append(Adjunto(tipo="imagen", url=foto, leyenda=loc.nombre))
            else:
                hechos["foto"] = "no tengo foto de este local"
        # Al hablar de un local concreto va su foto de portada (para que lo reconozcan) y su Instagram
        if pide != "foto" and not any(a.tipo == "imagen" for a in datos.adjuntos):
            portada = loc.fotos.get("portada")
            if _es_imagen(portada):
                datos.adjuntos.append(Adjunto(tipo="imagen", url=portada, leyenda=loc.nombre))
        ig = instagram_de(loc)
        if ig and "instagram" not in hechos:
            hechos["instagram"] = ig
        return datos

    async def _lista(self, ctx: Contexto, ent: dict, consulta: str, pide: str | None) -> Datos:
        db = ctx.db
        termino = str(ent.get("categoria") or "") or consulta
        res = buscar_locales(db, termino)
        if not res and termino != consulta:
            termino, res = consulta, buscar_locales(db, consulta)
        # "firma de contadores", "asesoría tributaria": no son locales comerciales sino oficinas de la Torre.
        # Si una oficina de la Torre cubre MÁS de lo pedido que cualquier local comercial, se responde con la Torre.
        con_torre = [r for r in buscar_locales(db, termino, incluir_torre=True) if r.fuertes]
        mejor_torre = max((len(r.fuertes) for r in con_torre if r.local.es_torre), default=0)
        mejor_local = max((len(r.fuertes) for r in res if r.fuertes), default=0)
        if mejor_torre > mejor_local:
            res = con_torre

        # "¿De qué locales tienes Instagram / carta?" sin decir de qué tipo
        if pide in ("carta", "instagram") and not conceptos(_quita_pedido(ctx.mensaje), "locales"):
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
            parecidos = self._consultorios_parecidos(db, f"{ctx.mensaje} {termino}")
            if parecidos:
                # «Odonto Vital» no está, pero hay consultorios de odontología en la Torre: se ofrecen esos
                from .torre_medica import linea_consultorio
                datos = self._datos_lista(parecidos, termino, pide)
                lineas = {l.nombre: linea_consultorio(l) for l in parecidos}
                datos.meta.update(lista="\n".join(lineas.values()), lineas_equidad=lineas, lista_equidad=list(lineas))
                datos.hechos["nota"] = (f"No hay un local o consultorio llamado así registrado. Dilo en una frase y "
                                        f"ofrece estos consultorios de la Torre Médica que hacen algo parecido.")
                if len(termino.split()) > 4:      # no recordar la pregunta entera como «categoría»
                    datos.entidades.pop("categoria", None)
                return datos
            rubros = sorted({l.rubro for l in locales(db, incluir_torre=False, incluir_servicios=False) if l.rubro})
            return Datos(hechos={"modo": "sin_resultados", "busqueda": termino, "rubros_del_centro_comercial": rubros},
                         entidades={"categoria": termino} if len(termino.split()) <= 4 else {})
        if len(seleccion) == 1:
            # Un solo local ("¿hay gimnasio?" → GIMNASIO CAJASAN): va su ficha completa, con foto de portada
            datos = self._ficha(seleccion[0], pide)
            datos.entidades["categoria"] = termino
            return datos
        return self._datos_lista(seleccion, termino, pide)

    @staticmethod
    def _consultorios_parecidos(db, texto: str) -> list:
        """Consultorios de salud de la Torre que comparten la raíz de una palabra de salud del mensaje
        («odonto» → odontología, «dermato» → dermatología)."""
        from .torre_medica import busca_salud, es_de_salud
        if not busca_salud(texto):
            return []
        raices = {w[:5] for w in palabras(normalizar(texto)) if len(w) >= 5 and busca_salud(w)}
        if not raices:
            return []
        torre = [l for l in locales(db) if l.es_torre and es_de_salud(l)]
        sel = [l for l in torre if any(r in normalizar(f"{l.nombre} {' '.join(l.productos)}") for r in raices)]
        return sorted(sel, key=lambda l: normalizar(l.nombre))[:10]

    def _datos_lista(self, seleccion: list, termino: str, pide: str | None) -> Datos:
        seleccion = sorted({l.id: l for l in seleccion}.values(), key=lambda l: normalizar(l.nombre))
        lineas = {l.nombre: linea_lista(l) for l in seleccion}
        hechos = {
            "modo": "lista", "busqueda": termino, "cantidad": len(seleccion),
            "locales_para_tu_contexto": [{"nombre": l.nombre, "rubro": l.rubro, "que_vende": ", ".join(l.productos[:8]),
                                          "horario": (l.horario or "")[:120]}
                                         for l in seleccion[:40]],
            "como_escribir": f"Escribe una frase corta de entrada; luego, en una línea sola, escribe exactamente "
                             f"{MARCA_LISTA} (ahí el sistema pone la lista completa con zona y WhatsApp); "
                             f"opcional: una línea final corta. NO escribas tú los locales.",
        }
        if pide == "carta":
            hechos["filtro"] = ("Los locales de la lista tienen carta o menú en línea (por eso están). Dilo así: "
                                "\"estos tienen carta\" y que te pidan la de cuál. No digas que TODOS los del centro "
                                "comercial la tienen ni que no hay cartas.")
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
            elif l.get("solo_telefono_fijo"):
                partes.append(f"☎️ Solo tiene número fijo: {l['solo_telefono_fijo'].split(' (')[0]}, puedes llamar ahí.")
            return "\n".join(partes)
        return None