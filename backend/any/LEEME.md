# Any 2.0 — guía de mantenimiento

Any 2.0 vive entera en `backend/any/`. No importa nada del bot viejo (orchestrator, ai, rag, category_search, webhook). Solo comparte la base de datos (`models/`), el envío por WhatsApp (`services/whatsapp.py`) y el login del panel (`routers/auth.py`).

## Recorrido de un mensaje

```
WhatsApp → /any/webhook (entrada.py)
  → harness.procesar()                     nucleo/harness.py
      contexto: historial + estado          nucleo/estado.py
      entrada: pausa humana, privacidad     nucleo/guardias.py
      router: regla de emergencia → IA      nucleo/router.py + prompts/router.md
      flujo: reúne datos en código → IA redacta (con herramientas si le faltan datos)
                                            flujos/<nombre>.py + prompts/flujos/<nombre>.md
      salida: formato, pisos, teléfonos, equidad, emergencia, nunca vacía
      traza → tabla orchestrator_traces (herramienta "any:<flujo>", método "any2")
  → enviar textos y adjuntos               entrada.py
```

## Probar

Desde `backend/`, con `DATABASE_URL` apuntando a una copia de la base (scripts/copiar_bd.py):

| Qué | Comando |
|---|---|
| Pruebas por secciones (sin IA) | `python -m any.evals.pruebas` |
| Banco de conversaciones reales con Groq | `python -m any.evals.correr --reporte reporte.md` |
| Solo un flujo, viendo cada respuesta | `python -m any.evals.correr --flujo servicios_mall --ver` |
| Solo la plomería, sin clave | `python -m any.evals.correr --llm simulado:x` |
| Chat de prueba en el navegador | levantar el backend y abrir `/any/chat` (entra con tu usuario del panel) |

El chat de prueba muestra el recorrido completo de cada respuesta: flujo, decisión del router, datos reunidos, herramientas, alertas de las guardias, tiempo y tokens. El campo "Fecha simulada" permite probar otro día (por ejemplo, para ver los eventos de esa semana).

## Cambiar de modelo

Variables de entorno con formato `proveedor:modelo` (proveedores: `groq`, `openai`, `anthropic`, `gemini`, `deepseek`, `local`, `simulado`):

```
ANY_LLM_ROUTER=groq:openai/gpt-oss-120b        # quién decide el flujo
ANY_LLM_FLUJOS=groq:openai/gpt-oss-120b        # quién redacta
ANY_LLM_FLUJO_LOCALES=openai:gpt-5-mini        # opcional: un modelo solo para un flujo
ANY_LLM_RESPALDO=anthropic:claude-haiku-5-5    # opcional: si el principal falla
GROQ_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY / GEMINI_API_KEY / DEEPSEEK_API_KEY
```

Otras: `ANY_HISTORIAL` (12), `ANY_SESION_HORAS` (4), `ANY_MAX_VUELTAS` (4), `ANY_TIMEOUT_LLM` (25), `META_APP_SECRET` (valida la firma de Meta), `ANY_VERIFY_TOKEN` (si no está, usa `VERIFY_TOKEN`), `ANY_PRUEBA_ABIERTA=1` (solo local: `/any/prueba` sin login).

## Agregar o arreglar un flujo

1. `flujos/<nombre>.py`: una clase `Flujo` con `nombre`, `descripcion` (la lee el router), `reunir(ctx)` (datos verificados, en código) y, si hace falta, `herramientas(ctx)` (de 0 a 4, que devuelvan datos).
2. `prompts/flujos/<nombre>.md`: qué hace el especialista en ese turno.
3. Registrarlo en `flujos/__init__.py` (y quitarlo de `PENDIENTES`).
4. Casos en `evals/casos/*.yaml` y correr el banco solo para ese flujo.

Regla de oro: los datos se reúnen en código y se prueban solos; la IA solo redacta con esos datos. Un dato que no está en los datos no se dice.

## Textos que se editan sin tocar código

- `prompts/persona.md`: la personalidad y las reglas del mall (una sola persona para todo).
- `datos/mensajes.yaml`: aviso de la Ley 1581, borrado de datos, error técnico, emergencia, frases de emergencia.
- `datos/sinonimos.yaml`: sinónimos de búsqueda (por palabra completa).

En la fase 7 todo esto pasa a editarse desde el panel, con versiones.

## Tablas propias

`any_estado` (flujo activo y de qué se habló), `any_mensajes_vistos` (deduplicación) y `any_aviso_privacidad`. Se crean solas la primera vez. El historial se guarda en la tabla compartida `conversations` (session_id `any2`), así el panel lo sigue mostrando.

## Antes de apuntar Meta a /any/webhook (fase 6)

- Agregar `"/any/webhook"` a `RUTAS_EXENTAS` en `services/seguridad.py`; si no, el límite de 120 peticiones por minuto por IP puede frenar a Meta.
- Configurar `META_APP_SECRET`.
- En Meta, cambiar la URL del webhook de `/webhook` a `/any/webhook`. Para volver atrás basta con cambiarla de nuevo.
