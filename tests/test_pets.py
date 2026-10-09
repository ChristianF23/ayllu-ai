"""Tests de utils/pets.py sin PostgreSQL (pools falsos)."""
import pytest

import utils.database as database
from utils import pets
from utils.pets import (
    add_pet,
    link_product,
    listar_mascotas,
    normalizar_nombre_mascota,
    products_for_pet,
    unlink_product,
)

TIENDA = "mercadolibre.com.co"
URL_OK = "https://articulo.mercadolibre.com.co/MCO-123-comida-gato"
INVISIBLES = ["\u200b", "\u200c", "\u200d", "\u202e", "\ufeff", "\u00ad", "\U000E0041",
              "\u2028", "\u2029"]


class _PoolIntocable:
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


class _Contexto:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        return False


class _Transaccion:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        self.conn.transacciones += 1
        return self

    async def __aexit__(self, *exc):
        return False


class _ConexionFalsa:
    """Responde según el SQL y registra cada llamada (sql, args)."""

    def __init__(self, mascota=None, producto=None, filas=(), insert_id=None,
                 estado="UPDATE 1", mascotas=(), vinculos=()):
        self.mascota = mascota
        self.producto = producto
        self.filas = list(filas)
        self.insert_id = insert_id
        self.estado = estado
        self.mascotas = list(mascotas)
        self.vinculos = list(vinculos)
        self.llamadas = []
        self.transacciones = 0

    def transaction(self):
        return _Transaccion(self)

    async def fetchval(self, sql, *args):
        self.llamadas.append((sql, args))
        return self.insert_id

    async def fetchrow(self, sql, *args):
        self.llamadas.append((sql, args))
        if "FROM products" in sql:
            return self.producto
        return self.mascota

    async def fetch(self, sql, *args):
        self.llamadas.append((sql, args))
        if "FROM pet_products" in sql and "pp.pet_id = $1" in sql:
            return self.filas
        if "FROM pets" in sql:
            return self.mascotas
        return self.vinculos

    async def execute(self, sql, *args):
        self.llamadas.append((sql, args))
        return self.estado


class _PoolFalso:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return _Contexto(self.conn)


def _fila(id_, url=URL_OK, store=TIENDA, price=10000, **extra):
    return {"id": id_, "name": "Comida gato", "brand": "Marca", "description": None,
            "price": price, "currency": "COP", "url": url, "store": store, **extra}


MILU = {"id": 1, "name": "Milú", "species": "gato", "is_active": True}


# --- normalización ---

@pytest.mark.parametrize("entrada", ["Milú", "milu", " MILU ", "MILÚ", "Milu"])
def test_normalizar_milu_comparte_clave(entrada):
    visible, clave = normalizar_nombre_mascota(entrada)
    assert clave == "milu"
    assert visible == entrada.strip()


@pytest.mark.parametrize("entrada,clave", [
    ("Ñoño", "nono"),
    ("Don  Gato", "don gato"),
    ("Mía-2", "mia-2"),
    ("O'Malley", "o'malley"),
    ("Café con Leche", "cafe con leche"),
])
def test_normalizar_clave(entrada, clave):
    assert normalizar_nombre_mascota(entrada)[1] == clave


@pytest.mark.parametrize("invalido", [
    "", "   ", "a" * 51, None, 5, ["Milu"], "Milu!", "Milu.", "Mi/lu", "Mi_lu", "Milu\n",
    "Mi\tlu", "Milu;DROP", "<b>", "--", "'", "Mi lu", "１２３", "Milu😺",
    *[f"Mi{c}lu" for c in INVISIBLES],
])
def test_normalizar_rechaza_invalidos(invalido):
    with pytest.raises(ValueError):
        normalizar_nombre_mascota(invalido)


def test_normalizar_50_caracteres_es_valido():
    assert normalizar_nombre_mascota("a" * 50)[1] == "a" * 50


# --- validación antes de tocar la BD ---

@pytest.mark.parametrize("nombre,especie", [
    ("Milu!", "gato"), ("", "gato"), ("Milu", ""), ("Milu", "gato persa"), ("Milu", "g4to"),
    ("Milu", "x" * 31), ("Milu", None), ("Milu", "ga\u200bto"),
])
async def test_add_pet_invalido_lanza_antes_de_tocar_bd(monkeypatch, nombre, especie):
    monkeypatch.setattr(database, "DB_POOL", _PoolIntocable())
    with pytest.raises(ValueError):
        await add_pet(nombre, especie)


@pytest.mark.parametrize("funcion", [link_product, unlink_product])
@pytest.mark.parametrize("nombre,producto", [
    ("Milu!", 1), ("", 1), ("Milu", 0), ("Milu", -1), ("Milu", 2**63), ("Milu", "1"),
    ("Milu", True), ("Milu", 1.0), ("Milu", None),
])
async def test_vinculos_invalidos_lanzan_antes_de_tocar_bd(monkeypatch, funcion, nombre, producto):
    monkeypatch.setattr(database, "DB_POOL", _PoolIntocable())
    with pytest.raises(ValueError):
        await funcion(nombre, producto)


@pytest.mark.parametrize("invalido", ["", "Milu!", "a" * 51, None, "Mi\u202elu"])
async def test_products_for_pet_nombre_invalido_lanza_antes_de_tocar_bd(monkeypatch, invalido):
    monkeypatch.setattr(database, "DB_POOL", _PoolIntocable())
    with pytest.raises(ValueError):
        await products_for_pet(invalido)


@pytest.mark.parametrize("llamada", [
    lambda: add_pet("Milu", "gato"),
    lambda: link_product("Milu", 1),
    lambda: unlink_product("Milu", 1),
])
async def test_escritura_sin_pool_runtime_error(monkeypatch, llamada):
    monkeypatch.setattr(database, "DB_POOL", None)
    with pytest.raises(RuntimeError):
        await llamada()


# --- add_pet ---

async def test_add_pet_nueva(monkeypatch):
    conn = _ConexionFalsa(insert_id=9)
    monkeypatch.setattr(database, "DB_POOL", _PoolFalso(conn))
    assert await add_pet("  Milú ", " Gato ") == 9
    sql, args = conn.llamadas[0]
    assert "ON CONFLICT (name_key) DO NOTHING" in sql
    assert args == ("Milú", "milu", "gato")


async def test_add_pet_existente_inactiva_no_se_reactiva(monkeypatch, caplog):
    conn = _ConexionFalsa(insert_id=None, mascota={"id": 4, "is_active": False})
    monkeypatch.setattr(database, "DB_POOL", _PoolFalso(conn))
    with caplog.at_level("WARNING", logger="AylluPets"):
        assert await add_pet("milu", "gato") == 4
    assert any("no se reactiva" in r.getMessage() for r in caplog.records)
    assert not any("UPDATE" in sql for sql, _ in conn.llamadas)


# --- link / unlink ---

PRODUCTO_OK = {"producto_activo": True, "tienda_activa": True}


@pytest.mark.parametrize("mascota,producto,mensaje", [
    (None, PRODUCTO_OK, "mascota activa"),
    ({"id": 1, "is_active": False}, PRODUCTO_OK, "mascota activa"),
    ({"id": 1, "is_active": True}, None, "No existe el producto"),
    ({"id": 1, "is_active": True}, {"producto_activo": False, "tienda_activa": True}, "inactivo"),
    ({"id": 1, "is_active": True}, {"producto_activo": True, "tienda_activa": False}, "tienda"),
])
async def test_vinculo_rechazado_no_escribe(monkeypatch, mascota, producto, mensaje):
    conn = _ConexionFalsa(mascota=mascota, producto=producto)
    monkeypatch.setattr(database, "DB_POOL", _PoolFalso(conn))
    with pytest.raises(ValueError, match=mensaje):
        await link_product("Milu", 5)
    assert not any(sql.lstrip().startswith(("INSERT", "UPDATE")) for sql, _ in conn.llamadas)


async def test_link_product_ok(monkeypatch):
    conn = _ConexionFalsa(mascota={"id": 3, "is_active": True}, producto=PRODUCTO_OK)
    monkeypatch.setattr(database, "DB_POOL", _PoolFalso(conn))
    assert await link_product(" MILÚ ", 5) is True
    assert conn.transacciones == 1
    (sql_m, args_m), (sql_p, args_p), (sql_i, args_i) = conn.llamadas
    assert "FOR SHARE" in sql_m and args_m == ("milu",)
    assert "FOR SHARE" in sql_p and args_p == (5,)
    assert "ON CONFLICT (pet_id, product_id) DO UPDATE SET is_active = TRUE" in sql_i
    assert args_i == (3, 5)
    # Solo toca el vínculo: nunca la mascota ni el producto.
    assert "UPDATE pets" not in sql_i and "UPDATE products" not in sql_i


@pytest.mark.parametrize("estado,esperado", [("UPDATE 1", True), ("UPDATE 0", False)])
async def test_unlink_product(monkeypatch, estado, esperado):
    conn = _ConexionFalsa(estado=estado)
    monkeypatch.setattr(database, "DB_POOL", _PoolFalso(conn))
    assert await unlink_product(" MILÚ ", 5) is esperado
    # Una sola sentencia, sin transacción ni verificaciones de actividad.
    (sql, args), = conn.llamadas
    plano = " ".join(sql.split())
    assert plano.startswith("UPDATE pet_products pp SET is_active = FALSE FROM pets p")
    assert "pp.pet_id = p.id AND p.name_key = $1 AND pp.product_id = $2" in plano
    assert "is_active = TRUE" not in plano and "FOR SHARE" not in plano
    assert args == ("milu", 5)
    assert conn.transacciones == 0


@pytest.mark.parametrize("mascota,producto", [
    ({"id": 1, "is_active": False}, PRODUCTO_OK),
    ({"id": 1, "is_active": True}, {"producto_activo": False, "tienda_activa": True}),
    ({"id": 1, "is_active": True}, {"producto_activo": True, "tienda_activa": False}),
    (None, None),
])
async def test_unlink_no_exige_actividad(monkeypatch, mascota, producto):
    # Aunque la mascota, el producto o la tienda estén inactivos, se puede desvincular.
    conn = _ConexionFalsa(mascota=mascota, producto=producto, estado="UPDATE 1")
    monkeypatch.setattr(database, "DB_POOL", _PoolFalso(conn))
    assert await unlink_product("milu", 5) is True
    assert len(conn.llamadas) == 1


def test_normalizar_nfd_coincide_con_nfc():
    nfd = "Milu\u0301"  # u + acento agudo combinante
    visible, clave = normalizar_nombre_mascota(nfd)
    assert visible == "Milú"
    assert clave == normalizar_nombre_mascota("milu")[1] == "milu"


# --- products_for_pet ---

async def test_products_for_pet_sin_pool_none(monkeypatch, caplog):
    monkeypatch.setattr(database, "DB_POOL", None)
    with caplog.at_level("ERROR", logger="AylluPets"):
        assert await products_for_pet("Milu") is None
    assert any(r.levelname == "ERROR" for r in caplog.records)


async def test_products_for_pet_bd_caida_none(monkeypatch, caplog):
    monkeypatch.setattr(database, "DB_POOL", _PoolQueFalla())
    with caplog.at_level("ERROR", logger="AylluPets"):
        assert await products_for_pet("Milu") is None
    assert any(r.levelname == "ERROR" and r.name == "AylluPets" for r in caplog.records)


async def test_products_for_pet_desconocida_none(monkeypatch):
    conn = _ConexionFalsa(mascota=None)
    monkeypatch.setattr(database, "DB_POOL", _PoolFalso(conn))
    assert await products_for_pet("Milu") is None
    assert len(conn.llamadas) == 1  # no consulta productos


async def test_products_for_pet_sql_parametrizado_y_filtros(monkeypatch):
    conn = _ConexionFalsa(mascota=MILU, filas=[_fila(1)])
    monkeypatch.setattr(database, "DB_POOL", _PoolFalso(conn))
    await products_for_pet("Milú")
    (sql_m, args_m), (sql_p, args_p) = conn.llamadas
    assert args_m == ("milu",) and "milu" not in sql_m.lower().replace("name_key", "")
    plano = " ".join(sql_p.split())
    assert args_p == (1, 10)
    for filtro in ("pp.is_active = TRUE", "p.is_active = TRUE", "s.is_active = TRUE",
                   "ORDER BY p.price ASC, p.id", "LIMIT $2"):
        assert filtro in plano


async def test_products_for_pet_formato(monkeypatch):
    conn = _ConexionFalsa(mascota=MILU, filas=[_fila(1, price=44650, description="Digestivo")])
    monkeypatch.setattr(database, "DB_POOL", _PoolFalso(conn))
    resultado = await products_for_pet("milu")
    assert resultado == {"mascota": "Milú", "especie": "gato", "productos": [{
        "id": 1, "name": "Comida gato", "brand": "Marca", "description": "Digestivo",
        "price": 44650.0, "currency": "COP", "url": URL_OK, "store": TIENDA,
    }]}
    assert isinstance(resultado["productos"][0]["price"], float)


async def test_products_for_pet_sin_productos(monkeypatch):
    monkeypatch.setattr(database, "DB_POOL", _PoolFalso(_ConexionFalsa(mascota=MILU)))
    assert await products_for_pet("milu") == {"mascota": "Milú", "especie": "gato",
                                              "productos": []}


async def test_products_for_pet_revalida_url_e_invisibles(monkeypatch, caplog):
    filas = [
        _fila(1),
        _fila(2, url="https://evilmercadolibre.com.co/x"),
        _fila(3, url="http://articulo.mercadolibre.com.co/x"),
        _fila(4, name="Comida\u202egato"),
        _fila(5, brand="Mar\u200bca"),
        _fila(6, description="Oculto\nsalto"),
        _fila(7, brand=None),
    ]
    monkeypatch.setattr(database, "DB_POOL", _PoolFalso(_ConexionFalsa(mascota=MILU, filas=filas)))
    with caplog.at_level("WARNING", logger="AylluPets"):
        resultado = await products_for_pet("milu")
    assert [p["id"] for p in resultado["productos"]] == [1, 7]
    assert sum(r.levelname == "WARNING" for r in caplog.records) == 5


# --- listar_mascotas ---

async def test_listar_mascotas(monkeypatch):
    conn = _ConexionFalsa(
        mascotas=[MILU, {"id": 2, "name": "Tom", "species": "gato", "is_active": False}],
        vinculos=[{"pet_id": 1, "id": 419, "name": "Biodieta"}],
    )
    monkeypatch.setattr(database, "DB_POOL", _PoolFalso(conn))
    assert await listar_mascotas() == [
        {"id": 1, "name": "Milú", "species": "gato", "is_active": True,
         "productos": [{"id": 419, "name": "Biodieta"}]},
        {"id": 2, "name": "Tom", "species": "gato", "is_active": False, "productos": []},
    ]
    for sql, _ in conn.llamadas:
        for palabra in ("INSERT", "UPDATE", "DELETE"):
            assert palabra not in sql.upper()


async def test_listar_mascotas_falla_cerrado(monkeypatch):
    monkeypatch.setattr(database, "DB_POOL", None)
    assert await listar_mascotas() == []
    monkeypatch.setattr(database, "DB_POOL", _PoolQueFalla())
    assert await listar_mascotas() == []


def test_modulo_usa_logger_aylluPets():
    assert pets.logger.name == "AylluPets"
