"""Contrato de acciones, llamadas acotadas y aislamiento del controlador."""

import json
from concurrent.futures import Future
from time import monotonic

import pytest
from pydantic import ValidationError

from ev_routing.llm.bedrock import BedrockPolicyClient
from ev_routing.search_policy import BedrockConfig, SearchConfig, SearchController, SearchPolicy


@pytest.mark.parametrize("proposal", [
    {"movement_limit": 99}, {"time_limit": 999}, {"feastol": 0.1},
    {"pricing": "heuristic_only"}, {"columns_per_round": 0},
    {"columns_per_round": "10"}, {"stabilization": "false"},
    {"code": "import os"}, {"decomposition": "delete_battery"},
])
def test_policy_rejects_model_changes_and_unsafe_search(proposal):
    with pytest.raises(ValidationError):
        SearchPolicy.model_validate(proposal)


def controller(provider, **options):
    return SearchController(
        SearchConfig(
            policy="adaptive", bedrock={"model_id": "test-model"},
            decision_interval_seconds=0, min_pricing_calls_between_decisions=1, **options,
        ),
        monotonic() + 60, provider,
    )


@pytest.mark.parametrize("reply", [
    None, [], {}, {"policy": {} , "usage": {} , "extra": 1, "invalid": True},
])
def test_malformed_provider_falls_back_without_executing_code(reply):
    if isinstance(reply, dict) and "policy" in reply:
        reply["policy"] = {"exec": "raise Exception()"}
    c = controller(lambda request: reply)
    c.start_phase("deliveries", {"customers": 2})
    assert c.policy.decomposition == "vehicle"
    assert c.report()["status"] == "fallback"
    assert c.records[0]["status"] == "rejected"
    c.close()


def test_decomposition_only_before_solve_and_call_limit():
    seen = []

    def provider(request):
        seen.append(request)
        return {"policy": {"decomposition": "vehicle_routing", "pricing": "exact"}}

    c = controller(provider, max_llm_calls=1)
    c.start_phase("deliveries", {"customers": 2})
    assert c.locked_decomposition == "vehicle_routing"
    c.pricing_calls = 100
    c.observe("pricing", {"dual_bound": None})
    assert len(seen) == 1
    request = c._request("pricing", {})
    c._receive({"request": request, "reply": {"policy": {"decomposition": "vehicle"}}, "seconds": 0})
    assert c.records[-1]["reason"] == "decomposition_locked_during_solve"
    assert c.policy.decomposition == "vehicle_routing"
    c.close()


def test_late_phase_response_is_recorded_but_cannot_change_next_phase():
    c = controller(lambda request: {"policy": {}})
    c.start_phase("deliveries", {})
    reply = {"request": c._request("pricing", {}), "reply": {"policy": {"pricing": "exact"}},
             "seconds": 0.01}
    c.pending = Future()
    c.phase = "energy"
    c.pending.set_result(reply)
    assert not c.collect()
    assert c.records[-1]["status"] == "not_applied"
    assert c.policy.pricing == "native"
    c.close()


def test_aws_error_sanitized_and_budget_exhaustion_skips_calls():
    def unavailable(request):
        raise RuntimeError("a-secret-that-must-not-be-persisted")

    c = controller(unavailable)
    c.start_phase("deliveries", {})
    assert "a-secret" not in json.dumps(c.report())
    assert c.records[0]["reason"] == "RuntimeError"
    c.deadline = monotonic()
    c.start_phase("energy", {})
    assert c.calls == 1
    c.close()


@pytest.mark.parametrize("model_id", [None, "", " \t "])
def test_adaptive_requires_model_and_respects_user_aws_defaults(model_id):
    with pytest.raises(ValidationError, match="bedrock-model"):
        SearchConfig(policy="adaptive", bedrock={"model_id": model_id})
    config = BedrockConfig(model_id=model_id)
    assert (config.region, config.profile, config.model_id) == ("us-east-1", "hackathon", None)
    assert SearchConfig(policy="standard", bedrock=config).bedrock.model_id is None


class FakeBedrock:
    def __init__(self, text='{"pricing": "exact"}', stop="end_turn"):
        self.text, self.stop, self.calls = text, stop, []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "stopReason": self.stop,
            "output": {"message": {"content": [{"text": self.text}]}},
            "usage": {"inputTokens": 12, "outputTokens": 8, "totalTokens": 20},
        }


def test_converse_uses_parameterized_model_and_json_without_dynamic_execution():
    native = FakeBedrock('```json\n{"pricing": "exact"}\n```')
    client = BedrockPolicyClient(
        BedrockConfig(model_id="my-inference-profile", max_output_tokens=768), client=native,
    )
    result = client({"structure": {"customers": 2}})
    assert result["policy"] == {"pricing": "exact"}
    assert result["usage"]["totalTokens"] == 20
    assert native.calls[0]["modelId"] == "my-inference-profile"
    assert native.calls[0]["inferenceConfig"] == {"maxTokens": 768}
    assert json.loads(native.calls[0]["messages"][0]["content"][0]["text"]) == {
        "structure": {"customers": 2},
    }


@pytest.mark.parametrize("text,stop", [
    ('{"pricing": "exact"', "end_turn"),
    ('{"pricing": "exact"}', "max_tokens"),
    ("[]", "end_turn"), ("__import__('os').system('false')", "end_turn"),
])
def test_converse_rejects_truncated_or_non_json_answers(text, stop):
    client = BedrockPolicyClient(
        BedrockConfig(model_id="test"), client=FakeBedrock(text, stop),
    )
    with pytest.raises(ValueError):
        client({})


def test_rejected_paid_response_preserves_token_usage():
    client = BedrockPolicyClient(
        BedrockConfig(model_id="test"), client=FakeBedrock("bad-json"),
    )
    c = controller(client)
    c.start_phase("deliveries", {})
    assert c.records[0]["reason"] == "invalid_json"
    assert c.records[0]["usage"]["totalTokens"] == 20
    assert c.report()["status"] == "fallback"
    c.close()

