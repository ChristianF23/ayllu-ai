---
type: Playbook
title: Ventas no cargaron
description: Qué hacer cuando la carga diaria de ventas falla o el reporte de la mañana está vacío.
tags: [playbook, ventas]
generated: { by: human:ejemplo, at: 2026-10-09T09:00:00Z }
status: draft
---

# Disparador

Código de salida distinto de 0 en [run_ventas](/bat/run-ventas.md), o el reporte de ventas sin datos del día anterior.

# Impacto

[dw.fact_ventas](/tablas/dw-fact-ventas.md) queda sin el día; los reportes de ventas muestran cero.

# Pasos

1. Revisar `logs\run_ventas_AAAAMMDD.log` y el código de salida.
2. Si el código es `2`, confirmar con el equipo POS que entregó [el archivo](/archivos/ventas-tienda.md).
3. Reejecutar `run_ventas.bat` con la fecha faltante; es idempotente.
4. Comprobar que `dw.fact_ventas` tiene filas para esa fecha.

# Escalamiento

Si el archivo no llega antes de las 07:00, avisar a `team:pos` y a `team:datos-ventas`.
