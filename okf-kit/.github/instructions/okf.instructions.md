---
applyTo: "knowledge/**/*.md"
---

# Reglas para escribir conceptos OKF v0.2

Aplican a los conceptos. **No** a `index.md` ni `log.md`: los índices no llevan frontmatter (salvo `okf_version` en la raíz) y se generan con la herramienta.

Un concepto es un `.md` con frontmatter YAML y cuerpo Markdown. Escribe en español. Los nombres de campos YAML van en inglés, tal como los define la spec.

## Frontmatter

- `type` es el único campo obligatorio. Usa estos valores: `SQL Server Table`, `Flat File`, `SSIS Package`, `Batch Job`, `Playbook`, `Metric`, `Reference`.
- Siempre incluye `title`, `description` (UNA frase), `resource` y `tags` cuando apliquen.
- Si un valor contiene `: ` (dos puntos y espacio), ponlo entre comillas dobles. Si no, el YAML queda inválido.
- Todas las fechas son ISO 8601 con zona: `2026-10-09T14:30:00Z`. No uses `timestamp`.
- `generated: { by: github-copilot/<modelo>, at: <fecha> }` es obligatorio en todo lo que escribas.
- `status` solo puede ser `draft`, `stable` o `deprecated`. Todo concepto nuevo nace en `draft`. Nunca uses `active`.
- NUNCA escribas `verified` ni uses un actor `human:...` en `generated.by` de lo que redactas tú: `human:` es solo para lo que escribió o confirmó una persona. Solo una persona confirma contenido. Si el concepto ya tiene `verified` y tú cambias el contenido, déjalo tal cual y avisa en tu respuesta que requiere re-verificación.
- No existe `trust_tier`: el nivel de confianza se deriva de `verified`.

## Procedencia

- Cada archivo, paquete o consulta de donde sacas datos va en `sources` con `id` estable, `resource` y `title`.
- Para respaldar una afirmación concreta, termina la frase con una nota al pie `[^id]` cuyo `id` exista en `sources`, y define `[^id]: <título>` al final.
- No agregues una sección `# Citations`.

## Cuerpo

- Usa estos encabezados cuando apliquen: `# Schema`, `# Linaje`, `# Notas para consumidores`.
- Describe solo lo que está en los datos que recibiste. Lo que no puedas comprobar, déjalo fuera o escribe `TODO(humano): <qué falta>`. Nunca inventes columnas, horarios, dueños ni reglas de negocio.
- Sé breve: el cuerpo se paga en tokens cada vez que un agente lo lee.

## Enlaces entre conceptos

- Usa enlaces absolutos desde la raíz del bundle: `[texto](/tablas/staging-ventas.md)`.
- El tipo de relación (lee, escribe, dispara, depende de) va en la prosa de la frase, no en el enlace.
- Enlaza solo a conceptos que existan. Si el destino no existe aún, avísalo en tu respuesta.
- No enlaces desde encabezados ni desde bloques de código.

## Prohibido

- Contraseñas, usuarios, tokens, cadenas de conexión completas, rutas con credenciales. Si el origen los trae, escribe `***` o solo el nombre lógico (`DWH_PROD`).
- Filas reales de datos. Documenta la estructura, no el contenido.
- Nombres `index.md` y `log.md` para conceptos: están reservados. Los índices los genera `okf-kit/herramientas/okf.py indices`.

## Antes de terminar

Ejecuta `python okf-kit/herramientas/okf.py validar knowledge` y corrige todos los errores.
