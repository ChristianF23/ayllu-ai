---
type: Flat File
title: "<nombre legible del archivo, ej. Ventas de tienda (CSV diario)>"
description: "<UNA frase: qué contiene, quién lo entrega y el grano>"
resource: file://<RUTA_LOGICA>/<patron_nombre>
tags: [<dominio>, archivo-plano, <sistema origen>]
owner: team:<equipo que lo entrega>
generated: { by: github-copilot/<modelo>, at: <AAAA-MM-DDThh:mm:ssZ> }
status: draft
sources:
  - id: muestra
    resource: <ruta de la especificación o del archivo de muestra revisado>
    title: <especificación / muestra>
---

<!-- Qué es, quién lo genera y para qué se usa. Nunca pegar filas reales: solo estructura. -->

# Formato

| Propiedad | Valor |
|---|---|
| Patrón de nombre | `<ventas_YYYYMMDD.csv>` |
| Delimitador | `<,>` |
| Calificador de texto | `<">` |
| Encoding | `<UTF-8 / Windows-1252>` |
| Fin de línea | `<CRLF / LF>` |
| Cabecera | <sí/no> |
| Formato de fecha | `<yyyy-MM-dd>` |
| Separador decimal | `<.>` |
| Llegada | <hora y frecuencia esperadas> |

# Schema

| Posición | Campo | Tipo | Descripción |
|---|---|---|---|
| 1 | `<campo>` | <tipo lógico> | <significado, valores permitidos> [^muestra] |

# Reglas de calidad

- <vacío permitido? duplicados? filas de totales? qué pasa si llega 0 bytes>

# Linaje

Lo consume [<paquete SSIS>](/ssis/<archivo>.md), que lo carga en [<tabla staging>](/tablas/<archivo>.md).

[^muestra]: <especificación / muestra>
