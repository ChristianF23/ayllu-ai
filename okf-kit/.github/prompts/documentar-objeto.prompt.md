---
description: Documenta un objeto de datos (tabla, archivo plano, paquete SSIS o .bat) como concepto OKF v0.2.
agent: agent
---

Documenta el objeto que te indico como un concepto OKF v0.2 en `knowledge/`.

Objeto: ${input:objeto:ruta del .dtsx/.bat, esquema.tabla, o nombre del archivo plano}
Tipo: ${input:tipo:SQL Server Table | Flat File | SSIS Package | Batch Job}

## Flujo (en este orden)

1. Si ya existe un concepto para este objeto en `knowledge/`, léelo y refínalo en vez de reescribirlo. Respeta lo que ya tenga `verified`.
2. Lee la fuente real: el `.dtsx`/`.bat`, o el resultado de metadatos que te adjunté en el chat. No documentes de memoria.
3. Abre la plantilla `okf-kit/plantillas/` que corresponde al tipo y úsala como esqueleto. Mira `okf-kit/ejemplo/` para ver el nivel de detalle esperado.
4. Revisa qué otros conceptos existen en `knowledge/` y enlaza solo a los que existan. Si el objeto lee o escribe algo que aún no está documentado, menciónalo al final de tu respuesta como pendiente.
5. Escribe UN archivo: `knowledge/<carpeta>/<nombre-en-minusculas-con-guiones>.md`. Carpetas: `tablas`, `archivos`, `ssis`, `bat`, `playbooks`.
6. Ejecuta `python okf-kit/herramientas/okf.py validar knowledge`, corrige los errores y luego `python okf-kit/herramientas/okf.py indices knowledge`.

## Reglas de contenido

- Sigue `.github/instructions/okf.instructions.md`.
- Redacta credenciales y cadenas de conexión antes de escribir cualquier cosa.
- Lo que no esté en la fuente va como `TODO(humano): ...`; no lo inventes. Esto aplica sobre todo a dueño, horario, significado de negocio y qué hacer si falla.
- No pegues, en el concepto ni en tu respuesta, filas reales de datos.

## Tu respuesta final

Solo tres cosas, en viñetas: archivo creado o modificado, lista de `TODO(humano)` pendientes, y conceptos enlazados que aún no existen.
