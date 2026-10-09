---
type: SQL Server Table
title: "<nombre legible, ej. Ventas diarias en staging>"
description: "<UNA frase: qué contiene y el grano (una fila por ...)>"
resource: mssql://<SERVIDOR_LOGICO>/<BaseDatos>/<esquema>/<tabla>
tags: [<dominio>, <capa: staging|dw|mart>]
owner: team:<equipo>
generated: { by: github-copilot/<modelo>, at: <AAAA-MM-DDThh:mm:ssZ> }
status: draft
sources:
  - id: metadatos
    resource: mssql://<SERVIDOR_LOGICO>/<BaseDatos>/INFORMATION_SCHEMA.COLUMNS
    title: Metadatos de columnas
---

<!-- 1-3 párrafos: qué representa la tabla, grano, rango de fechas, si se trunca o acumula. -->

# Schema

| Columna | Tipo | Nulo | Descripción |
|---|---|---|---|
| `<col>` | <tipo SQL Server exacto, ej. NVARCHAR(50)> | <sí/no> | <qué es; valores permitidos si se conocen> [^metadatos] |

# Claves y particiones

- **PK:** `<cols>`
- **FK:** `<col>` -> [<otra tabla>](/tablas/<archivo>.md)
- **Índices / particiones:** <solo si están en los metadatos>

# Linaje

<!-- El tipo de relación va en la prosa; el enlace solo expresa que existe. -->
Se carga con [<paquete SSIS>](/ssis/<archivo>.md). La consumen [<otra tabla o proceso>](/tablas/<archivo>.md).

# Notas para consumidores

- <reglas de negocio, trampas del grano, columnas obsoletas. Solo lo comprobable.>

[^metadatos]: Metadatos de columnas
