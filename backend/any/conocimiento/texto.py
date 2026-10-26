"""
Utilidades de texto en español. Todo se compara por PALABRA COMPLETA, nunca
por subcadena: esa fue la grieta principal del sistema viejo
("comer" dentro de "comercial", "niño" dentro de "Americanino",
"bar" dentro de "barbería").
"""
from __future__ import annotations

import re
import unicodedata

_PALABRA = re.compile(r"[a-z0-9ñ]+")

# Palabras sin contenido que no deben pesar en una búsqueda
VACIAS = set("""
a al algo algun alguna alguno algunos alla alli ante aqui asi como con cual cuales cuando de del desde donde
el ella ellas ello ellos en entre era es esa esas ese eso esos esta estan estas este esto estos fue
ha hay la las le les lo los mas me mi mis muy nada ni no nos o otra otro para pero poco por que quien se
sea si sin sobre son su sus tambien te tengo tiene tienen tienes ti tu tus un una unas uno unos usted ustedes
y ya yo quiero quisiera necesito busco buscar venden vende comprar compro conseguir consigo donde puedo
podria favor hola buenas buenos dias tardes noches gracias me regalas regala dime decir saber cuentame
centro comercial cc ccial mall puente local locales tienda tiendas almacen almacenes lugar lugares sitio
""".split())


def normalizar(texto: str) -> str:
    """minúsculas, sin tildes (pero conserva la ñ), espacios simples."""
    if not texto:
        return ""
    t = texto.lower().replace("ñ", "\x00")
    t = unicodedata.normalize("NFD", t)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = t.replace("\x00", "ñ")
    return re.sub(r"\s+", " ", t).strip()


def palabras(texto: str) -> list[str]:
    return _PALABRA.findall(normalizar(texto))


def raiz(palabra: str) -> str:
    """Raíz simple para plural y género: zapatos→zapat, zapato→zapat, niñas→niñ, tenis→tenis."""
    p = palabra
    if len(p) <= 3:
        return p
    if p.endswith("ces") and len(p) > 4:          # luces → luz
        return p[:-3] + "z"
    if p.endswith("es") and len(p) > 4 and p[-3] not in "aeiou" and not p.endswith("tes"):
        p = p[:-2]                                 # relojes → reloj, celulares → celular
    elif p.endswith("s") and not p.endswith("is") and not p.endswith("us"):
        p = p[:-1]                                 # zapatos → zapato (tenis y bus se quedan)
    if len(p) > 3 and p[-1] in "aoe":
        p = p[:-1]                                 # zapato → zapat, niña → niñ, bebé → beb
    return p


def raices(texto: str, quitar_vacias: bool = True) -> list[str]:
    return [raiz(p) for p in palabras(texto) if not (quitar_vacias and p in VACIAS)]


def contiene_frase(frase: str, texto: str) -> bool:
    """¿El texto contiene la frase como secuencia de palabras completas (comparando raíces)?"""
    f = [raiz(p) for p in palabras(frase)]
    t = [raiz(p) for p in palabras(texto)]
    if not f or len(f) > len(t):
        return False
    n = len(f)
    return any(t[i:i + n] == f for i in range(len(t) - n + 1))


def alguna_frase(frases: list[str], texto: str) -> str | None:
    for f in frases:
        if contiene_frase(f, texto):
            return f
    return None


def solo_digitos(texto: str) -> str:
    return "".join(c for c in (texto or "") if c.isdigit())


def link_whatsapp(telefono: str | None) -> str | None:
    """Solo los celulares (3xx xxx xxxx) tienen WhatsApp; un fijo no da link."""
    d = solo_digitos(telefono or "")
    if len(d) == 10:
        d = "57" + d
    if len(d) != 12 or not d.startswith("573"):
        return None
    return f"https://wa.me/{d}"


def telefono_fijo(telefono: str | None) -> str | None:
    """El número escrito bonito cuando NO es un celular (fijo, línea 01 8000…). None si es celular o no hay."""
    t = (telefono or "").strip()
    d = solo_digitos(t)
    if not d or link_whatsapp(t):
        return None
    if d.startswith("3"):
        return None       # celular mal escrito (le sobra o le falta un dígito): mejor no darlo
    if len(d) == 7:
        return f"(607) {d[:3]} {d[3:]}"
    if len(d) == 10 and d.startswith("60"):
        return f"({d[:3]}) {d[3:6]} {d[6:]}"
    if d.startswith("018000"):
        return f"01 8000 {d[6:9]} {d[9:]}".strip()
    return t