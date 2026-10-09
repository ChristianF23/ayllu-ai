---
type: SQL Server Table
title: Ventas diarias en staging
description: Copia sin transformar del archivo diario de ventas del POS; una fila por línea de venta.
resource: mssql://DWH_PROD/Staging/staging/ventas
tags: [ventas, staging]
owner: team:datos-ventas
generated: { by: github-copilot/ejemplo, at: 2026-10-09T10:00:00Z }
status: draft
sources:
  - id: metadatos
    resource: mssql://DWH_PROD/Staging/INFORMATION_SCHEMA.COLUMNS
    title: Metadatos de columnas
---

Tabla de paso: se trunca al inicio de cada carga y solo contiene el día en proceso.[^metadatos]

# Schema

| Columna | Tipo | Nulo | Descripción |
|---|---|---|---|
| `cod_tienda` | NVARCHAR(10) | no | Código de tienda tal como llega. [^metadatos] |
| `fecha_venta` | DATE | no | Día de la venta. [^metadatos] |
| `sku` | NVARCHAR(20) | no | Producto. [^metadatos] |
| `cantidad` | INT | no | Unidades; negativas en devoluciones. [^metadatos] |
| `monto` | DECIMAL(18,2) | no | Importe de la línea sin impuestos. [^metadatos] |

# Claves y particiones

- **PK:** ninguna (tabla de paso).

# Linaje

La carga [Carga_Ventas_Diaria](/ssis/carga-ventas-diaria.md) la llena desde [ventas_YYYYMMDD.csv](/archivos/ventas-tienda.md) y de ella se alimenta [dw.fact_ventas](/tablas/dw-fact-ventas.md).

[^metadatos]: Metadatos de columnas
