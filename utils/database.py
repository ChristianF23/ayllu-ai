import os
import logging
import asyncpg
from typing import Optional

logger = logging.getLogger("AylluDB")

# Variable global para mantener el Pool de Conexiones
DB_POOL: Optional[asyncpg.Pool] = None

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
            
        logger.info("✓ Base de datos PostgreSQL inicializada correctamente.")
    except Exception as e:
        logger.error(f"❌ Error al conectar a PostgreSQL: {str(e)}")
        raise e

async def _create_tables(conn: asyncpg.Connection):
    """
    Crea las tablas 'users_whitelist' y 'cost_logs' si no existen.
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
    """
    await conn.execute(ddl)

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