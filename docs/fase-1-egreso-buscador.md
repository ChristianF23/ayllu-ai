# Fase 1: egreso del buscador de tiendas (diseño)

> **Nota de estado:** la Fase 1 se resolvió con un catálogo propio en PostgreSQL (`products`), no con búsqueda en internet.
> Este diseño queda como referencia para cuando se retome la búsqueda con internet; el proxy de salida se decide antes de la Fase 3.
> `allowed_stores` y `utils/domain_allowlist.py` ya están commiteados.

Estado: propuesta, sin implementar. Base: `docker-compose.yml`, `Dockerfile.sandbox`, `sandbox_server/server.py`, `utils/sandbox_client.py`, `agents/orchestrator.py`, `bot/main.py`, y la tabla `allowed_stores` + `utils/domain_allowlist.py` (ya commiteados en la rama `fase-1-busqueda`; si cambian, revisar §2 y §5). **[verificar]** = depende de Docker y no se probó; se confirma con `docker compose config` y la prueba real del final.

**En una línea:** contenedor `search` con dos redes (una `internal` compartida solo con `app` y una bridge propia para salir), sin credenciales de BD. En cada petición el bot le pasa la lista activa de `allowed_stores`, y el servicio solo busca en tiendas que también tengan adaptador en código.

## 1. Topología de red

Hoy: `app` está en `default` y `sandbox_net`. `sandbox` está solo en `sandbox_net` (`internal: true`). `db` no declara `networks`, así que queda en `default`, y además publica `5432:5432` en el host. `default` es una bridge normal, así que **el bot ya tiene internet** (le hace falta para Telegram y OpenAI). El objetivo, entonces, no es negarle internet al bot. Es que `sandbox` siga sin salida, que `search` tenga salida y que `search` no comparta red con `sandbox` ni con `db`.

| Servicio | Redes | Internet | Ve a |
|---|---|---|---|
| `app` | `default`, `sandbox_net`, `search_net` | sí (`default`) | `db`, `sandbox`, `search` |
| `sandbox` | `sandbox_net` | no | `app` (no escucha puertos) |
| `search` | `search_net`, `search_egress` | sí (`search_egress`) | `app` (no escucha puertos) |
| `db` | `default` (sin cambios) | sí, no la usa | `app` |

```yaml
  search:                       # boceto, no es código final
    build: { context: ., dockerfile: Dockerfile.search }
    container_name: ayllu_search
    # igual que sandbox: read_only, tmpfs /tmp, cap_drop ALL, no-new-privileges,
    # mem_limit, cpus, pids_limit. Sin env_file ni volúmenes.
    networks: [search_net, search_egress]
  # en app: networks += search_net; environment: SEARCH_URL: http://search:8000
networks:
  sandbox_net: { internal: true }
  search_net: { internal: true }   # solo app y search
  search_egress: {}                 # bridge normal con NAT: SOLO search
```

- **Salida solo para `search`.** Una red `internal` nunca tiene salida. La salida viene de una bridge normal (`search_egress`) de la que solo es miembro `search`; `app` y `sandbox` no la declaran. Docker toma la puerta de enlace por defecto de una red no `internal`, y para `search` la única es `search_egress` **[verificar]**.
- **Por qué no reutilizar redes.** Si `search` estuviera en `sandbox_net`, el código del sandbox podría llamar a `/search` y tendría un relé a internet. Si estuviera en `default`, llegaría a `db:5432`.
- **Nombre del servicio.** Se llama `search` y no `search_service` porque el guion bajo no es válido en un hostname (RFC 1123) y algunos clientes HTTP rechazan `http://search_service:8000`.
- **Aislamiento.** Entre bridges distintas no hay tráfico, y el DNS interno solo resuelve servicios de redes compartidas **[verificar]**. Hay una excepción: desde `search_egress` sí se alcanza el host (por la IP de la puerta de enlace y, en Docker Desktop, por `host.docker.internal`), y con él sus puertos publicados, hoy el `5432` de `db`. Lo cubren la §3.4 y la decisión 2.

## 2. Dónde se impone la lista y quién la lee

- **A. `search` lee la BD con un rol de solo lectura.** Hay que unirlo a una red con `db` y darle credenciales, justo al contenedor más expuesto (internet + HTML no confiable). Si se compromete, tiene a la vez credenciales, ruta a Postgres y salida para exfiltrar. Un rol con `SELECT` solo sobre `allowed_stores` limita lo que se lee, pero la ruta de red a Postgres sigue ahí, y la contraseña del superusuario tiene valor por defecto en compose.
- **B. El bot lee `allowed_stores` y se la pasa en cada petición.** `search` no tiene credenciales ni ruta a `db`. Hay que confiar en `app`, pero `app` ya tiene `.env`, la clave de OpenAI y la BD completa: si `app` cae, da igual A o B. El riesgo propio de B es que el LLM toque la lista. No puede: la lista sale de la BD en código, y el esquema de la herramienta nunca expone dominios ni URLs.

**Recomendación: B**, con un techo en código dentro de `search`. Cada tienda necesita un *adaptador* registrado por su dominio (plantilla de URL de búsqueda + parser del HTML). Se busca solo si la tienda pedida está en la lista enviada **y** tiene adaptador. Así una fila errónea en la BD como `com.co`, que `normalize_domain` acepta, no abre nada, porque no tiene adaptador.

Falla cerrado en dos puntos:
1. **Bot.** Si `get_allowed_domains()` lanza (BD caída) o devuelve `[]`, no llama a `search` y la herramienta responde "búsqueda no disponible". No se cachea la lista: con una lista vieja se podría buscar con la BD caída.
2. **`search`.** Responde 403 si `allowed_domains` está vacía, si queda vacía tras normalizar o si `store` no está en ella. Responde 404 si `store` no tiene adaptador.

## 3. Defensas del fetcher (SSRF y abuso)

Solo librería estándar (`http.client`, `ssl`, `socket`, `ipaddress`, `html.parser`), como el sandbox, así que la imagen no necesita `pip`. Se copia a la imagen `utils/domain_allowlist.py`, que es un módulo puro.

1. **El LLM nunca da URLs.** Solo da `query`: texto de 1 a 100 caracteres, sin caracteres de control. La URL la arma el adaptador con `urllib.parse.quote(query, safe="")`.
2. **Forma de la URL.** `is_url_allowed(url, [store])` se aplica a toda URL antes de pedirla: solo `https`, puerto 443 o ninguno, sin `user@`, sin IP literal, sin espacios ni `\`.
3. **Dominio por límite de etiqueta.** La regla es `host == d or host.endswith("." + d)` (ya está en `is_url_allowed`) y se compara contra la tienda pedida, no contra toda la lista. Probado: `listado.mercadolibre.com.co` pasa; `evilmercadolibre.com.co`, `mercadolibre.com.co.evil.com`, `http://…` y `:8443` no.
4. **DNS e IP.** Resolver con `socket.getaddrinfo(..., AF_INET)` (solo IPv4: las redes de compose no tienen IPv6 por defecto **[verificar]**). Si **alguna** IP cumple `not ip.is_global or ip.is_multicast`, se rechaza. Hace falta `is_multicast` porque `224.0.0.1` da `is_global=True` (comprobado). Esto cubre IPs privadas, loopback, link-local (incluida la de metadata `169.254.169.254`), CGNAT `100.64/10` y `0.0.0.0`, y con ellas `db`, la puerta de enlace y `host.docker.internal`.
5. **DNS rebinding.** Se conecta a la IP ya validada, no al nombre. Una subclase de `HTTPSConnection` sobrescribe `connect()`: abre el socket a esa IP y lo envuelve con `ssl.create_default_context()` y `server_hostname=host`. Así se verifican el certificado y el hostname (nunca `CERT_NONE`), y la cabecera `Host` lleva el nombre original.
6. **Redirecciones.** No se siguen solas. Máximo 2 saltos: cada `Location` se resuelve con `urljoin` y repite los pasos 2 a 5 completos. No se permite bajar de `https` a `http`.
7. **Presupuesto.** Máximo 3 peticiones HTTP por búsqueda, contando redirecciones. Solo `GET` y solo la página de resultados; en la Fase 1 no se abren fichas de producto.
8. **Tiempos.** Conexión 5 s, lectura 10 s, total por búsqueda 20 s. El cliente del bot espera 25 s, el mismo patrón que `sandbox_client` (20 s frente a 10 s).
9. **Tamaño.** Se lee por bloques y se corta en 2 MB, sin fiarse de `Content-Length`. Se envía `Accept-Encoding: identity`; si la respuesta llega comprimida, se rechaza (sin riesgo de bomba gzip).
10. **Tipo y estado.** Solo se acepta `200` con `Content-Type: text/html`. Los 3xx van al paso 6 y todo lo demás es error.
11. **Sin estado.** Sin cookies, sin cabeceras de autenticación y con `User-Agent` fijo. Ningún dato del usuario (ID de Telegram, nombre) va en la petición.
12. **Abuso.** `ThreadingHTTPServer` abre hilos sin límite, así que un semáforo limita a 2 búsquedas a la vez (si no, 429), con al menos 1 s entre peticiones a la misma tienda. En el bot, máximo 3 llamadas a la herramienta por mensaje.
13. **Inyección de prompt.** Los títulos los escriben vendedores. Al LLM solo le llegan campos estructurados y recortados (§5), nunca HTML ni texto libre de la página, y siempre como datos. En la Fase 1 no hay herramientas de gasto, pero este formato hay que fijarlo ya.

## 4. Si Docker no restringe la salida por dominio

Compose no filtra la salida por dominio: `internal` es todo o nada. Sin firewall de host, desde `search_egress` `search` llega a cualquier IP y puerto, incluido el host. Los errores de lógica los frena el código de la §3. El **riesgo residual** es otro: que el proceso `search` se comprometa (un fallo en el parser o en `ssl`). Entonces la §3 no aplica y queda un relé libre hacia internet y hacia los puertos publicados del host. Mitigación:
- **Nada que robar:** sin `.env`, sin credenciales de BD (por eso B) y sin volumen del proyecto.
- **Sin ruta de red** a `db` ni a `sandbox` (§1).
- **Endurecimiento** igual al del sandbox: `read_only`, `cap_drop: ALL`, `no-new-privileges`, usuario sin privilegios y límites de memoria, CPU y procesos.
- **Superficie mínima:** solo librería estándar, sin navegador headless ni motor JS.
- **Auditoría:** cada petición queda en el log `AylluSearchServer` con URL, IP, estado y bytes.
- **Restricción real por dominio sin firewall de host:** un proxy de salida (Squid con lista `dstdomain`) como único miembro de `search_egress`, con `search` solo en redes `internal`. Ver la decisión 1.

## 5. Contrato de la API (`search_server/server.py`, estilo `sandbox_server`)

`GET /health` responde `200 {"status": "ok"}` sin salir a internet. `POST /search` acepta un cuerpo de hasta 4 KB:

```json
{"store": "mercadolibre.com.co", "allowed_domains": ["mercadolibre.com.co"],
 "query": "comida gato adulto 7 kg", "max_results": 10}
```
- **`store`** identifica la tienda por su dominio, la clave primaria de `allowed_stores`. Lo propone el LLM y lo valida el bot.
- **`allowed_domains`** es la salida de `get_allowed_domains()`; el LLM nunca la escribe.
- **`max_results`** va de 1 a 20 (10 por defecto).

```json
{"status": "ok", "store": "mercadolibre.com.co", "query": "comida gato adulto 7 kg",
 "results": [{"title": "...", "price": 189900, "currency": "COP",
              "url": "https://articulo.mercadolibre.com.co/MCO-..."}],
 "requests_made": 1}
```
- **`title`:** máximo 200 caracteres, sin caracteres de control.
- **`price`:** número o `null`.
- **`url`:** pasa `is_url_allowed` contra `store`, sin query ni fragmento.
- **`results: []`:** respuesta válida cuando no hubo resultados.

Errores: `{"status": "error", "error": "<código>", "detail": "..."}`.

| HTTP | `error` | Cuándo |
|---|---|---|
| 400 | `solicitud_invalida` | JSON roto, faltan campos, tipos o rangos inválidos |
| 403 | `tienda_no_permitida` | lista vacía, `store` fuera de la lista, o una URL, redirección o IP fuera de política |
| 404 | `tienda_sin_adaptador` | `store` sin adaptador (una ruta desconocida da `no encontrado`, como el sandbox) |
| 413 | `cuerpo_demasiado_grande` | cuerpo vacío o de más de 4 KB |
| 429 | `ocupado` | límite de concurrencia o de frecuencia |
| 502 | `error_tienda` | estado distinto de 200, tipo no HTML, más de 2 MB, error TLS, o HTML que el parser no reconoce |
| 504 | `tiempo_agotado` | se superan los 20 s |

Cliente `utils/search_client.py` (asíncrono, con `httpx` y `SEARCH_URL`): ante cualquier error devuelve `status: error` y no busca por su cuenta. Sin `SEARCH_URL` también devuelve error: a diferencia del sandbox no hay modo local, porque buscar desde `app` saltaría el aislamiento. Los tests prueban el fetcher inyectando el resolvedor y la conexión.

## 6. Decisiones abiertas (solo el usuario)

1. **¿Proxy de salida ahora o después?** Recomiendo empezar la Fase 1 sin proxy (código + endurecimiento de la §4) y añadir el contenedor Squid con lista por dominio antes de la Fase 3 (ejecución de compra).
2. **`5432:5432` de `db` publicado en todas las interfaces del host,** con contraseña por defecto en compose. `search` podría alcanzarlo por la puerta de enlace. Recomiendo quitar `ports` si no usas la BD desde el host, o usar `127.0.0.1:5432:5432` **[verificar si Docker Desktop lo sigue exponiendo vía `host.docker.internal`]**.
3. **Política con la tienda** (`robots.txt`, términos de uso, `User-Agent`). Recomiendo un `User-Agent` que identifique al bot, respetar `robots.txt` y la frecuencia de la §3.12. Si MercadoLibre bloquea bots o exige JS para listar, hay que replantear la fuente antes de construir el parser.

## Prueba real pendiente (con Docker encendido)

- `docker compose config`: revisar las redes de cada servicio y que `search` no tenga `env_file` ni volúmenes.
- Desde `ayllu_search`: `https://listado.mercadolibre.com.co` responde; `db` y `sandbox` no resuelven; `host.docker.internal:5432` es alcanzable por red (es lo esperado y lo bloquea el código).
- Desde `ayllu_sandbox`: `search` no resuelve y no hay salida. Revisar también si resuelve nombres externos, porque eso sería un canal de exfiltración por DNS.
- `python:3.11-slim` trae `ca-certificates`, necesario para verificar TLS.
