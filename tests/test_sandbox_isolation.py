import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.sandbox import PythonSandbox

SENTINEL = "SECRET_SENTINEL_abc123"


def run_isolation_suite():
    with tempfile.TemporaryDirectory() as project_dir:
        (Path(project_dir) / ".env").write_text(f"TOKEN={SENTINEL}\n", encoding="utf-8")
        abs_env = str(Path(project_dir) / ".env").replace("\\", "/")

        original_cwd = os.getcwd()
        os.chdir(project_dir)  # el padre corre "dentro del proyecto", como en Docker (/app)
        try:
            sandbox = PythonSandbox(timeout_seconds=5)

            attacks = {
                "ruta relativa": "print(open('.env').read())",
                "ruta absoluta": f"print(open('{abs_env}').read())",
                "listar directorio": "import os; print(os.listdir('.'))",
            }
            for name, code in attacks.items():
                res = sandbox.execute_code(code)
                leaked = SENTINEL in res["stdout"] or ".env" in res["stdout"]
                if name == "ruta absoluta":
                    leaked = SENTINEL in res["stdout"]
                assert not leaked, f"FUGA ({name}): el sandbox expuso el .env -> {res['stdout']!r}"
                print(f"OK  aislamiento ({name})")

            ok = sandbox.execute_code("print(2 + 2)")
            assert ok["status"] == "success" and ok["stdout"] == "4", f"código normal roto: {ok}"
            print("OK  código normal sigue funcionando")
        finally:
            os.chdir(original_cwd)

    fast = PythonSandbox(timeout_seconds=2)
    res = fast.execute_code("import time; time.sleep(10)")
    assert res["status"] == "timeout", f"timeout roto: {res}"
    print("OK  timeout sigue funcionando")


if __name__ == "__main__":
    run_isolation_suite()
    print("TODAS LAS PRUEBAS DE AISLAMIENTO PASARON")
