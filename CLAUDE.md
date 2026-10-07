# Ayllu AI

Bot de Telegram que enruta mensajes a un agente orquestador (LiteLLM, `gpt-4o-mini` con fallback a `gpt-4o`). PostgreSQL guarda la lista blanca de usuarios y los costos. Todo corre con Docker Compose. El idioma del proyecto (código, logs, docs) es español.

## Arquitectura

- `bot/main.py`: entrada de Telegram. Valida la lista blanca, llama al orquestador y registra el costo.
- `agents/orchestrator.py`: elige una ruta por palabras clave (runbook, sandbox con self-healing, chat LLM con contexto OKF).
- `utils/sandbox.py`: ejecuta Python en un subproceso con timeout, en un directorio temporal vacío, con `-I` y un guardia (audit hook) que bloquea abrir archivos fuera de ese directorio. Es defensa en profundidad; la frontera real sería un contenedor aparte sin el volumen del proyecto (pendiente).
- `utils/database.py`: pool asyncpg, tablas `users_whitelist` y `cost_logs`.
- `utils/okf_reader.py` y `knowledge/`: conceptos en Markdown con frontmatter YAML que se inyectan al prompt del sistema.
- `runbooks/`: acciones pre-aprobadas y seguras (ej. `db_inspector`).
- `tests/`: scripts de prueba (no usan pytest todavía).

## Reglas duras

1. **Nunca leer, imprimir ni copiar `.env`.** Contiene tokens y claves. Para saber qué variables existen, pregunta al usuario o lee el código.
2. **Nada de gasto de dinero sin aprobación humana explícita** en Telegram. Los límites (tope por orden, tope mensual, dominios permitidos) se aplican en código, no en el prompt.
3. El LLM nunca recibe datos de tarjetas ni contraseñas.
4. No ejecutar `git push`, `docker compose down -v` ni borrar volúmenes sin pedir permiso.

## Convenciones

- Código asíncrono en el bot: no usar llamadas bloqueantes dentro de handlers (usar `acompletion`, no `completion`).
- Un `logger` por módulo con nombre `Ayllu...`.
- Cambios pequeños, un commit por paso, mensajes en español.
- Todo cambio de comportamiento lleva un test.

## Equipo de agentes (en `.claude/agents/`)

- `dev`: implementa un cambio acotado.
- `tester`: escribe y ejecuta tests; solo edita dentro de `tests/`.
- `docs`: mantiene `CLAUDE.md`, README y `knowledge/`; solo edita Markdown.

La sesión principal coordina: divide la tarea, delega, revisa los diffs y hace los commits.

## Hoja de ruta

Misión 1: automatizar la compra de comida de la gata con aprobación humana. Fases: 0 base segura (sandbox, async), 1 búsqueda con tool calling, 2 órdenes con aprobación, 3 ejecución de compra, 4 recurrencia, alertas y evals.
