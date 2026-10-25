"""
Any 2.0 — asistente de WhatsApp del Centro Comercial El Puente.

Sistema independiente del bot anterior. No importa nada de services/
orchestrator, ai, rag, category_search ni routers/webhook. Solo comparte:
  - la base de datos (models/*): locales, eventos, conversaciones, etc.
  - el envío por WhatsApp (services/whatsapp.py: send_*).

Orden de cada mensaje (any/nucleo/harness.py):
  contexto → entrada (privacidad, pausa, emergencia, flujo en curso)
  → router IA → flujo especialista → salida (formato, equidad, promo) → traza

Carpetas:
  nucleo/        el orden fijo, el contexto, el router, las guardias, las trazas
  llm/           adaptador de modelos (Groq, OpenAI, Claude, Gemini…)
  conocimiento/  catálogo de locales, búsqueda por palabra y sinónimos, servicios
  flujos/        un archivo por tema; cada uno con sus herramientas
  prompts/       la persona única y las instrucciones de cada flujo (texto editable)
  datos/         sinónimos y mensajes fijos (texto editable, sin tocar código)
  evals/         banco de pruebas con conversaciones reales y su corredor
"""
