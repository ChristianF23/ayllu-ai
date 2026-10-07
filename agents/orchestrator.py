import os
import logging
from litellm import acompletion
from utils.okf_reader import okf_reader
from utils.sandbox import sandbox
from runbooks.db_inspector import runbook_inspect_table_count

logger = logging.getLogger("AylluOrchestrator")

class OrchestratorAgent:
    def __init__(self, default_model: str = "gpt-4o-mini", fallback_model: str = "gpt-4o"):
        self.default_model = default_model
        self.fallback_model = fallback_model
        self.api_key = os.getenv("OPENAI_API_KEY")

    async def execute_code_with_self_healing(self, code_to_run: str, max_attempts: int = 2) -> dict:
        """
        Ejecuta código Python en el Sandbox. Si falla, toma el traceback de error,
        se lo re-inyecta al LLM para corregirlo y vuelve a intentarlo hasta max_attempts.
        """
        current_code = code_to_run
        attempts_log = []

        for attempt in range(1, max_attempts + 1):
            logger.info(f"🧪 Intento {attempt}/{max_attempts} de ejecución en Sandbox...")
            result = sandbox.execute_code(current_code)

            if result["status"] == "success":
                logger.info(f"✓ Código ejecutado con éxito en el intento {attempt}")
                return {
                    "status": "success",
                    "attempts": attempt,
                    "final_code": current_code,
                    "stdout": result["stdout"],
                    "stderr": result["stderr"]
                }

            # Si falló, guardamos el log y reinyectamos el error al modelo
            attempts_log.append(f"Intento {attempt} falló con error: {result['stderr']}")
            logger.warning(f"⚠️ Fallo en intento {attempt}: {result['stderr']}")

            if attempt < max_attempts:
                # Prompt de autocorrección
                correction_prompt = (
                    f"El siguiente código Python falló durante su ejecución en el Sandbox:\n\n"
                    f"```python\n{current_code}\n```\n\n"
                    f"Mensaje de Error / Traceback:\n{result['stderr']}\n\n"
                    f"Por favor corrige el código para solucionar el error. "
                    f"Devuelve ÚNICAMENTE el código Python corregido dentro de un bloque ```python ... ``` sin explicaciones adicionales."
                )

                try:
                    response = await acompletion(
                        model=self.default_model,
                        fallbacks=[self.fallback_model],
                        messages=[
                            {"role": "system", "content": "Eres un programador experto en Python encargado de corregir errores de ejecución (Self-Healing Agent)."},
                            {"role": "user", "content": correction_prompt}
                        ]
                    )
                    raw_reply = response.choices[0].message.content
                    current_code = raw_reply.replace("```python", "").replace("```", "").strip()
                except Exception as e:
                    logger.error(f"❌ Error en llamada LLM de Self-Healing: {str(e)}")
                    break

        return {
            "status": "failed_after_healing",
            "attempts": max_attempts,
            "final_code": current_code,
            "stdout": "",
            "stderr": f"SelfHealingError: El código no pudo corregirse tras {max_attempts} intentos.\n" + "\n".join(attempts_log)
        }

    async def process_request(self, user_prompt: str, model: str = None) -> dict:
        target_model = model or self.default_model
        prompt_lower = user_prompt.lower()

        # 1. Invocación de Runbook: Conteo o inspección de tablas
        if "cuenta" in prompt_lower or "filas" in prompt_lower or "registros" in prompt_lower:
            for table in ["cost_logs", "users_whitelist"]:
                if table in prompt_lower:
                    runbook_res = await runbook_inspect_table_count(table)
                    if runbook_res["status"] == "success":
                        reply = (
                            f"🔧 **Ejecución de Runbook Seguro (`db_inspector`):**\n\n"
                            f"La tabla `{runbook_res['table']}` contiene actualmente "
                            f"**{runbook_res['total_records']}** registros en PostgreSQL."
                        )
                        return {
                            "status": "success",
                            "response": reply,
                            "model_used": "runbook_db_inspector",
                            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "estimated_cost_usd": 0.0}
                        }

        # 2. Invocación de Sandbox con Self-Healing Loop
        if "ejecuta este código python:" in prompt_lower or "corre este código:" in prompt_lower:
            code_to_run = user_prompt.split(":", 1)[1].strip().replace("```python", "").replace("```", "").strip()
            
            healing_res = await self.execute_code_with_self_healing(code_to_run, max_attempts=2)
            
            if healing_res["status"] == "success":
                status_emoji = "✅"
                output = healing_res["stdout"]
                attempts_note = f"(Resuelto en intento {healing_res['attempts']})" if healing_res['attempts'] > 1 else ""
            else:
                status_emoji = "❌"
                output = healing_res["stderr"]
                attempts_note = f"(Falló tras {healing_res['attempts']} intentos de Self-Healing)"

            reply = (
                f"🧪 **Ejecución en Sandbox Aislado con Self-Healing:**\n"
                f"**Estado:** {status_emoji} `{healing_res['status']}` {attempts_note}\n\n"
                f"**Código Final:**\n```python\n{healing_res['final_code']}\n```\n\n"
                f"**Salida / Log:**\n```text\n{output}\n```"
            )
            return {
                "status": "success",
                "response": reply,
                "model_used": "python_sandbox_self_healing",
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "estimated_cost_usd": 0.0}
            }

        # 3. Flujo Estándar LLM + OKF Context con Fallbacks de LiteLLM
        okf_context = okf_reader.get_context_summary()
        system_instruction = (
            "Eres el Agente Orquestador del ecosistema Ayllu AI.\n"
            "Tienes acceso al siguiente Bundle de Conocimiento OKF v0.2:\n\n"
            f"{okf_context}\n\n"
            "Responde con precisión apoyándote en las definiciones y reglas de negocio del paquete OKF."
        )

        try:
            response = await acompletion(
                model=target_model,
                fallbacks=[self.fallback_model],  # Fallback a gpt-4o si falla el modelo primario
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": user_prompt}
                ]
            )

            reply_text = response.choices[0].message.content
            usage = response.get("usage") or {}
            cost = (getattr(response, "_hidden_params", None) or {}).get("response_cost") or 0.0

            return {
                "status": "success",
                "response": reply_text,
                "model_used": response.get("model", target_model),
                "usage": {
                    "prompt_tokens": usage.get("prompt_tokens") or 0,
                    "completion_tokens": usage.get("completion_tokens") or 0,
                    "total_tokens": usage.get("total_tokens") or 0,
                    "estimated_cost_usd": cost
                }
            }

        except Exception as e:
            return {
                "status": "error",
                "message": f"Error en el Orquestador: {str(e)}"
            }

orchestrator = OrchestratorAgent()