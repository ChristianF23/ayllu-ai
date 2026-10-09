# Ayllu AI

Bot de Telegram que enruta mensajes a un agente orquestador (LiteLLM, `gpt-4o-mini` con fallback a `gpt-4o`). PostgreSQL guarda la lista blanca de usuarios y los costos. Todo corre con Docker Compose. El idioma del proyecto (código, logs, docs) es español.

## Arquitectura

- `bot/main.py`: entrada de Telegram. Valida la lista blanca, llama al orquestador y registra el costo.
- `agents/orchestrator.py`: elige una ruta por palabras clave (runbook, sandbox con self-healing, chat LLM con contexto OKF).
- `utils/sandbox.py`: motor que ejecuta Python en un subproceso con timeout, en un directorio temporal vacío, con `-I` y un guardia (audit hook) que bloquea abrir archivos fuera de ese directorio. Los tracebacks se corrigen para que las líneas apunten al código del agente.
- `sandbox_server/` + `Dockerfile.sandbox`: servidor HTTP mínimo (`POST /execute`) que corre ese motor en un contenedor aparte (`sandbox`): sin volumen del proyecto, sin `.env`, en la red `sandbox_net` (`internal`, sin internet), sistema de archivos de solo lectura, usuario sin privilegios y límites de memoria, CPU y procesos.
- `utils/sandbox_client.py`: cliente asíncrono que usa el bot (`SANDBOX_URL`). Si el sandbox remoto falla devuelve error y no cae a ejecución local; sin `SANDBOX_URL` (desarrollo/tests) usa el motor local en un hilo.
- `utils/database.py`: pool asyncpg, tablas `users_whitelist`, `cost_logs`, `allowed_stores` (semilla `mercadolibre.com.co`) y `products`.
- `utils/domain_allowlist.py`: normaliza dominios y verifica URLs (https, host en la lista); falla cerrado.
- `utils/catalog.py`: catálogo propio; `search_products` es de solo lectura, `add_product`/`deactivate_product` son solo del usuario (aún sin llamador ni comando de Telegram).
- Herramienta `buscar_productos` en el orquestador: tool calling de solo lectura con límites en código (3 rondas, 3 ejecuciones, 5 resultados); se suma el costo de todas las llamadas y el bot registra el costo parcial si el LLM falla a mitad.
- `utils/okf_reader.py` y `knowledge/`: conceptos en Markdown con frontmatter YAML que se inyectan al prompt del sistema.
- `runbooks/`: acciones pre-aprobadas y seguras (ej. `db_inspector`).
- `tests/`: pytest (`pytest.ini`, `requirements-dev.txt`). Marcadores: `db` (necesita PostgreSQL) y `llm` (gasta crédito; se omite por defecto, usar `-m llm`). Se corren dentro del contenedor: `docker exec ayllu_app python -m pytest`.

## Reglas duras

1. **Nunca leer, imprimir ni copiar `.env`.** Contiene tokens y claves. Para saber qué variables existen, pregunta al usuario o lee el código.
2. **Nada de gasto de dinero sin aprobación humana explícita** en Telegram. Los límites (tope por orden, tope mensual, dominios permitidos) se aplican en código, no en el prompt.
3. El LLM nunca recibe datos de tarjetas ni contraseñas.
4. No ejecutar `git push`, `docker compose down -v` ni borrar volúmenes sin pedir permiso.
5. `add_product`/`deactivate_product` y la lista de tiendas nunca se exponen como herramienta al LLM.

## Convenciones

- Código asíncrono en el bot: no usar llamadas bloqueantes dentro de handlers (usar `acompletion`, no `completion`).
- Un `logger` por módulo con nombre `Ayllu...`.
- Cambios pequeños, un commit por paso, mensajes en español.
- Todo cambio de comportamiento lleva un test.

## Equipo de agentes (en `.claude/agents/`)

- `dev`: implementa un cambio acotado.
- `tester`: escribe y ejecuta tests; solo edita dentro de `tests/`.
- `docs`: mantiene `CLAUDE.md`, README y `knowledge/`; solo edita Markdown.
- `reviewer`: revisa un diff contra estas reglas y reporta; no edita nada (solo lectura).

## Skills (en `.claude/skills/`)

- `nuevo-runbook`: pasos para crear un runbook (código, ruta en el orquestador, concepto OKF y tests).
- `nuevo-concepto-okf`: formato y reglas de un concepto en `knowledge/`.

La sesión principal coordina: divide la tarea, delega, revisa los diffs y hace los commits. Antes de cada commit pasa el diff por `reviewer`.

## Hoja de ruta

Estado: Fase 0 completa; Fase 1 implementada y probada con simulaciones, falta validarla con un LLM real. Fase 1: el scraping de MercadoLibre no es viable (`docs/fase-1-viabilidad-mercadolibre.md`), así que la búsqueda usa un catálogo propio en PostgreSQL. El servicio de búsqueda con internet (`docs/fase-1-egreso-buscador.md`) queda diferido; el proxy de salida se decide antes de la Fase 3. Pendiente: probar `buscar_productos` con un LLM real.

Misión 1: automatizar la compra de comida de la gata con aprobación humana. Fases: 0 base segura (sandbox, async), 1 búsqueda con tool calling, 2 órdenes con aprobación, 3 ejecución de compra, 4 recurrencia, alertas y evals.
