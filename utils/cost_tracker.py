import logging
import utils.database as db

logger = logging.getLogger("AylluCostTracker")

async def log_cost(
    user_id: int,
    model_used: str,
    prompt_tokens: int,
    completion_tokens: int,
    estimated_cost_usd: float,
    agent_id: str = "orchestrator"
) -> bool:
    """
    Registra una transacción de uso de tokens y costo financiero en PostgreSQL.
    Si el pool no está activo, intenta inicializarlo preventivamente.
    """
    # Si el pool no está inicializado, intentar activarlo
    if db.DB_POOL is None:
        logger.warning("DB_POOL no inicializado. Intentando conectar a la BD...")
        try:
            await db.init_db_pool()
        except Exception as e:
            logger.error(f"❌ Error al inicializar pool desde cost_tracker: {str(e)}")
            return False

    if db.DB_POOL is None:
        logger.error("No se puede registrar costo: El Pool de la BD continúa inactivo.")
        return False

    insert_query = """
    INSERT INTO cost_logs 
        (user_id, agent_id, model_used, prompt_tokens, completion_tokens, estimated_cost_usd)
    VALUES 
        ($1, $2, $3, $4, $5, $6);
    """
    try:
        async with db.DB_POOL.acquire() as conn:
            await conn.execute(
                insert_query,
                user_id,
                agent_id,
                model_used,
                prompt_tokens,
                completion_tokens,
                estimated_cost_usd
            )
            logger.info(f"✓ Costo guardado para el usuario {user_id}: ${estimated_cost_usd:.6f} USD")
            return True
    except Exception as e:
        logger.error(f"❌ Error al guardar log de costo en la BD: {str(e)}")
        return False