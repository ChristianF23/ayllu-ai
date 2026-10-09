"""
Prueba de punta a punta con el LLM real (gasta crédito; marcador llm, se omite
por defecto). Ejecutar a mano: docker exec ayllu_app python -m pytest -m llm tests/test_llm_busqueda.py
Crea su propia tienda y producto de prueba y los borra antes y después.
"""
import os

import pytest

import utils.database as database
from agents import orchestrator as orq
from agents.orchestrator import OrchestratorAgent
from utils.catalog import add_product
from utils.database import close_db_pool, init_db_pool

pytestmark = pytest.mark.llm

TIENDA = "tienda.llm-prueba-ayllu.com.co"
URL_PRUEBA = f"https://{TIENDA}/biodieta-digestivo-prueba"
NOMBRE = "Biodieta Digestivo - Bienestar Digestivo 1 kg"
MARCA = "Zqxllmayllu"
PRECIO = 44650


async def _borrar():
    async with database.DB_POOL.acquire() as conn:
        await conn.execute("DELETE FROM products WHERE store_domain = $1;", TIENDA)
        await conn.execute("DELETE FROM allowed_stores WHERE domain = $1;", TIENDA)


@pytest.fixture
async def catalogo_prueba():
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("Sin OPENAI_API_KEY: no se puede llamar al LLM.")
    try:
        await init_db_pool()
    except Exception as e:
        pytest.skip(f"PostgreSQL no disponible: {e}")
    await _borrar()
    try:
        async with database.DB_POOL.acquire() as conn:
            await conn.execute(
                "INSERT INTO allowed_stores (domain, is_active) VALUES ($1, TRUE);", TIENDA
            )
        await add_product(NOMBRE, MARCA, PRECIO, URL_PRUEBA, TIENDA)
        yield
    finally:
        await _borrar()
        await close_db_pool()


@pytest.fixture
def llamadas_herramienta(monkeypatch):
    """Envuelve la herramienta real para contar sus ejecuciones."""
    original = orq.HERRAMIENTAS["buscar_productos"]
    llamadas = []

    async def envoltura(argumentos):
        llamadas.append(argumentos)
        return await original(argumentos)

    monkeypatch.setitem(orq.HERRAMIENTAS, "buscar_productos", envoltura)
    return llamadas


async def test_frase_natural_encuentra_comida_digestiva(catalogo_prueba, llamadas_herramienta):
    agente = OrchestratorAgent()
    resultado = await agente.process_request(
        "Hola, ¿tienes alguna comida digestiva para gatos? Mi gata tiene el estómago sensible."
    )
    assert resultado["status"] == "success", resultado
    texto = resultado["response"]
    assert llamadas_herramienta, "El modelo no ejecutó buscar_productos."
    assert "44650" in texto or "44.650" in texto or "44,650" in texto, texto
    assert URL_PRUEBA in texto, texto


async def test_producto_inexistente_no_menciona_enlaces(catalogo_prueba, llamadas_herramienta):
    agente = OrchestratorAgent()
    resultado = await agente.process_request(
        "¿Tienes arena de titanio para dinosaurios marca Qwzxyplm?"
    )
    assert resultado["status"] == "success", resultado
    texto = resultado["response"]
    assert URL_PRUEBA not in texto, texto
    assert "http://" not in texto and "https://" not in texto, texto
