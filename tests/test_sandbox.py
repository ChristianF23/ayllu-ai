import pytest
from utils.sandbox import PythonSandbox, sandbox
from utils.database import init_db_pool, close_db_pool
from runbooks.db_inspector import runbook_inspect_table_count


def test_codigo_valido():
    res = sandbox.execute_code("print('¡Hola!'); print(f'Cálculo: {2 + 2}')")
    assert res["status"] == "success" and res["exit_code"] == 0
    assert "Cálculo: 4" in res["stdout"]


def test_timeout_aborta_el_proceso():
    res = PythonSandbox(timeout_seconds=2).execute_code("import time; time.sleep(20)")
    assert res["status"] == "timeout"


def test_error_de_ejecucion_se_captura():
    res = sandbox.execute_code("a = 10 / 0")
    assert res["status"] == "error"
    assert "ZeroDivisionError" in res["stderr"]


@pytest.mark.db
async def test_runbook_db_inspector():
    try:
        await init_db_pool()
    except Exception as e:
        pytest.skip(f"PostgreSQL no disponible: {e}")
    try:
        res = await runbook_inspect_table_count("cost_logs")
        assert res["status"] == "success"
        assert (await runbook_inspect_table_count("otra_tabla"))["status"] == "denied"
    finally:
        await close_db_pool()
