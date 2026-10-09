"""
Catálogo propio de productos (Fase 1, Misión 1).

El scraping de tiendas no es viable (docs/fase-1-viabilidad-mercadolibre.md),
así que el agente busca en una tabla 'products' que mantiene el usuario.
Los límites se aplican aquí, en código: el LLM solo podrá LEER el catálogo
(search_products); escribir (add_product, deactivate_product) es exclusivo
del usuario.

Se lee database.DB_POOL en tiempo de llamada (no se importa DB_POOL
directamente, que capturaría None al importar el módulo).
"""
import logging
import math
import re
import unicodedata
from decimal import Decimal, InvalidOperation

from utils import database
from utils.domain_allowlist import is_url_allowed, normalize_domain

logger = logging.getLogger("AylluCatalog")

_MAX_NOMBRE = 200
_MAX_MARCA = 100
_MAX_QUERY = 100
_MAX_TOKENS = 6
_MAX_RESULTADOS = 10
_PRECIO_MAXIMO = Decimal("100000000")
# Caracteres de control C0, DEL y C1.
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_CATEGORIAS_INVISIBLES = frozenset({"Cf", "Zl", "Zp"})
_MONEDA = re.compile(r"[A-Z]{3}")
_MAX_URL = 2000
_MAX_ID = 2**63 - 1


def _rechazar_invisibles(valor: str, campo: str) -> None:
    """
    Lanza ValueError si hay caracteres de control (C0, DEL, C1) o Unicode
    invisible/de formato: categorías Cf (zero-width, BOM, soft hyphen, bidi,
    tags), Zl y Zp. Pueden ocultar o reordenar lo que ve el humano.
    """
    if _CONTROL.search(valor):
        raise ValueError(f"{campo} contiene caracteres de control.")
    if any(unicodedata.category(c) in _CATEGORIAS_INVISIBLES for c in valor):
        raise ValueError(f"{campo} contiene caracteres Unicode invisibles o de formato.")


def _validar_texto(valor, campo: str, maximo: int) -> str:
    if not isinstance(valor, str):
        raise ValueError(f"{campo} debe ser texto.")
    _rechazar_invisibles(valor, campo)
    limpio = valor.strip()
    if not limpio:
        raise ValueError(f"{campo} está vacío.")
    if len(limpio) > maximo:
        raise ValueError(f"{campo} supera {maximo} caracteres.")
    return limpio


def _validar_precio(precio) -> Decimal:
    if isinstance(precio, bool) or not isinstance(precio, (Decimal, int, float, str)):
        raise ValueError("El precio debe ser numérico.")
    if isinstance(precio, float) and not math.isfinite(precio):
        raise ValueError("El precio debe ser finito.")
    try:
        valor = Decimal(str(precio).strip()) if isinstance(precio, str) else Decimal(str(precio))
    except (InvalidOperation, ValueError):
        raise ValueError(f"Precio inválido: {precio!r}")
    if not valor.is_finite():
        raise ValueError("El precio debe ser finito.")
    if valor <= 0:
        raise ValueError("El precio debe ser mayor que cero.")
    if valor > _PRECIO_MAXIMO:
        raise ValueError(f"El precio supera el máximo permitido ({_PRECIO_MAXIMO}).")
    # NUMERIC(12,2) redondearía en silencio: se exige como máximo 2 decimales.
    if valor != valor.quantize(Decimal("0.01")):
        raise ValueError(f"El precio admite como máximo 2 decimales: {precio!r}")
    return valor


def _escapar_like(token: str) -> str:
    """Escapa '\\', '%' y '_' para usar el token como literal con ESCAPE '\\'."""
    return token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def add_product(name, brand, price, url, store_domain, currency="COP") -> int:
    """
    Valida en código e inserta (o actualiza por url) un producto del catálogo.
    Devuelve su id. Lanza ValueError si algún dato es inválido o si la tienda
    no existe o está inactiva; RuntimeError si no hay pool.

    ADVERTENCIA: cambia lo que el agente puede ofrecer al usuario. NUNCA debe
    exponerse como herramienta al LLM. Antes de conectarla a un handler de
    Telegram se exige usuario en la lista blanca y aprobación humana explícita.
    """
    nombre = _validar_texto(name, "El nombre", _MAX_NOMBRE)
    marca = None if brand is None else _validar_texto(brand, "La marca", _MAX_MARCA)
    precio = _validar_precio(price)
    if not isinstance(currency, str) or not _MONEDA.fullmatch(currency):
        raise ValueError(f"Moneda inválida: {currency!r} (3 letras mayúsculas).")
    if not isinstance(store_domain, str):
        raise ValueError("La tienda debe ser texto.")
    _rechazar_invisibles(store_domain, "La tienda")
    tienda = normalize_domain(store_domain)
    if not isinstance(url, str):
        raise ValueError("La URL debe ser texto.")
    if len(url) > _MAX_URL:
        raise ValueError(f"La URL supera {_MAX_URL} caracteres.")
    _rechazar_invisibles(url, "La URL")
    if not is_url_allowed(url, [tienda]):
        raise ValueError(f"La URL no es https de la tienda {tienda}: {url!r}")

    if not database.DB_POOL:
        raise RuntimeError("Pool de PostgreSQL no inicializado.")

    tienda_query = """
    SELECT is_active FROM allowed_stores
    WHERE domain = $1
    FOR SHARE;
    """
    upsert_query = """
    INSERT INTO products (name, brand, price, currency, url, store_domain, is_active, updated_at)
    VALUES ($1, $2, $3, $4, $5, $6, TRUE, CURRENT_TIMESTAMP)
    ON CONFLICT (url) DO UPDATE SET
        name = EXCLUDED.name,
        brand = EXCLUDED.brand,
        price = EXCLUDED.price,
        currency = EXCLUDED.currency,
        store_domain = EXCLUDED.store_domain,
        is_active = TRUE,
        updated_at = CURRENT_TIMESTAMP
    RETURNING id;
    """
    async with database.DB_POOL.acquire() as conn:
        async with conn.transaction():
            activa = await conn.fetchval(tienda_query, tienda)
            if not activa:
                raise ValueError(f"La tienda {tienda} no existe o está inactiva.")
            product_id = await conn.fetchval(
                upsert_query, nombre, marca, precio, currency, url, tienda
            )

    logger.info(f"✓ Producto {product_id} guardado en el catálogo ({tienda}).")
    return product_id


async def deactivate_product(product_id: int) -> bool:
    """
    Marca un producto como inactivo. Devuelve True si afectó una fila.
    Igual que add_product: NUNCA se expone como herramienta al LLM.
    """
    if isinstance(product_id, bool) or not isinstance(product_id, int):
        raise ValueError("El id del producto debe ser entero.")
    if not 1 <= product_id <= _MAX_ID:
        raise ValueError(f"El id del producto debe estar entre 1 y {_MAX_ID}.")
    if not database.DB_POOL:
        raise RuntimeError("Pool de PostgreSQL no inicializado.")

    query = """
    UPDATE products SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP
    WHERE id = $1;
    """
    async with database.DB_POOL.acquire() as conn:
        estado = await conn.execute(query, product_id)
    afectado = estado.split()[-1] != "0"
    if afectado:
        logger.info(f"Producto {product_id} desactivado.")
    else:
        logger.warning(f"No existe el producto {product_id}: nada que desactivar.")
    return afectado


async def search_products(query: str, max_results: int = 5) -> list[dict]:
    """
    Busca productos activos de tiendas activas cuyo nombre o marca contengan
    todos los tokens de la consulta (sin distinguir mayúsculas), del más
    barato al más caro. Lanza ValueError si la consulta es inválida (antes de
    tocar la BD). Falla cerrado: sin pool o ante error de BD devuelve [].

    Contrato para el wrapper de tool calling: la consulta viene del modelo,
    así que el wrapper DEBE capturar ValueError y devolver al modelo un
    mensaje de error legible (no propagar la excepción al handler del bot).
    """
    texto = _validar_texto(query, "La consulta", _MAX_QUERY)
    tokens = texto.split()[:_MAX_TOKENS]
    if isinstance(max_results, bool) or not isinstance(max_results, int):
        raise ValueError("max_results debe ser entero.")
    limite = max(1, min(_MAX_RESULTADOS, max_results))

    if not database.DB_POOL:
        logger.error("❌ Pool de PostgreSQL no inicializado: catálogo vacío.")
        return []

    # Solo se interpolan números de parámetro ($n), nunca datos.
    condiciones = [
        f"(p.name ILIKE ${i} ESCAPE '\\' OR p.brand ILIKE ${i} ESCAPE '\\')"
        for i in range(1, len(tokens) + 1)
    ]
    sql = f"""
    SELECT p.id, p.name, p.brand, p.price, p.currency, p.url, p.store_domain AS store
    FROM products p
    JOIN allowed_stores s ON s.domain = p.store_domain
    WHERE p.is_active = TRUE AND s.is_active = TRUE
      AND {" AND ".join(condiciones)}
    ORDER BY p.price ASC, p.id
    LIMIT ${len(tokens) + 1};
    """
    parametros = [f"%{_escapar_like(t)}%" for t in tokens] + [limite]

    try:
        async with database.DB_POOL.acquire() as conn:
            filas = await conn.fetch(sql, *parametros)

        resultados = []
        for fila in filas:
            if not is_url_allowed(fila["url"], [fila["store"]]):
                logger.warning(
                    f"Producto {fila['id']} descartado: url fuera de la tienda {fila['store']!r}."
                )
                continue
            resultados.append({
                "id": fila["id"],
                "name": fila["name"],
                "brand": fila["brand"],
                "price": float(fila["price"]),
                "currency": fila["currency"],
                "url": fila["url"],
                "store": fila["store"],
            })
        return resultados
    except Exception as e:
        logger.error(f"❌ Error al buscar en el catálogo, sin resultados: {str(e)}")
        return []
