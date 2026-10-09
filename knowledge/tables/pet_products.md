---
type: PostgreSQL Table
title: Pet Products Table
description: Vínculo explícito mascota-producto que define qué come o usa cada mascota; el agente lo lee con productos_de_mascota.
resource: postgresql://ayllu_db/public/pet_products
tags: [pets, products, mascotas, postgresql]
timestamp: 2026-10-09T00:00:00Z
status: draft
---

# Schema Definition

| Column | Type | Description |
|---|---|---|
| `pet_id` | BIGINT NOT NULL, FK `pets(id)` | Mascota. |
| `product_id` | BIGINT NOT NULL, FK `products(id)` | Producto. |
| `is_active` | BOOLEAN, default TRUE | Si el vínculo está vigente. |
| `created_at` | TIMESTAMPTZ | Fecha del vínculo. |

Clave primaria: (`pet_id`, `product_id`).

# Reglas de negocio
- Escribe solo el usuario, por código (`utils/pets.py`: `link_product`, `unlink_product`, vía `scripts/cargar_producto.py asignar`/`desasignar`). Nunca el LLM.
- Vincular exige mascota activa y producto activo de tienda activa; reactiva solo el vínculo, nunca la mascota ni el producto. Desvincular marca `is_active = FALSE` y no exige que nada esté activo (siempre se puede limpiar un vínculo).
- Desactivar un producto (`deactivate_product`) desactiva también sus vínculos; si luego se reactiva con `add_product`, para recuperarlos hay que volver a `asignar`.
- "Compra comida para Milu" se resuelve con este vínculo, no por texto libre: `products_for_pet` (solo lectura) devuelve los productos con vínculo activo, activos y de tiendas activas, del más barato al más caro (máximo 10).
- Si la mascota no existe o no tiene productos, el agente lo dice y no sustituye por una búsqueda sin avisar.

# Relaciones y Enlaces
- Mascota: [Pets](/tables/pets.md).
- Producto: [Products](/tables/products.md).
