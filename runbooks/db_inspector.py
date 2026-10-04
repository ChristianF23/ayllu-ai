import logging
import utils.database as db
from typing import Dict, Any

logger = logging.getLogger("RunbookDBInspector")

async def runbook_inspect_table_count(table_name: str) -> Dict[str, Any]:
    """
    Runbook Pre-Aprobado: Cuenta el número total de registros en una tabla permitida.
    """
    allowed_tables = ["cost_logs", "users_whitelist"]
    
    if table_name not in allowed_tables:
        return {
            "status": "denied",
            "message": f"Acceso denegado: La tabla '{table_name}' no está en la lista blanca de inspección."
        }

    if db.DB_POOL is None:
        return {"status": "error", "message": "Base de datos no conectada."}

    query = f"SELECT COUNT(*) AS total FROM {table_name};"
    
    try:
        async with db.DB_POOL.acquire() as conn:
            row = await conn.fetchrow(query)
            return {
                "status": "success",
                "table": table_name,
                "total_records": row["total"]
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}