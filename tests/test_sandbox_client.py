import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from utils import sandbox_client

MARCADOR = "EJECUTADO_LOCALMENTE"


@pytest.fixture
def stub(monkeypatch):
    servidores = []

    def iniciar(responder):
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                responder(self)

            def log_message(self, *args):
                pass

        srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        srv.daemon_threads = True
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        servidores.append(srv)
        monkeypatch.setenv("SANDBOX_URL", f"http://127.0.0.1:{srv.server_address[1]}")

    yield iniciar
    for srv in servidores:
        srv.shutdown()
        srv.server_close()


def responder(handler, status, cuerpo, content_type="application/json"):
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(cuerpo)))
    handler.end_headers()
    handler.wfile.write(cuerpo)


def assert_falla_cerrado(res, tipo_excepcion):
    assert res["status"] == "exception"
    assert res["exit_code"] == -1
    assert res["stdout"] == ""
    assert "SandboxUnavailableError" in res["stderr"]
    assert tipo_excepcion in res["stderr"]


async def test_falla_cerrado_si_el_sandbox_devuelve_500(stub):
    stub(lambda h: responder(h, 500, b'{"error": "interno"}'))
    res = await sandbox_client.execute_code(f"print('{MARCADOR}')")
    assert_falla_cerrado(res, "HTTPStatusError")
    assert MARCADOR not in res["stdout"]


async def test_falla_cerrado_si_el_sandbox_excede_el_timeout(stub, monkeypatch):
    monkeypatch.setattr(sandbox_client, "_HTTP_TIMEOUT_SECONDS", 0.3)

    def lento(h):
        time.sleep(1.5)
        try:
            responder(h, 200, b'{"status": "success", "exit_code": 0, "stdout": "tarde", "stderr": ""}')
        except OSError:
            pass

    stub(lento)
    inicio = time.monotonic()
    res = await sandbox_client.execute_code(f"print('{MARCADOR}')")
    assert time.monotonic() - inicio < 1.5
    assert_falla_cerrado(res, "ReadTimeout")


async def test_falla_cerrado_si_el_sandbox_devuelve_cuerpo_no_json(stub):
    stub(lambda h: responder(h, 200, b"esto no es json", "text/plain"))
    res = await sandbox_client.execute_code(f"print('{MARCADOR}')")
    assert_falla_cerrado(res, "JSONDecodeError")
