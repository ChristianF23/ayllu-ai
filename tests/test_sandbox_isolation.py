import pytest
from utils.sandbox import PythonSandbox

SENTINEL = "SECRET_SENTINEL_abc123"


@pytest.fixture
def proyecto(tmp_path, monkeypatch):
    """Simula el directorio del proyecto (como /app en Docker) con un .env falso."""
    (tmp_path / ".env").write_text(f"TOKEN={SENTINEL}\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_no_lee_env_por_ruta_relativa(proyecto):
    res = PythonSandbox(timeout_seconds=5).execute_code("print(open('.env').read())")
    assert SENTINEL not in res["stdout"]


def test_no_lee_env_por_ruta_absoluta(proyecto):
    ruta = (proyecto / ".env").as_posix()
    res = PythonSandbox(timeout_seconds=5).execute_code(f"print(open('{ruta}').read())")
    assert SENTINEL not in res["stdout"]
    assert res["status"] == "error"


def test_no_lista_el_directorio_del_proyecto(proyecto):
    res = PythonSandbox(timeout_seconds=5).execute_code("import os; print(os.listdir('.'))")
    assert ".env" not in res["stdout"]


def test_no_hereda_variables_de_entorno(proyecto, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", SENTINEL)
    res = PythonSandbox(timeout_seconds=5).execute_code("import os; print(os.environ.get('OPENAI_API_KEY'))")
    assert SENTINEL not in res["stdout"]


def test_codigo_normal_sigue_funcionando(proyecto):
    res = PythonSandbox(timeout_seconds=5).execute_code("print(2 + 2)")
    assert res["status"] == "success" and res["stdout"] == "4"
