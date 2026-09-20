"""
routers/uploads.py

Subida REAL de imágenes y PDF — el admin sube el archivo directo desde
su computador/celular, el sistema lo OPTIMIZA (comprime) automáticamente
y lo guarda, devolviendo el link público listo para usar en el panel.

⚠️ DOS COSAS AUTOMÁTICAS que hace este módulo:

1. IMÁGENES → se convierten a JPG y se COMPRIMEN:
   - WhatsApp solo entrega bien JPG/PNG (rechaza webp/gif en silencio).
   - Si la imagen es grande (fotos de celular de varios MB), se
     redimensiona y se baja la calidad lo justo para que quede liviana
     (~ bajo 1 MB) sin perder nitidez visible. Así llega rápido por
     WhatsApp incluso con datos móviles.

2. PDF (cartas/menús) → se COMPRIME con pikepdf:
   - El admin sube la carta (hasta 25 MB), el sistema le baja el peso
     manteniéndola legible, para que WhatsApp la envíe ágil.

Límite de 25 MB: amplio para cualquier carta razonable, pero sin
permitir archivos tan pesados que tarden en subir o enviarse.
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

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff"}
MAX_IMAGE_MB = 25   # aceptamos imágenes grandes; las comprimimos nosotros
MAX_PDF_MB = 25     # cartas pesadas permitidas; las comprimimos nosotros

# Objetivo de compresión (para que WhatsApp las envíe ágil)
IMG_MAX_LADO = 1600      # ningún lado mayor a 1600 px (suficiente para ver bien)
IMG_CALIDAD = 82         # calidad JPG (82 = buena y liviana)


def _comprimir_pdf(content: bytes) -> bytes:
    """Comprime un PDF con pikepdf. Devuelve el optimizado, o el original
    si algo falla o si no logró reducirlo."""
    try:
        import pikepdf
        entrada = io.BytesIO(content)
        salida = io.BytesIO()
        with pikepdf.open(entrada) as pdf:
            pdf.save(salida,
                     compress_streams=True,
                     object_stream_mode=pikepdf.ObjectStreamMode.generate,
                     linearize=True)
        optimizado = salida.getvalue()
        return optimizado if len(optimizado) < len(content) else content
    except Exception as e:
        logger.error(f"No se pudo comprimir el PDF (se usa el original): {e}")
        return content


@router.post("/image")
async def upload_image(file: UploadFile = File(...)):
    ext = Path(file.filename or "").suffix.lower()
    content = await file.read()
    size_mb = len(content) / (1024 * 1024)

    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)

    # ── PDF: comprimir y guardar ──────────────────────────────────
    if ext == ".pdf":
        if size_mb > MAX_PDF_MB:
            raise HTTPException(status_code=400, detail=f"El PDF pesa {size_mb:.1f} MB — el máximo es {MAX_PDF_MB} MB. Comprímelo un poco antes de subirlo.")
        comprimido = _comprimir_pdf(content)
        nuevo_mb = len(comprimido) / (1024 * 1024)
        filename = f"{uuid.uuid4().hex}.pdf"
        (upload_dir / filename).write_bytes(comprimido)
        public_url = f"{settings.PUBLIC_BASE_URL}/uploads/{filename}"
        print(f"  📄  PDF subido y comprimido: {filename} ({size_mb:.2f} MB → {nuevo_mb:.2f} MB)")
        return {"ok": True, "url": public_url, "tipo": "pdf",
                "peso_original_mb": round(size_mb, 2), "peso_final_mb": round(nuevo_mb, 2)}

    # ── IMÁGENES ──────────────────────────────────────────────────
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Tipo de archivo no permitido ({ext or 'sin extensión'}). Usa JPG, PNG, WEBP, GIF o PDF.")
    if size_mb > MAX_IMAGE_MB:
        raise HTTPException(status_code=400, detail=f"La imagen pesa {size_mb:.1f} MB — el máximo es {MAX_IMAGE_MB} MB.")

    try:
        img = Image.open(io.BytesIO(content))
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
            fondo = Image.new("RGB", img.size, (255, 255, 255))
            fondo.paste(img, mask=img.split()[-1])
            img = fondo
        else:
            img = img.convert("RGB")

        # COMPRESIÓN: reducir si algún lado supera IMG_MAX_LADO
        w, h = img.size
        if max(w, h) > IMG_MAX_LADO:
            escala = IMG_MAX_LADO / max(w, h)
            img = img.resize((int(w * escala), int(h * escala)), Image.LANCZOS)
    except Exception as e:
        logger.error(f"Error procesando la imagen: {e}")
        raise HTTPException(status_code=400, detail="No se pudo procesar la imagen. ¿Está dañada o no es válida?")

    filename = f"{uuid.uuid4().hex}.jpg"
    filepath = upload_dir / filename
    try:
        img.save(filepath, format="JPEG", quality=IMG_CALIDAD, optimize=True)
    except Exception as e:
        logger.error(f"Error guardando imagen JPG: {e}")
        raise HTTPException(status_code=500, detail="No se pudo guardar la imagen en el servidor")

    nuevo_mb = filepath.stat().st_size / (1024 * 1024)
    public_url = f"{settings.PUBLIC_BASE_URL}/uploads/{filename}"
    print(f"  🖼️   Imagen subida, convertida a JPG y comprimida: {filename} ({size_mb:.2f} MB → {nuevo_mb:.2f} MB)")
    return {"ok": True, "url": public_url,
            "peso_original_mb": round(size_mb, 2), "peso_final_mb": round(nuevo_mb, 2)}