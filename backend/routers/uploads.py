"""
routers/uploads.py

Subida REAL de imágenes — el admin sube el archivo directo desde su
computador/celular, el sistema lo guarda en el Volume persistente de
Railway y devuelve el link público listo para pegar en cualquier
campo de foto (Locales, Zonas, Eventos, Sorteos, Base de Conocimiento).

⚠️ IMPORTANTE — CONVERSIÓN AUTOMÁTICA A JPG:
WhatsApp Cloud API solo acepta imágenes JPG y PNG cuando se mandan por
link. Formatos como .webp o .gif los rechaza SILENCIOSAMENTE (responde
200 OK pero nunca entrega la foto al cliente). Para que esto NUNCA falle,
aquí convertimos TODA imagen subida a JPG antes de guardarla — sin
importar en qué formato venga. Así el admin puede subir lo que sea
(webp, png, gif, etc.) y siempre queda en un formato que WhatsApp
entrega bien.
"""
import io
import logging
import uuid
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from PIL import Image
from config import get_settings

settings = get_settings()
logger = logging.getLogger("mall_bot")
router = APIRouter(prefix="/uploads", tags=["uploads"])

# Formatos que aceptamos SUBIR (luego los convertimos todos a JPG)
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff"}
MAX_FILE_SIZE_MB = 8


@router.post("/image")
async def upload_image(file: UploadFile = File(...)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo de archivo no permitido ({ext or 'sin extensión'}). Usa JPG, PNG, WEBP o GIF.",
        )

    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(
            status_code=400,
            detail=f"La imagen pesa {size_mb:.1f} MB — el máximo permitido es {MAX_FILE_SIZE_MB} MB.",
        )

    # ── Conversión a JPG (la clave para que WhatsApp SIEMPRE la acepte) ──
    # Abrimos la imagen con Pillow y la re-guardamos como JPG, sin
    # importar su formato original. Esto también aplana transparencias
    # (webp/png con fondo transparente) sobre blanco, porque JPG no
    # soporta transparencia.
    try:
        img = Image.open(io.BytesIO(content))
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
            fondo = Image.new("RGB", img.size, (255, 255, 255))
            fondo.paste(img, mask=img.split()[-1])  # usa el canal alfa como máscara
            img = fondo
        else:
            img = img.convert("RGB")
    except Exception as e:
        logger.error(f"Error procesando la imagen subida: {e}")
        raise HTTPException(status_code=400, detail="No se pudo procesar la imagen. ¿Está dañada o no es una imagen válida?")

    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)

    # SIEMPRE .jpg, sin importar qué subieron
    filename = f"{uuid.uuid4().hex}.jpg"
    filepath = upload_dir / filename

    try:
        img.save(filepath, format="JPEG", quality=88, optimize=True)
    except Exception as e:
        logger.error(f"Error guardando imagen JPG: {e}")
        raise HTTPException(status_code=500, detail="No se pudo guardar la imagen en el servidor")

    public_url = f"{settings.PUBLIC_BASE_URL}/uploads/{filename}"
    print(f"  🖼️   Imagen subida y convertida a JPG: {filename} (original {ext}, {size_mb:.2f} MB)")
    return {"ok": True, "url": public_url}