import os
from litellm import completion

class OrchestratorAgent:
    """
    Agente Orquestador principal para el ecosistema Ayllu AI.
    Maneja las peticiones de los usuarios mediante LiteLLM y extrae
    información de uso y costes de la llamada al modelo.
    """
    def __init__(self, default_model: str = "gpt-4o-mini"):
        self.default_model = default_model
        # Asegurar que LiteLLM tenga acceso a la API Key
        self.api_key = os.getenv("OPENAI_API_KEY")

    def process_request(self, user_prompt: str, model: str = None) -> dict:
        """
        Procesa una solicitud enviándola al modelo especificado mediante LiteLLM.
        Devuelve un diccionario con el texto generado y las métricas de tokens/costo.
        """
        target_model = model or self.default_model

        try:
            # Petición agnóstica a través de LiteLLM
            response = completion(
                model=target_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Eres el Agente Orquestador del ecosistema Ayllu AI. "
                            "Respondes de forma clara, concisa y profesional."
                        )
                    },
                    {"role": "user", "content": user_prompt}
                ]
            )

            # Extraer respuesta del modelo
            reply_text = response.choices[0].message.content

            # Extraer métricas de consumo
            usage = response.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            total_tokens = usage.get("total_tokens", 0)
            
            # LiteLLM calcula automáticamente el costo aproximado en USD
            response_cost = response.get("_response_ms", 0) # Tiempo de respuesta
            estimated_cost = getattr(response, "_hidden_params", {}).get("response_cost", 0.0)

            return {
                "status": "success",
                "response": reply_text,
                "model_used": target_model,
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                    "estimated_cost_usd": estimated_cost
                }
            }

        except Exception as e:
            return {
                "status": "error",
                "message": f"Error al procesar la solicitud en el Orquestador: {str(e)}"
            }

# Instancia global o helmsman para pruebas rápidas
orchestrator = OrchestratorAgent()