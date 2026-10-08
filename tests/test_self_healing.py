import pytest
from agents.orchestrator import orchestrator


@pytest.mark.llm
async def test_self_healing_corrige_nameerror():
    res = await orchestrator.execute_code_with_self_healing(
        "a_list = [1, 2, 3]; print(sum(a_list_inexistente))", max_attempts=2
    )
    assert res["status"] == "success"
    assert res["attempts"] == 2
    assert res["stdout"] == "6"
