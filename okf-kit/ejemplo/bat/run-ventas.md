---
type: Batch Job
title: run_ventas
description: "Orquesta la carga diaria de ventas: valida que llegó el archivo y ejecuta el paquete SSIS."
resource: file://scripts/run_ventas.bat
tags: [bat, ventas, orquestacion]
owner: team:datos-ventas
schedule: "Programador de tareas, todos los días 02:00"
generated: { by: github-copilot/ejemplo, at: 2026-10-09T10:00:00Z }
status: draft
sources:
  - id: script
    resource: file://scripts/run_ventas.bat
    title: Script run_ventas.bat
    last_modified: 2026-09-20T00:00:00Z
---

Deja las ventas del día anterior cargadas en el DW antes de que corran los reportes de la mañana.

# Pasos

1. `if not exist entrada_pos\ventas_%FECHA%.csv exit /b 2`: aborta si no llegó el archivo. [^script]
2. `dtexec /F Carga_Ventas_Diaria.dtsx /Par $Project::FechaProceso;%FECHA%`: ejecuta [Carga_Ventas_Diaria](/ssis/carga-ventas-diaria.md). [^script]
3. Escribe el resultado en `logs\run_ventas_%FECHA%.log`. [^script]

# Parámetros y variables de entorno

| Nombre | Valor / origen | Uso |
|---|---|---|
| `%FECHA%` | Ayer, AAAAMMDD, calculado en el script | Día a procesar. |

# Códigos de salida y logs

- `2`: no llegó el archivo. `1`: falló el paquete. `0`: ok.

# Dependencias y reproceso

- Idempotente: el paquete borra el día antes de insertarlo.
- Para reprocesar un día ver [Ventas no cargaron](/playbooks/ventas-no-cargaron.md).

[^script]: Script run_ventas.bat
