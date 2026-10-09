"""
deactivate_product desactiva también los vínculos mascota-producto, para que
un vínculo viejo no "resucite" cuando add_product reactiva el producto por url.
"""
import pytest

import utils.database as database
from utils.catalog import add_product, deactivate_product
from utils.database import close_db_pool, init_db_pool
from utils.pets import add_pet, link_product, products_for_pet

TIENDA = "desactivar-prueba-ayllu.com.co"
PATRON_MASCOTAS = "zqxdesactivar%"
MASCOTA = "Zqxdesactivar"


class _Conexion:
    def __init__(self, estado="UPDATE 1"):
        self.estado = estado
        self.llamadas = []

    async def execute(self, sql, *args):
        self.llamadas.append((sql, args))
        return self.estado


class _Contexto:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        return False


class _Pool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return _Contexto(self.conn)


@pytest.mark.parametrize("estado,esperado", [("UPDATE 1", True), ("UPDATE 0", False)])
async def test_sql_desactiva_producto_y_vinculos_en_una_sentencia(monkeypatch, estado, esperado):
    conn = _Conexion(estado)
    monkeypatch.setattr(database, "DB_POOL", _Pool(conn))
    assert await deactivate_product(7) is esperado
    (sql, args), = conn.llamadas  # una sola sentencia: atómica
    plano = " ".join(sql.split())
    assert "UPDATE pet_products SET is_active = FALSE WHERE product_id = $1" in plano
    assert "UPDATE products SET is_active = FALSE" in plano and "WHERE id = $1" in plano
    assert plano.startswith("WITH ")
    assert args == (7,)


# --- con PostgreSQL ---

async def _borrar():
    async with database.DB_POOL.acquire() as conn:
        await conn.execute(
            "DELETE FROM pet_products WHERE pet_id IN "
            "(SELECT id FROM pets WHERE name_key LIKE $1) "
            "OR product_id IN (SELECT id FROM products WHERE store_domain = $2);",
            PATRON_MASCOTAS, TIENDA,
        )
        await conn.execute("DELETE FROM pets WHERE name_key LIKE $1;", PATRON_MASCOTAS)
        await conn.execute("DELETE FROM products WHERE store_domain = $1;", TIENDA)
        await conn.execute("DELETE FROM allowed_stores WHERE domain = $1;", TIENDA)


@pytest.fixture
async def pool():
    try:
        await init_db_pool()
    except Exception as e:
        pytest.skip(f"PostgreSQL no disponible: {e}")
    await _borrar()
    async with database.DB_POOL.acquire() as conn:
        await conn.execute(
            "INSERT INTO allowed_stores (domain, is_active) VALUES ($1, TRUE);", TIENDA
        )
    try:
        yield database.DB_POOL
    finally:
        await _borrar()
        await close_db_pool()


async def _agregar(sufijo="a"):
    return await add_product("Alimento prueba", "Zqxmarca", 1000,
                             f"https://{TIENDA}/p-{sufijo}", TIENDA)


@pytest.mark.db
async def test_desactivar_producto_desactiva_sus_vinculos(pool):
    await add_pet(MASCOTA, "gato")
    pid = await _agregar()
    otro = await _agregar("b")
    await link_product(MASCOTA, pid)
    await link_product(MASCOTA, otro)

    assert await deactivate_product(pid) is True
    async with pool.acquire() as conn:
        filas = {r["product_id"]: r["is_active"] for r in await conn.fetch(
            "SELECT product_id, is_active FROM pet_products WHERE product_id = ANY($1::bigint[]);",
            [pid, otro],
        )}
    assert filas == {pid: False, otro: True}  # solo los vínculos de ese producto


@pytest.mark.db
async def test_reactivar_producto_no_resucita_vinculos(pool):
    await add_pet(MASCOTA, "gato")
    pid = await _agregar()
    await link_product(MASCOTA, pid)
    await deactivate_product(pid)

    # add_product reactiva el producto por url...
    assert await _agregar() == pid
    # ...pero el vínculo sigue inactivo hasta volver a asignarlo.
    assert (await products_for_pet(MASCOTA))["productos"] == []
    await link_product(MASCOTA, pid)
    assert [p["id"] for p in (await products_for_pet(MASCOTA))["productos"]] == [pid]
