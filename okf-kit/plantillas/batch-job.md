---
type: Batch Job
title: "<nombre del .bat sin extensión>"
description: "<UNA frase: qué orquesta y cuándo corre>"
resource: file://<RUTA_LOGICA>/<nombre>.bat
tags: [bat, <dominio>, orquestacion]
owner: team:<equipo>
schedule: "<cuándo y quién lo dispara: Programador de tareas / SQL Agent / manual>"
generated: { by: github-copilot/<modelo>, at: <AAAA-MM-DDThh:mm:ssZ> }
status: draft
sources:
  - id: script
    resource: file://<RUTA_LOGICA>/<nombre>.bat
    title: Script <nombre>.bat
    last_modified: <AAAA-MM-DDThh:mm:ssZ>
---

<!-- Qué proceso de negocio ejecuta y qué deja listo al terminar. -->

# Pasos

1. `<comando redactado, sin credenciales>`: <qué hace>. [^script]
2. `dtexec /F <paquete>.dtsx`: ejecuta [<paquete>](/ssis/<p>.md).

# Parámetros y variables de entorno

| Nombre | Valor / origen | Uso |
|---|---|---|
| `%1` | <ej. fecha de proceso AAAAMMDD> | <uso> |

# Códigos de salida y logs

- `ERRORLEVEL` <n>: <significado>. Log en `<ruta lógica>`.

# Dependencias y reproceso

- Requiere que antes haya corrido [<proceso previo>](/bat/<b>.md).
- ¿Es idempotente? <sí/no/desconocido>. Para reprocesar ver [<playbook>](/playbooks/<p>.md).

[^script]: Script <nombre>.bat
