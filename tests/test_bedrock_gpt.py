"""GPT por Converse: esfuerzo correcto, trazabilidad y errores, sin red."""

import json
from threading import get_ident
from time import monotonic

import pytest

from ev_routing.llm.bedrock import BedrockPolicyClient, BedrockResponseError
from ev_routing.llm_head import LLMHead
from ev_routing.search_policy import DEFAULT_BEDROCK_MODEL, BedrockConfig, SearchConfig


class Client:
    def __init__(self, text='{"columns_per_round":75}', stop="end_turn"):
        self.text, self.stop = text, stop
        self.payload = None

    def converse(self, **payload):
        self.payload = payload
        return {
            "output": {"message": {"role": "assistant", "content": [
                {"reasoningContent": {"reasoningText": {"text": "private-reasoning"}}},
                {"text": self.text},
            ]}},
            "usage": {"inputTokens": 100, "outputTokens": 20, "totalTokens": 120},
            "stopReason": self.stop,
            "ResponseMetadata": {"HTTPHeaders": {"Authorization": "must-not-be-logged"}},
        }


def test_gpt_low_effort_payload_usage_and_live_trace(tmp_path, capsys):
    native = Client()
    client = BedrockPolicyClient(
        BedrockConfig(model_id=DEFAULT_BEDROCK_MODEL), client=native, temperature=0,
        trace_directory=str(tmp_path), show_trace=True,
    )
    result = client({"event": "before_search", "structure": {"customers": 40}})
    assert result["policy"] == {"columns_per_round": 75}
    assert result["usage"]["totalTokens"] == 120
    assert native.payload["additionalModelRequestFields"] == {"reasoning": {"effort": "low"}}
    assert "temperature" not in native.payload["inferenceConfig"]
    assert json.loads(native.payload["messages"][0]["content"][0]["text"])["structure"]["customers"] == 40
    assert json.loads((tmp_path / "llm-request.json").read_text()) == native.payload
    saved = (tmp_path / "llm-response.json").read_text()
    console = capsys.readouterr().out
    assert '"columns_per_round":75' in console
    assert "private-reasoning" not in saved + console
    assert "must-not-be-logged" not in saved + console


@pytest.mark.parametrize("text,stop,code", [
    ('{"columns_per_round":75}', "max_tokens", "incomplete_response"),
    ("invalid JSON", "end_turn", "invalid_json"),
    ("[]", "end_turn", "invalid_object"),
])
def test_incomplete_or_invalid_gpt_response_preserves_usage(text, stop, code):
    with pytest.raises(BedrockResponseError, match=code) as caught:
        BedrockPolicyClient(
            BedrockConfig(model_id=DEFAULT_BEDROCK_MODEL), client=Client(text, stop),
        )({})
    assert caught.value.usage["totalTokens"] == 120


def test_explicit_gpt_effort_and_anthropic_effort_use_different_fields():
    gpt = BedrockPolicyClient(BedrockConfig(
        model_id=DEFAULT_BEDROCK_MODEL, reasoning_effort="medium",
    )).request_payload({})
    claude = BedrockPolicyClient(BedrockConfig(
        model_id="us.anthropic.claude-fable-5", reasoning_effort="high",
    )).request_payload({})
    assert gpt["additionalModelRequestFields"] == {"reasoning": {"effort": "medium"}}
    assert claude["additionalModelRequestFields"] == {
        "thinking": {"type": "adaptive"}, "output_config": {"effort": "high"},
    }


@pytest.mark.parametrize("policy,injected,preloads", [
    ("adaptive", False, True), ("adaptive", True, False), ("standard", False, False),
])
def test_sdk_setup_precedes_cpu_search_only_for_real_adaptive_provider(
    monkeypatch, policy, injected, preloads,
):
    from ev_routing.llm import bedrock

    threads = []
    native = Client()

    def prepare(config):
        threads.append(get_ident())
        return native

    monkeypatch.setattr(bedrock, "create_bedrock_client", prepare)
    config = SearchConfig(policy=policy, bedrock=BedrockConfig(model_id=DEFAULT_BEDROCK_MODEL))
    head = LLMHead(
        config, {}, monotonic() + 3, 3,
        provider=(lambda _: {}) if injected else None,
    )
    assert threads == ([get_ident()] if preloads else [])
    assert head.calls == 0  # La precarga local no invoca al proveedor.
    assert native.payload is None
    if preloads:
        reply = head._call({"event": "before_search"}, config.bedrock, 1)
        assert reply["reply"]["policy"] == {"columns_per_round": 75}
        assert threads == [get_ident()]  # El trabajador reutiliza el transporte.


def test_missing_optional_sdk_still_records_provider_fallback(monkeypatch):
    from ev_routing.llm import bedrock

    def missing(config):
        raise ModuleNotFoundError("boto3")

    monkeypatch.setattr(bedrock, "create_bedrock_client", missing)
    config = SearchConfig(policy="adaptive", bedrock=BedrockConfig(model_id=DEFAULT_BEDROCK_MODEL))
    head = LLMHead(config, {}, monotonic() + 3, 3)
    head.decide("before_search", {"phase": "planning"})
    if head.pending is not None:
        head.pending.result(timeout=1)
    head.collect()
    assert head.report()["status"] == "fallback"
    assert head.records[0]["reason"] == "ModuleNotFoundError"
