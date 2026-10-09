---
type: SSIS Package
title: Carga_Ventas_Diaria
description: Carga el CSV diario de ventas del POS a staging y luego al hecho de ventas del DW.
resource: ssis://ProyectoVentas/Carga_Ventas_Diaria.dtsx
tags: [ssis, ventas, diario]
owner: team:datos-ventas
generated: { by: github-copilot/ejemplo, at: 2026-10-09T10:00:00Z }
status: draft
sources:
  - id: dtsx
    resource: ssis://ProyectoVentas/Carga_Ventas_Diaria.dtsx
    title: Paquete Carga_Ventas_Diaria.dtsx
    last_modified: 2026-09-15T00:00:00Z
---

Mueve las ventas del día desde el archivo del POS hasta el DW en dos saltos (archivo -> staging -> DW).

# Flujo

1. **Truncar staging** (Execute SQL): vacía [staging.ventas](/tablas/staging-ventas.md). [^dtsx]
2. **Cargar CSV** (Data Flow): lee [ventas_YYYYMMDD.csv](/archivos/ventas-tienda.md), convierte fechas y decimales al formato SQL Server y escribe en staging. [^dtsx]
3. **Borrar día en DW** (Execute SQL): elimina de [dw.fact_ventas](/tablas/dw-fact-ventas.md) las filas de la fecha en proceso. [^dtsx]
4. **Cargar hecho** (Data Flow): resuelve `sk_tienda` y `sk_producto` con lookups y escribe en el DW. [^dtsx]

# Parámetros y conexiones

| Nombre | Tipo | Para qué sirve |
|---|---|---|
| `$Project::FechaProceso` | Parámetro | Día a cargar (AAAAMMDD). |
| `cm_dwh` | Conexión OLE DB | Servidor lógico DWH_PROD. |
| `cm_csv_ventas` | Conexión Flat File | Carpeta lógica `entrada_pos`. |

# Manejo de errores

- Las filas sin coincidencia en los lookups van a la tabla `staging.ventas_rechazadas`; el paquete no falla.

# Linaje

Lo dispara [run_ventas](/bat/run-ventas.md).

[^dtsx]: Paquete Carga_Ventas_Diaria.dtsx
