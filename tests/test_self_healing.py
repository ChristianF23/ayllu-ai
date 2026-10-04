import asyncio
import logging
from agents.orchestrator import orchestrator

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("TestSelfHealing")

async def test_healing():
    logger.info("=== INICIANDO PRUEBA DE SELF-HEALING LOOP (FASE 7) ===")

    # Código con error deliberado (NameError: 'a' no está definida y error sintáctico)
    broken_code = "a_list = [1, 2, 3]; print(sum(a_list_inexistente))"

    logger.info("Enviando código con error intencional al Self-Healing Agent...")
    res = await orchestrator.execute_code_with_self_healing(broken_code, max_attempts=2)

    print(f"\nEstado Final: {res['status']}")
    print(f"Número de Intentos: {res['attempts']}")
    print(f"Código Corregido:\n{res['final_code']}")
    print(f"Salida (stdout):\n{res['stdout']}")

    assert res['status'] == 'success', "❌ Falla en la prueba de Self-Healing"
    logger.info("🎉 ¡PRUEBA DE SELF-HEALING PASADA CON ÉXITO!")

if __name__ == "__main__":
    asyncio.run(test_healing())