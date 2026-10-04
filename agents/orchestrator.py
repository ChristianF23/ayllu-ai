import os
import asyncio
from litellm import completion
from utils.okf_reader import okf_reader
from utils.sandbox import sandbox
from runbooks.db_inspector import runbook_inspect_table_count

class OrchestratorAgent:
    def __init__(self, default_model: str = "gpt-4o-mini"):
        self.default_model = default_model
        self.api_key = os.getenv("OPENAI_API_KEY")

    async def process_request(self, user_prompt: str, model: str = None) -> dict:
        target_model = model or self.default_model

        # 1. Detección directa de Runbook o Sandbox por intención
        prompt_lower = user_prompt.lower()

        # Invocación de Runbook: Conteo o inspección de tablas
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

        # Invocación de Sandbox: Petición de ejecutar un código Python directo
        if "ejecuta este código python:" in prompt_lower or "corre este código:" in prompt_lower:
            # Extraer el fragmento de código
            code_to_run = user_prompt.split(":", 1)[1].strip().replace("```python", "").replace("```", "").strip()
            sandbox_res = sandbox.execute_code(code_to_run)
            
            status_emoji = "✅" if sandbox_res["status"] == "success" else "⚠️"
            output = sandbox_res["stdout"] if sandbox_res["status"] == "success" else sandbox_res["stderr"]
            
            reply = (
                f"🧪 **Ejecución en Sandbox Aislado (10s limit):**\n"
                f"**Estado:** {status_emoji} `{sandbox_res['status']}` (Exit Code: `{sandbox_res['exit_code']}`)\n\n"
                f"**Salida:**\n```text\n{output}\n```"
            )
            return {
                "status": "success",
                "response": reply,
                "model_used": "python_sandbox",
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "estimated_cost_usd": 0.0}
            }

        # 2. Flujo Estándar con LLM + OKF Context
        okf_context = okf_reader.get_context_summary()
        system_instruction = (
            "Eres el Agente Orquestador del ecosistema Ayllu AI.\n"
            "Tienes acceso al siguiente Bundle de Conocimiento OKF v0.2:\n\n"
            f"{okf_context}\n\n"
            "Responde con precisión apoyándote en las definiciones y reglas de negocio del paquete OKF."
        )

        try:
            response = completion(
                model=target_model,
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": user_prompt}
                ]
            )

            reply_text = response.choices[0].message.content
            usage = response.get("usage", {})

            return {
                "status": "success",
                "response": reply_text,
                "model_used": target_model,
                "usage": {
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                    "estimated_cost_usd": getattr(response, "_hidden_params", {}).get("response_cost", 0.0)
                }
            }

        except Exception as e:
            return {
                "status": "error",
                "message": f"Error en el Orquestador: {str(e)}"
            }

orchestrator = OrchestratorAgent()