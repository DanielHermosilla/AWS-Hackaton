"""Conversation retries and shared AWS session guards, without AWS or a solver."""

from types import SimpleNamespace

import pytest

from backend.assist_service import _cliente_bedrock
from backend.bedrock_session import BedrockSession
from ev_routing.assist import Asistente, Sesion
from ev_routing.assist.bedrock_chat import ErrorBedrock
from ev_routing.search_policy import BedrockConfig


RESULT = {
    "status": "ok",
    "solve": {
        "status": "feasible",
        "solution": {
            "served_visit_ids": ["C1"],
            "unserved_visit_ids": [],
            "net_energy_kwh": 3,
            "routes": [],
        },
    },
    "validation": {"feasible": True},
}


class FollowupFailure:
    def __init__(self, tool=None, parameters=None):
        self.tool, self.parameters = tool, parameters or {}
        self.calls = 0

    def conversar(self, *args, **kwargs):
        self.calls += 1
        if self.calls == 1 and self.tool:
            return {"output": {"message": {"content": [{
                "toolUse": {"toolUseId": "action", "name": self.tool,
                            "input": self.parameters},
            }]}}}
        raise ErrorBedrock("synthetic interrupted conversation")


def test_failed_followup_does_not_repeat_a_completed_solve():
    resolutions = []
    session = Sesion(resolutor=lambda config: resolutions.append(config) or RESULT)
    client = FollowupFailure("resolver")

    response = Asistente(session, client).turno("calcula")

    assert len(resolutions) == 1
    assert response.resolvio and response.modo == "local"
    assert session.ultimo_resultado is RESULT
    assert [action.herramienta for action in response.acciones] == ["resolver"]
    assert client.calls == 2
    assert session.mensajes[-1]["role"] == "assistant"


def test_failed_followup_preserves_parameter_change_without_replaying_the_request():
    resolutions = []
    session = Sesion(resolutor=lambda config: resolutions.append(config) or RESULT)
    client = FollowupFailure("cambiar_parametro", {"clave": "vehiculos", "valor": 3})

    response = Asistente(session, client, confirmar_importantes=False).turno(
        "usa 3 vehiculos y calcula"
    )

    assert session.overrides == {"vehiculos": 3}
    assert len(session.historial) == 1
    assert not resolutions
    assert not response.resolvio and response.modo == "local"
    assert [action.herramienta for action in response.acciones] == ["cambiar_parametro"]


def test_initial_bedrock_failure_can_still_use_the_local_interpreter():
    resolutions = []
    session = Sesion(resolutor=lambda config: resolutions.append(config) or RESULT)

    response = Asistente(session, FollowupFailure()).turno("calcula sin gpt")

    assert len(resolutions) == 1
    assert response.resolvio and response.modo == "local"
    assert session.config_efectiva()["busqueda"] == "standard"


@pytest.fixture
def shared_chat():
    clock = [0]

    class NativeClient:
        def __init__(self):
            self.calls = []
            self.failure = False

        def converse(self, **payload):
            self.calls.append({"locked": session._request_lock.locked(), "payload": payload})
            if self.failure:
                raise RuntimeError("synthetic remote failure")
            return {"output": {"message": {"content": [{"text": "Synthetic reply."}]}}}

    native = NativeClient()
    sdk_session = SimpleNamespace(client=lambda *args, **kwargs: native)
    session = BedrockSession(
        BedrockConfig(model_id="us.openai.gpt-5.6-luna", profile=None),
        session_factory=lambda **kwargs: sdk_session,
        clock=lambda: clock[0],
        ttl_seconds=1,
    )
    client = _cliente_bedrock(SimpleNamespace(bedrock=session))
    assert client is not None
    return session, client, native, clock


def converse(client):
    return client.conversar(
        [{"role": "user", "content": [{"text": "Synthetic turn."}]}],
        sistema="Synthetic test.",
    )


def test_shared_chat_rejects_the_next_call_after_disconnect(shared_chat):
    session, client, native, _ = shared_chat
    converse(client)
    session.disconnect()

    with pytest.raises(ErrorBedrock):
        converse(client)

    assert len(native.calls) == 1
    assert session.status()["state"] == "disconnected"


def test_shared_chat_rechecks_expiration_before_each_call(shared_chat):
    session, client, native, clock = shared_chat
    converse(client)
    clock[0] = 2

    with pytest.raises(ErrorBedrock):
        converse(client)

    assert len(native.calls) == 1
    assert session.status()["state"] == "expired"


def test_shared_chat_respects_another_session_request(shared_chat):
    session, client, native, _ = shared_chat
    session._request_lock.acquire()
    try:
        with pytest.raises(ErrorBedrock):
            converse(client)
        assert not native.calls
    finally:
        session._request_lock.release()


def test_shared_chat_holds_and_releases_the_session_lock_on_remote_error(shared_chat):
    session, client, native, _ = shared_chat
    native.failure = True
    with pytest.raises(ErrorBedrock):
        converse(client)
    assert not session._request_lock.locked()

    native.failure = False
    converse(client)

    assert len(native.calls) == 2
    assert all(call["locked"] for call in native.calls)
    assert not session._request_lock.locked()
