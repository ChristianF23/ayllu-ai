"""
Mascotas y vínculo explícito mascota-producto (Misión 1).

"Compra comida para Milu" se resuelve en CÓDIGO con este vínculo, no por
texto libre: el agente solo LEE (products_for_pet). Escribir (add_pet,
link_product, unlink_product) es exclusivo del usuario y NUNCA se expone al
LLM. Esta fase no crea órdenes ni compra nada.

Se lee database.DB_POOL en tiempo de llamada (no se importa DB_POOL
directamente, que capturaría None al importar el módulo).
"""
import logging
import unicodedata

from utils import database
from utils.catalog import _MAX_ID, _rechazar_invisibles
from utils.domain_allowlist import is_url_allowed

logger = logging.getLogger("AylluPets")

_MAX_NOMBRE_MASCOTA = 50
_MAX_ESPECIE = 30
_MAX_PRODUCTOS_MASCOTA = 10
# Además de letras (con acentos y ñ): dígitos ASCII, espacio, guion y apóstrofo.
_PERMITIDOS_EXTRA = frozenset("0123456789 -'")


def normalizar_nombre_mascota(nombre) -> tuple[str, str]:
    """
    Devuelve (nombre_visible, clave). El nombre visible es el texto sin
    espacios alrededor; la clave es casefold + NFKD sin marcas diacríticas +
    espacios colapsados, así "Milú", "milu" y " MILU " comparten clave.
    Antes de validar se aplica NFC, así "Milú" escrito en forma descompuesta
    (u + U+0301) se acepta igual. Lanza ValueError si el nombre es inválido.
    """
    if not isinstance(nombre, str):
        raise ValueError("El nombre de la mascota debe ser texto.")
    nombre = unicodedata.normalize("NFC", nombre)
    _rechazar_invisibles(nombre, "El nombre de la mascota")
    visible = nombre.strip()
    if not visible:
        raise ValueError("El nombre de la mascota está vacío.")
    if len(visible) > _MAX_NOMBRE_MASCOTA:
        raise ValueError(f"El nombre de la mascota supera {_MAX_NOMBRE_MASCOTA} caracteres.")
    for c in visible:
        if not (c.isalpha() or c in _PERMITIDOS_EXTRA):
            raise ValueError(
                f"Carácter no permitido en el nombre de la mascota: {c!r} "
                "(solo letras, dígitos, espacio, guion y apóstrofo)."
            )
    if not any(c.isalnum() for c in visible):
        raise ValueError("El nombre de la mascota necesita al menos una letra o dígito.")

    descompuesto = unicodedata.normalize("NFKD", visible.casefold())
    sin_marcas = "".join(c for c in descompuesto if not unicodedata.combining(c))
    clave = " ".join(sin_marcas.split())
    if not clave or len(clave) > _MAX_NOMBRE_MASCOTA:
        raise ValueError("El nombre de la mascota no se puede normalizar.")
    return visible, clave


def _validar_especie(especie) -> str:
    if not isinstance(especie, str):
        raise ValueError("La especie debe ser texto.")
    _rechazar_invisibles(especie, "La especie")
    limpia = especie.strip().lower()
    if not limpia or len(limpia) > _MAX_ESPECIE or not limpia.isalpha():
        raise ValueError(
            f"Especie inválida: {especie!r} (1 a {_MAX_ESPECIE} letras, sin espacios)."
        )
    return limpia


def _validar_product_id(product_id) -> int:
    if isinstance(product_id, bool) or not isinstance(product_id, int):
        raise ValueError("El id del producto debe ser entero.")
    if not 1 <= product_id <= _MAX_ID:
        raise ValueError(f"El id del producto debe estar entre 1 y {_MAX_ID}.")
    return product_id


def _pool():
    if not database.DB_POOL:
        raise RuntimeError("Pool de PostgreSQL no inicializado.")
    return database.DB_POOL


async def add_pet(name, species) -> int:
    """
    Registra una mascota (o devuelve el id de la que ya tiene esa clave de
    nombre). No reactiva una mascota inactiva ni cambia su especie.
    Lanza ValueError si los datos son inválidos; RuntimeError sin pool.

    Por diseño la clave ignora mayúsculas y acentos: "Mía" y "Mia" son la
    MISMA mascota. Un nombre en otro alfabeto (ej. cirílico) no se
    translitera y crea OTRA mascota.

    ADVERTENCIA: cambia para quién puede comprar el agente. Solo el usuario.
    NUNCA debe exponerse como herramienta al LLM. Antes de conectarla a un
    handler de Telegram se exige usuario en la lista blanca y aprobación
    humana explícita.
    """
    visible, clave = normalizar_nombre_mascota(name)
    especie = _validar_especie(species)
    pool = _pool()

    insert_query = """
    INSERT INTO pets (name, name_key, species, is_active)
    VALUES ($1, $2, $3, TRUE)
    ON CONFLICT (name_key) DO NOTHING
    RETURNING id;
    """
    select_query = "SELECT id, is_active FROM pets WHERE name_key = $1;"
    async with pool.acquire() as conn:
        nuevo = await conn.fetchval(insert_query, visible, clave, especie)
        if nuevo is not None:
            logger.info(f"✓ Mascota {visible!r} registrada con id {nuevo}.")
            return nuevo
        fila = await conn.fetchrow(select_query, clave)

    if fila["is_active"]:
        logger.info(f"La mascota {visible!r} ya existía (id {fila['id']}).")
    else:
        logger.warning(f"La mascota {visible!r} ya existía y está inactiva: no se reactiva.")
    return fila["id"]


async def _verificar_mascota_y_producto(conn, clave: str, visible: str, product_id: int) -> int:
    """Dentro de una transacción: mascota activa y producto activo de tienda activa."""
    mascota = await conn.fetchrow(
        "SELECT id, is_active FROM pets WHERE name_key = $1 FOR SHARE;", clave
    )
    if mascota is None or not mascota["is_active"]:
        raise ValueError(f"No hay una mascota activa llamada {visible!r}.")
    producto = await conn.fetchrow(
        """
        SELECT p.is_active AS producto_activo, s.is_active AS tienda_activa
        FROM products p
        JOIN allowed_stores s ON s.domain = p.store_domain
        WHERE p.id = $1
        FOR SHARE;
        """,
        product_id,
    )
    if producto is None:
        raise ValueError(f"No existe el producto {product_id}.")
    if not producto["producto_activo"]:
        raise ValueError(f"El producto {product_id} está inactivo.")
    if not producto["tienda_activa"]:
        raise ValueError(f"La tienda del producto {product_id} está inactiva.")
    return mascota["id"]


async def link_product(pet_name, product_id) -> bool:
    """
    Vincula (o reactiva el vínculo de) un producto con una mascota. Nunca
    reactiva la mascota ni el producto. Lanza ValueError si la mascota no
    existe o está inactiva, o si el producto no existe, está inactivo o es de
    una tienda inactiva; RuntimeError sin pool. Devuelve True.

    ADVERTENCIA: cambia lo que el agente comprará para la mascota. Solo el
    usuario. NUNCA debe exponerse como herramienta al LLM. Antes de conectarla
    a un handler de Telegram se exige usuario en la lista blanca y aprobación
    humana explícita.
    """
    visible, clave = normalizar_nombre_mascota(pet_name)
    pid = _validar_product_id(product_id)
    pool = _pool()

    upsert = """
    INSERT INTO pet_products (pet_id, product_id, is_active)
    VALUES ($1, $2, TRUE)
    ON CONFLICT (pet_id, product_id) DO UPDATE SET is_active = TRUE;
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            pet_id = await _verificar_mascota_y_producto(conn, clave, visible, pid)
            await conn.execute(upsert, pet_id, pid)
    logger.info(f"✓ Producto {pid} vinculado a la mascota {visible!r}.")
    return True


async def unlink_product(pet_name, product_id) -> bool:
    """
    Desactiva el vínculo mascota-producto. A propósito NO exige que la
    mascota, el producto ni la tienda estén activos: así siempre se puede
    limpiar un vínculo. Valida nombre e id en código antes de tocar la BD.
    Devuelve True si había un vínculo (activo o no) que marcar, False si no.

    ADVERTENCIA: cambia lo que el agente comprará para la mascota. Solo el
    usuario. NUNCA debe exponerse como herramienta al LLM. Antes de conectarla
    a un handler de Telegram se exige usuario en la lista blanca y aprobación
    humana explícita.
    """
    visible, clave = normalizar_nombre_mascota(pet_name)
    pid = _validar_product_id(product_id)
    pool = _pool()

    update = """
    UPDATE pet_products pp SET is_active = FALSE
    FROM pets p
    WHERE pp.pet_id = p.id AND p.name_key = $1 AND pp.product_id = $2;
    """
    async with pool.acquire() as conn:
        estado = await conn.execute(update, clave, pid)
    afectado = estado.split()[-1] != "0"
    if afectado:
        logger.info(f"Producto {pid} desvinculado de la mascota {visible!r}.")
    else:
        logger.warning(f"La mascota {visible!r} no tenía vinculado el producto {pid}.")
    return afectado


def _fila_valida(fila) -> bool:
    """Defensa en profundidad, igual que search_products."""
    if not is_url_allowed(fila["url"], [fila["store"]]):
        logger.warning(
            f"Producto {fila['id']} descartado: url fuera de la tienda {fila['store']!r}."
        )
        return False
    try:
        for campo in ("name", "brand", "description"):
            if fila[campo] is not None:
                _rechazar_invisibles(str(fila[campo]), campo)
    except ValueError:
        logger.warning(
            f"Producto {fila['id']} descartado: texto con caracteres de control o invisibles."
        )
        return False
    return True


async def products_for_pet(pet_name) -> dict | None:
    """
    SOLO LECTURA. Productos vinculados (vínculo activo) a una mascota activa,
    solo productos activos de tiendas activas, del más barato al más caro
    (máximo 10). Lanza ValueError si el nombre es inválido (antes de tocar la
    BD). Falla cerrado: None si la mascota no existe o está inactiva, sin pool
    o ante error de BD. Una lista vacía de productos es válida.
    """
    visible, clave = normalizar_nombre_mascota(pet_name)
    if not database.DB_POOL:
        logger.error("❌ Pool de PostgreSQL no inicializado: sin mascotas.")
        return None

    mascota_query = """
    SELECT id, name, species FROM pets
    WHERE name_key = $1 AND is_active = TRUE;
    """
    productos_query = """
    SELECT p.id, p.name, p.brand, p.description, p.price, p.currency, p.url,
           p.store_domain AS store
    FROM pet_products pp
    JOIN products p ON p.id = pp.product_id
    JOIN allowed_stores s ON s.domain = p.store_domain
    WHERE pp.pet_id = $1
      AND pp.is_active = TRUE AND p.is_active = TRUE AND s.is_active = TRUE
    ORDER BY p.price ASC, p.id
    LIMIT $2;
    """
    try:
        async with database.DB_POOL.acquire() as conn:
            mascota = await conn.fetchrow(mascota_query, clave)
            if mascota is None:
                logger.info(f"No hay una mascota activa llamada {visible!r}.")
                return None
            filas = await conn.fetch(productos_query, mascota["id"], _MAX_PRODUCTOS_MASCOTA)

        productos = [
            {
                "id": fila["id"],
                "name": fila["name"],
                "brand": fila["brand"],
                "description": fila["description"],
                "price": float(fila["price"]),
                "currency": fila["currency"],
                "url": fila["url"],
                "store": fila["store"],
            }
            for fila in filas
            if _fila_valida(fila)
        ]
        return {"mascota": mascota["name"], "especie": mascota["species"], "productos": productos}
    except Exception as e:
        logger.error(f"❌ Error al leer los productos de la mascota, sin resultados: {str(e)}")
        return None


async def listar_mascotas() -> list[dict]:
    """
    SOLO LECTURA, para la herramienta de carga del usuario. Todas las mascotas
    (activas e inactivas) con sus vínculos activos. Falla cerrado: [].
    """
    if not database.DB_POOL:
        logger.error("❌ Pool de PostgreSQL no inicializado: no se pueden listar mascotas.")
        return []

    mascotas_query = "SELECT id, name, species, is_active FROM pets ORDER BY name_key;"
    vinculos_query = """
    SELECT pp.pet_id, p.id, p.name
    FROM pet_products pp
    JOIN products p ON p.id = pp.product_id
    WHERE pp.is_active = TRUE
    ORDER BY pp.pet_id, p.id;
    """
    try:
        async with database.DB_POOL.acquire() as conn:
            mascotas = await conn.fetch(mascotas_query)
            vinculos = await conn.fetch(vinculos_query)
        por_mascota = {}
        for v in vinculos:
            por_mascota.setdefault(v["pet_id"], []).append({"id": v["id"], "name": v["name"]})
        return [
            {
                "id": m["id"],
                "name": m["name"],
                "species": m["species"],
                "is_active": bool(m["is_active"]),
                "productos": por_mascota.get(m["id"], []),
            }
            for m in mascotas
        ]
    except Exception as e:
        logger.error(f"❌ Error al listar mascotas, sin resultados: {str(e)}")
        return []
