---
name: nuevo-concepto-okf
description: Crea un concepto OKF (Markdown con frontmatter YAML) en knowledge/ siguiendo el formato de los existentes. Úsalo cuando se agregue una tabla, métrica o runbook que el orquestador deba conocer.
---

# Crear un concepto OKF

Un concepto es un archivo `.md` en `knowledge/<categoría>/` que `utils/okf_reader.py` lee al arrancar el bot. Hoy las categorías son `tables/`, `metrics/` y `runbooks/`.

## Pasos

1. **Mira un ejemplo de la misma categoría** (por ejemplo `knowledge/runbooks/db_inspector.md`) y copia su estructura.
2. **Escribe el frontmatter** entre dos líneas `---`. Es obligatorio: sin él el lector descarta el archivo.

   ```yaml
   ---
   type: Runbook            # Runbook, PostgreSQL Table, Metric...
   title: Nombre corto
   description: Una frase que diga para qué sirve.
   tags: [runbook, ejemplo]
   timestamp: 2026-01-01T00:00:00Z   # fecha real de creación, ISO 8601
   status: draft            # draft hasta que alguien lo revise
   trust_tier: verified     # ver nota abajo
   ---
   ```

3. **Escribe el cuerpo en Markdown** describiendo lo que el código hace *de verdad*: léelo antes de documentarlo. Para un runbook: módulo, función, parámetros y valores permitidos. Para una tabla: columnas y tipos tal como están en `utils/database.py`.
4. **Verifica que se carga**: `docker exec ayllu_app python -c "from utils.okf_reader import okf_reader; print(okf_reader.load_bundle())"` debe contar un concepto más.

## Reglas

- **`status`**: el lector solo inyecta al prompt los conceptos con `status: active`. Crea el concepto como `draft` y pásalo a `active` cuando una persona lo haya revisado.
- **`trust_tier: verified`** significa que una persona confirmó el contenido. Si nadie lo ha revisado, no lo pongas.
- **Nunca incluyas secretos**: ni contenido de `.env`, ni tokens, ni contraseñas. Todo lo que está en `knowledge/` puede terminar en un prompt del LLM.
- **El cuerpo es lo que paga tokens en cada mensaje.** Sé breve y no repitas lo que ya dice el código.
- Escribe en español.
