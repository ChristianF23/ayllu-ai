"""Flujo real de scripts/cargar_producto.py contra PostgreSQL (marcador db)."""
import re

import pytest

import utils.database as database
from scripts import cargar_producto as cp
from utils.database import close_db_pool, init_db_pool

SUFIJO = ".cargar-prueba-ayllu.com.co"
TIENDA = f"tienda{SUFIJO}"
TIENDA_INACTIVA = f"inactiva{SUFIJO}"
PATRON = f"%{SUFIJO}"
MASCOTA = "Zqxcargamascota"
PATRON_MASCOTAS = "zqxcargamascota%"


async def _limpiar():
    """Abre su propio pool, borra los datos de prueba y lo cierra."""
    await init_db_pool()
    try:
        async with database.DB_POOL.acquire() as conn:
            await conn.execute(
                "DELETE FROM pet_products WHERE pet_id IN "
                "(SELECT id FROM pets WHERE name_key LIKE $1) "
                "OR product_id IN (SELECT id FROM products WHERE store_domain LIKE $2);",
                PATRON_MASCOTAS, PATRON,
            )
            await conn.execute("DELETE FROM pets WHERE name_key LIKE $1;", PATRON_MASCOTAS)
            await conn.execute("DELETE FROM products WHERE store_domain LIKE $1;", PATRON)
            await conn.execute("DELETE FROM allowed_stores WHERE domain LIKE $1;", PATRON)
    finally:
        await close_db_pool()


async def _consultar(sql, *args):
    await init_db_pool()
    try:
        async with database.DB_POOL.acquire() as conn:
            return await conn.fetchrow(sql, *args)
    finally:
        await close_db_pool()


@pytest.fixture
async def limpio():
    try:
        await _limpiar()
    except Exception as e:
        pytest.skip(f"PostgreSQL no disponible: {e}")
    try:
        yield
    finally:
        await _limpiar()


def _args(argv):
    return cp.construir_parser().parse_args(argv)


def _agregar_argv(url_sufijo, tienda=TIENDA, precio="44650", extra=()):
    return ["agregar", "--nombre", "Alimento gato prueba", "--marca", "MarcaPruebaCarga",
            "--precio", precio, "--url", f"https://{tienda}/{url_sufijo}",
            "--tienda", tienda, *extra]


@pytest.mark.db
async def test_flujo_crear_tienda_agregar_listar_desactivar(limpio, capsys):
    # Sin --crear-tienda la tienda no existe: falla con código 1.
    assert await cp.cmd_agregar(_args(_agregar_argv("a"))) == 1
    assert "no existe o está inactiva" in capsys.readouterr().err
    assert database.DB_POOL is None

    assert await cp.cmd_agregar(_args(_agregar_argv("a", extra=["--crear-tienda"]))) == 0
    salida = capsys.readouterr().out
    pid = int(re.search(r"id (\d+)", salida).group(1))
    assert "$44.650 COP" in salida
    assert database.DB_POOL is None

    fila = await _consultar("SELECT name, price, store_domain, is_active FROM products WHERE id = $1;", pid)
    assert fila["store_domain"] == TIENDA and fila["is_active"] is True

    assert await cp.cmd_listar(_args(["listar", "--consulta", "MarcaPruebaCarga"])) == 0
    salida = capsys.readouterr().out
    assert f"[{pid}] Alimento gato prueba | MarcaPruebaCarga | $44.650 COP | {TIENDA} | activo" in salida
    assert f"{TIENDA} | activa" in salida

    assert await cp.cmd_desactivar(_args(["desactivar", "--id", str(pid)])) == 0
    capsys.readouterr()
    assert await cp.cmd_listar(_args(["listar", "--consulta", "MarcaPruebaCarga"])) == 0
    assert f"[{pid}] Alimento gato prueba" in capsys.readouterr().out.split("Tiendas")[0]
    fila = await _consultar("SELECT is_active FROM products WHERE id = $1;", pid)
    assert fila["is_active"] is False
    assert database.DB_POOL is None


@pytest.mark.db
async def test_crear_tienda_no_reactiva_tienda_inactiva(limpio, capsys):
    await init_db_pool()
    try:
        async with database.DB_POOL.acquire() as conn:
            await conn.execute(
                "INSERT INTO allowed_stores (domain, is_active) VALUES ($1, FALSE);",
                TIENDA_INACTIVA,
            )
    finally:
        await close_db_pool()

    argv = _agregar_argv("b", tienda=TIENDA_INACTIVA, extra=["--crear-tienda"])
    assert await cp.cmd_agregar(_args(argv)) == 1
    assert "no existe o está inactiva" in capsys.readouterr().err
    fila = await _consultar("SELECT is_active FROM allowed_stores WHERE domain = $1;", TIENDA_INACTIVA)
    assert fila["is_active"] is False
    total = await _consultar("SELECT COUNT(*) AS n FROM products WHERE store_domain = $1;",
                             TIENDA_INACTIVA)
    assert total["n"] == 0


@pytest.mark.db
async def test_crear_tienda_con_url_de_otro_dominio_no_crea_tienda(limpio, capsys):
    tienda_typo = f"tiedna{SUFIJO}"
    argv = ["agregar", "--nombre", "Alimento gato prueba", "--precio", "44650",
            "--url", f"https://{TIENDA}/c", "--tienda", tienda_typo, "--crear-tienda"]
    assert await cp.cmd_agregar(_args(argv)) == 1
    assert "La URL no es https de la tienda" in capsys.readouterr().err
    fila = await _consultar(
        "SELECT COUNT(*) AS n FROM allowed_stores WHERE domain = ANY($1::text[]);",
        [tienda_typo, TIENDA],
    )
    assert fila["n"] == 0


@pytest.mark.db
async def test_desactivar_id_inexistente_sale_1(limpio, capsys):
    assert await cp.cmd_desactivar(_args(["desactivar", "--id", str(2**62)])) == 1
    assert "no existe" in capsys.readouterr().err


@pytest.mark.db
async def test_flujo_mascota_asignar_mascotas_desasignar(limpio, capsys):
    assert await cp.cmd_agregar(_args(_agregar_argv("pet", extra=["--crear-tienda"]))) == 0
    pid = int(re.search(r"id (\d+)", capsys.readouterr().out).group(1))

    assert await cp.cmd_mascota(_args(["mascota", "--nombre", MASCOTA, "--especie", "gato"])) == 0
    assert MASCOTA in capsys.readouterr().out
    assert database.DB_POOL is None

    # Mismo nombre con otra forma: avisa por stderr, código 0, no cambia la especie.
    argv = ["mascota", "--nombre", MASCOTA.lower(), "--especie", "perro"]
    assert await cp.cmd_mascota(_args(argv)) == 0
    err = capsys.readouterr().err
    assert "ya existía" in err and "especie gato" in err
    fila = await _consultar("SELECT species FROM pets WHERE name_key = $1;", MASCOTA.lower())
    assert fila["species"] == "gato"

    argv = ["asignar", "--mascota", MASCOTA.upper(), "--producto-id", str(pid)]
    assert await cp.cmd_asignar(_args(argv)) == 0
    assert "vinculado" in capsys.readouterr().out

    assert await cp.cmd_mascotas(_args(["mascotas"])) == 0
    salida = capsys.readouterr().out
    assert f"{MASCOTA} | gato | activa" in salida
    assert f"- [{pid}] Alimento gato prueba" in salida

    argv = ["desasignar", "--mascota", MASCOTA.lower(), "--producto-id", str(pid)]
    assert await cp.cmd_desasignar(_args(argv)) == 0
    assert await cp.cmd_mascotas(_args(["mascotas"])) == 0
    lineas = capsys.readouterr().out.splitlines()
    i = next(n for n, linea in enumerate(lineas) if f"{MASCOTA} | gato" in linea)
    assert lineas[i + 1].strip() == "(sin productos vinculados)"

    # Mascota inexistente o producto inexistente: código 1.
    argv = ["asignar", "--mascota", "Zqxcargamascotanada", "--producto-id", str(pid)]
    assert await cp.cmd_asignar(_args(argv)) == 1
    assert "mascota" in capsys.readouterr().err
    assert database.DB_POOL is None
