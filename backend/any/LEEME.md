# Any — Chatbot WhatsApp del Centro Comercial El Puente (San Gil)
**Documento de traspaso. Actualizado: 24/10/2026 (noche).** Léelo completo antes de tocar código.

> **Estado al 24/10/2026:** se decidió reconstruir el bot como **Any 2.0** (sección 9). El sistema actual sigue atendiendo con el orquestador mientras tanto, con los parches de la **fase 0** (sección 9.2). El **esqueleto de Any 2.0 (fase 1)** está entregado (sección 9.7). El plan completo, con diagnóstico y diagramas, está en el doc **"Any 2.0 — Diagnóstico y plan de reconstrucción"** (https://claude.ai/artifact/Hmv8Mm5FqW1iPkTGqtZ9q2).

## 0. Cómo trabajamos (reglas del dueño)
- Sebastián (JELCOM) **sube los archivos a mano** al repo `sebastian221-art/chat_bot_cc` (rama `master`) y Railway despliega. **Nunca hacer push ni commits.** Se entregan archivos separados con su ruta.
- "No dañes lo que ya funciona": cada arreglo se prueba contra los datos reales (export del panel o copia de la base) antes de entregar, comparando antes y después.
- El cliente (el mall) prueba por WhatsApp y manda **trazas del orquestador** (exportadas desde el panel) + logs de Railway. Se analizan traza por traza.
- Sebastián será quien mantenga todo el sistema: código ordenado, modular, cada flujo en su archivo, probado por secciones.
- Ninguna pieza nueva sale a clientes sin pasar por el banco de pruebas con conversaciones reales y un periodo en paralelo (lección del agente v1, sección 8).
- **Any 2.0 se escribe desde cero en `backend/any/`**: no se sobrescriben archivos viejos. La fase 0 fue solo un parche temporal sobre el sistema viejo mientras tanto.

## 1. Arquitectura actual (sistema viejo)
- **Backend**: FastAPI + SQLAlchemy + PostgreSQL (driver **pg8000**) en Railway. Raíz de la app = `backend/` (montada como `/app`). `/uploads` en Volume persistente (público: WhatsApp descarga de ahí las fotos).
- **IA**: Groq. `GROQ_MODEL` = `openai/gpt-oss-120b` (texto), `GROQ_VISION_MODEL` (qwen) para el afiche. RAG con ChromaDB (`services/rag.py`) **sin modelo de embeddings configurado → usa all-MiniLM-L6-v2, entrenado en inglés** (una de las causas de que la base de conocimiento se lea mal en español).
- **WhatsApp Cloud API** (`services/whatsapp.py`): límite 3900 chars → `_partir_mensaje()`.
- **Panel**: Next.js (`panel/`), cliente API `panel/lib/api.ts` (manda `Authorization: Bearer` en todas las peticiones).
- **Flujo de un mensaje**: `routers/webhook.py` → privacidad (Ley 1581), escalamiento, pausa → switch (`services/orchestrator_switch.py`): `agente_*` → `services/agente.py`; `produccion`/`solo_yo` → `services/orchestrator.py`; si no → `webhook._route_message` (flujo viejo).
- Hasta 5 capas deciden el mismo mensaje (reglas del orquestador → IA clasificadora → correcciones de cine → `_route_message` → `generate_response` con su propio clasificador). Es la grieta 2 del diagnóstico.

## 2. Orquestador (`services/orchestrator.py` + `orchestrator_tools.py`)
Reglas por palabra clave (palabra completa + plurales) → si nada coincide, IA clasificadora elige herramienta. Traza por mensaje en el panel.
Atajos antes de decidir: `_respuesta_inscripcion_evento` y `_atajo_carta_link`. Correcciones de cine después de decidir.
Herramientas: `emergencia`, `queja`, `administracion_mall`, `gestion_domicilio`, `cartelera_cine`, `numero_tienda`, `busqueda_categoria`, `ubicacion_mall`, `torre_medica`, `eventos`, `sorteos`, `promociones`, `conversacion_general` (delega en `_route_message`).
Promo al final: `ai._texto_promo_para_pegar`, salvo emergencia/queja/eventos/sorteos/promos/general/domicilio/administración/ubicación y respuestas < 120 chars.

### Cine (`services/cine.py`)
Comprar/reservar → `https://www.cinelandia.com.co/san-gil`; tarifas → `resumir_tarifas()`; confitería; película puntual; cartelera. Tarifas y confitería en `Store.extra_info` de "Cinelandia Múltiplex".

### Búsqueda por categoría (`services/category_search.py` + `rag.find_all_stores_by_category`)
- Desde la fase 0 (24/10) compara **palabras completas** (ver 9.2). Antes comparaba pedazos de texto.
- **Siempre se listan TODOS** los locales relevantes (equidad), orden alfabético, `• *Nombre* — Zona · Tel: …`.
- **NO se habla de niveles/pisos** (pedido del mall, 20/10): solo zonas. Excepción: Torre Médica. Desde la fase 0 ya no quedan textos con "Piso 1"/"Piso X" en el código; el Punto de Información se ubica en Pasillo Barichara.

### Vigencia
`Event.esta_vigente()`, `Raffle.esta_vigente()`, `Marketing.esta_vigente()` (fechas DD/MM/AAAA en texto).

## 3. Datos y carga
- Plantillas Excel del mall: Locales, Administrativo, Cine. Importadores `services/excel_importer.py`, `services/extra_importers.py`.
- El primer tag de cada local es el **rubro** del Excel (p. ej. "Droguerías, Salud y Ópticas"); el resto son las palabras de qué vende. La zona está en `location_hint`; `floor` trae "Nivel N"/"Piso N" (solo se usa el piso en la Torre Médica).
- **Revisión de datos (23-24/10)**: `Locales_revision_datos.xlsx` (35 locales con problemas, 10 filas a borrar: 4 "Teléfono:" basura y 4 duplicados de la Torre) y `Datos_pendientes_CC_El_Puente.xlsx` (cajeros, parqueadero, Punto de Información, nombre de la plazoleta, misa, baños, horarios, administración, seguridad, cine, especialidades de la Torre). **Pendiente que el mall los llene.**
- Instagram no se scrapea (Meta bloquea).

## 4. Sincronización automática (`services/sincronizador.py`)
Cinelandia (cartelera, confitería, tarifas), web de El Puente (servicios, Torre), afiche de campañas (Wix da 403 a Railway → plan B: botón "Leer afiche (imagen)"). Corre al arrancar y cada 24 h. Ojo: sobrescribe la cartelera, tarifas/combos y conocimiento de servicios; lo editado a mano en eso se pierde.

## 5. Prompt de la IA (`services/ai.py`, BASE_PERSONA)
70 reglas con 16 contradicciones detectadas (inventario C, 24/10). Para Any 2.0 se reescribió como **una sola persona sin contradicciones** (`backend/any/prompts/persona.md`).

## 6. Entorno de pruebas local
- `backend/scripts/copiar_bd.py`: copia la base de Railway a `backend/local.db` (solo lectura sobre Railway). Arrancar con `DATABASE_URL=sqlite:///./local.db`. Chat de prueba viejo en `http://localhost:8000/chat` (`/webhook/test`); chat de Any 2.0 en `/any/chat`.
- En este entorno de Claude: stubs de `chromadb` y `langchain_groq` en el scratchpad (`stubs/`), SQLite con el export real de locales. **Desde aquí no se puede llamar a Groq** (la red lo bloquea): los reportes con IA real los corre Sebastián.

## 7. Pendientes
- Subir los 9 archivos de la fase 0 (sección 9.2) y probar por WhatsApp (opcional: es un parche temporal).
- Subir el esqueleto de Any 2.0 (sección 9.7) y correr `python -m any.evals.pruebas` y `python -m any.evals.correr --reporte reporte.md` con la clave de Groq; mandar el reporte.
- Enviar al centro comercial `Datos_pendientes_CC_El_Puente.xlsx` y `Locales_revision_datos.xlsx`; borrar las 10 filas basura/duplicadas.
- Cada mes: subir el afiche nuevo con "Leer afiche (imagen)".

## 8. Agente v1 (21/10/2026) — retirado
Se construyó `services/agente.py` (un solo agente con 9 herramientas, tool calling de Groq) y los modos `agente_pruebas` / `agente_todos` del switch. Estuvo en producción ~10 minutos el 23/10 y **falló en 4 de 8 conversaciones**: no forzaba respuesta al llegar al tope de vueltas (#26), reutilizó la búsqueda por pedazos de texto y su "red de equidad" metió una barbería en "entretenimiento para adultos" (#30), no conectaba domicilios ni QR (#27), y se había probado con modelo simulado y datos inventados. Producción volvió al orquestador. El archivo sigue en el repo pero **no se usa**; Any 2.0 lo reemplaza.

## 9. Any 2.0 — reconstrucción (decidida el 24/10/2026)
### 9.1 Diagnóstico (32 trazas del 23/10)
16 de 32 fallaron. Solo 1 por el modelo de IA; 8 por búsqueda y datos, 5 por arquitectura (capas que se pisan, plantillas), 2 por el agente v1. Seis grietas: búsqueda por pedazos de texto; hasta 5 capas decidiendo; herramientas-plantilla sin hilo; datos faltantes; reglas contradictorias y promos duplicadas; flujos con estado sin dueño.

### 9.2 Fase 0 — entregada el 24/10 (parche temporal, pendiente de subir)
9 archivos, probados con el export real de locales (62 búsquedas comparadas antes/después: 46 iguales, 16 cambios y todos correcciones; 15/15 casos de punta a punta; app levantada con TestClient):
1. **Búsqueda por palabra completa** (`category_search.py`: `_en_palabra`; `rag.py`: `_palabras`, `_raiz`, `_coincide_palabra`, `_coincide_frase`, `_tags_sin_rubro`). Supermercados → Jumbo; ropa para niños → Offcorss y Tomaticos; tiendas deportivas + People Plays; "centro comercial" ya no dispara comida; se quitó "Ópticas" del rubro de droguerías para la comparación. Categoría nueva `supermercado`.
2. **Regla de cine** (`orchestrator._parece_pregunta_de_funcion`): no se activa si el mensaje habla del centro comercial/cc/mall/funcionamiento/local/tienda.
3. **Torre Médica** (`_ejecutar_torre_medica`): busca la necesidad en los consultorios (nombre, tags, descripción); si no hay coincidencia lista los consultorios en vez de "no tengo datos"; filtra filas "Teléfono:" y duplicados; solo presenta como de la Torre a locales que están en la Torre.
4. **Pisos**: todas las menciones "Piso 1"/"Piso X" del código cambiadas por zonas.
5. **API protegida**: `routers/api.py` y `routers/uploads.py` exigen sesión (`Depends(get_current_user)`). `/uploads/*` (fotos), `/webhook*` y `/chat` siguen públicos.
6. **Sorteos**: `_ejecutar_sorteos` devolvía `"\n\n".join(lineas)` (variable inexistente cuando la IA redactaba) → ahora `texto`.
7. **Router IA**: nombre exacto primero; si viene en una frase, gana la última herramienta nombrada.

### 9.3 Arquitectura de Any 2.0
- Carpeta propia `backend/any/`, **independiente del sistema viejo**: solo comparte la base de datos (`models/`), el envío por WhatsApp (`services/whatsapp.py`) y el login del panel (`routers/auth.py`).
- Núcleo (harness) con orden fijo: contexto → entrada (pausa humana, privacidad) → **router** (regla dura de emergencia → flujo con estado activo → IA con salida JSON: flujo + entidades + seguimiento + consulta reescrita) → **especialista** (reúne datos verificados en código; la IA solo redacta, con herramientas si le faltan datos; la última vuelta siempre obliga a responder) → salida (formato WhatsApp, sin pisos, teléfonos verificados, equidad, emergencia completa, nunca vacía) → traza.
- 12 flujos, un archivo cada uno: conversación, locales, cine, eventos, sorteos y promos, servicios del mall, Torre Médica, administración, domicilios (estado), navegación QR (estado), foto del cliente, emergencias y quejas. **Sin plantillas** salvo emergencia y privacidad.
- **Capa de conocimiento**: catálogo normalizado (zona, rubro, productos; sin filas basura ni duplicados); búsqueda por palabra completa con raíz (plural/género) y sinónimos en YAML; filtro de relevancia. Fase 2 agrega embeddings multilingües (híbrida), reordenamiento y medición de la búsqueda aparte.
- **Adaptador de LLM** (`any/llm/`): OpenAI-compatible por httpx (Groq, OpenAI, Gemini, DeepSeek, local) + Anthropic + simulado; `proveedor:modelo` por rol o por flujo, con respaldo. Se elige modelo con el banco de pruebas (candidatos: gpt-oss-120b, GPT-5 mini, Claude Haiku 5.5).
- Núcleo propio, sin LangGraph ni Agents SDK, por los problemas de dependencias que ya hubo en Railway.

### 9.4 Plan por fases
0 Estabilizar (hecha, falta subir) · **1 Esqueleto (hecha, falta subir y correr con Groq)** · 2 Conocimiento + locales · 3 Cine, eventos, sorteos, Torre, administración (+ regla única de promos) · 4 Domicilios, QR, foto · 5 Piloto en sombra 1 semana · 6 Retiro del sistema viejo · **7 Panel**: recorrido visual de cada mensaje por flujo + configurar sin código (sinónimos, contactos, textos, reglas de promo, persona) · **8 API para agentes** (Emilia y otros: leer trazas/conversaciones, detectar fallas, corregir datos con llaves, permisos y registro; visión y extracción). Cada fase avanza solo si aprueba su prueba.

### 9.5 Pasos de arranque y estado
1. **Inventario del sistema viejo** — hecho el 24/10: ~180 capacidades, 70 reglas de prompt con 16 contradicciones, 29 tablas, 77 endpoints → 294 requisitos (`Inventario_Any_sistema_viejo.md`).
2. **Banco de pruebas** — `backend/any/evals/casos/casos_reales.yaml`: 12 conversaciones / 72 turnos reales (20–23/10), con flujo esperado, debe/no_debe, criterio y fecha simulada; 9 turnos dependen de datos del mall.
3. Fase 0 — entregada.
4. Esqueleto (fase 1) — entregado el 24/10 (9.7).
**Para seguir se necesita de Sebastián:** subir el esqueleto, correr el banco con su clave de Groq (desde el entorno de Claude no hay salida a Groq) y mandar el reporte; copia completa de la base (`copiar_bd.py` → `local.db`).

### 9.6 Hallazgos del inventario que Any 2.0 debe resolver (además de las grietas)
- Webhook: sin deduplicación por `message_id` ni validación de firma; audios, PDFs y ubicaciones se ignoran sin respuesta; las imágenes se saltan privacidad, escalamiento y switch. **Resuelto en el esqueleto** (dedup, firma con `META_APP_SECRET`, lote completo, respuesta a tipos no soportados).
- QR: la regex `zona\s+…` va primero que todo; "en la zona de comidas" se lee como código "DE". (fase 4)
- Privacidad: el primer mensaje del cliente se descartaba al mostrar el aviso; borrado parcial. **Resuelto en el esqueleto** (aviso como mensaje previo + respuesta; borrado en todas las tablas con columna de teléfono).
- Domicilios: la sesión de gestión nunca expira; la calificación 1–5 no se captura. (fase 4; el estado de Any 2.0 ya caduca con la sesión de 4 h)
- Saludo + pregunta ("hola, ¿a qué hora abren?") se respondía solo como saludo. (el router IA decide por la intención)
- Analytics usa UTC (horas pico corridas 5 h). (fase 7)
- Panel: permisos de supervisor inconsistentes con el menú; Flujo del Bot y Orquestador dependen de que el usuario se llame `admin`. (fase 7)

### 9.7 Fase 1 — esqueleto entregado el 24/10 (`Any2_fase1_esqueleto.zip`)
- **Archivos**: carpeta nueva `backend/any/` completa + **una línea** en `backend/main.py` (`app.include_router(... "any.entrada" ...)`). Ningún otro archivo viejo cambia. Guía de mantenimiento: `backend/any/LEEME.md`.
- **Estructura**: `config.py`, `entrada.py` (`/any/webhook`, `/any/prueba`, `/any/chat`), `nucleo/` (harness, tipos, estado, router, guardias, trazas, mensajes), `llm/` (base, openai_compat, anthropic, simulado, registro), `conocimiento/` (texto, catalogo, buscador, servicios), `flujos/` (base + conversacion, servicios_mall, emergencia_queja; los otros 9 registrados como pendientes: responden con honestidad sin inventar), `prompts/` (persona.md, router.md, flujos/*.md), `datos/` (mensajes.yaml, sinonimos.yaml), `evals/` (pruebas.py, correr.py, casos/), `static/chat.html`.
- **Tablas nuevas** (se crean solas): `any_estado`, `any_mensajes_vistos`, `any_aviso_privacidad`. Historial en `conversations` (session_id `any2`), trazas en `orchestrator_traces` (método `any2`, herramienta `any:<flujo>`).
- **Pruebas en este entorno**: 20/20 pruebas por secciones (texto, catálogo, búsqueda, adaptadores con servidor falso, router, guardias, entrada de Meta, recorrido completo: aviso, pausa humana, emergencia, borrado, pin de ubicación, modelo caído). Banco de 72 turnos corrido con modelo simulado para validar la plomería; falta correrlo con Groq. El webhook viejo sigue respondiendo igual.
- **Antes de apuntar Meta a `/any/webhook`** (fase 6): agregar `"/any/webhook"` a `RUTAS_EXENTAS` en `services/seguridad.py` y configurar `META_APP_SECRET`.
- Los datos de la base de pruebas de Claude para mall_info, conocimiento, eventos y sorteos son de prueba (las tarifas de parqueadero, por ejemplo, no están confirmadas por el mall).

### 9.8 Primer banco con Groq real (24/10) y fase 2 — locales
- **Banco con gpt-oss-120b:** router 69/72 (96 %). Servicios del mall 9/10, conversación 4/5, pruebas por secciones 19/20 (la de baños falla porque `info_points` está vacía en producción: dato del mall). Los demás ❌ eran temas aún no construidos.
- **Hallazgo grave:** con un tema sin datos, el modelo inventó un local ("Estilo & Corte", Pasillo Vélez, wa.me/57XXXXXXXXXX copiado del ejemplo de la persona) y una zona mal escrita ("Pasillo Barichra"). Corregido: los temas pendientes responden un texto fijo sin IA (`tema_pendiente` en mensajes.yaml); se quitó el ejemplo 57XXXXXXXXXX de la persona; guardias nuevas que quitan links de relleno y corrigen o marcan pasillos que no existen.
- **Flujo locales** (`any/flujos/locales.py` + `prompts/flujos/locales.md` + `locales_juez.md`): modo FICHA (teléfono, zona, horario, carta como foto/PDF/link, Instagram desde `catalogo_link` o la descripción, foto) y modo LISTA (todos los relevantes, orden alfabético; la lista la inserta el código en `{LISTA}`, la IA solo escribe la entrada y el cierre). Un juez IA poda candidatos y no puede agregar locales que no estén. Nunca se muestra `extra_info` (trae nombres de responsables).
- **Búsqueda:** palabras de pedido (número, carta, todos…) ya no cuentan como búsqueda; sinónimos con "generales" (amplían a todo el grupo) y "especificos" (se buscan solos); `amplia_a` para que el juez revise un grupo mayor (tenis → calzado); la descripción sola no basta para entrar a una lista; `encontrar_local` tolera tildes, mayúsculas y nombres a medias ("la barra", "12b").
- Con modelo simulado: 33/33 turnos de locales correctos en datos y formato; 24/24 pruebas por secciones. Falta correr el banco con Groq.

### 9.9 Fase 2 cerrada y fase 3 entregada (25/10)
- **Banco con Groq tras los ajustes de la fase 2:** 62/72 correctos, router 70/72, locales 32/33, servicios del mall 9/9. Los 10 restantes eran temas de la fase 3 más "?" (aceptable: repite el horario del hilo).
- **Fase 3 entregada (20 archivos):** flujos `cine` (cartelera de `cine_funciones`, película puntual con póster, tarifas del DÍA interpretadas del bloque de tarifas, confitería, compra = link oficial + taquilla), `eventos` (solo vigentes según la fecha del contexto, inscripción solo con lo que dice la descripción, afiche), `sorteos_promos` (sorteos y promociones vigentes, registro de facturas con link oficial + Punto de Información + reglas del conocimiento, entiende "¿ese descuento en qué es?"), `torre_medica` (aquí sí piso y consultorio; si nada coincide, directorio completo armado en código), `administracion` (contacto real del local Administración; nunca precios ni disponibilidad). Módulos nuevos: `conocimiento/vigencia.py`, `fotos.py`, `cine_datos.py`.
- **Regla única de promociones** (`nucleo/promociones.py`): solo en locales, servicios, conversación y cine; nunca en el primer mensaje; tope 2 por sesión; espaciado de 3 mensajes; la de mayor prioridad entre eventos (próximos 15 días), sorteos y promociones vigentes no mostradas; se registra en `promotions_shown` solo si aparece en el texto.
- Canales oficiales en `datos/mensajes.yaml`: `cine_compra_url`, `registro_facturas_url`.
- Pruebas por secciones: 27/27 con la base de prueba. Falta el banco con Groq. Revisar que `local.db` tenga `events` y `entity_photos` (en la salida de la copia no aparecieron).
- Pendiente: fase 4 (domicilios, QR, foto del cliente).

### 9.10 Novedad en cada respuesta y blindaje de datos (25/10, madrugada)
- **Pedido del mall:** cada respuesta promociona una novedad vigente (evento, sorteo o promoción), rotando. Parámetros en `any/datos/reglas.yaml` (sin promo en emergencia, privacidad, eventos, sorteos y domicilios; tope 12 por sesión; también en el saludo). Si la IA no la menciona, el código agrega la línea "De paso: …" con datos reales. Las líneas "De paso" no se le muestran al router (contaminaban el tema).
- **Revisiones de salida agregadas tras el banco real:** precios y porcentajes que no están en los datos → se quita la línea; fechas que no están en los datos (numéricas o "31 de enero de 2027") → se quita la línea; nombres de los datos mal copiados ("Puente de Información", "Barichra") → se corrigen comparando palabra por palabra; caracteres invisibles fuera; tema nombrado ("¿hay promociones?") gana sobre el tema anterior.
- Incidente: el banco cayó a 33/72 por un error de carga de modelos (Marketing→Store) que solo ocurría fuera de `main.py`; corregido cargando todos los modelos al inicio del núcleo.
- **Banco con Groq: 69/72**, 30/30 pruebas por secciones (en producción 29/30: faltan los puntos de interés como baños).
- Siguiente: fase 4 (domicilios con vencimiento a 4 h y confirmación SÍ/NO, QR de zonas, foto del cliente).

### 9.11 Fase 3 cerrada (70/72) y fase 4 entregada (25/10)
- Banco con Groq tras los ajustes: **70/72** (los 2 restantes, "¿Y de ropa?" tras un descuento y "?", son ambigüedades aceptables). Pruebas 29/30 en producción (falta cargar puntos de interés).
- **Fase 4 (19 archivos):**
  - `flujos/domicilios.py`: pedido con estado (local → datos → resumen exacto en código → confirmación SÍ/NO → link wa.me al local con el pedido escrito). Extracción de datos con IA (`domicilios_extraer.md`), celular por defecto = el mismo WhatsApp, pago efectivo/transferencia, carta adjunta al empezar. "cancelar" en cualquier momento. Si el cliente pregunta otra cosa, se responde y se le recuerda el pedido abierto. Vence a las 4 h (sesión). Registra en `delivery_managements` y `delivery_transfers` (panel).
  - `flujos/navegacion_qr.py`: QR estricto ("Estoy en Zona X" o un código que exista en `zones`; "zona de comidas" ya no se lee como código), registra `zone_scans` siempre, confirma dónde está el cliente y luego dice en qué zona queda el local. No inventa giros ni distancias (no hay rutas en la base).
  - `flujos/imagen.py`: modelo de visión (`ANY_LLM_VISION`, por defecto el `GROQ_VISION_MODEL` del sistema viejo) → JSON con qué es y términos de búsqueda → misma búsqueda de locales con lista en código. Marca icónica solo como referencia de estilo.
  - Router: reglas exactas para foto y QR; aviso al router cuando hay un pedido abierto. Guardias: los links se apartan antes de revisar precios/fechas/teléfonos (un link con el pedido escrito daba falsos positivos). Chat de prueba con botón de foto. Banco nuevo `casos_fase4.yaml` (2 conversaciones de domicilio).
- Ya no quedan temas pendientes: los 12 especialistas existen. Siguiente: fase 5 (una semana en sombra).

### 9.12 Any 2.0 en producción y primer pulido (25/10)
- **Cambio a producción sin tocar Meta:** variable `ANY_PRINCIPAL=1` en Railway hace que el mismo `/webhook` lo atienda Any 2.0 (router registrado antes del webhook viejo en `main.py`). `ANY_NUMEROS_PRUEBA` limita Any 2.0 a ciertos números. `GET /any/estado` muestra si está activa. Volver atrás: `ANY_PRINCIPAL=0`. Si Any falla en un mensaje, se envía una disculpa (el cliente nunca queda sin respuesta).
- Trazas: Any 2.0 guarda el paso a paso en el formato del panel (lista de textos); `models/orchestrator_trace.py` tolera las trazas guardadas antes en otro formato (la página de trazas se caía).
- "Eliminar mis datos" borra también las trazas del número (Ley 1581): se perdieron las 70 trazas de la prueba manual. Para probar sin WhatsApp: `python -m any.evals.produccion` (manda el banco al servidor real vía `/any/prueba`, reporte con todas las respuestas y los datos que usó cada una).
- **Banco en producción: 99/103.** Revisión a mano de las 103 respuestas → pulido 1 (24 archivos): guardia de nombres ya no cambia "el Punto de Información" por "El Puente"; precios con "mil/millones"; pisos con ordinal ("2.º piso"); voseo → tuteo; marca `{LIST}` tolerada y lista siempre antes del "De paso"; textos de promociones en MAYÚSCULAS suavizados; búsqueda sin palabras genéricas (servicio, marcas, comprar); coincidencias solo por descripción pasan por el juez (Maxiland Kids ya no es "gimnasio"); sinónimos de vida nocturna, gimnasio y ocasión formal; Torre Médica solo muestra salud cuando piden doctor (no abogados) y "vacunación" encuentra FOSCAL; fin de semana y "hoy" de cada evento calculados en código; el historial que ve cada flujo ya no incluye las líneas "De paso"; recordatorio del pedido abierto 1 de cada 3 mensajes; prompts sin tiendas de ejemplo inventadas (Zara/H&M), sin "ya fue notificado", sin afirmar vacantes; cine ofrece tarifas/combos en vez de decir que no los tiene.
- Datos por revisar en el panel (no se pudieron verificar desde aquí): wifi (¿la red "ElPuente_Free" está cargada?), baños, cajeros, tarifas del parqueadero.