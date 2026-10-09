---
type: PostgreSQL Table
title: Products Table
description: Catálogo propio de productos que mantiene el usuario; el agente solo lo lee con la herramienta buscar_productos.
resource: postgresql://ayllu_db/public/products
tags: [catalog, products, search, postgresql]
timestamp: 2026-10-09T00:00:00Z
status: draft
---

# Schema Definition

| Column | Type | Description |
|---|---|---|
| `id` | BIGSERIAL | ID primario. |
| `name` | VARCHAR(200) NOT NULL | Nombre del producto. |
| `brand` | VARCHAR(100) | Marca (opcional). |
| `price` | NUMERIC(12,2) NOT NULL, CHECK >= 0 | Precio. |
| `currency` | CHAR(3) NOT NULL, default `COP` | Moneda. |
| `url` | TEXT NOT NULL UNIQUE | Enlace al producto en la tienda. |
| `store_domain` | VARCHAR(255) NOT NULL, FK `allowed_stores(domain)` | Tienda. |
| `is_active` | BOOLEAN, default TRUE | Si aparece en búsquedas. |
| `updated_at` | TIMESTAMPTZ | Última modificación. |

# Reglas de negocio
- Escriben solo el usuario, por código (`utils/catalog.py`: `add_product`, `deactivate_product`). Nunca el LLM. Aún no hay comando de Telegram para cargar productos.
- `add_product` valida en código: texto sin caracteres de control ni Unicode invisible, precio > 0, hasta 100000000 y máximo 2 decimales, moneda de 3 letras mayúsculas, URL https de la tienda indicada, tienda existente y activa. Hace upsert por `url`.
- `search_products` (solo lectura) devuelve productos activos de tiendas activas, del más barato al más caro; descarta filas con URL fuera de su tienda o texto invisible.
- El agente consulta con `buscar_productos` (máximo 5 resultados).

# Relaciones y Enlaces
- Tienda: [Allowed Stores](/tables/allowed_stores.md).
