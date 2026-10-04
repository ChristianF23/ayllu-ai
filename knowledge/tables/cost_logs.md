---
type: PostgreSQL Table
title: Cost Logs Table
description: Esquema de la tabla donde se registran las interacciones con LLMs, tokens consumidos y costos estimados en USD.
resource: postgresql://ayllu_db/public/cost_logs
tags: [metrics, costs, llm, auditing, postgresql]
timestamp: 2026-10-04T15:00:00Z
generated:
  by: ayllu_schema_generator
  at: 2026-10-04T15:00:00Z
verified:
  by: human_admin
  at: 2026-10-04T15:00:00Z
status: active
trust_tier: verified
---

# Schema Definition

| Column | Type | Description |
|---|---|---|
| `id` | BIGINT | ID primario autoincremental de la transacción. |
| `user_id` | BIGINT | ID numérico de Telegram del usuario que realizó la consulta. |
| `agent_id` | VARCHAR(100) | Identificador del agente que atendió la petición (ej. `orchestrator`). |
| `model_used` | VARCHAR(100) | Modelo de IA invocado (ej. `gpt-4o-mini`). |
| `prompt_tokens` | INTEGER | Cantidad de tokens consumidos en el prompt de entrada. |
| `completion_tokens` | INTEGER | Cantidad de tokens generados en la respuesta. |
| `estimated_cost_usd` | NUMERIC(10,6) | Costo financiero estimado en USD según LiteLLM. |
| `created_at` | TIMESTAMPTZ | Fecha y hora exacta (UTC) en que se guardó el registro. |

# Relaciones y Enlaces
- Utilizado para calcular la métrica [Daily Cost](/metrics/daily_cost.md).