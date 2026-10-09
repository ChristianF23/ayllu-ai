---
type: PostgreSQL Table
title: Allowed Stores Table
description: Lista de dominios de tiendas permitidas para el catálogo y la búsqueda de productos.
resource: postgresql://ayllu_db/public/allowed_stores
tags: [catalog, stores, allowlist, security, postgresql]
timestamp: 2026-10-09T00:00:00Z
status: draft
---

# Schema Definition

| Column | Type | Description |
|---|---|---|
| `domain` | VARCHAR(255) PRIMARY KEY | Dominio normalizado (minúsculas, sin punto final). |
| `is_active` | BOOLEAN, default TRUE | Si la tienda está habilitada. |
| `created_at` | TIMESTAMPTZ | Fecha de alta. |

# Reglas de negocio
- Semilla al arrancar: `mercadolibre.com.co`. Es idempotente y no reactiva una tienda desactivada por el usuario.
- La edita solo el usuario; nunca se expone como herramienta al LLM.
- `utils/domain_allowlist.py` valida en código: `normalize_domain` rechaza IPs literales, esquemas, puertos y etiquetas inválidas; `is_url_allowed` exige https, sin credenciales, puerto ausente o 443, y host igual al dominio o subdominio suyo. Falla cerrado.
- Un producto de una tienda inactiva no aparece en búsquedas ni puede agregarse.

# Relaciones y Enlaces
- Referenciada por [Products](/tables/products.md).
