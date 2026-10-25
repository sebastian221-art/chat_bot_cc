"""
Registro de flujos. Para agregar uno: crear flujos/<nombre>.py con una clase
Flujo, su prompt en prompts/flujos/<nombre>.md, y registrarlo aquí.

PENDIENTES lista los flujos que el router ya conoce pero que aún no están
construidos (fases 2 a 4). Mientras tanto, si el router elige uno de ellos,
el núcleo responde con el flujo de respaldo y lo marca en la traza.
"""
from .base import Flujo
from .conversacion import Conversacion
from .emergencia_queja import EmergenciaQueja
from .locales import Locales
from .cine import Cine
from .eventos import Eventos
from .sorteos_promos import SorteosPromos
from .torre_medica import TorreMedica
from .administracion import Administracion
from .servicios_mall import ServiciosMall
from .domicilios import Domicilios
from .navegacion_qr import NavegacionQR
from .imagen import Imagen

FLUJOS: dict[str, Flujo] = {f.nombre: f for f in [Conversacion(), ServiciosMall(), EmergenciaQueja(), Locales(),
                                                Cine(), Eventos(), SorteosPromos(), TorreMedica(), Administracion(),
                                                Domicilios(), NavegacionQR(), Imagen()]}

PENDIENTES: dict[str, str] = {}   # todos los especialistas están construidos (fase 4)

RESPALDO = "conversacion"


def catalogo_para_router() -> str:
    filas = [f"- {n}: {f.descripcion}" for n, f in FLUJOS.items()]
    filas += [f"- {n}: {d}" for n, d in PENDIENTES.items()]
    return "\n".join(filas)


def nombres_validos() -> set[str]:
    return set(FLUJOS) | set(PENDIENTES)