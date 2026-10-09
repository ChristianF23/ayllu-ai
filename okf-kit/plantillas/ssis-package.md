---
type: SSIS Package
title: "<nombre del paquete sin extensión>"
description: "<UNA frase: qué mueve, de dónde a dónde>"
resource: ssis://<Proyecto>/<Paquete>.dtsx
tags: [ssis, <dominio>, <frecuencia>]
owner: team:<equipo>
generated: { by: github-copilot/<modelo>, at: <AAAA-MM-DDThh:mm:ssZ> }
status: draft
sources:
  - id: dtsx
    resource: ssis://<Proyecto>/<Paquete>.dtsx
    title: Paquete <Paquete>.dtsx
    last_modified: <AAAA-MM-DDThh:mm:ssZ>
---

<!-- Propósito de negocio en 1-2 párrafos. No repetir el flujo detallado. -->

# Flujo

<!-- Tareas en el orden de precedencia real del paquete. -->

1. **<Nombre de la tarea>** (<Execute SQL | Data Flow | Script | File System ...>): <qué hace>. [^dtsx]
2. **<Data Flow>**: lee de [<origen>](/archivos/<a>.md), transforma (<derived columns, lookups, conversiones relevantes>), escribe en [<destino>](/tablas/<t>.md).

# Parámetros y conexiones

<!-- SOLO nombres y propósito. Jamás cadenas de conexión, usuarios ni contraseñas. -->

| Nombre | Tipo | Para qué sirve |
|---|---|---|
| `$Project::<Param>` | Parámetro | <uso> |
| `<ConnMgr>` | Conexión OLE DB / Flat File | <a qué sistema lógico apunta> |

# Manejo de errores

- <rutas de error, redirección de filas, reintentos, qué tabla o archivo recibe los rechazos>

# Linaje

Lee [<fuente>](/archivos/<a>.md). Escribe en [<destino>](/tablas/<t>.md). Lo dispara [<proceso bat>](/bat/<b>.md).

[^dtsx]: Paquete <Paquete>.dtsx
