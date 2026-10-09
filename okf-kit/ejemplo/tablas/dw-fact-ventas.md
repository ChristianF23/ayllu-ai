---
type: SQL Server Table
title: Hecho de ventas
description: Una fila por línea de venta con la clave de tienda y producto ya resueltas; base de los reportes de ventas.
resource: mssql://DWH_PROD/DW/dw/fact_ventas
tags: [ventas, dw]
owner: team:datos-ventas
generated: { by: github-copilot/ejemplo, at: 2026-10-09T10:00:00Z }
verified: { by: human:ejemplo, at: 2026-10-09T15:00:00Z }
status: stable
stale_after: 2027-04-09T00:00:00Z
sources:
  - id: metadatos
    resource: mssql://DWH_PROD/DW/INFORMATION_SCHEMA.COLUMNS
    title: Metadatos de columnas
---

Acumula todas las ventas desde 2022. Se inserta por día y es idempotente: la carga borra el día antes de insertarlo.[^metadatos]

# Schema

| Columna | Tipo | Nulo | Descripción |
|---|---|---|---|
| `sk_tienda` | INT | no | Clave sustituta de tienda. [^metadatos] |
| `sk_producto` | INT | no | Clave sustituta de producto. [^metadatos] |
| `fecha_venta` | DATE | no | Día de la venta. [^metadatos] |
| `cantidad` | INT | no | Unidades. [^metadatos] |
| `monto` | DECIMAL(18,2) | no | Importe sin impuestos. [^metadatos] |

# Claves y particiones

- **PK:** (`sk_tienda`, `sk_producto`, `fecha_venta`)

# Linaje

Se carga desde [staging.ventas](/tablas/staging-ventas.md) con [Carga_Ventas_Diaria](/ssis/carga-ventas-diaria.md).

[^metadatos]: Metadatos de columnas
