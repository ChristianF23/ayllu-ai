import threading

import httpx
import pytest

from sandbox_server.server import make_server
from utils import sandbox_client


@pytest.fixture
def servidor(monkeypatch):
    srv = make_server("127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    monkeypatch.setenv("SANDBOX_URL", url)
    yield url
    srv.shutdown()
    srv.server_close()


async def test_cliente_ejecuta_codigo_en_el_servidor(servidor):
    res = await sandbox_client.execute_code("print(6 * 7)")
    assert res["status"] == "success" and res["stdout"] == "42"


async def test_cliente_recibe_errores_del_codigo(servidor):
    res = await sandbox_client.execute_code("1 / 0")
    assert res["status"] == "error" and "ZeroDivisionError" in res["stderr"]


def test_health(servidor):
    assert httpx.get(f"{servidor}/health").json() == {"status": "ok"}


def test_solicitud_invalida_devuelve_400(servidor):
    assert httpx.post(f"{servidor}/execute", json={"otro": 1}).status_code == 400
    assert httpx.post(f"{servidor}/execute", content=b"no es json").status_code == 400


def test_ruta_desconocida_devuelve_404(servidor):
    assert httpx.post(f"{servidor}/otra", json={}).status_code == 404


async def test_falla_cerrado_si_el_sandbox_no_responde(monkeypatch):
    monkeypatch.setenv("SANDBOX_URL", "http://127.0.0.1:9")  # puerto sin servicio
    res = await sandbox_client.execute_code("print('no debe ejecutarse localmente')")
    assert res["status"] == "exception"
    assert "SandboxUnavailableError" in res["stderr"]
    assert res["stdout"] == ""


async def test_sin_url_usa_el_sandbox_local(monkeypatch):
    monkeypatch.delenv("SANDBOX_URL", raising=False)
    res = await sandbox_client.execute_code("print('local')")
    assert res["status"] == "success" and res["stdout"] == "local"
