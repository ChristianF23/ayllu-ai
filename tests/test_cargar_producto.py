"""Tests de scripts/cargar_producto.py sin PostgreSQL (catalog/database falsos)."""
from decimal import Decimal

import pytest

from scripts import cargar_producto as cp

ARGS_AGREGAR = [
    "agregar", "--nombre", "Alimento gato 3kg", "--marca", "MarcaEjemplo",
    "--precio", "44650", "--url", "https://tienda-ejemplo.com.co/alimento",
    "--tienda", "tienda-ejemplo.com.co",
]


class _Falsos:
    """Registra en orden las llamadas a database/catalog."""

    def __init__(self, add_product=None, deactivate=True, productos=(), tiendas=()):
        self.llamadas = []
        self._add_product = add_product
        self._deactivate = deactivate
        self._productos = list(productos)
        self._tiendas = list(tiendas)

    async def init_db_pool(self):
        self.llamadas.append(("init_db_pool",))

    async def close_db_pool(self):
        self.llamadas.append(("close_db_pool",))

    async def add_allowed_store(self, dominio):
        self.llamadas.append(("add_allowed_store", dominio))
        return dominio

    async def add_product(self, *args, **kwargs):
        self.llamadas.append(("add_product", *args, kwargs))
        if isinstance(self._add_product, BaseException):
            raise self._add_product
        return 7

    async def deactivate_product(self, pid):
        self.llamadas.append(("deactivate_product", pid))
        if isinstance(self._deactivate, BaseException):
            raise self._deactivate
        return self._deactivate

    async def listar_productos(self, incluir_inactivos=True):
        self.llamadas.append(("listar_productos", incluir_inactivos))
        return self._productos

    async def listar_tiendas(self):
        self.llamadas.append(("listar_tiendas",))
        return self._tiendas

    def nombres(self):
        return [ll[0] for ll in self.llamadas]


@pytest.fixture
def falsos(monkeypatch):
    def _instalar(**kw):
        f = _Falsos(**kw)
        for nombre in ("init_db_pool", "close_db_pool", "add_allowed_store"):
            monkeypatch.setattr(cp.database, nombre, getattr(f, nombre))
        for nombre in ("add_product", "deactivate_product", "listar_productos", "listar_tiendas"):
            monkeypatch.setattr(cp.catalog, nombre, getattr(f, nombre))
        return f
    return _instalar


def _args(argv):
    return cp.construir_parser().parse_args(argv)


# --- parsear_precio ---

@pytest.mark.parametrize("texto,esperado", [
    ("44650", Decimal("44650")),
    ("44650.5", Decimal("44650.5")),
    ("44650.50", Decimal("44650.50")),
    (" 1 ", Decimal("1")),
    ("44.65", Decimal("44.65")),
])
def test_parsear_precio_valido(texto, esperado):
    assert cp.parsear_precio(texto) == esperado


@pytest.mark.parametrize("texto", ["44.650", "$44.650", "1.234.567", "$44650", "1,5", "44,650"])
def test_parsear_precio_rechaza_separador_de_miles(texto):
    with pytest.raises(ValueError, match="separador de miles"):
        cp.parsear_precio(texto)


@pytest.mark.parametrize("texto", ["abc", "-1", "0", "0.00", "1e3", "", "1.234", "nan",
                                   "inf", "1.", ".5", "1 000",
                                   "٤٤٦٥٠", "４４６５０", "44650.٥"])
def test_parsear_precio_rechaza_invalidos(texto):
    with pytest.raises(ValueError):
        cp.parsear_precio(texto)


@pytest.mark.parametrize("precio,esperado", [
    (Decimal("44650"), "$44.650 COP"),
    (Decimal("44650.5"), "$44.650,50 COP"),
    (Decimal("1234567.89"), "$1.234.567,89 COP"),
    (Decimal("500"), "$500 COP"),
])
def test_formatear_precio(precio, esperado):
    assert cp.formatear_precio(precio, "COP") == esperado


# --- parser ---

def test_parser_agregar():
    args = _args(ARGS_AGREGAR + ["--crear-tienda"])
    assert args.subcomando == "agregar"
    assert args.nombre == "Alimento gato 3kg" and args.marca == "MarcaEjemplo"
    assert args.precio == "44650" and args.moneda == "COP"
    assert args.crear_tienda is True


def test_parser_valores_por_defecto():
    args = _args(["agregar", "--nombre", "N", "--precio", "1", "--url", "u", "--tienda", "t"])
    assert args.marca is None and args.moneda == "COP" and args.crear_tienda is False
    assert args.descripcion is None
    assert _args(["listar"]).consulta is None
    assert _args(["desactivar", "--id", "3"]).id == 3


@pytest.mark.parametrize("argv", [
    [],
    ["borrar"],
    ["agregar", "--nombre", "N"],
    ["desactivar", "--id", "abc"],
    ["desactivar"],
])
def test_main_error_de_uso_sale_con_1(falsos, argv, capsys):
    f = falsos()
    assert cp.main(argv) == 1
    assert f.llamadas == []  # no se toca la BD
    assert "Error de uso" in capsys.readouterr().err


# --- agregar ---

async def test_agregar_llama_add_product_con_argumentos_correctos(falsos, capsys):
    f = falsos()
    assert await cp.cmd_agregar(_args(ARGS_AGREGAR + ["--moneda", "USD"])) == 0
    assert f.llamadas == [
        ("init_db_pool",),
        ("add_product", "Alimento gato 3kg", "MarcaEjemplo", Decimal("44650"),
         "https://tienda-ejemplo.com.co/alimento", "tienda-ejemplo.com.co", "USD",
         {"description": None}),
        ("close_db_pool",),
    ]
    salida = capsys.readouterr().out
    assert "id 7" in salida and "$44.650 USD" in salida


async def test_agregar_crear_tienda_llama_add_allowed_store_antes(falsos, capsys):
    f = falsos()
    assert await cp.cmd_agregar(_args(ARGS_AGREGAR + ["--crear-tienda"])) == 0
    assert f.nombres() == ["init_db_pool", "add_allowed_store", "add_product", "close_db_pool"]
    assert f.llamadas[1] == ("add_allowed_store", "tienda-ejemplo.com.co")
    salida = capsys.readouterr().out
    assert "tienda-ejemplo.com.co" in salida and "NO se reactiva" in salida


async def test_agregar_sin_crear_tienda_no_registra_tienda(falsos):
    f = falsos()
    await cp.cmd_agregar(_args(ARGS_AGREGAR))
    assert "add_allowed_store" not in f.nombres()


async def test_agregar_value_error_sale_1_y_cierra_pool(falsos, capsys):
    f = falsos(add_product=ValueError("La tienda x no existe o está inactiva."))
    assert await cp.cmd_agregar(_args(ARGS_AGREGAR)) == 1
    assert f.nombres()[-1] == "close_db_pool"
    err = capsys.readouterr().err
    assert "no existe o está inactiva" in err and "Traceback" not in err


async def test_agregar_error_inesperado_sale_2_y_cierra_pool(falsos, capsys):
    f = falsos(add_product=RuntimeError("BD caída"))
    assert await cp.cmd_agregar(_args(ARGS_AGREGAR)) == 2
    assert f.nombres()[-1] == "close_db_pool"
    assert "Traceback" not in capsys.readouterr().err


async def test_agregar_cierra_pool_si_init_falla(falsos, monkeypatch):
    f = falsos()

    async def init_que_falla():
        raise ConnectionError("sin BD")

    monkeypatch.setattr(cp.database, "init_db_pool", init_que_falla)
    assert await cp.cmd_agregar(_args(ARGS_AGREGAR)) == 2
    assert f.nombres() == ["close_db_pool"]


@pytest.mark.parametrize("precio", ["44.650", "$44.650", "abc", "0"])
async def test_agregar_precio_invalido_sale_1_sin_tocar_bd(falsos, precio, capsys):
    f = falsos()
    argv = list(ARGS_AGREGAR)
    argv[argv.index("--precio") + 1] = precio
    assert await cp.cmd_agregar(_args(argv)) == 1
    assert f.llamadas == []
    assert "Error" in capsys.readouterr().err


def _con(argv, opcion, valor):
    argv = list(argv)
    if opcion not in argv:
        return argv + [opcion, valor]
    argv[argv.index(opcion) + 1] = valor
    return argv


@pytest.mark.parametrize("opcion,valor", [
    ("--url", "https://otra-tienda.com.co/alimento"),
    ("--url", "http://tienda-ejemplo.com.co/alimento"),
    ("--url", "https://evil-tienda-ejemplo.com.co/x"),
    ("--tienda", "tienda-ejemplo.com.co.evil.com"),
    ("--tienda", "127.0.0.1"),
    ("--nombre", "  "),
    ("--nombre", "Alimento​gato"),
    ("--marca", "M" * 101),
    ("--moneda", "cop"),
    ("--precio", "100000000.01"),
    ("--descripcion", "  "),
    ("--descripcion", "D" * 301),
    ("--descripcion", "Oculto\u202etexto"),
])
async def test_agregar_crear_tienda_invalido_no_registra_tienda(falsos, opcion, valor, capsys):
    f = falsos()
    argv = _con(ARGS_AGREGAR, opcion, valor) + ["--crear-tienda"]
    assert await cp.cmd_agregar(_args(argv)) == 1
    assert "add_allowed_store" not in f.nombres()
    assert f.llamadas == []  # ni siquiera se abre el pool
    assert "Error" in capsys.readouterr().err


async def test_agregar_falla_tras_crear_tienda_avisa_que_quedo_registrada(falsos, capsys):
    f = falsos(add_product=ValueError("La tienda tienda-ejemplo.com.co no existe o está inactiva."))
    assert await cp.cmd_agregar(_args(ARGS_AGREGAR + ["--crear-tienda"])) == 1
    assert f.nombres() == ["init_db_pool", "add_allowed_store", "add_product", "close_db_pool"]
    err = capsys.readouterr().err
    assert "tienda-ejemplo.com.co quedó registrada" in err and "listar" in err


async def test_agregar_falla_sin_crear_tienda_no_avisa_registro(falsos, capsys):
    falsos(add_product=ValueError("La tienda x no existe o está inactiva."))
    assert await cp.cmd_agregar(_args(ARGS_AGREGAR)) == 1
    assert "quedó registrada" not in capsys.readouterr().err


def test_main_agregar_devuelve_codigo(falsos):
    f = falsos()
    assert cp.main(ARGS_AGREGAR) == 0
    assert f.nombres() == ["init_db_pool", "add_product", "close_db_pool"]


async def test_agregar_descripcion_se_pasa_a_add_product(falsos, capsys):
    f = falsos()
    argv = ARGS_AGREGAR + ["--descripcion", "  Para gatos con digestión sensible. "]
    assert await cp.cmd_agregar(_args(argv)) == 0
    llamada = f.llamadas[1]
    assert llamada[0] == "add_product"
    assert llamada[-1] == {"description": "  Para gatos con digestión sensible. "}
    assert "Descripción: Para gatos con digestión sensible." in capsys.readouterr().out


def test_parser_descripcion():
    assert _args(ARGS_AGREGAR + ["--descripcion", "Texto"]).descripcion == "Texto"


# --- listar ---

def _producto(id_, nombre, marca, activo=True, descripcion=None):
    return {"id": id_, "name": nombre, "brand": marca, "description": descripcion,
            "price": Decimal("44650.00"),
            "currency": "COP", "url": "https://t.com.co/x", "store": "t.com.co",
            "is_active": activo}


async def test_listar_muestra_productos_y_tiendas(falsos, capsys):
    f = falsos(
        productos=[_producto(1, "Alimento gato", "MarcaA"), _producto(2, "Arena", None, False)],
        tiendas=[{"domain": "t.com.co", "is_active": True},
                 {"domain": "vieja.com.co", "is_active": False}],
    )
    assert await cp.cmd_listar(_args(["listar"])) == 0
    assert f.nombres() == ["init_db_pool", "listar_productos", "listar_tiendas", "close_db_pool"]
    assert ("listar_productos", True) in f.llamadas
    salida = capsys.readouterr().out
    assert "[1] Alimento gato | MarcaA | $44.650 COP | t.com.co | activo" in salida
    assert "[2] Arena | - | $44.650 COP | t.com.co | inactivo" in salida
    assert "t.com.co | activa" in salida and "vieja.com.co | inactiva" in salida


async def test_listar_muestra_descripcion(falsos, capsys):
    falsos(productos=[_producto(1, "Alimento gato", "MarcaA", descripcion="Para digestión sensible."),
                      _producto(2, "Arena", None)])
    assert await cp.cmd_listar(_args(["listar"])) == 0
    salida = capsys.readouterr().out
    assert "Para digestión sensible." in salida
    lineas = salida.splitlines()
    i = next(n for n, l in enumerate(lineas) if l.strip().startswith("[1]"))
    assert lineas[i + 1].strip() == "Para digestión sensible."
    j = next(n for n, l in enumerate(lineas) if l.strip().startswith("[2]"))
    assert not lineas[j + 1].startswith("      ")


async def test_listar_filtra_por_consulta(falsos, capsys):
    falsos(productos=[_producto(1, "Alimento GATO", None), _producto(2, "Arena", "GatoMarca"),
                      _producto(3, "Snack perro", None)])
    assert await cp.cmd_listar(_args(["listar", "--consulta", "gato"])) == 0
    salida = capsys.readouterr().out
    assert "[1]" in salida and "[2]" in salida and "[3]" not in salida


async def test_listar_error_inesperado_sale_2_y_cierra_pool(falsos, monkeypatch):
    f = falsos()

    async def falla(incluir_inactivos=True):
        raise RuntimeError("x")

    monkeypatch.setattr(cp.catalog, "listar_productos", falla)
    assert await cp.cmd_listar(_args(["listar"])) == 2
    assert f.nombres()[-1] == "close_db_pool"


# --- desactivar ---

async def test_desactivar_ok(falsos, capsys):
    f = falsos(deactivate=True)
    assert await cp.cmd_desactivar(_args(["desactivar", "--id", "5"])) == 0
    assert f.llamadas == [("init_db_pool",), ("deactivate_product", 5), ("close_db_pool",)]
    assert "desactivado" in capsys.readouterr().out


async def test_desactivar_inexistente_sale_1(falsos, capsys):
    f = falsos(deactivate=False)
    assert await cp.cmd_desactivar(_args(["desactivar", "--id", "5"])) == 1
    assert f.nombres()[-1] == "close_db_pool"
    assert "no existe" in capsys.readouterr().err


async def test_desactivar_id_invalido_sale_1_y_cierra_pool(falsos):
    f = falsos(deactivate=ValueError("El id del producto debe estar entre 1 y ..."))
    assert await cp.cmd_desactivar(_args(["desactivar", "--id", "0"])) == 1
    assert f.nombres()[-1] == "close_db_pool"


async def test_desactivar_error_inesperado_sale_2(falsos):
    f = falsos(deactivate=RuntimeError("x"))
    assert await cp.cmd_desactivar(_args(["desactivar", "--id", "5"])) == 2
    assert f.nombres()[-1] == "close_db_pool"
