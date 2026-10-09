# Kit OKF v0.2 para ingeniería de datos

Plantillas, prompts de GitHub Copilot, un bundle de ejemplo y un validador para documentar fuentes (archivos planos, tablas SQL Server), ETL (SSIS) y procesos `.bat` en el **Open Knowledge Format v0.2**.

Está basado en la spec oficial: [`GoogleCloudPlatform/open-knowledge-format`](https://github.com/GoogleCloudPlatform/open-knowledge-format) (`SPEC.md`, v0.2, que es la última versión publicada). No requiere instalar nada más que Python y PyYAML.

## Contenido

| Ruta | Para qué |
|---|---|
| `plantillas/` | Un esqueleto por tipo: `sql-server-table`, `flat-file`, `ssis-package`, `batch-job`, `playbook`. |
| `ejemplo/` | Bundle completo y ficticio del flujo archivo -> staging -> DW, con SSIS, `.bat` y playbook. |
| `herramientas/okf.py` | `validar` (conformidad y secretos) e `indices` (genera los `index.md`). |
| `.github/` | Instrucciones y prompt para Copilot. Se copian a la raíz del repo de trabajo. |

## Cómo usarlo en el trabajo

1. Copia a tu repo: `.github/`, `okf-kit/` y crea la carpeta `knowledge/` (con subcarpetas `tablas`, `archivos`, `ssis`, `bat`, `playbooks`).
2. En Copilot Chat (modo agente) ejecuta `/documentar-objeto` y adjunta el `.dtsx`, el `.bat`, o la salida de metadatos. Los nombres de campos del front matter del prompt (`agent:`) dependen de tu versión de VS Code; si no lo reconoce, usa `mode: agent`.
3. Revisa el concepto. Cuando esté correcto, **una persona** añade `verified: { by: human:<tu-id>, at: <fecha> }` y cambia `status` a `stable`.
4. Antes de cada commit: `python okf-kit/herramientas/okf.py validar knowledge`.
5. Tests del validador: `python -m pytest okf-kit/tests`.

## Metadatos de SQL Server para adjuntar a Copilot

```sql
SELECT c.COLUMN_NAME, c.DATA_TYPE, c.CHARACTER_MAXIMUM_LENGTH,
       c.NUMERIC_PRECISION, c.NUMERIC_SCALE, c.IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS c
WHERE c.TABLE_SCHEMA = '<esquema>' AND c.TABLE_NAME = '<tabla>'
ORDER BY c.ORDINAL_POSITION;
```

Adjunta el resultado como texto. Para PK/FK usa `sys.key_constraints` y `sys.foreign_keys`.

## Reglas clave de la spec v0.2 (resumen)

- Solo `type` es obligatorio; todo lo demás es opcional y la spec exige tolerancia con ello.
- `timestamp` pasó a `generated: { by, at }`. `trust_tier` no existe: la confianza se deriva de `verified` (sin `verified` = no verificado; solo actores no humanos = confirmado por máquina; algún `human:<id>` = revisado por una persona).
- `status`: `draft | stable | deprecated`. Sin `status` equivale a `stable`.
- `stale_after`: instante absoluto a partir del cual el concepto se considera vencido.
- `sources` con `id` + notas al pie `[^id]` reemplazan a la sección `# Citations`.
- El linaje no tiene campo propio: se expresa con enlaces entre conceptos. El tipo de relación va en la prosa.
- `index.md` y `log.md` son nombres reservados. `index.md` no lleva frontmatter, salvo el de la raíz (`okf_version`).

## Lo que este kit NO hace (todavía)

- No extrae hechos de los `.dtsx` o `.bat` con scripts: hoy Copilot lee el archivo directamente. Para paquetes grandes conviene un extractor determinista (XML de SSIS) que redacte credenciales antes de llegar al LLM.
- No detecta documentos desactualizados respecto al código fuente (por ejemplo con un hash en `sources`).
