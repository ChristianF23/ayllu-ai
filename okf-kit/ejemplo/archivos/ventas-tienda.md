---
type: Flat File
title: Ventas de tienda (CSV diario)
description: Archivo CSV diario con una fila por línea de venta, entregado por el sistema de punto de venta de cada tienda.
resource: file://entrada_pos/ventas_YYYYMMDD.csv
tags: [ventas, archivo-plano, pos]
owner: team:pos
generated: { by: github-copilot/ejemplo, at: 2026-10-09T10:00:00Z }
status: draft
sources:
  - id: spec-pos
    resource: file://docs/spec_pos_ventas.pdf
    title: Especificación de interfaz POS-Ventas v3
---

Archivo diario que deja el POS en la carpeta lógica `entrada_pos`. Lo consume el paquete de carga de ventas.

# Formato

| Propiedad | Valor |
|---|---|
| Patrón de nombre | `ventas_YYYYMMDD.csv` |
| Delimitador | `;` |
| Calificador de texto | `"` |
| Encoding | Windows-1252 |
| Fin de línea | CRLF |
| Cabecera | sí |
| Formato de fecha | `dd/MM/yyyy` |
| Separador decimal | `,` |
| Llegada | antes de las 01:30, todos los días |

# Schema

| Posición | Campo | Tipo | Descripción |
|---|---|---|---|
| 1 | `cod_tienda` | texto(10) | Código de la tienda. [^spec-pos] |
| 2 | `fecha_venta` | fecha | Día de la venta. [^spec-pos] |
| 3 | `sku` | texto(20) | Producto vendido. [^spec-pos] |
| 4 | `cantidad` | entero | Unidades; negativo en devoluciones. [^spec-pos] |
| 5 | `monto` | decimal(18,2) | Importe de la línea, sin impuestos. [^spec-pos] |

# Reglas de calidad

- Un archivo de 0 bytes se considera falla del POS, no "día sin ventas".
- No debe haber filas de totales.

# Linaje

Lo lee [Carga_Ventas_Diaria](/ssis/carga-ventas-diaria.md), que lo carga en [staging.ventas](/tablas/staging-ventas.md).

[^spec-pos]: Especificación de interfaz POS-Ventas v3
