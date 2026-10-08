import os
import asyncio
import logging
from typing import Dict, Any

import httpx

from utils.sandbox import sandbox

logger = logging.getLogger("AylluSandboxClient")

# El sandbox corta a los 10 s; damos margen para la red y el arranque del subproceso.
_HTTP_TIMEOUT_SECONDS = 20


async def execute_code(code: str) -> Dict[str, Any]:
    """
    Ejecuta código en el sandbox sin bloquear el event loop.
    Con SANDBOX_URL usa el contenedor aparte; si el contenedor falla, devuelve
    error (no cae a ejecución local). Sin SANDBOX_URL (desarrollo/tests) usa el
    motor local en un hilo.
    """
    url = os.getenv("SANDBOX_URL")
    if not url:
        logger.warning("SANDBOX_URL no definida: usando sandbox local (solo para desarrollo).")
        return await asyncio.to_thread(sandbox.execute_code, code)

    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
            response = await client.post(f"{url.rstrip('/')}/execute", json={"code": code})
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error(f"❌ Sandbox remoto no disponible: {e}")
        return {
            "status": "exception",
            "exit_code": -1,
            "stdout": "",
            "stderr": f"SandboxUnavailableError: no se pudo contactar al sandbox ({type(e).__name__})"
        }
