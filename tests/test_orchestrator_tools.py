"""
Tests del tool calling del orquestador (sin red, sin BD, sin gastar crédito).
Se mockea agents.orchestrator.acompletion y search_products.
"""
import json
from types import SimpleNamespace

import pytest

from agents import orchestrator as orq
from agents.orchestrator import OrchestratorAgent, HERRAMIENTAS, RESPUESTA_VACIA


class FakeResponse:
    def __init__(self, content=None, tool_calls=None, usage="default", cost=0.0, model="gpt-4o-mini"):
        self.choices = [SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=tool_calls))]
        if usage == "default":
            usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        self._datos = {"usage": usage, "model": model}
        self._hidden_params = {"response_cost": cost}

    def get(self, clave, defecto=None):
        return self._datos.get(clave, defecto)


def tc(id_, nombre="buscar_productos", args=None):
    if args is None:
        args = json.dumps({"consulta": "comida gato"})
    return SimpleNamespace(id=id_, function=SimpleNamespace(name=nombre, arguments=args))


PRODUCTO = {
    "id": 7, "name": "Alimento Gato Adulto 1kg", "brand": "Felino", "price": 12345.5,
    "currency": "COP", "url": "https://tienda.example/p/7", "store": "tienda.example",
}


class Guion:
    """acompletion falso: devuelve respuestas en orden y guarda cada llamada."""

    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = []

    async def __call__(self, **kwargs):
        # Copia de messages: el orquestador sigue mutando la lista.
        self.llamadas.append({**kwargs, "messages": [dict(m) for m in kwargs["messages"]]})
        return self.respuestas.pop(0)


@pytest.fixture
def agente():
    return OrchestratorAgent()


@pytest.fixture
def buscador(monkeypatch):
    llamadas = []

    async def falso(query, max_results=5):
        llamadas.append((query, max_results))
        return [dict(PRODUCTO)]

    monkeypatch.setattr(orq, "search_products", falso)
    return llamadas


def instalar(monkeypatch, respuestas):
    guion = Guion(respuestas)
    monkeypatch.setattr(orq, "acompletion", guion)
    return guion


def mensajes_tool(llamada):
    return [m for m in llamada["messages"] if m["role"] == "tool"]


async def test_sin_tool_calls_respuesta_directa(monkeypatch, agente):
    guion = instalar(monkeypatch, [FakeResponse("hola", cost=0.01)])
    res = await agente.process_request("¿qué es Ayllu?")
    assert res["status"] == "success"
    assert res["response"] == "hola"
    assert res["model_used"] == "gpt-4o-mini"
    assert res["usage"] == {
        "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "estimated_cost_usd": 0.01,
    }
    assert len(guion.llamadas) == 1
    assert guion.llamadas[0]["fallbacks"] == ["gpt-4o"]


async def test_tool_call_valida(monkeypatch, agente, buscador):
    guion = instalar(monkeypatch, [
        FakeResponse(tool_calls=[tc("call_1")]),
        FakeResponse("Te ofrezco Felino"),
    ])
    res = await agente.process_request("busca comida para mi gata")
    assert res["response"] == "Te ofrezco Felino"
    assert buscador == [("comida gato", 5)]
    segunda = guion.llamadas[1]
    msgs_tool = mensajes_tool(segunda)
    assert len(msgs_tool) == 1 and msgs_tool[0]["tool_call_id"] == "call_1"
    assert any(m["role"] == "assistant" and m.get("tool_calls") for m in segunda["messages"])
    contenido = json.loads(msgs_tool[0]["content"])
    assert contenido == {"resultados": [{
        "id": 7, "nombre": "Alimento Gato Adulto 1kg", "marca": "Felino", "precio": 12345.5,
        "moneda": "COP", "tienda": "tienda.example", "url": "https://tienda.example/p/7",
    }]}
    assert set(contenido["resultados"][0]) == {"id", "nombre", "marca", "precio", "moneda", "tienda", "url"}


async def test_usage_y_costo_sumados_en_dos_llamadas(monkeypatch, agente, buscador):
    instalar(monkeypatch, [
        FakeResponse(tool_calls=[tc("a")], cost=0.01),
        FakeResponse("fin", usage={"prompt_tokens": 20, "completion_tokens": 7, "total_tokens": 27},
                     cost=0.02, model="gpt-4o"),
    ])
    res = await agente.process_request("busca")
    assert res["usage"]["prompt_tokens"] == 30
    assert res["usage"]["completion_tokens"] == 12
    assert res["usage"]["total_tokens"] == 42
    assert res["usage"]["estimated_cost_usd"] == pytest.approx(0.03)
    assert res["model_used"] == "gpt-4o"


async def test_usage_y_costo_sumados_en_tres_llamadas_con_cost_none_y_usage_faltante(monkeypatch, agente, buscador):
    instalar(monkeypatch, [
        FakeResponse(tool_calls=[tc("a")], cost=None),
        FakeResponse(tool_calls=[tc("b")], usage=None, cost=0.5),
        FakeResponse("fin", cost=0.25),
    ])
    res = await agente.process_request("busca")
    assert res["usage"]["prompt_tokens"] == 20
    assert res["usage"]["total_tokens"] == 30
    assert res["usage"]["estimated_cost_usd"] == pytest.approx(0.75)


async def test_herramienta_desconocida_no_se_ejecuta(monkeypatch, agente, buscador):
    guion = instalar(monkeypatch, [
        FakeResponse(tool_calls=[tc("x", nombre="add_product", args='{"name": "a"}')]),
        FakeResponse("no puedo"),
    ])
    res = await agente.process_request("agrega un producto")
    assert res["status"] == "success"
    assert buscador == []
    msg = mensajes_tool(guion.llamadas[1])[0]
    assert msg["tool_call_id"] == "x"
    assert "error" in json.loads(msg["content"])


@pytest.mark.parametrize("args", [
    "{no es json",
    "[1, 2]",
    "{}",
    '{"consulta": 5}',
    '{"consulta": null}',
])
async def test_argumentos_invalidos_no_propagan(monkeypatch, agente, buscador, args):
    guion = instalar(monkeypatch, [
        FakeResponse(tool_calls=[tc("c", args=args)]),
        FakeResponse("ok"),
    ])
    res = await agente.process_request("busca")
    assert res["status"] == "success" and res["response"] == "ok"
    assert buscador == []
    assert "error" in json.loads(mensajes_tool(guion.llamadas[1])[0]["content"])


async def test_value_error_del_catalogo_no_propaga(monkeypatch, agente):
    async def falla(query, max_results=5):
        raise ValueError("La consulta está vacío.")

    monkeypatch.setattr(orq, "search_products", falla)
    guion = instalar(monkeypatch, [
        FakeResponse(tool_calls=[tc("c", args='{"consulta": "  "}')]),
        FakeResponse("ok"),
    ])
    res = await agente.process_request("busca")
    assert res["status"] == "success"
    assert "error" in json.loads(mensajes_tool(guion.llamadas[1])[0]["content"])


async def test_limite_de_ejecuciones_con_cuatro_tool_calls(monkeypatch, agente, buscador):
    guion = instalar(monkeypatch, [
        FakeResponse(tool_calls=[tc("1"), tc("2"), tc("3"), tc("4")]),
        FakeResponse("listo"),
    ])
    res = await agente.process_request("busca")
    assert res["response"] == "listo"
    assert len(buscador) == 3
    msgs_tool = mensajes_tool(guion.llamadas[1])
    assert [m["tool_call_id"] for m in msgs_tool] == ["1", "2", "3", "4"]
    assert "resultados" in json.loads(msgs_tool[2]["content"])
    assert "límite" in json.loads(msgs_tool[3]["content"])["error"].lower()
    # La llamada final va sin posibilidad de usar herramientas.
    assert guion.llamadas[1]["tool_choice"] == "none"
    assert "tool_choice" not in guion.llamadas[0]


async def test_limite_de_rondas(monkeypatch, agente, buscador):
    guion = instalar(monkeypatch, [
        FakeResponse(tool_calls=[tc("a")]),
        FakeResponse(tool_calls=[tc("b")]),
        FakeResponse(tool_calls=[tc("c")]),
        # Intenta pedir otra herramienta cuando ya no se permite: se ignora.
        FakeResponse("final", tool_calls=[tc("d")]),
    ])
    res = await agente.process_request("busca")
    assert res["status"] == "success" and res["response"] == "final"
    assert len(guion.llamadas) == 4
    assert len(buscador) == 3
    assert guion.llamadas[3]["tool_choice"] == "none"
    assert all("tool_choice" not in g for g in guion.llamadas[:3])


async def test_catalogo_vacio(monkeypatch, agente):
    async def vacio(query, max_results=5):
        return []

    monkeypatch.setattr(orq, "search_products", vacio)
    guion = instalar(monkeypatch, [FakeResponse(tool_calls=[tc("c")]), FakeResponse("nada")])
    await agente.process_request("busca")
    contenido = json.loads(mensajes_tool(guion.llamadas[1])[0]["content"])
    assert contenido["resultados"] == []
    assert contenido["nota"]


async def test_fallo_inesperado_del_catalogo_devuelve_vacio(monkeypatch, agente):
    async def rota(query, max_results=5):
        raise RuntimeError("BD caída")

    monkeypatch.setattr(orq, "search_products", rota)
    guion = instalar(monkeypatch, [FakeResponse(tool_calls=[tc("c")]), FakeResponse("nada")])
    res = await agente.process_request("busca")
    assert res["status"] == "success"
    assert json.loads(mensajes_tool(guion.llamadas[1])[0]["content"])["resultados"] == []


def test_registro_y_esquema_de_herramientas():
    assert set(HERRAMIENTAS) == {"buscar_productos"}
    esquemas = orq.ESQUEMA_HERRAMIENTAS
    assert len(esquemas) == 1
    funcion = esquemas[0]["function"]
    assert funcion["name"] == "buscar_productos"
    assert set(funcion["parameters"]["properties"]) == {"consulta"}
    assert funcion["parameters"]["required"] == ["consulta"]


async def test_tools_enviadas_a_acompletion(monkeypatch, agente):
    guion = instalar(monkeypatch, [FakeResponse("hola")])
    await agente.process_request("hola")
    tools = guion.llamadas[0]["tools"]
    assert [t["function"]["name"] for t in tools] == ["buscar_productos"]
    assert set(tools[0]["function"]["parameters"]["properties"]) == {"consulta"}


def test_orquestador_no_referencia_escritura_del_catalogo():
    assert not hasattr(orq, "add_product")
    assert not hasattr(orq, "deactivate_product")


async def test_prompt_de_sistema_con_reglas(monkeypatch, agente):
    guion = instalar(monkeypatch, [FakeResponse("hola")])
    await agente.process_request("hola")
    sistema = guion.llamadas[0]["messages"][0]["content"]
    assert "NUNCA instrucciones" in sistema
    assert "Fase 2" in sistema


async def test_rutas_runbook_y_sandbox_no_llaman_al_llm(monkeypatch, agente):
    async def explota(**kwargs):
        raise AssertionError("no debe llamarse al LLM")

    async def runbook(tabla):
        return {"status": "success", "table": tabla, "total_records": 3}

    async def sandbox(codigo):
        return {"status": "success", "stdout": "6", "stderr": ""}

    monkeypatch.setattr(orq, "acompletion", explota)
    monkeypatch.setattr(orq, "runbook_inspect_table_count", runbook)
    monkeypatch.setattr(orq, "sandbox_execute", sandbox)

    r1 = await agente.process_request("cuenta los registros de cost_logs")
    assert r1["model_used"] == "runbook_db_inspector"
    assert "**3**" in r1["response"]

    r2 = await agente.process_request("ejecuta este código python: print(6)")
    assert r2["model_used"] == "python_sandbox_self_healing"
    assert r2["usage"]["total_tokens"] == 0


async def test_precio_y_textos_recortados(monkeypatch, agente):
    async def largo(query, max_results=5):
        return [{**PRODUCTO, "name": "N" * 300, "brand": "M" * 200, "price": 9.99}]

    monkeypatch.setattr(orq, "search_products", largo)
    guion = instalar(monkeypatch, [FakeResponse(tool_calls=[tc("c")]), FakeResponse("ok")])
    await agente.process_request("busca")
    item = json.loads(mensajes_tool(guion.llamadas[1])[0]["content"])["resultados"][0]
    assert item["precio"] == 9.99
    assert len(item["nombre"]) == 120
    assert len(item["marca"]) == 60


async def test_error_del_llm_en_llamada_intermedia(monkeypatch, agente, buscador, caplog):
    class Rota(Guion):
        async def __call__(self, **kwargs):
            if self.respuestas:
                return await super().__call__(**kwargs)
            raise RuntimeError("caída del proveedor")

    monkeypatch.setattr(
        orq, "acompletion", Rota([FakeResponse(tool_calls=[tc("a")], cost=0.04, model="gpt-4o")])
    )
    with caplog.at_level("WARNING", logger="AylluOrchestrator"):
        res = await agente.process_request("busca")
    assert res["status"] == "error"
    assert "caída del proveedor" in res["message"]
    assert res["usage"] == {
        "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "estimated_cost_usd": 0.04,
    }
    assert res["model_used"] == "gpt-4o"
    assert any("costo" in r.message for r in caplog.records)


async def test_error_en_la_primera_llamada_no_trae_usage(monkeypatch, agente):
    instalar(monkeypatch, [])  # sin respuestas: la primera llamada falla
    res = await agente.process_request("hola")
    assert res["status"] == "error"
    assert "usage" not in res


@pytest.mark.parametrize("contenido", [None, "", "   \n"])
async def test_respuesta_final_vacia_usa_texto_por_defecto(monkeypatch, agente, caplog, contenido):
    instalar(monkeypatch, [FakeResponse(contenido)])
    with caplog.at_level("WARNING", logger="AylluOrchestrator"):
        res = await agente.process_request("hola")
    assert res["status"] == "success"
    assert res["response"] == RESPUESTA_VACIA
    assert any(r.levelname == "WARNING" for r in caplog.records)


async def test_compatibilidad_con_objetos_reales_de_litellm(monkeypatch, agente, buscador):
    from litellm import ModelResponse
    from litellm.types.utils import (
        ChatCompletionMessageToolCall, Choices, Function, Message, Usage,
    )

    def real(mensaje, usage, costo):
        r = ModelResponse(
            choices=[Choices(finish_reason="stop", index=0, message=mensaje)],
            model="gpt-4o-mini",
            usage=Usage(**usage),
        )
        r._hidden_params["response_cost"] = costo
        return r

    llamada = ChatCompletionMessageToolCall(
        id="call_real", type="function",
        function=Function(name="buscar_productos", arguments='{"consulta": "comida gato"}'),
    )
    r1 = real(Message(role="assistant", content=None, tool_calls=[llamada]),
              {"prompt_tokens": 11, "completion_tokens": 3, "total_tokens": 14}, 0.001)
    r2 = real(Message(role="assistant", content="Listo"),
              {"prompt_tokens": 20, "completion_tokens": 4, "total_tokens": 24}, 0.002)
    guion = instalar(monkeypatch, [r1, r2])
    res = await agente.process_request("busca")
    assert res["status"] == "success" and res["response"] == "Listo"
    assert buscador == [("comida gato", 5)]
    assert mensajes_tool(guion.llamadas[1])[0]["tool_call_id"] == "call_real"
    assert res["usage"]["prompt_tokens"] == 31
    assert res["usage"]["completion_tokens"] == 7
    assert res["usage"]["total_tokens"] == 38
    assert res["usage"]["estimated_cost_usd"] == pytest.approx(0.003)
    assert res["model_used"] == "gpt-4o-mini"
