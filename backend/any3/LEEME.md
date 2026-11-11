# Any 3.0 — el agente

Vive al lado de Any 2.0 sin cambiarla. Solo atiende los números de `ANY3_NUMEROS` (por defecto 3154559242).
Si cualquier cosa de Any 3.0 falla, responde Any 2.0: el cliente nunca se queda sin respuesta.

## Cómo piensa
1. **Cerebro** — lee el directorio COMPLETO (137 locales con lo que venden, la Torre, la información oficial,
   eventos, sorteos y promociones) más la conversación, y elige por ID qué responde la pregunta. No depende de
   que una palabra coincida: entiende "gomistas", "lavar el carro", "zapatos para dama", "la de la barra".
   El código descarta cualquier ID que no exista (no puede inventar locales).
2. **Datos** — el código arma las fichas y listas con teléfonos, WhatsApp, Instagram, cartas y fotos reales
   (las mismas de Any 2.0).
3. **Redactor** — escribe con los prompts de Any 2.0, solo con esos datos. Las listas las pone el código.
4. **Vigilante** — otra IA revisa la respuesta terminada contra los datos: si inventa, contradice, no responde,
   niega lo que sí hay o mete locales que no son → quita esos locales, o reescribe una vez, o usa la respuesta
   armada por código.
5. Guardias de salida de Any 2.0 (números, precios, fechas inventadas, número de la gerente…).

Cine, domicilios, quejas/emergencias, administración, fotos que manda el cliente y un pedido a medias los
responde Any 2.0 igual que hoy.

## Variables (Railway)
| Variable | Para qué | Por defecto |
|---|---|---|
| `ANTHROPIC_API_KEY` | usar Claude (recomendado) | — (sin ella usa Groq) |
| `ANY3_NUMEROS` | quién la usa: números con coma, `todos` o `ninguno` | `3154559242` |
| `ANY3_LLM` | modelo del cerebro y del redactor | Claude Haiku si hay clave; si no, Groq |
| `ANY3_LLM_VIGILANTE` | modelo del vigilante | el mismo |
| `ANY3_LLM_RESPALDO` | si el modelo principal falla | Groq gpt-oss-120b |
| `ANY3_VIGILANTE` | `0` apaga la revisión | encendido |

## Rutas
- `GET /any3/estado` — si está activa, a quién atiende, qué modelo usa.
- `GET /any3/chat` — chat de prueba con Any 3.0 (sesión del panel).
- `POST /any3/examen?modelo=…` y `GET /any3/examen` — examen del cerebro con preguntas reales.
- `GET /any3/vacios` — lo que preguntaron y no estaba en la base (datos por completar).

## Pruebas
- `python -m any3.pruebas <base.db>` — plomería sin clave (modelo simulado).
- `python -m any3.examen` — calidad con un modelo real.
