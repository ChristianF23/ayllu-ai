"""Tests del catálogo sin PostgreSQL (pools falsos)."""
import re
from decimal import Decimal

import pytest

import utils.database as database
from utils import catalog
from utils.catalog import _escapar_like, add_product, search_products

TIENDA = "mercadolibre.com.co"
URL_OK = "https://articulo.mercadolibre.com.co/MCO-123-comida-gato"


class _PoolIntocable:
    """Falla el test si alguien intenta usar la BD."""

    def acquire(self):
        raise AssertionError("Se tocó la BD antes de validar")


class _ContextoQueFalla:
    async def __aenter__(self):
        raise ConnectionError("BD caída")

    async def __aexit__(self, *exc):
        return False


class _PoolQueFalla:
    def acquire(self):
        return _ContextoQueFalla()


class _ConexionFalsa:
    def __init__(self, filas):
        self.filas = filas
        self.llamadas = []

    async def fetch(self, sql, *args):
        self.llamadas.append((sql, args))
        return self.filas


class _Contexto:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        return False


class _PoolFalso:
    def __init__(self, filas=()):
        self.conn = _ConexionFalsa(list(filas))

    def acquire(self):
        return _Contexto(self.conn)


def _fila(id_, url, store=TIENDA, price=Decimal("10000.00")):
    return {"id": id_, "name": "Comida gato", "brand": "Marca", "price": price,
            "currency": "COP", "url": url, "store": store}


# --- add_product: validaciones antes de tocar la BD ---

def _kwargs(**cambios):
    base = dict(name="Comida gato 3kg", brand="Marca", price=Decimal("85000"),
                url=URL_OK, store_domain=TIENDA, currency="COP")
    base.update(cambios)
    return base


INVISIBLES = ["​", "‮", "\U000E0041", "﻿", "­"]


@pytest.mark.parametrize("cambios", [
    {"price": 0},
    {"price": "0"},
    {"price": Decimal("0.00")},
    {"price": 0.004},
    {"price": "0.004"},
    {"price": 1e-7},
    {"price": Decimal("85000.001")},
    {"price": -1},
    {"price": Decimal("-0.01")},
    {"price": float("nan")},
    {"price": float("inf")},
    {"price": float("-inf")},
    {"price": Decimal("NaN")},
    {"price": Decimal("Infinity")},
    {"price": "NaN"},
    {"price": "inf"},
    {"price": "abc"},
    {"price": "10,5"},
    {"price": ""},
    {"price": "1e9"},
    {"price": 100_000_000.01},
    {"price": True},
    {"price": None},
    {"price": [1]},
    {"name": "Comida\ngato"},
    {"name": "Comida\x00gato"},
    {"name": ""},
    {"name": "   "},
    {"name": "a" * 201},
    {"name": None},
    {"brand": "Mar\nca"},
    {"brand": "b" * 101},
    {"url": "http://articulo.mercadolibre.com.co/MCO-123"},
    {"url": "https://amazon.com/producto"},
    {"url": "https://evilmercadolibre.com.co/MCO-123"},
    {"url": "https://mercadolibre.com.co.evil.com/MCO-123"},
    {"url": "https://user@mercadolibre.com.co/x"},
    {"url": ""},
    {"currency": "cop"},
    {"currency": "CO"},
    {"currency": "COPP"},
    {"currency": "C0P"},
    {"currency": None},
    {"store_domain": "https://mercadolibre.com.co"},
    {"store_domain": "127.0.0.1"},
])
async def test_add_product_invalido_lanza_antes_de_tocar_bd(monkeypatch, cambios):
    monkeypatch.setattr(database, "DB_POOL", _PoolIntocable())
    with pytest.raises(ValueError):
        await add_product(**_kwargs(**cambios))


@pytest.mark.parametrize("invisible", INVISIBLES)
@pytest.mark.parametrize("campo", ["name", "brand", "url", "store_domain"])
async def test_add_product_rechaza_unicode_invisible(monkeypatch, campo, invisible):
    monkeypatch.setattr(database, "DB_POOL", _PoolIntocable())
    valor = _kwargs()[campo]
    # Insertado en medio (en la url, dentro de la ruta, donde is_url_allowed no mira).
    mitad = len(valor) - 3
    with pytest.raises(ValueError):
        await add_product(**_kwargs(**{campo: valor[:mitad] + invisible + valor[mitad:]}))


@pytest.mark.parametrize("separador", [" ", " "])
async def test_add_product_rechaza_separadores_de_linea_unicode(monkeypatch, separador):
    monkeypatch.setattr(database, "DB_POOL", _PoolIntocable())
    with pytest.raises(ValueError):
        await add_product(**_kwargs(name=f"Comida{separador}gato"))


async def test_add_product_url_demasiado_larga(monkeypatch):
    monkeypatch.setattr(database, "DB_POOL", _PoolIntocable())
    base = "https://articulo.mercadolibre.com.co/"
    with pytest.raises(ValueError):
        await add_product(**_kwargs(url=base + "a" * (2001 - len(base))))
    # Exactamente 2000 pasa la validación y llega al chequeo del pool.
    monkeypatch.setattr(database, "DB_POOL", None)
    with pytest.raises(RuntimeError):
        await add_product(**_kwargs(url=base + "a" * (2000 - len(base))))


@pytest.mark.parametrize("precio", [0.01, 1, 85000, 85000.5, "85000.50",
                                    Decimal("85000.10"), Decimal("100000000")])
async def test_add_product_precios_validos_pasan_validacion(monkeypatch, precio):
    # Con datos válidos y sin pool se llega al chequeo del pool (RuntimeError).
    monkeypatch.setattr(database, "DB_POOL", None)
    with pytest.raises(RuntimeError):
        await add_product(**_kwargs(price=precio, brand=None))


async def test_add_product_sin_pool_runtime_error(monkeypatch):
    monkeypatch.setattr(database, "DB_POOL", None)
    with pytest.raises(RuntimeError):
        await add_product(**_kwargs())


@pytest.mark.parametrize("invalido", ["1", True, 1.0, None, 0, -1, 2**63, 10**30])
async def test_deactivate_product_id_invalido(monkeypatch, invalido):
    monkeypatch.setattr(database, "DB_POOL", _PoolIntocable())
    with pytest.raises(ValueError):
        await catalog.deactivate_product(invalido)


# --- add_product / deactivate_product con conexión falsa (sin PostgreSQL) ---

class _Transaccion:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        self.conn.transacciones += 1
        return self

    async def __aexit__(self, *exc):
        return False


class _ConexionEscritura:
    def __init__(self, tienda_activa=True, id_devuelto=42, estado_update="UPDATE 1"):
        self.tienda_activa = tienda_activa
        self.id_devuelto = id_devuelto
        self.estado_update = estado_update
        self.fetchval_llamadas = []
        self.execute_llamadas = []
        self.transacciones = 0

    def transaction(self):
        return _Transaccion(self)

    async def fetchval(self, sql, *args):
        self.fetchval_llamadas.append((sql, args))
        if "allowed_stores" in sql:
            return self.tienda_activa
        return self.id_devuelto

    async def fetchrow(self, sql, *args):
        raise AssertionError("fetchrow no esperado")

    async def fetch(self, sql, *args):
        raise AssertionError("fetch no esperado")

    async def execute(self, sql, *args):
        self.execute_llamadas.append((sql, args))
        return self.estado_update


class _PoolEscritura:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return _Contexto(self.conn)


@pytest.mark.parametrize("tienda_activa", [None, False])
async def test_add_product_tienda_inexistente_o_inactiva_no_hace_upsert(monkeypatch, tienda_activa):
    conn = _ConexionEscritura(tienda_activa=tienda_activa)
    monkeypatch.setattr(database, "DB_POOL", _PoolEscritura(conn))
    with pytest.raises(ValueError):
        await add_product(**_kwargs())
    assert len(conn.fetchval_llamadas) == 1
    assert not any("INSERT INTO products" in sql for sql, _ in conn.fetchval_llamadas)


async def test_add_product_camino_feliz(monkeypatch):
    conn = _ConexionEscritura(tienda_activa=True, id_devuelto=7)
    monkeypatch.setattr(database, "DB_POOL", _PoolEscritura(conn))
    pid = await add_product(**_kwargs(name="  Comida gato 3kg ", store_domain="MercadoLibre.com.co.",
                                      price="85000.50"))
    assert pid == 7
    assert conn.transacciones == 1
    (sql_tienda, args_tienda), (sql_upsert, args_upsert) = conn.fetchval_llamadas
    assert "allowed_stores" in sql_tienda and args_tienda == (TIENDA,)
    assert "INSERT INTO products" in sql_upsert
    assert "store_domain = EXCLUDED.store_domain" in sql_upsert
    assert args_upsert == ("Comida gato 3kg", "Marca", Decimal("85000.50"), "COP", URL_OK, TIENDA)


@pytest.mark.parametrize("estado,esperado", [("UPDATE 1", True), ("UPDATE 0", False)])
async def test_deactivate_product_con_conexion_falsa(monkeypatch, estado, esperado):
    conn = _ConexionEscritura(estado_update=estado)
    monkeypatch.setattr(database, "DB_POOL", _PoolEscritura(conn))
    assert await catalog.deactivate_product(5) is esperado
    (sql, args), = conn.execute_llamadas
    assert "is_active = FALSE" in sql and args == (5,)


async def test_deactivate_product_sin_pool_runtime_error(monkeypatch):
    monkeypatch.setattr(database, "DB_POOL", None)
    with pytest.raises(RuntimeError):
        await catalog.deactivate_product(1)


# --- _escapar_like ---

@pytest.mark.parametrize("entrada,esperado", [
    ("gato", "gato"),
    ("100%", "100\\%"),
    ("a_b", "a\\_b"),
    ("c:\\x", "c:\\\\x"),
    ("\\%_", "\\\\\\%\\_"),
    ("", ""),
])
def test_escapar_like(entrada, esperado):
    assert _escapar_like(entrada) == esperado


# --- search_products ---

@pytest.mark.parametrize("query", ["", "   ", "a" * 101, "comida\ngato",
                                   "comida\tgato", "x\x00", None, 123])
async def test_search_query_invalida_lanza(monkeypatch, query):
    monkeypatch.setattr(database, "DB_POOL", _PoolIntocable())
    with pytest.raises(ValueError):
        await search_products(query)


async def test_search_sin_pool_falla_cerrado(monkeypatch, caplog):
    monkeypatch.setattr(database, "DB_POOL", None)
    with caplog.at_level("ERROR", logger="AylluCatalog"):
        assert await search_products("gato") == []
    assert any(r.levelname == "ERROR" for r in caplog.records)


async def test_search_bd_caida_falla_cerrado(monkeypatch, caplog):
    monkeypatch.setattr(database, "DB_POOL", _PoolQueFalla())
    with caplog.at_level("ERROR", logger="AylluCatalog"):
        assert await search_products("gato") == []
    assert any(r.levelname == "ERROR" and r.name == "AylluCatalog" for r in caplog.records)


@pytest.mark.parametrize("pedido,esperado", [(0, 1), (-5, 1), (1, 1), (5, 5),
                                             (10, 10), (11, 10), (1000, 10)])
async def test_search_max_results_acotado(monkeypatch, pedido, esperado):
    pool = _PoolFalso()
    monkeypatch.setattr(database, "DB_POOL", pool)
    await search_products("gato", max_results=pedido)
    _, args = pool.conn.llamadas[0]
    assert args[-1] == esperado


async def test_search_tokens_parametrizados_y_escapados(monkeypatch):
    pool = _PoolFalso()
    monkeypatch.setattr(database, "DB_POOL", pool)
    await search_products("  Gato 100% a_b uno dos tres cuatro cinco  ")
    sql, args = pool.conn.llamadas[0]
    # Máximo 6 tokens + el límite; los datos nunca van en el SQL.
    assert list(args[:-1]) == ["%Gato%", "%100\\%%", "%a\\_b%", "%uno%", "%dos%", "%tres%"]
    assert "Gato" not in sql and "100" not in sql
    assert "ESCAPE '\\'" in sql


@pytest.mark.parametrize("query,n_tokens", [("gato", 1), ("a b c d e f", 6),
                                            ("a b c d e f g h", 6)])
async def test_search_placeholders_coinciden_con_parametros(monkeypatch, query, n_tokens):
    pool = _PoolFalso()
    monkeypatch.setattr(database, "DB_POOL", pool)
    await search_products(query)
    sql, args = pool.conn.llamadas[0]
    placeholders = set(re.findall(r"\$(\d+)", sql))
    assert placeholders == {str(i) for i in range(1, len(args) + 1)}
    assert len(args) == n_tokens + 1
    # Cada token usa ESCAPE '\' exactamente (en name y en brand).
    assert sql.count("ESCAPE '\\'") == 2 * n_tokens
    assert "ESCAPE '\\\\'" not in sql


@pytest.mark.parametrize("invisible", INVISIBLES + [" ", " "])
async def test_search_query_con_unicode_invisible_lanza(monkeypatch, invisible):
    monkeypatch.setattr(database, "DB_POOL", _PoolIntocable())
    with pytest.raises(ValueError):
        await search_products(f"comida{invisible}gato")


async def test_search_devuelve_dicts_con_precio_float(monkeypatch):
    monkeypatch.setattr(database, "DB_POOL", _PoolFalso([_fila(1, URL_OK)]))
    resultado = await search_products("gato")
    assert resultado == [{"id": 1, "name": "Comida gato", "brand": "Marca",
                          "price": 10000.0, "currency": "COP", "url": URL_OK,
                          "store": TIENDA}]
    assert isinstance(resultado[0]["price"], float)


async def test_search_descarta_url_fuera_de_la_tienda(monkeypatch, caplog):
    filas = [
        _fila(1, URL_OK),
        _fila(2, "https://evilmercadolibre.com.co/MCO-1"),
        _fila(3, "http://articulo.mercadolibre.com.co/MCO-2"),
        _fila(4, "https://amazon.com/x"),
    ]
    monkeypatch.setattr(database, "DB_POOL", _PoolFalso(filas))
    with caplog.at_level("WARNING", logger="AylluCatalog"):
        resultado = await search_products("gato")
    assert [r["id"] for r in resultado] == [1]
    assert sum(r.levelname == "WARNING" for r in caplog.records) == 3
