import re
from utils.sandbox import sandbox, _fix_traceback_lines


def test_traceback_apunta_a_la_linea_del_agente():
    res = sandbox.execute_code("x = 1\nraise ValueError('boom')")
    assert res["status"] == "error"
    m = re.search(r'File "<string>", line (\d+)', res["stderr"])
    assert m and m.group(1) == "2", res["stderr"]


def test_fix_traceback_no_baja_de_uno():
    assert 'line 1' in _fix_traceback_lines('File "<string>", line 2')
