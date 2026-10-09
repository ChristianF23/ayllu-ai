"""Tests de mascotas y vínculos contra PostgreSQL real (marcador db)."""
import asyncpg
import pytest

import utils.database as database
from utils.catalog import add_product, deactivate_product
from utils.database import close_db_pool, init_db_pool
from utils.pets import (
    add_pet,
    link_product,
    listar_mascotas,
    products_for_pet,
    unlink_product,
)

TIENDA = "mascotas-prueba-ayllu.com.co"
TIENDA_INACTIVA = "mascotas-inactiva-ayllu.com.co"
TIENDAS = [TIENDA, TIENDA_INACTIVA]
# Claves de nombre de las mascotas de prueba (todas empiezan por "zqxmascota").
PATRON_MASCOTAS = "zqxmascota%"
MASCOTA = "Zqxmascotá"
MASCOTA_CLAVE = "zqxmascota"
OTRA = "Zqxmascota Dos"


def _url(tienda, sufijo):
    return f"https://{tienda}/producto-{sufijo}"


async def _borrar_datos_de_prueba():
    async with database.DB_POOL.acquire() as conn:
        await conn.execute(
            "DELETE FROM pet_products WHERE pet_id IN "
            "(SELECT id FROM pets WHERE name_key LIKE $1) "
            "OR product_id IN (SELECT id FROM products WHERE store_domain = ANY($2::text[]));",
            PATRON_MASCOTAS, TIENDAS,
        )
        await conn.execute("DELETE FROM pets WHERE name_key LIKE $1;", PATRON_MASCOTAS)
        await conn.execute(
            "DELETE FROM products WHERE store_domain = ANY($1::text[]);", TIENDAS
        )
        await conn.execute(
            "DELETE FROM allowed_stores WHERE domain = ANY($1::text[]);", TIENDAS
        )


@pytest.fixture
async def pool():
    try:
        await init_db_pool()
    except Exception as e:
        pytest.skip(f"PostgreSQL no disponible: {e}")
    await _borrar_datos_de_prueba()
    async with database.DB_POOL.acquire() as conn:
        await conn.execute(
            "INSERT INTO allowed_stores (domain, is_active) VALUES ($1, TRUE);", TIENDA
        )
    try:
        yield database.DB_POOL
    finally:
        await _borrar_datos_de_prueba()
        await close_db_pool()


async def _producto(sufijo, precio=1000, tienda=TIENDA):
    return await add_product(f"Alimento {sufijo}", "Zqxmarca", precio, _url(tienda, sufijo), tienda)


async def _ids(nombre):
    resultado = await products_for_pet(nombre)
    return None if resultado is None else [p["id"] for p in resultado["productos"]]


@pytest.mark.db
async def test_tablas_existen(pool):
    async with pool.acquire() as conn:
        tablas = {r["table_name"] for r in await conn.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_name IN ('pets', 'pet_products');"
        )}
        await database._create_tables(conn)  # idempotente
    assert tablas == {"pets", "pet_products"}


@pytest.mark.db
async def test_add_pet_y_clave_normalizada(pool):
    pid = await add_pet(MASCOTA, "Gato")
    assert await add_pet(" ZQXMASCOTA ", "perro") == pid  # misma clave, no duplica
    async with pool.acquire() as conn:
        fila = await conn.fetchrow("SELECT name, name_key, species FROM pets WHERE id = $1;", pid)
    assert (fila["name"], fila["name_key"], fila["species"]) == (MASCOTA, MASCOTA_CLAVE, "gato")


@pytest.mark.db
async def test_vinculo_y_orden_por_precio(pool):
    await add_pet(MASCOTA, "gato")
    caro = await _producto("caro", 9000)
    barato = await _producto("barato", 1000)
    sin_vinculo = await _producto("libre", 500)
    assert await link_product("zqxmascota", caro) is True
    assert await link_product("ZQXMASCOTÁ", barato) is True
    resultado = await products_for_pet(" zqxmascota ")
    assert resultado["mascota"] == MASCOTA and resultado["especie"] == "gato"
    assert [p["id"] for p in resultado["productos"]] == [barato, caro]
    assert sin_vinculo not in [p["id"] for p in resultado["productos"]]
    assert resultado["productos"][0]["price"] == 1000.0


@pytest.mark.db
async def test_desvincular_y_reactivar_vinculo(pool):
    await add_pet(MASCOTA, "gato")
    pid = await _producto("v")
    await link_product(MASCOTA, pid)
    assert await unlink_product(MASCOTA, pid) is True
    assert await _ids(MASCOTA) == []
    await link_product(MASCOTA, pid)
    assert await _ids(MASCOTA) == [pid]
    async with pool.acquire() as conn:
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM pet_products pp JOIN pets p ON p.id = pp.pet_id "
            "WHERE p.name_key = $1;", MASCOTA_CLAVE,
        )
    assert total == 1


@pytest.mark.db
async def test_no_reactiva_mascota_inactiva(pool):
    mid = await add_pet(MASCOTA, "gato")
    pid = await _producto("i")
    await link_product(MASCOTA, pid)
    async with pool.acquire() as conn:
        await conn.execute("UPDATE pets SET is_active = FALSE WHERE id = $1;", mid)
    assert await add_pet(MASCOTA, "gato") == mid
    with pytest.raises(ValueError):
        await link_product(MASCOTA, pid)
    assert await products_for_pet(MASCOTA) is None
    async with pool.acquire() as conn:
        assert await conn.fetchval("SELECT is_active FROM pets WHERE id = $1;", mid) is False


@pytest.mark.db
async def test_producto_inactivo_o_tienda_inactiva_no_aparece(pool):
    await add_pet(MASCOTA, "gato")
    a = await _producto("a")
    b = await _producto("b", 2000)
    await link_product(MASCOTA, a)
    await link_product(MASCOTA, b)
    assert await _ids(MASCOTA) == [a, b]

    await deactivate_product(a)
    assert await _ids(MASCOTA) == [b]
    with pytest.raises(ValueError, match="inactivo"):
        await link_product(MASCOTA, a)

    async with pool.acquire() as conn:
        await conn.execute("UPDATE allowed_stores SET is_active = FALSE WHERE domain = $1;", TIENDA)
    assert await _ids(MASCOTA) == []
    with pytest.raises(ValueError, match="tienda"):
        await link_product(MASCOTA, b)


@pytest.mark.db
async def test_mascota_sin_productos_y_desconocida(pool):
    await add_pet(OTRA, "perro")
    assert await products_for_pet(OTRA) == {"mascota": OTRA, "especie": "perro", "productos": []}
    assert await products_for_pet("Zqxmascotainexistente") is None


@pytest.mark.db
async def test_link_mascota_o_producto_inexistente(pool):
    pid = await _producto("x")
    with pytest.raises(ValueError, match="mascota"):
        await link_product("Zqxmascotainexistente", pid)
    await add_pet(MASCOTA, "gato")
    with pytest.raises(ValueError, match="No existe el producto"):
        await link_product(MASCOTA, 2**62)


@pytest.mark.db
async def test_fk_de_pet_products(pool):
    mid = await add_pet(MASCOTA, "gato")
    async with pool.acquire() as conn:
        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await conn.execute(
                "INSERT INTO pet_products (pet_id, product_id) VALUES ($1, $2);", mid, 2**62
            )
        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await conn.execute(
                "INSERT INTO pet_products (pet_id, product_id) VALUES ($1, $2);",
                2**62, await _producto("fk"),
            )


@pytest.mark.db
async def test_listar_mascotas_incluye_vinculos_activos(pool):
    mid = await add_pet(MASCOTA, "gato")
    a = await _producto("la")
    b = await _producto("lb")
    await link_product(MASCOTA, a)
    await link_product(MASCOTA, b)
    await unlink_product(MASCOTA, b)
    mascotas = {m["id"]: m for m in await listar_mascotas()}
    assert [p["id"] for p in mascotas[mid]["productos"]] == [a]
    assert mascotas[mid]["species"] == "gato" and mascotas[mid]["is_active"] is True


@pytest.mark.db
@pytest.mark.parametrize("que_desactivar", ["producto", "tienda", "mascota"])
async def test_desvincular_aunque_haya_algo_inactivo(pool, que_desactivar):
    mid = await add_pet(MASCOTA, "gato")
    pid = await _producto("u")
    await link_product(MASCOTA, pid)
    async with pool.acquire() as conn:
        if que_desactivar == "producto":
            await conn.execute("UPDATE products SET is_active = FALSE WHERE id = $1;", pid)
        elif que_desactivar == "tienda":
            await conn.execute("UPDATE allowed_stores SET is_active = FALSE WHERE domain = $1;",
                               TIENDA)
        else:
            await conn.execute("UPDATE pets SET is_active = FALSE WHERE id = $1;", mid)
    assert await unlink_product(MASCOTA, pid) is True
    async with pool.acquire() as conn:
        activo = await conn.fetchval(
            "SELECT is_active FROM pet_products WHERE pet_id = $1 AND product_id = $2;", mid, pid
        )
    assert activo is False
    # Sin vínculo previo: False.
    assert await unlink_product(MASCOTA, 2**62) is False


@pytest.mark.db
async def test_desactivar_desvincular_reactivar_no_reaparece(pool):
    await add_pet(MASCOTA, "gato")
    pid = await _producto("r")
    await link_product(MASCOTA, pid)
    await deactivate_product(pid)
    assert await unlink_product(MASCOTA, pid) is True
    assert await _producto("r") == pid  # add_product reactiva por url
    assert await _ids(MASCOTA) == []
