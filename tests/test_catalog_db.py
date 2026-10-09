"""Tests del catálogo contra PostgreSQL real (marcador db)."""
from decimal import Decimal

import asyncpg
import pytest

import utils.database as database
from utils.catalog import add_product, deactivate_product, search_products
from utils.database import close_db_pool, init_db_pool

TIENDA = "catalogo-prueba-ayllu.com.co"
TIENDA_INACTIVA = "catalogo-inactiva-ayllu.com.co"
TIENDA_INEXISTENTE = "catalogo-inexistente-ayllu.com.co"
# Subdominio de TIENDA: una misma url es válida para ambas tiendas.
TIENDA_SUB = f"sub.{TIENDA}"
TIENDAS = [TIENDA, TIENDA_INACTIVA, TIENDA_INEXISTENTE, TIENDA_SUB]

# Palabra improbable para aislar las búsquedas de datos reales.
MARCA = "Zqxayllu"


def _url(tienda, sufijo):
    return f"https://{tienda}/producto-{sufijo}"


@pytest.fixture
async def pool():
    try:
        await init_db_pool()
    except Exception as e:
        pytest.skip(f"PostgreSQL no disponible: {e}")
    await _borrar_datos_de_prueba()
    async with database.DB_POOL.acquire() as conn:
        await conn.execute(
            "INSERT INTO allowed_stores (domain, is_active) "
            "VALUES ($1, TRUE), ($2, FALSE), ($3, TRUE);",
            TIENDA, TIENDA_INACTIVA, TIENDA_SUB,
        )
    try:
        yield database.DB_POOL
    finally:
        await _borrar_datos_de_prueba()
        await close_db_pool()


async def _borrar_datos_de_prueba():
    async with database.DB_POOL.acquire() as conn:
        await conn.execute(
            "DELETE FROM products WHERE store_domain = ANY($1::text[]);", TIENDAS
        )
        await conn.execute(
            "DELETE FROM allowed_stores WHERE domain = ANY($1::text[]);", TIENDAS
        )


async def _agregar(nombre, precio, sufijo, marca=MARCA, tienda=TIENDA):
    return await add_product(nombre, marca, precio, _url(tienda, sufijo), tienda)


@pytest.mark.db
async def test_upsert_por_url_actualiza_precio(pool):
    id1 = await _agregar("Comida gato adulto", Decimal("85000"), "a")
    id2 = await _agregar("Comida gato adulto 3kg", Decimal("79900.50"), "a")
    assert id1 == id2
    async with pool.acquire() as conn:
        fila = await conn.fetchrow("SELECT name, price FROM products WHERE id = $1;", id1)
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM products WHERE url = $1;", _url(TIENDA, "a")
        )
    assert fila["name"] == "Comida gato adulto 3kg"
    assert fila["price"] == Decimal("79900.50")
    assert total == 1


@pytest.mark.db
async def test_upsert_por_url_actualiza_store_domain(pool):
    url = _url(TIENDA_SUB, "s")
    id1 = await add_product("Comida gato", MARCA, 1000, url, TIENDA)
    id2 = await add_product("Comida gato", MARCA, 1000, url, TIENDA_SUB)
    assert id1 == id2
    async with pool.acquire() as conn:
        tienda = await conn.fetchval("SELECT store_domain FROM products WHERE id = $1;", id1)
    assert tienda == TIENDA_SUB
    assert [r["store"] for r in await search_products(MARCA)] == [TIENDA_SUB]


@pytest.mark.db
async def test_upsert_reactiva_producto_desactivado(pool):
    pid = await _agregar("Comida gato", 1000, "r")
    assert await deactivate_product(pid) is True
    assert await search_products(f"{MARCA} gato") == []
    await _agregar("Comida gato", 1000, "r")
    assert [r["id"] for r in await search_products(f"{MARCA} gato")] == [pid]


@pytest.mark.db
async def test_busqueda_tokens_and_case_insensitive_y_orden(pool):
    await _agregar("Comida GATO adulto", 90000, "1")
    await _agregar("comida gato cachorro", 50000, "2")
    await _agregar("Comida perro adulto", 10000, "3")

    resultado = await search_products(f"{MARCA.lower()} GaTo comida")
    assert [r["price"] for r in resultado] == [50000.0, 90000.0]
    assert all(r["store"] == TIENDA and r["currency"] == "COP" for r in resultado)

    # AND: "gato" y "perro" juntos no coinciden con nada
    assert await search_products(f"{MARCA} gato perro") == []
    # La marca también se busca
    assert len(await search_products(MARCA)) == 3


@pytest.mark.db
async def test_comodines_like_son_literales(pool):
    await _agregar("Arena 100% natural", 20000, "p")
    await _agregar("Arena 1000 natural", 15000, "q")
    await _agregar("Arena a_b", 5000, "u")
    await _agregar("Arena axb", 4000, "v")

    assert [r["name"] for r in await search_products(f"{MARCA} 100%")] == ["Arena 100% natural"]
    assert [r["name"] for r in await search_products(f"{MARCA} a_b")] == ["Arena a_b"]
    assert [r["name"] for r in await search_products(f"{MARCA} %")] == ["Arena 100% natural"]


@pytest.mark.db
async def test_max_results(pool):
    for i in range(12):
        await _agregar(f"Snack gato {i}", 1000 + i, f"m{i}")
    assert len(await search_products(MARCA, max_results=3)) == 3
    assert len(await search_products(MARCA, max_results=50)) == 10


@pytest.mark.db
async def test_producto_inactivo_no_aparece(pool):
    pid = await _agregar("Comida gato", 1000, "i")
    assert await deactivate_product(pid) is True
    assert await search_products(MARCA) == []
    # id válido pero inexistente (el rango 1..2**63-1 se valida antes de la BD)
    assert await deactivate_product(2**62) is False


@pytest.mark.db
async def test_tienda_inactiva_no_aparece(pool):
    pid = await _agregar("Comida gato", 1000, "t")
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE allowed_stores SET is_active = FALSE WHERE domain = $1;", TIENDA
        )
    assert await search_products(MARCA) == []
    async with pool.acquire() as conn:
        activo = await conn.fetchval("SELECT is_active FROM products WHERE id = $1;", pid)
    assert activo is True  # el producto sigue activo; lo oculta la tienda


@pytest.mark.db
async def test_add_product_tienda_inactiva_falla(pool):
    with pytest.raises(ValueError):
        await _agregar("Comida gato", 1000, "x", tienda=TIENDA_INACTIVA)


@pytest.mark.db
async def test_add_product_tienda_inexistente_falla(pool):
    with pytest.raises(ValueError):
        await _agregar("Comida gato", 1000, "x", tienda=TIENDA_INEXISTENTE)
    async with pool.acquire() as conn:
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM products WHERE store_domain = $1;", TIENDA_INEXISTENTE
        )
    assert total == 0


@pytest.mark.db
async def test_fk_impide_producto_de_tienda_inexistente(pool):
    async with pool.acquire() as conn:
        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await conn.execute(
                "INSERT INTO products (name, price, url, store_domain) VALUES ($1, $2, $3, $4);",
                "Directo", Decimal("1"), _url(TIENDA_INEXISTENTE, "fk"), TIENDA_INEXISTENTE,
            )


@pytest.mark.db
async def test_check_precio_no_negativo(pool):
    async with pool.acquire() as conn:
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                "INSERT INTO products (name, price, url, store_domain) VALUES ($1, $2, $3, $4);",
                "Directo", Decimal("-1"), _url(TIENDA, "neg"), TIENDA,
            )
