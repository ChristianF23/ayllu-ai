import sys
from pathlib import Path

import pytest
import yaml

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "herramientas"))
import okf  # noqa: E402

BASE = """---
type: Reference
generated: { by: github-copilot/test, at: 2026-10-09T10:00:00Z }
---
"""


def _validar(tmp_path, texto):
    ruta = tmp_path / "c.md"
    ruta.write_text(texto, encoding="utf-8")
    return okf.validar_concepto(ruta, tmp_path)


def test_ejemplo_es_conforme():
    for ruta in okf.conceptos(RAIZ / "ejemplo"):
        errores, avisos = okf.validar_concepto(ruta, RAIZ / "ejemplo")
        assert errores == [] and avisos == [], ruta


@pytest.mark.parametrize("plantilla", sorted((RAIZ / "plantillas").glob("*.md")))
def test_plantillas_tienen_yaml_valido(plantilla):
    fm, _ = okf.separar(plantilla.read_text(encoding="utf-8"))
    assert isinstance(fm, dict) and fm["type"]


def test_falta_type(tmp_path):
    errores, _ = _validar(tmp_path, "---\ntitle: x\n---\ncuerpo")
    assert any("type" in e for e in errores)


def test_status_active_no_es_valido(tmp_path):
    errores, _ = _validar(tmp_path, BASE.replace("---\n", "---\nstatus: active\n", 1) + "x")
    assert any("status" in e for e in errores)


def test_fecha_sin_zona(tmp_path):
    texto = BASE.replace("2026-10-09T10:00:00Z", "2026-10-09") + "x"
    errores, _ = _validar(tmp_path, texto)
    assert any("generated.at" in e for e in errores)


def test_nota_al_pie_sin_definicion(tmp_path):
    errores, _ = _validar(tmp_path, BASE + "afirmación [^zz]")
    assert any("[^zz]" in e for e in errores)


def test_enlace_roto_es_aviso_no_error(tmp_path):
    errores, avisos = _validar(tmp_path, BASE + "[x](/nada.md)")
    assert errores == [] and any("enlace roto" in a for a in avisos)


def test_campos_legados_avisan(tmp_path):
    _, avisos = _validar(tmp_path, BASE.replace("---\n", "---\ntrust_tier: verified\n", 1) + "x")
    assert any("trust_tier" in a for a in avisos)


@pytest.mark.parametrize("secreto", [
    "Password=abc123",
    'Password="abc123"',
    "password: abc123",
    "Pwd = abc123;",
    "User ID=sa",
    "sqlcmd -S srv -U sa -P abc123",
    "dtexec /F p.dtsx /Decrypt abc123",
    "api_key: abc123",
])
def test_detecta_secretos(tmp_path, secreto):
    errores, _ = _validar(tmp_path, BASE + secreto)
    assert any("secreto" in e for e in errores)


@pytest.mark.parametrize("seguro", ["Password=***", "Password=<oculto>", "Server=DWH_PROD;Integrated Security=SSPI"])
def test_no_marca_datos_redactados(tmp_path, seguro):
    errores, _ = _validar(tmp_path, BASE + seguro)
    assert errores == []


def test_indices_y_validacion_end_to_end(tmp_path):
    (tmp_path / "tablas").mkdir()
    (tmp_path / "tablas" / "a.md").write_text(BASE + "x", encoding="utf-8")
    assert okf.indices(tmp_path) == 0
    raiz = (tmp_path / "index.md").read_text(encoding="utf-8")
    assert 'okf_version: "0.2"' in raiz and "tablas/index.md" in raiz
    assert okf.validar(tmp_path) == 0


def test_indices_conserva_guion_final_y_tolera_type_numerico(tmp_path):
    (tmp_path / "a.md").write_text(
        "---\ntype: 5\ntitle: Ventas -\ndescription: desc -\n---\nx", encoding="utf-8")
    okf.indices(tmp_path)
    assert "[Ventas -](a.md) - desc -" in (tmp_path / "index.md").read_text(encoding="utf-8")
