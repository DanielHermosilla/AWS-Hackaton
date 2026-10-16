"""Ephemeral AWS sessions: no network and no real credentials."""

import json

import pytest

from ev_routing.search_policy import BedrockConfig


class FakeClient:
    def __init__(self):
        self.requests = []
        self.failure = None

    def converse(self, **payload):
        self.requests.append(payload)
        if self.failure:
            raise self.failure
        return {
            "output": {"message": {"role": "assistant", "content": [{"text": '{"connected":true}'}]}},
            "usage": {"inputTokens": 10, "outputTokens": 4, "totalTokens": 14},
            "stopReason": "end_turn",
            "ResponseMetadata": {"HTTPHeaders": {"Authorization": "never-return-this"}},
        }


class FakeSession:
    def __init__(self, client):
        self.native = client

    def client(self, service_name, **kwargs):
        assert service_name == "bedrock-runtime"
        return self.native


def make_session():
    from backend.bedrock_session import BedrockSession

    now = [100.0]
    native = FakeClient()
    received = []

    def factory(**kwargs):
        received.append(kwargs)
        return FakeSession(native)

    session = BedrockSession(
        BedrockConfig(model_id="us.openai.gpt-5.6-luna", profile=None),
        session_factory=factory, clock=lambda: now[0], ttl_seconds=60,
    )
    return session, native, received, now


def credentials():
    return {
        "mode": "temporary", "region": "us-east-1", "model_id": "us.openai.gpt-5.6-luna",
        "access_key_id": "TEMP-ACCESS-DO-NOT-EXPOSE",
        "secret_access_key": "secret-do-not-expose",
        "session_token": "token-do-not-expose",
    }


def test_imported_session_feature_is_available():
    from backend import bedrock_session

    assert callable(bedrock_session.BedrockSession)


def test_temporary_connection_is_high_ephemeral_and_does_not_return_secrets(monkeypatch):
    session, native, received, _ = make_session()
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    state = session.connect(credentials())
    assert state["connected"] is True
    assert state["state"] == "connected"
    assert state["reasoning_effort"] == "high"
    assert native.requests[0]["additionalModelRequestFields"] == {"reasoning": {"effort": "high"}}
    assert received[0]["aws_session_token"] == "token-do-not-expose"
    assert session.settings().profile is None
    serialized = json.dumps([state, session.status(), session.settings().model_dump()])
    assert all(secret not in serialized for secret in credentials().values()
               if secret in {"TEMP-ACCESS-DO-NOT-EXPOSE", "secret-do-not-expose", "token-do-not-expose"})
    assert "Authorization" not in serialized
    import os
    assert "AWS_ACCESS_KEY_ID" not in os.environ


def test_connection_reuses_its_credentials_for_history_and_solver():
    session, native, received, _ = make_session()
    session.connect(credentials())
    base = BedrockConfig(model_id="us.openai.gpt-5.6-luna", profile="ignored", reasoning_effort="low")
    session.policy_provider(base)({"event": "before_search"})
    session.history_provider(base)({"source_sha256": "abc"})
    assert len(received) == 1
    assert len(native.requests) == 3
    assert native.requests[1]["additionalModelRequestFields"] == {"reasoning": {"effort": "low"}}
    assert native.requests[2]["additionalModelRequestFields"] == {"reasoning": {"effort": "high"}}


def test_disconnect_blocks_existing_providers_and_does_not_restore_ambient_credentials():
    from backend.bedrock_session import BedrockSessionError

    session, native, _, _ = make_session()
    session.connect(credentials())
    provider = session.history_provider()
    session.disconnect()
    assert session.status()["state"] == "disconnected"
    with pytest.raises(BedrockSessionError, match="Conecta"):
        provider({"anything": "untrusted"})
    with pytest.raises(BedrockSessionError, match="Conecta"):
        session.history_provider()({})
    assert len(native.requests) == 1


def test_expired_session_cannot_be_reused():
    from backend.bedrock_session import BedrockSessionError

    session, native, _, now = make_session()
    session.connect(credentials())
    provider = session.history_provider()
    now[0] += 61
    assert session.status()["state"] == "expired"
    with pytest.raises(BedrockSessionError):
        provider({})
    assert len(native.requests) == 1


def test_new_session_invalidates_previous_provider():
    from backend.bedrock_session import BedrockSessionError

    session, native, _, _ = make_session()
    session.connect(credentials())
    provider = session.history_provider()
    session.connect({"mode": "configured", "profile": "hackathon"})
    with pytest.raises(BedrockSessionError):
        provider({})
    assert len(native.requests) == 2


def test_invalid_credentials_never_appear_in_error():
    from backend.bedrock_session import BedrockSessionError

    session, _, _, _ = make_session()
    bad = credentials()
    bad["unknown_secret"] = "unknown-secret-do-not-expose"
    with pytest.raises(BedrockSessionError) as caught:
        session.connect(bad)
    assert "do-not-expose" not in str(caught.value)
    assert session.status()["connected"] is False


def test_sdk_errors_are_sanitized():
    from backend.bedrock_session import BedrockSessionError
    from botocore.exceptions import ClientError

    session, native, _, _ = make_session()
    native.failure = ClientError({
        "Error": {"Code": "AccessDeniedException", "Message": "secret-do-not-expose"},
    }, "Converse")
    with pytest.raises(BedrockSessionError) as caught:
        session.connect(credentials())
    assert caught.value.code == "access_denied"
    assert "secret-do-not-expose" not in str(caught.value)
    assert session.status()["connected"] is False


def test_unknown_model_never_silently_downgrades_high():
    from backend.bedrock_session import BedrockSessionError

    session, native, _, _ = make_session()
    with pytest.raises(BedrockSessionError) as caught:
        session.connect({"mode": "configured", "model_id": "vendor.unknown-model"})
    assert caught.value.code == "unsupported_reasoning_model"
    assert native.requests == []


def test_no_paid_probe_occurs_when_reading_status():
    session, native, received, _ = make_session()
    assert session.status()["state"] == "configured_unverified"
    assert not session.status()["connected"]
    assert received == []
    assert native.requests == []


def test_provider_can_use_preconfigured_chain_and_marks_verified_after_response():
    session, native, received, _ = make_session()
    session.policy_provider()({"event": "before_search"})
    assert session.status()["connected"]
    assert len(native.requests) == 1
    assert len(received) == 1


def test_disconnect_during_probe_cannot_resurrect_credentials():
    from backend.bedrock_session import BedrockSessionError

    session, native, _, _ = make_session()
    original = native.converse

    def disconnect_during_response(**payload):
        response = original(**payload)
        session.disconnect()
        return response

    native.converse = disconnect_during_response
    with pytest.raises(BedrockSessionError):
        session.connect(credentials())
    assert session.status()["state"] == "disconnected"
    assert not session.status()["connected"]


def test_all_temporary_credential_fields_are_required():
    from backend.bedrock_session import BedrockSessionError

    session, native, received, _ = make_session()
    payload = credentials()
    del payload["session_token"]
    with pytest.raises(BedrockSessionError):
        session.connect(payload)
    assert received == []
    assert native.requests == []


def test_unconfigured_manager_preserves_runtime_model_configuration():
    from backend.bedrock_session import BedrockSession

    session = BedrockSession()
    caller = BedrockConfig(model_id="us.openai.gpt-5.6-luna", profile="hackathon")
    settings = session.settings(caller)
    assert settings.model_id == caller.model_id
    assert settings.profile == caller.profile
