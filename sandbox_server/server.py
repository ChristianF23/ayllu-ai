"""
Servidor HTTP mínimo del sandbox. Corre en su propio contenedor, sin el volumen
del proyecto, sin .env y sin acceso a internet. Solo usa la librería estándar.

POST /execute  {"code": "..."}  ->  resultado de PythonSandbox.execute_code
GET  /health                    ->  {"status": "ok"}
"""
import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from utils.sandbox import PythonSandbox

logger = logging.getLogger("AylluSandboxServer")

MAX_BODY_BYTES = 200_000
_sandbox = PythonSandbox(timeout_seconds=10)


class SandboxHandler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send_json(200, {"status": "ok"})
        else:
            self._send_json(404, {"error": "no encontrado"})

    def do_POST(self):
        if self.path != "/execute":
            self._send_json(404, {"error": "no encontrado"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length <= 0 or length > MAX_BODY_BYTES:
                self._send_json(413, {"error": "cuerpo vacío o demasiado grande"})
                return
            code = json.loads(self.rfile.read(length)).get("code")
            if not isinstance(code, str):
                raise ValueError("falta 'code' (str)")
        except (ValueError, json.JSONDecodeError) as e:
            self._send_json(400, {"error": f"solicitud inválida: {e}"})
            return
        self._send_json(200, _sandbox.execute_code(code))

    def log_message(self, format, *args):
        logger.info("%s - %s", self.address_string(), format % args)


def make_server(host: str = "0.0.0.0", port: int = 8000) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), SandboxHandler)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    logger.info("Sandbox escuchando en :8000")
    make_server().serve_forever()
