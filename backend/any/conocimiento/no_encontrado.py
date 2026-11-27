"""Cuando Any no encuentra algo (27/11, administración del centro comercial).

«No lo tengo registrado» suena a «la administración no ha puesto esa información». Pero tampoco se puede decir
«eso no queda aquí» de todo: las listas de productos de cada local no están completas. Se responde según QUÉ no se
encontró:

- nombre   → un negocio, marca, empresa o entidad por su nombre («¿Fenalco queda en el CC?»). El directorio de
             locales es la lista oficial: si no está, NO queda aquí. «No, Fenalco no queda en el Centro Comercial El
             Puente». Nunca se dice dónde queda (para no mandar a la gente a otro centro comercial). Queda anotado en
             la traza («no_queda_aqui») para que la administración vea si falta algún local en el directorio.
- producto → un producto, servicio o actividad que ningún local declara: «en El Puente no encontré un local que lo
             ofrezca», lo más parecido si lo hay, y el Punto de Información para confirmarlo.
- dato_mall → un dato del centro comercial que no está en la información: «eso te lo responden en el Punto de
             Información».
(El detalle de un local que sí existe no llega aquí: va a la ficha y se remite al WhatsApp del local.)
"""
from __future__ import annotations

import re

from .texto import normalizar

LINEA_MALL = "317 432 0138"

_PREGUNTA_POR_LUGAR = re.compile(r"\b(queda|quedan|esta|estan|hay|tienen|existe|abrieron|funciona)\b.*\b(cc|centro "
                                 r"comercial|mall|el puente|aqui|aca)\b|\b(donde queda|donde esta|hay un|hay una)\b")
_DATO_MALL = re.compile(r"\b(wifi|wi fi|internet|enfermeria|primeros auxilios|bano|banos|lactancia|cajero|"
                        r"silla de ruedas|coche|lockers?|casillero|guarda ?ropa|objetos perdidos|ascensor|"
                        r"rampa|parqueadero|bicicleta|mascotas?|cargador|enchufe)\b")


def _inactivo_con_ese_nombre(ctx, busqueda: str):
    """Registros que la administración tiene como «no activos» (Fenalco, Alma Rooftop…): tampoco quedan aquí."""
    try:
        from models.store import Store
        b = normalizar(busqueda)
        if len(b) < 3:
            return None
        for s in ctx.db.query(Store).filter(Store.active.is_(False)).all():
            n = normalizar(s.name or "")
            if n and (b in n or n in b):
                return s.name
    except Exception:
        try:
            ctx.db.rollback()
        except Exception:
            pass
    return None


def _parece_nombre(mensaje: str, busqueda: str) -> bool:
    """Sin clasificación del cerebro: ¿pregunta por un negocio con nombre propio?"""
    original = (mensaje or "").strip()
    palabras = re.findall(r"[A-Za-zÁÉÍÓÚÑáéíóúñ][\wÁÉÍÓÚÑáéíóúñ&'’.-]*", original)
    mayus = [p for p in palabras[1:] if p[:1].isupper() and normalizar(p) not in {"el", "la", "cc", "puente"}]
    b = (busqueda or "").strip()
    return bool(mayus) or bool(b and b[:1].isupper() and len(b.split()) <= 3)


def tipo_de_no_hay(ctx, el) -> tuple[str, str | None]:
    busqueda = el.busqueda or ctx.mensaje
    inactivo = _inactivo_con_ese_nombre(ctx, busqueda)
    if inactivo:
        return "nombre", inactivo
    tipo = getattr(el, "no_hay_tipo", "") or ""
    if tipo in ("nombre", "producto", "dato_mall"):
        return tipo, None
    t = normalizar(ctx.mensaje)
    if _DATO_MALL.search(t):
        return "dato_mall", None
    if _parece_nombre(ctx.mensaje, busqueda) and _PREGUNTA_POR_LUGAR.search(t):
        return "nombre", None
    return "producto", None


def como_responder_no_hay(ctx, el) -> tuple[str, str, dict]:
    tipo, inactivo = tipo_de_no_hay(ctx, el)
    que = (el.busqueda or "").strip() or "eso"
    sin_frases = ("NUNCA digas «no lo tengo registrado», «no está registrado», «en mi base de datos», «en nuestro "
                  "directorio» ni «no tengo información»: suena a que el centro comercial no cargó el dato.")
    if tipo == "nombre":
        nombre = inactivo or que
        try:
            ctx.traza.paso("no_queda_aqui", {"busqueda": nombre, "mensaje": ctx.mensaje[:200]})
        except Exception:
            pass
        como = (f"Lo que busca ({nombre}) NO queda en el Centro Comercial El Puente: el directorio de locales es la "
                f"lista oficial. Dilo con naturalidad y seguridad, primero el no: «No, {nombre} no queda en el Centro "
                "Comercial El Puente». NO digas dónde queda ni menciones otro centro comercial, otra dirección o "
                "sucursal. Luego ofrece ayuda con algo que sí hay aquí (una frase). " + sin_frases)
        return tipo, como, {}
    if tipo == "dato_mall":
        como = ("Es un dato del centro comercial que no está en la información de este turno. Di con calidez que eso "
                f"te lo responden en el Punto de Información (Pasillo Barichara) o en la línea {LINEA_MALL}, y ofrece "
                "ayuda con otra cosa. No afirmes que no existe. " + sin_frases)
        return tipo, como, {}
    como = (f"Ningún local del centro comercial declara «{que}». Dilo así, con calidez: «En El Puente no encontré un "
            "local que lo ofrezca» (no afirmes que no existe en ninguna parte del centro comercial). Si hay algo "
            "parecido en los datos, ofrécelo; si no, la línea del centro comercial para confirmarlo "
            f"({LINEA_MALL}) y una pregunta para seguir ayudando. Si el pedido es vago, pregunta qué necesita. "
            + sin_frases)
    return tipo, como, {}


# Frases que suenan a «la administración no cargó el dato». Último filtro, por si el redactor las escribe igual.
_FRASES = [
    (re.compile(r"(?i)\s*(?:en|dentro de)\s+(?:(?:mi|nuestra|nuestro)\s+(?:base de datos|directorio|registro|sistema)|"
                r"la\s+base\s+de\s+datos)(?:\s+del\s+centro\s+comercial(?:\s+el\s+puente)?)?"), ""),
    (re.compile(r"(?i)\bno\s+(lo|la|los|las)\s+tengo\s+registrad[oa]s?\b"), r"no \1 tengo"),
    (re.compile(r"(?i)\bno\s+tengo\s+registrad[oa]s?\b"), "no tengo"),
    (re.compile(r"(?i)\bno\s+(está|esta|están|estan)\s+registrad[oa]s?\b"), r"no \1"),
    (re.compile(r"(?i)\bno\s+aparece\s+registrad[oa]\b"), "no aparece"),
    (re.compile(r"(?i)\bno\s+(?:tengo|cuento con|contamos con|tenemos)\s+(?:un\s+)?registro\s+de\b"), "no encontré"),
]


def suavizar(texto: str) -> str:
    if not texto or not re.search(r"(?i)registrad|base de datos|directorio|registro de",
                                  texto):
        return texto
    for patron, cambio in _FRASES:
        def _cambiar(m, cambio=cambio):
            nuevo = m.expand(cambio)
            return nuevo[:1].upper() + nuevo[1:] if m.group(0)[:1].isupper() and nuevo else nuevo
        texto = patron.sub(_cambiar, texto)
    return re.sub(r"[ \t]{2,}", " ", texto).replace(" .", ".").replace(" ,", ",")
