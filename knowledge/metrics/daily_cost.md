---
type: Metric
title: Daily Cost USD
description: Regla de negocio y consulta SQL canónica para obtener el total de peticiones, tokens y costo en USD acumulado en el día actual en UTC.
tags: [billing, daily, metrics, sql]
timestamp: 2026-10-04T15:00:00Z
status: active
trust_tier: verified
---

# Definición de la Métrica
Calcula el consumo financiero total diario sumando el campo `estimated_cost_usd` de la tabla [cost_logs](/tables/cost_logs.md).

# SQL Canonical Query
```sql
SELECT 
    COUNT(id) AS total_requests,
    SUM(prompt_tokens + completion_tokens) AS total_tokens,
    COALESCE(SUM(estimated_cost_usd), 0.0) AS total_cost_usd
FROM cost_logs
WHERE created_at >= CURRENT_DATE;