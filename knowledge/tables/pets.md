---
type: PostgreSQL Table
title: Pets Table
description: Mascotas del usuario (ej. una gata); el agente solo las lee con la herramienta productos_de_mascota.
resource: postgresql://ayllu_db/public/pets
tags: [pets, mascotas, postgresql]
timestamp: 2026-10-09T00:00:00Z
status: draft
---

# Schema Definition

| Column | Type | Description |
|---|---|---|
| `id` | BIGSERIAL | ID primario. |
| `name` | VARCHAR(50) NOT NULL | Nombre para mostrar. |
| `name_key` | VARCHAR(50) NOT NULL UNIQUE | Clave normalizada (minúsculas, sin acentos, espacios colapsados): "Milú", "milu" y " MILU " coinciden. |
| `species` | VARCHAR(30) NOT NULL | Especie en minúsculas (ej. `gato`). |
| `is_active` | BOOLEAN, default TRUE | Si el agente puede usarla. |
| `created_at` | TIMESTAMPTZ | Fecha de registro. |

# Reglas de negocio
- Escribe solo el usuario, por código (`utils/pets.py`: `add_pet`, vía `scripts/cargar_producto.py mascota`). Nunca el LLM.
- `add_pet` valida en código: nombre de 1 a 50 caracteres (letras, dígitos, espacio, guion y apóstrofo; sin control ni Unicode invisible), especie de 1 a 30 letras. Si la clave ya existe devuelve ese id y no reactiva una mascota inactiva.
- Por diseño la clave ignora mayúsculas y acentos: "Mía" y "Mia" son la misma mascota (el script `mascota` avisa si ya existía y no cambia su especie). Un nombre en otro alfabeto no se translitera y crea otra mascota.
- No hay semillas: las mascotas reales las carga el usuario.

# Relaciones y Enlaces
- Productos vinculados: [Pet Products](/tables/pet_products.md).
