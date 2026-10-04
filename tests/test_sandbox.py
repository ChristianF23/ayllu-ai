import asyncio
import logging
from utils.sandbox import sandbox
from utils.database import init_db_pool, close_db_pool
from runbooks.db_inspector import runbook_inspect_table_count

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("TestSandbox")

async def test_suite():
    logger.info("=== INICIANDO PRUEBAS DE LA FASE 6 (SANDBOXING & RUNBOOKS) ===")

    # -------------------------------------------------------------
    # PRUEBA 1: Código Python Válido (Ejecución limpia)
    # -------------------------------------------------------------
    logger.info("\n--- PRUEBA 1: Código Python Válido ---")
    valid_code = "print('¡Hola desde el Sandbox de Ayllu AI!'); print(f'Cálculo: {2 + 2}')"
    res1 = sandbox.execute_code(valid_code)
    print(f"Status: {res1['status']}")
    print(f"Exit Code: {res1['exit_code']}")
    print(f"Stdout:\n{res1['stdout']}")
    assert res1['status'] == 'success' and res1['exit_code'] == 0, "❌ Falla en PRUEBA 1"
    logger.info("✓ PRUEBA 1 PASADA CON ÉXITO")

    # -------------------------------------------------------------
    # PRUEBA 2: Control de Timeout (Bucle Infinito o Bloqueo)
    # -------------------------------------------------------------
    logger.info("\n--- PRUEBA 2: Control de Timeout (Límite 10s) ---")
    timeout_code = "import time; print('Iniciando bucle infinito...'); time.sleep(20); print('Esto no debería imprimirse')"
    res2 = sandbox.execute_code(timeout_code)
    print(f"Status: {res2['status']}")
    print(f"Exit Code: {res2['exit_code']}")
    print(f"Stderr:\n{res2['stderr']}")
    assert res2['status'] == 'timeout', "❌ Falla en PRUEBA 2"
    logger.info("✓ PRUEBA 2 PASADA CON ÉXITO (Timeout abortó el proceso limpiamente)")

    # -------------------------------------------------------------
    # PRUEBA 3: Captura de Errores Sintácticos o de Código
    # -------------------------------------------------------------
    logger.info("\n--- PRUEBA 3: Captura de Error de Sintaxis / Excepción ---")
    error_code = "a = 10 / 0"
    res3 = sandbox.execute_code(error_code)
    print(f"Status: {res3['status']}")
    print(f"Stderr:\n{res3['stderr']}")
    assert res3['status'] == 'error' and 'ZeroDivisionError' in res3['stderr'], "❌ Falla en PRUEBA 3"
    logger.info("✓ PRUEBA 3 PASADA CON ÉXITO")

    # -------------------------------------------------------------
    # PRUEBA 4: Runbook Pre-Aprobado (db_inspector)
    # -------------------------------------------------------------
    logger.info("\n--- PRUEBA 4: Invocación de Runbook Pre-Aprobado ---")
    await init_db_pool()
    try:
        res4 = await runbook_inspect_table_count("cost_logs")
        print(f"Resultado Runbook (cost_logs): {res4}")
        assert res4['status'] == 'success', "❌ Falla en PRUEBA 4"
        logger.info("✓ PRUEBA 4 PASADA CON ÉXITO")
    finally:
        await close_db_pool()

    logger.info("\n🎉 ¡TODAS LAS PRUEBAS DE LA OPCIÓN A FUERON EXITOSAS!")

if __name__ == "__main__":
    asyncio.run(test_suite())