"""
Herramienta de línea de comandos para que EL USUARIO cargue el catálogo.

Es la única vía de escritura del catálogo: NO se expone al bot, a Telegram
ni al LLM. Se ejecuta a mano dentro del contenedor (la conexión a la BD sale
de las variables de entorno del contenedor, vía utils.database).

Ejemplos (producto y tienda ficticios):

    docker exec ayllu_app python -m scripts.cargar_producto agregar \\
        --nombre "Alimento gato adulto 3kg" --marca "MarcaEjemplo" \\
        --precio 44650 --url "https://tienda-ejemplo.com.co/alimento-gato-3kg" \\
        --tienda tienda-ejemplo.com.co --crear-tienda

    docker exec ayllu_app python -m scripts.cargar_producto listar --consulta gato
    docker exec ayllu_app python -m scripts.cargar_producto desactivar --id 3

Mascotas y vínculo explícito mascota-producto (nombres ficticios):

    docker exec ayllu_app python -m scripts.cargar_producto mascota --nombre Michi --especie gato
    docker exec ayllu_app python -m scripts.cargar_producto asignar --mascota michi --producto-id 3
    docker exec ayllu_app python -m scripts.cargar_producto desasignar --mascota michi --producto-id 3
    docker exec ayllu_app python -m scripts.cargar_producto mascotas

El precio se escribe como número con punto decimal (44650 o 44650.50), sin
símbolo ni separador de miles. Códigos de salida: 0 ok, 1 error de
validación o de uso, 2 error inesperado.
"""
import argparse
import asyncio
import logging
import re
import sys
from decimal import Decimal

from utils import catalog, database, pets
from utils.domain_allowlist import is_url_allowed, normalize_domain

logger = logging.getLogger("AylluCargaProducto")

# Solo dígitos ASCII: \d aceptaría dígitos Unicode (ej. arábigo-índicos).
_PRECIO = re.compile(r"[0-9]+(\.[0-9]{1,2})?")
# "44.650", "1.234.567": punto como separador de miles (formato colombiano).
_MILES_CON_PUNTO = re.compile(r"[0-9]{1,3}(\.[0-9]{3})+")
_MONEDA = re.compile(r"[A-Z]{3}")
_MAX_URL = 2000

_MENSAJE_MILES = (
    "El precio {texto!r} parece llevar símbolo o separador de miles. "
    "Escríbelo como número sin símbolo ni separador de miles, con punto "
    "decimal si hace falta (ej. 44650 o 44650.50)."
)


class _Parser(argparse.ArgumentParser):
    """ArgumentParser que sale con código 1 (no 2) ante un error de uso."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f"Error de uso: {message}\n")


def parsear_precio(texto: str) -> Decimal:
    """
    Convierte el texto del precio a Decimal. Lanza ValueError con mensaje en
    español si no es un número positivo con punto decimal (máx. 2 decimales).
    No adivina formatos con separador de miles: los rechaza.
    """
    if not isinstance(texto, str):
        raise ValueError("El precio debe ser texto.")
    limpio = texto.strip()
    if "$" in limpio or "," in limpio or _MILES_CON_PUNTO.fullmatch(limpio):
        raise ValueError(_MENSAJE_MILES.format(texto=texto))
    if not _PRECIO.fullmatch(limpio):
        raise ValueError(
            f"Precio inválido: {texto!r}. Usa un número positivo con punto "
            "decimal y como máximo 2 decimales (ej. 44650 o 44650.50)."
        )
    valor = Decimal(limpio)
    if valor <= 0:
        raise ValueError("El precio debe ser mayor que cero.")
    return valor


def prevalidar_agregar(args, precio: Decimal) -> str:
    """
    Repite en código, sin tocar la BD, las validaciones de catalog.add_product
    (nombre, marca, descripción, precio, moneda, tienda y que la URL sea https de esa
    tienda). Así --crear-tienda no registra un dominio por un comando que
    luego fallaría. Devuelve la tienda normalizada; lanza ValueError.
    """
    catalog._validar_texto(args.nombre, "El nombre", catalog._MAX_NOMBRE)
    if args.marca is not None:
        catalog._validar_texto(args.marca, "La marca", catalog._MAX_MARCA)
    if args.descripcion is not None:
        catalog._validar_texto(args.descripcion, "La descripción", catalog._MAX_DESCRIPCION)
    catalog._validar_precio(precio)
    if not _MONEDA.fullmatch(args.moneda):
        raise ValueError(f"Moneda inválida: {args.moneda!r} (3 letras mayúsculas).")
    catalog._rechazar_invisibles(args.tienda, "La tienda")
    tienda = normalize_domain(args.tienda)
    if len(args.url) > _MAX_URL:
        raise ValueError(f"La URL supera {_MAX_URL} caracteres.")
    catalog._rechazar_invisibles(args.url, "La URL")
    if not is_url_allowed(args.url, [tienda]):
        raise ValueError(f"La URL no es https de la tienda {tienda}: {args.url!r}")
    return tienda


def formatear_precio(precio, moneda: str) -> str:
    """Solo para mostrar: Decimal('44650.5') -> '$44.650,50 COP'."""
    valor = Decimal(str(precio)).quantize(Decimal("0.01"))
    entero, centavos = f"{valor:.2f}".split(".")
    entero = f"{int(entero):,}".replace(",", ".")
    texto = entero if centavos == "00" else f"{entero},{centavos}"
    return f"${texto} {moneda}"


def construir_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="python -m scripts.cargar_producto",
        description="Carga y mantenimiento manual del catálogo de productos.",
    )
    sub = parser.add_subparsers(dest="subcomando", required=True)

    agregar = sub.add_parser("agregar", help="Agrega o actualiza (por url) un producto.")
    agregar.add_argument("--nombre", required=True)
    agregar.add_argument("--marca", default=None)
    agregar.add_argument("--precio", required=True,
                         help="Número con punto decimal, sin separador de miles (ej. 44650).")
    agregar.add_argument("--url", required=True)
    agregar.add_argument("--tienda", required=True, help="Dominio de la tienda.")
    agregar.add_argument("--moneda", default="COP")
    agregar.add_argument("--descripcion", default=None,
                         help="Descripción opcional (máx. 300 caracteres). Si se omite, "
                              "se conserva la que ya tenga el producto.")
    agregar.add_argument("--crear-tienda", action="store_true",
                         help="Registra la tienda si no existe (no reactiva una inactiva).")

    listar = sub.add_parser("listar", help="Lista productos y tiendas.")
    listar.add_argument("--consulta", default=None,
                        help="Filtra productos cuyo nombre o marca contengan este texto.")

    desactivar = sub.add_parser("desactivar", help="Desactiva un producto por id.")
    desactivar.add_argument("--id", type=int, required=True)

    mascota = sub.add_parser("mascota", help="Registra una mascota (no reactiva una inactiva).")
    mascota.add_argument("--nombre", required=True)
    mascota.add_argument("--especie", required=True, help="Ej. gato, perro.")

    for nombre, ayuda in (("asignar", "Vincula un producto a una mascota."),
                          ("desasignar", "Desactiva el vínculo de un producto con una mascota.")):
        vinculo = sub.add_parser(nombre, help=ayuda)
        vinculo.add_argument("--mascota", required=True)
        vinculo.add_argument("--producto-id", type=int, required=True)

    sub.add_parser("mascotas", help="Lista las mascotas con sus productos vinculados.")

    return parser


async def cmd_agregar(args) -> int:
    # Validación completa ANTES de tocar la BD (y antes de crear la tienda).
    try:
        precio = parsear_precio(args.precio)
        prevalidar_agregar(args, precio)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    tienda_creada = None
    try:
        await database.init_db_pool()
        if args.crear_tienda:
            print(f"Registrando tienda {args.tienda!r} (si ya existe inactiva, NO se reactiva).")
            tienda_creada = await database.add_allowed_store(args.tienda)
            print(f"Tienda registrada o existente: {tienda_creada}")
        try:
            product_id = await catalog.add_product(
                args.nombre, args.marca, precio, args.url, args.tienda, args.moneda,
                description=args.descripcion,
            )
        except Exception:
            if tienda_creada:
                print(
                    f"Aviso: la tienda {tienda_creada} quedó registrada en allowed_stores "
                    "aunque el producto no se guardó. Revísala con el subcomando 'listar'.",
                    file=sys.stderr,
                )
            raise
        print(f"Producto guardado con id {product_id}.")
        marca = f" ({args.marca})" if args.marca else ""
        print(f"  {args.nombre.strip()}{marca} - {formatear_precio(precio, args.moneda)}")
        if args.descripcion:
            print(f"  Descripción: {args.descripcion.strip()}")
        print(f"  Tienda: {args.tienda}  URL: {args.url}")
        return 0
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception:
        logger.exception("Error inesperado al agregar el producto.")
        return 2
    finally:
        await database.close_db_pool()


async def cmd_listar(args) -> int:
    try:
        await database.init_db_pool()
        productos = await catalog.listar_productos(incluir_inactivos=True)
        tiendas = await catalog.listar_tiendas()
        if args.consulta:
            consulta = args.consulta.strip().casefold()
            productos = [
                p for p in productos
                if consulta in p["name"].casefold()
                or consulta in (p["brand"] or "").casefold()
            ]

        print(f"Productos ({len(productos)}):")
        for p in productos:
            estado = "activo" if p["is_active"] else "inactivo"
            marca = p["brand"] or "-"
            print(f"  [{p['id']}] {p['name']} | {marca} | "
                  f"{formatear_precio(p['price'], p['currency'])} | {p['store']} | {estado}")
            if p.get("description"):
                print(f"      {p['description']}")
        print(f"Tiendas ({len(tiendas)}):")
        for t in tiendas:
            estado = "activa" if t["is_active"] else "inactiva"
            print(f"  {t['domain']} | {estado}")
        return 0
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception:
        logger.exception("Error inesperado al listar el catálogo.")
        return 2
    finally:
        await database.close_db_pool()


async def cmd_desactivar(args) -> int:
    try:
        await database.init_db_pool()
        if await catalog.deactivate_product(args.id):
            print(f"Producto {args.id} desactivado.")
            return 0
        print(f"Error: no existe el producto {args.id}.", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception:
        logger.exception("Error inesperado al desactivar el producto.")
        return 2
    finally:
        await database.close_db_pool()


async def _ejecutar_con_pool(accion, contexto: str) -> int:
    """init/close del pool siempre; ValueError -> 1, otro error -> 2."""
    try:
        await database.init_db_pool()
        return await accion()
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception:
        logger.exception(f"Error inesperado al {contexto}.")
        return 2
    finally:
        await database.close_db_pool()


async def cmd_mascota(args) -> int:
    # Validación completa ANTES de tocar la BD.
    try:
        pets.normalizar_nombre_mascota(args.nombre)
        pets._validar_especie(args.especie)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    async def accion():
        # Para avisar si el nombre ya existía ("Mía" y "Mia" comparten clave).
        existentes = {m["id"]: m for m in await pets.listar_mascotas()}
        pet_id = await pets.add_pet(args.nombre, args.especie)
        previa = existentes.get(pet_id)
        if previa is not None:
            estado = "activa" if previa["is_active"] else "inactiva (NO se reactiva)"
            print(
                f"Aviso: ya existía la mascota {previa['name']!r} (id {pet_id}, especie "
                f"{previa['species']}, {estado}); no se cambia su especie ni se crea otra.",
                file=sys.stderr,
            )
            return 0
        print(f"Mascota {args.nombre.strip()!r} registrada con id {pet_id}.")
        return 0

    return await _ejecutar_con_pool(accion, "registrar la mascota")


def _prevalidar_vinculo(args) -> None:
    pets.normalizar_nombre_mascota(args.mascota)
    pets._validar_product_id(args.producto_id)


async def cmd_asignar(args) -> int:
    try:
        _prevalidar_vinculo(args)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    async def accion():
        await pets.link_product(args.mascota, args.producto_id)
        print(f"Producto {args.producto_id} vinculado a la mascota {args.mascota.strip()!r}.")
        return 0

    return await _ejecutar_con_pool(accion, "vincular el producto")


async def cmd_desasignar(args) -> int:
    try:
        _prevalidar_vinculo(args)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    async def accion():
        if await pets.unlink_product(args.mascota, args.producto_id):
            print(f"Producto {args.producto_id} desvinculado de la mascota {args.mascota.strip()!r}.")
            return 0
        print(f"Error: la mascota {args.mascota.strip()!r} no tenía vinculado el producto "
              f"{args.producto_id}.", file=sys.stderr)
        return 1

    return await _ejecutar_con_pool(accion, "desvincular el producto")


async def cmd_mascotas(args) -> int:
    async def accion():
        mascotas = await pets.listar_mascotas()
        print(f"Mascotas ({len(mascotas)}):")
        for m in mascotas:
            estado = "activa" if m["is_active"] else "inactiva"
            print(f"  [{m['id']}] {m['name']} | {m['species']} | {estado}")
            if not m["productos"]:
                print("      (sin productos vinculados)")
            for p in m["productos"]:
                print(f"      - [{p['id']}] {p['name']}")
        return 0

    return await _ejecutar_con_pool(accion, "listar las mascotas")


_SUBCOMANDOS = {
    "agregar": cmd_agregar,
    "listar": cmd_listar,
    "desactivar": cmd_desactivar,
    "mascota": cmd_mascota,
    "asignar": cmd_asignar,
    "desasignar": cmd_desasignar,
    "mascotas": cmd_mascotas,
}


def main(argv=None) -> int:
    logging.basicConfig(level=logging.WARNING,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    try:
        args = construir_parser().parse_args(argv)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 1
    return asyncio.run(_SUBCOMANDOS[args.subcomando](args))


if __name__ == "__main__":
    sys.exit(main())
