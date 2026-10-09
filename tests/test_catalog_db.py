"""Tests del catálogo contra PostgreSQL real (marcador db)."""
from decimal import Decimal

import asyncpg
import pytest

import utils.database as database
from utils.catalog import add_product, deactivate_product, listar_productos, search_products
from utils.database import close_db_pool, init_db_pool

TIENDA = "catalogo-prueba-ayllu.com.co"
TIENDA_INACTIVA = "catalogo-inactiva-ayllu.com.co"
TIENDA_INEXISTENTE = "catalogo-inexistente-ayllu.com.co"
# Subdominio de TIENDA: una misma url es válida para ambas tiendas.
TIENDA_SUB = f"sub.{TIENDA}"
TIENDAS = [TIENDA, TIENDA_INACTIVA, TIENDA_INEXISTENTE, TIENDA_SUB]

# Palabra improbable para aislar las búsquedas de datos reales.
MARCA = "Zqxayllu"
MARCA_2 = "Zqxsegunda"


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


async def _buscar(consulta, max_results=10):
    """
    Busca con el tope de resultados (10) y deja solo los de las tiendas de
    prueba. Las consultas llevan marcas únicas (Zqx...) para que los datos
    reales no ocupen el LIMIT antes de este filtro.
    """
    return [r for r in await search_products(consulta, max_results=max_results)
            if r["store"] in TIENDAS]


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
    assert await _buscar(f"{MARCA} gato") == []
    await _agregar("Comida gato", 1000, "r")
    assert [r["id"] for r in await _buscar(f"{MARCA} gato")] == [pid]


@pytest.mark.db
async def test_busqueda_case_insensitive_puntaje_y_orden(pool):
    # Antes la búsqueda exigía todos los tokens (AND); ahora puntúa con mínimo.
    await _agregar("Comida GATO adulto", 90000, "1")
    await _agregar("comida gato cachorro", 50000, "2")
    await _agregar("Comida perro adulto", 10000, "3")

    # n=3 -> mínimo 2. Puntaje 3 (marca+gato+comida) primero, por precio; luego el perro (2).
    resultado = await _buscar(f"{MARCA.lower()} GaTo comida")
    assert [r["price"] for r in resultado] == [50000.0, 90000.0, 10000.0]
    assert all(r["store"] == TIENDA and r["currency"] == "COP" for r in resultado)

    # "gato perro": cada producto suma marca + uno de los dos = 2 >= 2.
    assert len(await _buscar(f"{MARCA} gato perro")) == 3
    # La marca también se busca
    assert len(await _buscar(MARCA)) == 3


@pytest.mark.db
async def test_frase_natural_encuentra_producto(pool):
    pid = await _agregar("Biodieta Digestivo - Bienestar Digestivo 1 kg", 44650, "bio")
    # n=4 (comid, digestiv, gat, marca) -> mínimo 2: digestiv + marca.
    resultado = await _buscar(f"comida digestiva para gatos {MARCA}")
    assert [r["id"] for r in resultado] == [pid]


@pytest.mark.db
async def test_mayor_puntaje_primero_aunque_cueste_mas(pool):
    caro = await _agregar("Biodieta Digestivo gato", 90000, "caro")
    barato = await _agregar("Snack digestivo", 1000, "barato")
    resultado = await _buscar(f"digestivo gato {MARCA}")
    assert [r["id"] for r in resultado] == [caro, barato]


@pytest.mark.db
async def test_genero_y_plural_en_la_consulta(pool):
    pid = await _agregar("Bienestar Digestivo", 1000, "gen", marca=MARCA_2)
    assert [r["id"] for r in await _buscar(f"{MARCA_2} digestiva")][:1] == [pid]
    assert [r["id"] for r in await _buscar(f"{MARCA_2} DIGESTIVOS")][:1] == [pid]
    # Con 3 tokens (mínimo 2) la marca sola no basta: hace falta "digestiv".
    assert [r["id"] for r in await _buscar(f"{MARCA_2} digestiva perro")] == [pid]


@pytest.mark.db
async def test_gata_encuentra_producto_para_gatos(pool):
    pid = await _agregar("Alimento seco para gatos 1 kg", 30000, "gata", marca=MARCA_2)
    assert [r["id"] for r in await _buscar(f"{MARCA_2} gata")] == [pid]
    assert [r["id"] for r in await _buscar(f"comida para la gata {MARCA_2}")] == [pid]


@pytest.mark.db
async def test_cuatro_tokens_exigen_dos_coincidencias(pool):
    una = await _agregar("Alimento seco", 1000, "una", marca=MARCA_2)
    dos = await _agregar("Arena titanio", 5000, "dos", marca=MARCA_2)
    # n=4 -> mínimo 2: "una" solo coincide con la marca (1) y NO aparece.
    resultado = await _buscar(f"{MARCA_2} titanio dinosaurio volcanes")
    assert [r["id"] for r in resultado] == [dos]
    assert una not in [r["id"] for r in resultado]


@pytest.mark.db
async def test_kg_no_puntua(pool):
    barato = await _agregar("Alimento seco", 1000, "sin-kg", marca=MARCA_2)
    con_kg = await _agregar("Alimento seco 1 kg", 9000, "con-kg", marca=MARCA_2)
    # Si "kg" puntuara, el producto con kg (más caro) saldría primero.
    resultado = await _buscar(f"{MARCA_2} kg")
    assert [r["id"] for r in resultado] == [barato, con_kg]
    with pytest.raises(ValueError):
        await search_products("kg 500")


@pytest.mark.db
async def test_sin_coincidencias_devuelve_vacio(pool):
    await _agregar("Comida gato", 1000, "nada")
    assert await search_products("qwzxyplm vbnkjhtr") == []


@pytest.mark.db
async def test_comodines_like_son_literales(pool):
    await _agregar("Arena Zqx100%natural", 20000, "p", marca="Otra")
    await _agregar("Arena Zqx1000natural", 15000, "q", marca="Otra")
    await _agregar("Arena Zqxa_b", 5000, "u", marca="Otra")
    await _agregar("Arena Zqxaxb", 4000, "v", marca="Otra")

    assert [r["name"] for r in await _buscar("zqx100%")] == ["Arena Zqx100%natural"]
    assert [r["name"] for r in await _buscar("zqxa_b")] == ["Arena Zqxa_b"]
    assert [r["name"] for r in await _buscar("0%natural")] == ["Arena Zqx100%natural"]


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
async def test_listar_productos_incluye_inactivos_y_tienda_inactiva(pool):
    activo = await _agregar("Comida gato", Decimal("44650.50"), "l1")
    inactivo = await _agregar("Arena gato", 1000, "l2")
    await deactivate_product(inactivo)
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE allowed_stores SET is_active = FALSE WHERE domain = $1;", TIENDA
        )

    todos = {p["id"]: p for p in await listar_productos() if p["store"] == TIENDA}
    assert set(todos) == {activo, inactivo}
    assert todos[activo]["is_active"] is True and todos[inactivo]["is_active"] is False
    assert todos[activo]["price"] == Decimal("44650.50")
    assert todos[activo]["brand"] == MARCA

    solo_activos = {p["id"] for p in await listar_productos(incluir_inactivos=False)}
    assert activo in solo_activos and inactivo not in solo_activos


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
