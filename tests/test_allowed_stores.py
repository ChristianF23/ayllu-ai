import pytest

import utils.database as database
from utils.database import (
    add_allowed_store,
    close_db_pool,
    get_allowed_domains,
    init_db_pool,
)

DOMINIO_PRUEBA = "tienda-prueba-ayllu.com.co"
DOMINIO_INACTIVO = "tienda-inactiva-ayllu.com.co"


async def test_get_allowed_domains_sin_pool_falla_cerrado(monkeypatch, caplog):
    monkeypatch.setattr(database, "DB_POOL", None)
    with caplog.at_level("ERROR", logger="AylluDB"):
        assert await get_allowed_domains() == []
    assert any(r.levelname == "ERROR" for r in caplog.records)


class _ContextoQueFalla:
    async def __aenter__(self):
        raise ConnectionError("BD caída")

    async def __aexit__(self, *exc):
        return False


class _PoolQueFalla:
    def acquire(self):
        return _ContextoQueFalla()


async def test_get_allowed_domains_bd_caida_falla_cerrado(monkeypatch, caplog):
    monkeypatch.setattr(database, "DB_POOL", _PoolQueFalla())
    with caplog.at_level("ERROR", logger="AylluDB"):
        assert await get_allowed_domains() == []
    assert any(r.levelname == "ERROR" for r in caplog.records)


async def test_add_allowed_store_invalido_lanza_antes_de_tocar_bd(monkeypatch):
    monkeypatch.setattr(database, "DB_POOL", None)
    with pytest.raises(ValueError):
        await add_allowed_store("https://evil.com/")


@pytest.fixture
async def pool():
    try:
        await init_db_pool()
    except Exception as e:
        pytest.skip(f"PostgreSQL no disponible: {e}")
    await _borrar_dominios_de_prueba()
    try:
        yield database.DB_POOL
    finally:
        await _borrar_dominios_de_prueba()
        await close_db_pool()


async def _borrar_dominios_de_prueba():
    async with database.DB_POOL.acquire() as conn:
        await conn.execute(
            "DELETE FROM allowed_stores WHERE domain = ANY($1::text[]);",
            [DOMINIO_PRUEBA, DOMINIO_INACTIVO],
        )


@pytest.mark.db
async def test_semilla_existe(pool):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT is_active FROM allowed_stores WHERE domain = 'mercadolibre.com.co';"
        )
    assert row is not None


@pytest.mark.db
async def test_semilla_es_idempotente(pool):
    async with pool.acquire() as conn:
        await database._seed_allowed_stores(conn)
        await database._seed_allowed_stores(conn)
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM allowed_stores WHERE domain = 'mercadolibre.com.co';"
        )
    assert total == 1


@pytest.mark.db
async def test_add_allowed_store_normaliza_e_inserta(pool):
    guardado = await add_allowed_store("  Tienda-Prueba-AYLLU.com.co.  ")
    assert guardado == DOMINIO_PRUEBA
    assert DOMINIO_PRUEBA in await get_allowed_domains()
    # Repetir no duplica ni falla
    await add_allowed_store(DOMINIO_PRUEBA)
    assert (await get_allowed_domains()).count(DOMINIO_PRUEBA) == 1


@pytest.mark.db
async def test_get_allowed_domains_ordenados(pool):
    await add_allowed_store(DOMINIO_PRUEBA)
    dominios = await get_allowed_domains()
    assert dominios == sorted(dominios)


@pytest.mark.db
@pytest.mark.parametrize("invalido", [
    "", "https://mercadolibre.com.co", "mercadolibre.com.co/ruta",
    "mercadolibre.com.co:443", "127.0.0.1", "mal dominio.com",
])
async def test_add_allowed_store_rechaza_invalidos(pool, invalido):
    antes = await get_allowed_domains()
    with pytest.raises(ValueError):
        await add_allowed_store(invalido)
    assert await get_allowed_domains() == antes


@pytest.mark.db
async def test_tienda_inactiva_no_aparece_ni_se_reactiva(pool, monkeypatch):
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO allowed_stores (domain, is_active) VALUES ($1, FALSE);",
            DOMINIO_INACTIVO,
        )
    assert DOMINIO_INACTIVO not in await get_allowed_domains()

    # Aunque sea semilla, reiniciar la semilla no la reactiva
    monkeypatch.setattr(database, "SEED_ALLOWED_STORES", (DOMINIO_INACTIVO,))
    async with pool.acquire() as conn:
        await database._seed_allowed_stores(conn)
        activo = await conn.fetchval(
            "SELECT is_active FROM allowed_stores WHERE domain = $1;", DOMINIO_INACTIVO
        )
    assert activo is False
    assert DOMINIO_INACTIVO not in await get_allowed_domains()

    # Tampoco add_allowed_store la reactiva en silencio
    await add_allowed_store(DOMINIO_INACTIVO)
    assert DOMINIO_INACTIVO not in await get_allowed_domains()


@pytest.mark.db
async def test_add_allowed_store_loguea_estado_real(pool, caplog):
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO allowed_stores (domain, is_active) VALUES ($1, FALSE);",
            DOMINIO_INACTIVO,
        )
    with caplog.at_level("INFO", logger="AylluDB"):
        assert await add_allowed_store(DOMINIO_INACTIVO) == DOMINIO_INACTIVO
        assert await add_allowed_store(DOMINIO_PRUEBA) == DOMINIO_PRUEBA

    mensajes = [r.getMessage() for r in caplog.records]
    assert any("inactiva" in m and "no se reactiva" in m and DOMINIO_INACTIVO in m
               for m in mensajes)
    assert not any("registrada" in m and DOMINIO_INACTIVO in m for m in mensajes)
    assert any("registrada y activa" in m and DOMINIO_PRUEBA in m for m in mensajes)
    async with pool.acquire() as conn:
        activo = await conn.fetchval(
            "SELECT is_active FROM allowed_stores WHERE domain = $1;", DOMINIO_INACTIVO
        )
    assert activo is False


async def test_close_db_pool_deja_pool_en_none(monkeypatch):
    class _PoolFalso:
        cerrado = False

        async def close(self):
            self.cerrado = True

    falso = _PoolFalso()
    monkeypatch.setattr(database, "DB_POOL", falso)
    await close_db_pool()
    assert falso.cerrado is True
    assert database.DB_POOL is None
