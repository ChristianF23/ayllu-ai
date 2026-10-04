---
type: Runbook
title: DB Inspector Runbook
description: Procedimiento operativo seguro pre-aprobado para inspeccionar la cantidad de registros en las tablas del sistema sin escribir SQL manual.
tags: [runbook, database, inspection, safe]
timestamp: 2026-10-04T15:00:00Z
status: active
trust_tier: verified
---

# Descripción del Runbook
Permite obtener de forma segura el recuento de filas en tablas permitidas (`cost_logs`, `users_whitelist`).

# Función en Código
- **Módulo:** `runbooks.db_inspector`
- **Función:** `runbook_inspect_table_count(table_name: str)`
- **Tablas Permitidas:** `cost_logs`, `users_whitelist`