"""El bot registra el costo ya incurrido cuando el orquestador falla tras llamar al LLM."""
from types import SimpleNamespace

import pytest

from bot import main as bot_main


class FakeMessage:
    text = "hola"

    def __init__(self):
        self.respuestas = []
        self.chat = SimpleNamespace(send_action=self._accion)

    async def _accion(self, action):
        pass

    async def reply_text(self, texto, **kwargs):
        self.respuestas.append(texto)


@pytest.fixture
def entorno(monkeypatch):
    registros = []

    async def permitido(user_id):
        return True

    async def log_falso(**kwargs):
        registros.append(kwargs)

    monkeypatch.setattr(bot_main, "is_user_allowed", permitido)
    monkeypatch.setattr(bot_main, "log_cost", log_falso)
    mensaje = FakeMessage()
    update = SimpleNamespace(effective_user=SimpleNamespace(id=42, username="u"), message=mensaje)
    return registros, mensaje, update


def fijar_resultado(monkeypatch, resultado):
    async def proceso(user_prompt):
        return resultado

    monkeypatch.setattr(bot_main.orchestrator, "process_request", proceso)


async def test_error_con_costo_registra_log_cost(monkeypatch, entorno):
    registros, mensaje, update = entorno
    fijar_resultado(monkeypatch, {
        "status": "error", "message": "Error en el Orquestador: x", "model_used": "gpt-4o",
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "estimated_cost_usd": 0.04},
    })
    await bot_main.handle_message(update, None)
    assert registros == [{
        "user_id": 42, "model_used": "gpt-4o", "prompt_tokens": 10, "completion_tokens": 5,
        "estimated_cost_usd": 0.04, "agent_id": "orchestrator",
    }]
    assert mensaje.respuestas == ["❌ Ocurrió un error al procesar tu mensaje: Error en el Orquestador: x"]


async def test_error_sin_usage_no_registra(monkeypatch, entorno):
    registros, mensaje, update = entorno
    fijar_resultado(monkeypatch, {"status": "error", "message": "Error en el Orquestador: x"})
    await bot_main.handle_message(update, None)
    assert registros == []
    assert len(mensaje.respuestas) == 1


async def test_error_con_usage_en_cero_no_registra(monkeypatch, entorno):
    registros, _, update = entorno
    fijar_resultado(monkeypatch, {
        "status": "error", "message": "x", "model_used": "m",
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "estimated_cost_usd": 0.0},
    })
    await bot_main.handle_message(update, None)
    assert registros == []
