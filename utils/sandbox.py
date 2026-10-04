import sys
import subprocess
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("AylluSandbox")

class PythonSandbox:
    """
    Entorno de ejecución aislado para evaluar código Python o scripts
    generados por los agentes en un entorno controlado.
    
    Reglas de Seguridad:
    - Timeout estricto de 10 segundos.
    - Captura de stdout, stderr y código de salida.
    - Entorno limpio (cero herencia de secretos .env).
    """
    def __init__(self, timeout_seconds: int = 10):
        self.timeout_seconds = timeout_seconds

    def execute_code(self, code_string: str) -> Dict[str, Any]:
        """
        Ejecuta un bloque de código Python aislado en un subproceso estricto.
        """
        try:
            # Ejecución en subproceso sin pasar las variables de entorno sensibles
            process = subprocess.Popen(
                [sys.executable, "-c", code_string],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env={"PYTHONUNBUFFERED": "1"}  # Entorno sanitizado sin .env
            )

            stdout, stderr = process.communicate(timeout=self.timeout_seconds)

            return {
                "status": "success" if process.returncode == 0 else "error",
                "exit_code": process.returncode,
                "stdout": stdout.strip(),
                "stderr": stderr.strip()
            }

        except subprocess.TimeoutExpired:
            process.kill()
            logger.warning(f"⚠️ Ejecución en Sandbox abortada por Timeout ({self.timeout_seconds}s)")
            return {
                "status": "timeout",
                "exit_code": -1,
                "stdout": "",
                "stderr": f"ExecutionTimeoutError: El script superó el tiempo máximo permitido ({self.timeout_seconds} segundos)."
            }
        except Exception as e:
            logger.error(f"❌ Error interno en Sandbox: {str(e)}")
            return {
                "status": "exception",
                "exit_code": -1,
                "stdout": "",
                "stderr": f"SandboxInternalError: {str(e)}"
            }

sandbox = PythonSandbox(timeout_seconds=10)