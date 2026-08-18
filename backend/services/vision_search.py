"""
services/vision_search.py

El "bot que ve fotos": el cliente manda una imagen de un producto que
le interesa, la IA de visión de Groq la describe, y esa descripción
se usa como si fuera una pregunta normal de texto — así se reutiliza
todo el motor de búsqueda (RAG) y la personalidad de Any, sin duplicar
lógica.
"""
import logging
from services.ai import analyze_product_image, generate_response

logger = logging.getLogger("mall_bot")


async def handle_image_message(
    user_name: str,
    image_bytes: bytes,
    mime_type: str,
    caption: str = "",
    conversation_history: list[dict] | None = None,
) -> str:
    description = await analyze_product_image(image_bytes, mime_type, caption)

    if not description:
        return (
            "No pude analizar bien esa imagen 😅 ¿Me puedes contar con palabras "
            "qué buscas? Por ejemplo: \"busco zapatillas blancas deportivas\"."
        )

    # Usamos la descripción como si fuera la pregunta del cliente — así
    # el mismo buscador (RAG) de tiendas/eventos/conocimiento entra en juego.
    search_query = (
        f"El cliente mandó una foto de un producto. Descripción visual: {description}. "
        f"¿Qué tienda o local del mall tiene algo parecido a esto?"
    )

    response, _, _, _, _ = await generate_response(
        user_message=search_query,
        user_name=user_name,
        conversation_history=conversation_history or [],
    )

    return f"📸 Analicé tu foto — parece {description.lower()}\n\n{response}"