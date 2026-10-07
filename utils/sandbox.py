import os
import sys
import sysconfig
import tempfile
import re
import subprocess
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("AylluSandbox")

# Guardia que se ejecuta DENTRO del subproceso antes del código del agente:
# bloquea abrir archivos fuera del directorio de trabajo temporal y de la librería de Python.
_GUARD = """
import sys, os
_allowed = [os.path.realpath(p) for p in sys.argv[1:] if p]
sys.argv = sys.argv[:1]
def _hook(event, args):
    if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
        path = os.fsdecode(args[0])
        if path.isdigit():
            return
        real = os.path.realpath(path)
        if not any(real == a or real.startswith(a + os.sep) for a in _allowed):
            raise PermissionError("Sandbox: acceso a archivos fuera del directorio aislado: " + path)
sys.addaudithook(_hook)
"""

# Líneas que el guardia añade antes del código del agente (guardia + salto de unión).
_GUARD_OFFSET = _GUARD.count("\n") + 1
_TRACEBACK_LINE = re.compile(r'(File "<string>", line )(\d+)')

def _fix_traceback_lines(stderr: str) -> str:
    """Resta el desfase del guardia para que los tracebacks apunten a las líneas del código del agente."""
    return _TRACEBACK_LINE.sub(lambda m: f"{m.group(1)}{max(int(m.group(2)) - _GUARD_OFFSET, 1)}", stderr)

class PythonSandbox:
    """
    Entorno de ejecución aislado para evaluar código Python o scripts
    generados por los agentes en un entorno controlado.
    
    Reglas de Seguridad:
    - Timeout estricto de 10 segundos.
    - Captura de stdout, stderr y código de salida.
    - Entorno limpio (cero herencia de secretos .env).
    - Directorio de trabajo temporal vacío, Python en modo aislado (-I) y un
      guardia que bloquea abrir archivos fuera de ese directorio.
    Nota: es una defensa en profundidad, no una frontera de seguridad total.
    La frontera real es ejecutar el sandbox en un contenedor sin el volumen del proyecto.
    """
    def __init__(self, timeout_seconds: int = 10):
        self.timeout_seconds = timeout_seconds

    def execute_code(self, code_string: str) -> Dict[str, Any]:
        """
        Ejecuta un bloque de código Python aislado en un subproceso estricto.
        """
        try:
            with tempfile.TemporaryDirectory(prefix="ayllu_sandbox_") as work_dir:
                return self._run(code_string, work_dir)
        except Exception as e:
            logger.error(f"❌ Error interno en Sandbox: {str(e)}")
            return {
                "status": "exception",
                "exit_code": -1,
                "stdout": "",
                "stderr": f"SandboxInternalError: {str(e)}"
            }

    def _run(self, code_string: str, work_dir: str) -> Dict[str, Any]:
        allowed = [work_dir, sysconfig.get_paths()["stdlib"], sys.prefix, sys.base_prefix]
        guarded_code = _GUARD + "\n" + code_string
        try:
            process = subprocess.Popen(
                [sys.executable, "-I", "-c", guarded_code, *allowed],
                cwd=work_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env={"PYTHONUNBUFFERED": "1", "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")}
            )

            stdout, stderr = process.communicate(timeout=self.timeout_seconds)

            return {
                "status": "success" if process.returncode == 0 else "error",
                "exit_code": process.returncode,
                "stdout": stdout.strip(),
                "stderr": _fix_traceback_lines(stderr.strip())
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

sandbox = PythonSandbox(timeout_seconds=10)