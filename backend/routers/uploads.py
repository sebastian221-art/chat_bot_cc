"""
routers/uploads.py

Subida REAL de imágenes — el admin sube el archivo directo desde su
computador/celular, el sistema lo guarda en el Volume persistente de
Railway y devuelve el link público listo para pegar en cualquier
campo de foto (Locales, Zonas, Eventos, Sorteos, Base de Conocimiento).

Sin esto, había que subir la imagen a otro lado (Imgur, Drive, etc.),
copiar el link y pegarlo — ahora es un solo clic.
"""
import logging
import uuid
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from config import get_settings

settings = get_settings()
logger = logging.getLogger("mall_bot")
router = APIRouter(prefix="/uploads", tags=["uploads"])

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
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

    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = upload_dir / filename

    try:
        with open(filepath, "wb") as f:
            f.write(content)
    except Exception as e:
        logger.error(f"Error guardando imagen: {e}")
        raise HTTPException(status_code=500, detail="No se pudo guardar la imagen en el servidor")

    public_url = f"{settings.PUBLIC_BASE_URL}/uploads/{filename}"
    print(f"  🖼️   Imagen subida: {filename} ({size_mb:.2f} MB)")
    return {"ok": True, "url": public_url}