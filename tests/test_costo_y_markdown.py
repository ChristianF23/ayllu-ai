import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from telegram.error import BadRequest

from agents.orchestrator import orchestrator


class _Resp(dict):
    def __init__(self):
        super().__init__(usage=None, model="gpt-4o-mini")
        self.choices = [SimpleNamespace(message=SimpleNamespace(content="hola"))]
        self._hidden_params = {"response_cost": None}


def test_costo_none_y_acompletion():
    with patch("agents.orchestrator.acompletion", new=AsyncMock(return_value=_Resp())) as m:
        res = asyncio.run(orchestrator.process_request("hola"))
    assert m.await_count == 1
    assert res["status"] == "success"
    assert res["usage"]["estimated_cost_usd"] == 0.0
    assert res["usage"]["total_tokens"] == 0


def test_reply_safe_reintenta_sin_markdown():
    from bot.main import reply_safe
    msg = SimpleNamespace(reply_text=AsyncMock(side_effect=[BadRequest("Can't parse entities"), None]))
    asyncio.run(reply_safe(msg, "texto *roto"))
    assert msg.reply_text.await_count == 2
    assert "parse_mode" not in msg.reply_text.await_args_list[1].kwargs


if __name__ == "__main__":
    test_costo_none_y_acompletion()
    test_reply_safe_reintenta_sin_markdown()
    print("OK")
