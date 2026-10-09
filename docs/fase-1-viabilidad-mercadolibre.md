# Fase 1: viabilidad de buscar en MercadoLibre Colombia

Fecha: 2026-10-09, rama `fase-1-busqueda`. Responde a la decisión 3 de la §6 de `docs/fase-1-egreso-buscador.md`.

## Veredicto: NO VIABLE (scraping con cliente honesto y sin JS)

Con un `User-Agent` que se identifica como bot, el listado no entrega HTML: responde `302` hacia una página de verificación anti-bot. La API oficial de búsqueda responde `403` sin token. Además, `robots.txt` prohíbe todo el sitio a los agentes de IA (`ClaudeBot`, `Claude-User`, `GPTBot`, `ChatGPT-User`, `PerplexityBot`...), que es la categoría de Ayllu aunque su UA caiga en `*`.

**Recomendación:** no construir el parser HTML de MercadoLibre. Antes de seguir, el usuario elige:
1. **API oficial con token (OAuth).** El usuario registra una app en el portal de desarrolladores y se prueba si la búsqueda responde con token (no probado: requiere cuenta). Cambia el diseño: `search` tendría un secreto (token de ML), un adaptador JSON en vez de HTML y el host `api.mercadolibre.com`, que está fuera de `mercadolibre.com.co`.
2. **Otra tienda** con listado en HTML estático y `robots.txt` permisivo. Repetir esta misma prueba (≤8 GET, UA honesto) antes de diseñar su adaptador.
3. **Descartado:** navegador headless, UA de navegador, cookies o reintentos para pasar la verificación. Sería saltarse el bloqueo y contradice la §4 (superficie mínima).

## Método

5 GET desde Python local (`python -I`, solo `http.client` y `ssl`), ≥1,5 s entre peticiones, `User-Agent: AylluBot/0.1 (+uso personal; investigacion de viabilidad)`, `Accept-Encoding: identity`, sin cookies y sin seguir redirecciones. Todo se leyó en memoria; no se guardó nada en disco. Tras el bloqueo no se reintentó el listado.

| # | GET | Resultado |
|---|---|---|
| 1 | `www.mercadolibre.com.co/robots.txt` | 200, texto, 2,4 KB |
| 2 | `listado.mercadolibre.com.co/robots.txt` | 200, texto, 11 KB |
| 3 | `listado.mercadolibre.com.co/comida-para-gatos` | **302**, cuerpo de 194 B, `Location: https://www.mercadolibre.com.co/gz/account-verification?go=<URL pedida>&tid=<id>` |
| 4 | `listado.mercadolibre.com.co/robots.txt` (otra vez, para leer el grupo de bots de IA) | 200 |
| 5 | `api.mercadolibre.com/sites/MCO/search?q=comida%20gato` | **403** `{"message":"forbidden","error":"forbidden","status":403,"cause":[]}` |

## Hallazgos

**1. robots.txt.**
- Ambos archivos declaran `Crawl-delay: 5`. El 1 s de la §3.12 se queda corto.
- Grupo de bots de IA (`Amazonbot`, `PerplexityBot`, `Perplexity-User`, `ClaudeBot`, `Claude-User`, `GPTBot`, `ChatGPT-User`): `Disallow: /` en `listado.` (comprobado). En `www.` aparece el mismo grupo de UAs (sus reglas no se imprimieron). La tienda no quiere agentes de IA, ni siquiera los que navegan a pedido de un usuario.
- Grupo `*` de `listado.` (250 reglas): la búsqueda base `/<termino-con-guiones>` está permitida (`/comida-para-gatos`, `/comida-gato-adulto-7-kg`). Están prohibidos la paginación (`/*_Desde_`), el orden (`/*_OrderId_`), los rangos de precio (`/*_PriceRange_`, `_PriceMin_`, `_PriceMax_`), `/*_NoIndex_True`, `/supermercado/*`, toda ruta que contenga `merca` (`/*merca`) y una lista de términos para adultos. Solo se podría pedir la primera página, sin filtros.
- Grupo `*` de `www.` (42 reglas): prohíbe carrito, checkout, perfiles, recomendaciones y `/*.js`. No menciona rutas de búsqueda.

**2. Listado real.** No se pudo ver el HTML: la respuesta fue el `302` a `/gz/account-verification`. Trae la cabecera `x-is-search-bot` (el servidor clasifica al cliente) y fija cookies (`_d2id`, `_csrf`, `_mldataSessionId`, `x-theme`). No hay evidencia sobre HTML estático, JSON-LD ni estado precargado, así que **no hay selectores ni claves comprobados**. `robots.txt` permite la ruta, pero el servidor bloquea al cliente, y manda el servidor.

**3. Cliente honesto.** Bloqueado en la primera petición de listado. No se siguió la redirección, no se reintentó y no se probó otro UA.

**4. API oficial.** `403 forbidden` sin autenticación y sin pista en `cause`: exige token, o el endpoint ya no es público. Con token, sin probar.

**5. Hosts.** Vistos: `listado.mercadolibre.com.co`, que redirige a `www.mercadolibre.com.co` (salto entre subdominios), y `api.mercadolibre.com`, **fuera** de `mercadolibre.com.co`. No vistos por el bloqueo: los de fichas de producto (se esperan `articulo.mercadolibre.com.co` y `www.mercadolibre.com.co/p/...`) y los de imágenes (se espera `http2.mlstatic.com`, que no se pide).

## Riesgos para el diseño actual (sirven aunque cambie la fuente)

- **La §3.6 seguiría la redirección hasta el muro.** `www.mercadolibre.com.co` pasa `is_url_allowed` contra `mercadolibre.com.co`, así que el fetcher gastaría un salto en la página de verificación y acabaría en `502` por HTML no reconocido. Mejor: que cada adaptador declare sus rutas de verificación o login (aquí `/gz/account-verification`) y que un `Location` hacia ellas sea un bloqueo, sin seguirlo, con un error propio (p. ej. `tienda_bloqueo`) y su log.
- **Frecuencia.** El adaptador debería llevar su propio `crawl_delay` (aquí 5 s) en vez del 1 s global.
- **robots.txt en código.** El adaptador debería declarar qué rutas genera, y un test comprobar que no caen en un `Disallow` (aquí: nunca `_Desde_` ni `_OrderId_`, y cuidado con consultas que contengan `merca`).

## Qué probaría el test (fixtures sintéticos, nunca copias de páginas reales)

- Fetcher: un `302` sintético con `Location: https://www.mercadolibre.com.co/gz/account-verification?go=...` da error de bloqueo, con 1 sola petición y sin seguir el salto.
- Fetcher: `403` y `429` dan error y no hay reintentos.
- Adaptador: la URL que genera para una consulta de prueba no coincide con ninguna regla `Disallow` de un `robots.txt` sintético mínimo (`/*_Desde_`, `/*_OrderId_`, `/*merca`).
- Parser: solo cuando haya una fuente viable. Su fixture se escribe a mano, imitando la estructura comprobada en la prueba de esa fuente.
