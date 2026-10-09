import os
import logging
import asyncpg
from typing import Optional

from utils.domain_allowlist import normalize_domain

logger = logging.getLogger("AylluDB")

# Variable global para mantener el Pool de Conexiones
DB_POOL: Optional[asyncpg.Pool] = None

# Tiendas permitidas por defecto para la búsqueda (semilla de allowed_stores)
SEED_ALLOWED_STORES = ("mercadolibre.com.co",)

async def init_db_pool():
    """
    Inicializa el pool de conexiones asíncronas de PostgreSQL y
    ejecuta la creación de tablas e inserción inicial de la lista blanca.
    """
    global DB_POOL
    
    # Lectura de variables de conexión
    user = os.getenv("POSTGRES_USER", "ayllu_user")
    password = os.getenv("POSTGRES_PASSWORD", "ayllu_password")
    database = os.getenv("POSTGRES_DB", "ayllu_db")
    host = os.getenv("POSTGRES_HOST", "db")
    port = os.getenv("POSTGRES_PORT", "5432")

    database_url = f"postgresql://{user}:{password}@{host}:{port}/{database}"

    try:
        logger.info("Connecting to PostgreSQL pool...")
        DB_POOL = await asyncpg.create_pool(dsn=database_url, min_size=1, max_size=10)
        
        # Crear esquema y sincronizar la lista blanca inicial
        async with DB_POOL.acquire() as conn:
            await _create_tables(conn)
            await _sync_initial_whitelist(conn)
            await _seed_allowed_stores(conn)

        logger.info("✓ Base de datos PostgreSQL inicializada correctamente.")
    except Exception as e:
        logger.error(f"❌ Error al conectar a PostgreSQL: {str(e)}")
        raise e

async def _create_tables(conn: asyncpg.Connection):
    """
    Crea las tablas 'users_whitelist', 'cost_logs' y 'allowed_stores' si no existen.
    """
    ddl = """
    CREATE TABLE IF NOT EXISTS users_whitelist (
        telegram_id BIGINT PRIMARY KEY,
        username VARCHAR(255),
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS cost_logs (
        id BIGSERIAL PRIMARY KEY,
        user_id BIGINT REFERENCES users_whitelist(telegram_id),
        agent_id VARCHAR(100) DEFAULT 'orchestrator',
        model_used VARCHAR(100) NOT NULL,
        prompt_tokens INT NOT NULL,
        completion_tokens INT NOT NULL,
        estimated_cost_usd NUMERIC(10, 6) NOT NULL,
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS allowed_stores (
        domain VARCHAR(255) PRIMARY KEY,
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    );
    """
    await conn.execute(ddl)

async def _seed_allowed_stores(conn: asyncpg.Connection):
    """
    Inserta las tiendas semilla si no existen. Idempotente: no reactiva
    una tienda que el usuario haya desactivado.
    """
    insert_query = """
    INSERT INTO allowed_stores (domain, is_active)
    VALUES ($1, TRUE)
    ON CONFLICT (domain) DO NOTHING;
    """
    for domain in SEED_ALLOWED_STORES:
        await conn.execute(insert_query, normalize_domain(domain))

async def _sync_initial_whitelist(conn: asyncpg.Connection):
    """
    Sincroniza los usuarios iniciales desde ALLOWED_TELEGRAM_USERS en .env.
    Protegido contra ausencia de la variable para no fallar en el futuro.
    """
    raw_users = os.getenv("ALLOWED_TELEGRAM_USERS", "").strip()
    
    # Si la variable de ambiente no existe o está vacía, omite la sincronización sin fallar
    if not raw_users:
        logger.info("No se especificaron usuarios en ALLOWED_TELEGRAM_USERS (.env). "
                    "Se utilizarán exclusivamente los registrados en la BD.")
        return

    # Parsear IDs válidos
    allowed_ids = [
        int(uid.strip()) 
        for uid in raw_users.split(",") 
        if uid.strip().isdigit()
    ]

    # Inserción idempotente (sin sobrescribir estados previos si el usuario ya existe)
    insert_query = """
    INSERT INTO users_whitelist (telegram_id, username, is_active)
    VALUES ($1, 'SyncedFromEnv', TRUE)
    ON CONFLICT (telegram_id) DO NOTHING;
    """
    for user_id in allowed_ids:
        await conn.execute(insert_query, user_id)
        
    logger.info(f"✓ Sincronizados {len(allowed_ids)} usuarios desde .env a 'users_whitelist'.")

async def close_db_pool():
    """
    Cierra el pool de conexiones de forma limpia al apagar el bot.
    """
    global DB_POOL
    if DB_POOL:
        await DB_POOL.close()
        DB_POOL = None
        logger.info("Pool de PostgreSQL cerrado.")

async def is_user_allowed(telegram_id: int) -> bool:
    """
    Consulta en la tabla 'users_whitelist' si el usuario está activo.
    """
    if not DB_POOL:
        return False

    query = """
    SELECT is_active FROM users_whitelist 
    WHERE telegram_id = $1;
    """
    async with DB_POOL.acquire() as conn:
        row = await conn.fetchrow(query, telegram_id)
        return row["is_active"] if row else False

async def get_allowed_domains() -> list[str]:
    """
    Devuelve los dominios activos de 'allowed_stores', ordenados.
    Falla cerrado: sin pool devuelve lista vacía (nunca una lista por defecto).
    """
    if not DB_POOL:
        logger.error("❌ Pool de PostgreSQL no inicializado: no hay tiendas permitidas.")
        return []

    query = """
    SELECT domain FROM allowed_stores
    WHERE is_active = TRUE
    ORDER BY domain;
    """
    try:
        async with DB_POOL.acquire() as conn:
            rows = await conn.fetch(query)
            return [row["domain"] for row in rows]
    except Exception as e:
        logger.error(f"❌ Error al leer allowed_stores, sin tiendas permitidas: {str(e)}")
        return []

async def add_allowed_store(domain: str) -> str:
    """
    Normaliza y agrega una tienda permitida. Lanza ValueError si el dominio
    es inválido. Si ya existe no cambia su estado (no reactiva una tienda
    inactiva). Devuelve el dominio normalizado.

    ADVERTENCIA: cambia la política de búsqueda (qué tiendas se consultan).
    NUNCA debe exponerse como herramienta al LLM. Antes de conectarla a un
    handler de Telegram se exige usuario en la lista blanca y aprobación
    humana explícita.
    """
    normalized = normalize_domain(domain)
    if not DB_POOL:
        raise RuntimeError("Pool de PostgreSQL no inicializado.")

    insert_query = """
    INSERT INTO allowed_stores (domain, is_active)
    VALUES ($1, TRUE)
    ON CONFLICT (domain) DO NOTHING
    RETURNING is_active;
    """
    select_query = """
    SELECT is_active FROM allowed_stores
    WHERE domain = $1;
    """
    async with DB_POOL.acquire() as conn:
        inserted = await conn.fetchrow(insert_query, normalized)
        if inserted is not None:
            logger.info(f"✓ Tienda permitida registrada y activa: {normalized}")
            return normalized
        is_active = await conn.fetchval(select_query, normalized)

    if is_active:
        logger.info(f"Tienda permitida ya existía y está activa: {normalized}")
    else:
        logger.warning(f"Tienda {normalized} ya existía y está inactiva: no se reactiva.")
    return normalized