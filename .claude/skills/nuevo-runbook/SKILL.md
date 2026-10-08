---
name: nuevo-runbook
description: Crea un runbook nuevo de Ayllu AI (acción pre-aprobada y segura) con su código, concepto OKF, ruta en el orquestador y tests. Úsalo cuando se pida agregar una acción que el bot pueda ejecutar sin escribir código libre.
---

# Crear un runbook

Un runbook es una función `async` fija, escrita y revisada por una persona, que el orquestador puede invocar. Es la alternativa segura a ejecutar código libre: el LLM elige *cuál* runbook y con *qué* parámetro, pero no cambia lo que hace. El modelo es `runbooks/db_inspector.py`; léelo primero.

## Antes de escribir código, define

- **Nombre** del runbook y qué hace en una frase.
- **Parámetros** y la **lista permitida** de valores válidos para cada uno. Si un parámetro puede ser cualquier cosa, no es un runbook seguro.
- **Que no gaste dinero ni escriba datos.** Un runbook de solo lectura es el caso normal. Si el pedido implica gasto, detente y consulta: requiere aprobación humana en Telegram y límites aplicados en código.

## Pasos

1. **Código** en `runbooks/<nombre>.py`, con el mismo patrón que `db_inspector`:
   - `logger = logging.getLogger("AylluRunbook...")`.
   - Función `async def runbook_<nombre>(...) -> Dict[str, Any]`.
   - Valida cada parámetro contra su lista permitida **antes** de usarlo; si no está, devuelve `{"status": "denied", "message": ...}`.
   - Si usa la base de datos, revisa `db.DB_POOL is None` y devuelve `{"status": "error", ...}`. Nunca construyas SQL con texto que no salga de la lista permitida.
   - Devuelve siempre un diccionario con `status` en `success`, `denied` o `error`.
2. **Ruta en el orquestador**: en `agents/orchestrator.py`, `process_request` enruta por palabras clave. Agrega la rama del runbook con el mismo formato de respuesta (`status`, `response`, `model_used`, `usage` en cero) y el cambio más pequeño posible.
3. **Concepto OKF** en `knowledge/runbooks/<nombre>.md`, siguiendo la skill `nuevo-concepto-okf`.
4. **Tests** en `tests/test_runbook_<nombre>.py` (pytest, ver `tests/test_sandbox.py`). Como mínimo:
   - un valor fuera de la lista permitida devuelve `denied`;
   - sin pool de base de datos devuelve `error`;
   - el camino exitoso, con la base simulada o con el marcador `@pytest.mark.db`.
5. **Corre los tests** dentro del contenedor y reporta el resultado real: `docker exec ayllu_app python -m pytest -q`.

## Reparto de trabajo

Si trabajas desde la sesión principal, delega: `dev` escribe el código y la ruta, `tester` los tests y `docs` el concepto. Después pasa el diff por `reviewer`. No hagas `git push`.

## No hagas

- Leer o imprimir `.env`.
- Aceptar SQL, rutas de archivo o comandos como parámetro.
- Dejar que el runbook llame a internet o a un servicio de pago sin aprobación humana.
