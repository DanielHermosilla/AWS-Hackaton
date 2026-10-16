"""Historical AI extraction is a bounded schema proposal, never executable physics."""

import pytest

from ev_routing.search_policy import BedrockConfig


def profile():
    return {
        "schema_version": "1.0", "source_sha256": "a" * 64,
        "file_format": "csv", "size_bytes": 900, "filename": "observaciones.csv",
        "columns": ["car", "trip", "time", "lat", "lon", "speed_km/h", "power_kW"],
        "sample_rows": [
            {"car": "a", "trip": "t", "time": 1, "lat": 42.2, "lon": -83.2,
             "speed_km/h": 20, "power_kW": 3},
        ],
        "sample_statistics": {"speed_km/h": {"numeric_min": 20, "numeric_max": 20,
                                            "non_null_count": 1, "missing_count": 0}},
        "sample_row_count": 1,
        "declared_metadata": {
            "vehicle_kind": "EV", "timestamp_unit": "elapsed_s",
            "coordinates_unit": "degrees", "power_sign": "positive_consumption",
        },
        "recognized_format": None,
    }


def proposal():
    return {
        "schema_version": "1.0",
        "mapping": {
            "columns": {
                "vehicle_id": "car", "trip_id": "trip", "timestamp": "time",
                "latitude": "lat", "longitude": "lon", "speed_kph": "speed_km/h",
                "power_kw": "power_kW",
            },
            "units": {
                "timestamp": "elapsed_s", "latitude": "degrees", "longitude": "degrees",
                "speed_kph": "km/h", "power_kw": "kW",
            },
            "current_sign": None, "energy_sign": "positive_consumption", "vehicle_kind": "EV",
            "evidence": [
                {"kind": "metadata", "key": "vehicle_kind", "value": "EV"},
                {"kind": "metadata", "key": "timestamp_unit", "value": "elapsed_s"},
                {"kind": "metadata", "key": "coordinates_unit", "value": "degrees"},
                {"kind": "metadata", "key": "power_sign", "value": "positive_consumption"},
                {"kind": "column", "key": "speed_km/h"},
                {"kind": "column", "key": "power_kW"},
            ],
        },
        "observations": [{
            "name": "Velocidad máxima de la muestra", "value": 20, "unit": "km/h",
            "evidence": [{"kind": "statistic", "key": "speed_km/h",
                          "statistic": "numeric_max", "value": 20}],
            "explanation": "Solo describe la muestra inspeccionada.",
        }],
        "assumptions": [],
        "limitations": ["La muestra no demuestra cobertura de todas las calles."],
        "unresolved_fields": [],
    }


def config():
    return BedrockConfig(model_id="us.openai.gpt-5.6-luna", reasoning_effort="high", profile=None)


def analyze(answer, data=None):
    from ev_routing.llm.history import analyze_history_profile

    return analyze_history_profile(
        data or profile(), config=config(),
        provider=lambda request: {"policy": answer, "usage": {"totalTokens": 100},
                                  "stop_reason": "end_turn"},
    )


def test_imported_history_feature_is_available():
    from ev_routing.llm import history

    assert callable(history.analyze_history_profile)


def test_valid_mapping_retains_provenance_and_records_high():
    result = analyze(proposal())
    assert result["interpretation"]["mapping"]["units"]["power_kw"] == "kW"
    assert result["ai"]["reasoning_effort"] == "high"
    assert result["ai"]["source_sha256"] == "a" * 64
    assert result["ai"]["usage"]["totalTokens"] == 100
    assert result["ai"]["scope"] == "sample_profile_not_complete_file"


@pytest.mark.parametrize("mutation", ["unknown_column", "unit", "sign", "EV", "evidence", "number"])
def test_unfounded_mapping_or_evidence_is_rejected(mutation):
    from ev_routing.llm.history import HistoryInterpretationError

    answer = proposal()
    if mutation == "unknown_column":
        answer["mapping"]["columns"]["power_kw"] = "invented"
    elif mutation == "unit":
        answer["mapping"]["units"]["power_kw"] = "volts"
    elif mutation == "sign":
        answer["mapping"]["energy_sign"] = "positive_charging"
    elif mutation == "EV":
        data = profile()
        data["declared_metadata"]["vehicle_kind"] = "PHEV"
        with pytest.raises(HistoryInterpretationError):
            analyze(answer, data)
        return
    elif mutation == "evidence":
        answer["mapping"]["evidence"][0]["key"] = "nonexistent"
    else:
        answer["observations"][0]["value"] = 999
    with pytest.raises(HistoryInterpretationError):
        analyze(answer)


def test_arbitrary_physical_change_and_code_are_not_allowed():
    from ev_routing.llm.history import HistoryInterpretationError

    answer = proposal()
    answer["problem_config"] = {"reserve_kwh": 0}
    with pytest.raises(HistoryInterpretationError):
        analyze(answer)
    answer = proposal()
    answer["mapping"]["columns"]["power_kw"] = "__import__('os').system('x')"
    with pytest.raises(HistoryInterpretationError):
        analyze(answer)


def test_unknown_units_are_reported_without_applying_mapping():
    answer = proposal()
    answer["mapping"] = None
    answer["unresolved_fields"] = ["No se declara la unidad de energía."]
    result = analyze(answer)
    assert result["interpretation"]["mapping"] is None
    assert result["interpretation"]["unresolved_fields"]


def test_never_claims_high_for_a_low_provider_configuration():
    from ev_routing.llm.history import HistoryInterpretationError, analyze_history_profile

    with pytest.raises(HistoryInterpretationError, match="HIGH"):
        analyze_history_profile(profile(), provider=lambda _: {},
                                config=config().model_copy(update={"reasoning_effort": "low"}))


def test_oversize_profile_is_rejected_before_provider_call():
    from ev_routing.llm.history import HistoryInterpretationError, analyze_history_profile

    called = []
    data = profile()
    data["declared_metadata"]["too_large"] = "x" * 70_000
    with pytest.raises(HistoryInterpretationError):
        analyze_history_profile(data, config=config(), provider=lambda x: called.append(x))
    assert not called


def test_no_unbounded_prompt_secrets_or_hidden_instructions():
    from ev_routing.llm.history import HistoryInterpretationError, analyze_history_profile

    data = profile()
    data["AWS_SECRET_ACCESS_KEY"] = "secret-value-never-send"
    called = []
    with pytest.raises(HistoryInterpretationError):
        analyze_history_profile(data, config=config(), provider=lambda x: called.append(x))
    assert not called


def test_model_reported_observation_is_scoped_and_matches_local_statistic():
    result = analyze(proposal())
    observation = result["interpretation"]["observations"][0]
    assert observation["value"] == 20
    assert "muestra" in observation["explanation"]


def test_ai_assumptions_remain_unapplied():
    answer = proposal()
    answer["assumptions"] = [{
        "description": "Verificar cómo cambia el consumo con la temperatura.",
        "evidence": [{"kind": "column", "key": "power_kW"}], "applied": False,
    }]
    assert not analyze(answer)["interpretation"]["assumptions"][0]["applied"]
    answer["assumptions"][0]["applied"] = True
    from ev_routing.llm.history import HistoryInterpretationError
    with pytest.raises(HistoryInterpretationError):
        analyze(answer)


def test_canonical_header_cannot_support_a_different_unit():
    from ev_routing.llm.history import HistoryInterpretationError

    data = profile()
    data["columns"][-1] = "power_kw"
    data["sample_rows"][0]["power_kw"] = data["sample_rows"][0].pop("power_kW")
    answer = proposal()
    answer["mapping"]["columns"]["power_kw"] = "power_kw"
    answer["mapping"]["units"]["power_kw"] = "W"
    answer["mapping"]["evidence"][-1]["key"] = "power_kw"
    with pytest.raises(HistoryInterpretationError):
        analyze(answer, data)


def test_current_sign_needs_current_evidence_not_an_unrelated_metadata_value():
    from ev_routing.llm.history import HistoryInterpretationError

    data = profile()
    data["columns"].extend(["current_a", "voltage_v"])
    answer = proposal()
    answer["mapping"]["columns"].update(current_a="current_a", voltage_v="voltage_v")
    answer["mapping"]["units"].update(current_a="A", voltage_v="V")
    answer["mapping"]["current_sign"] = "positive_consumption"
    with pytest.raises(HistoryInterpretationError):
        analyze(answer, data)


def test_ev_classification_cannot_reuse_an_unrelated_ev_string():
    from ev_routing.llm.history import HistoryInterpretationError

    data = profile()
    data["declared_metadata"] = {**data["declared_metadata"], "project": "EV"}
    del data["declared_metadata"]["vehicle_kind"]
    answer = proposal()
    answer["mapping"]["evidence"][0]["key"] = "project"
    with pytest.raises(HistoryInterpretationError):
        analyze(answer, data)


def test_statistical_phase_can_only_repeat_computed_values():
    data = profile()
    data["computed_summary"] = {"trips": {"count": 3}}
    answer = proposal()
    answer["mapping"] = None
    answer["observations"] = [{
        "name": "Viajes analizados", "value": 3, "unit": None,
        "explanation": "Calculados localmente sobre el archivo.",
        "evidence": [{"kind": "computed", "key": "trips.count", "value": 3}],
    }]
    assert analyze(answer, data)["interpretation"]["observations"][0]["value"] == 3


def test_invalid_response_preserves_bounded_usage_without_preserving_raw_text():
    from ev_routing.llm.history import HistoryInterpretationError, analyze_history_profile

    with pytest.raises(HistoryInterpretationError) as caught:
        analyze_history_profile(
            profile(), config=config(),
            provider=lambda _: {"policy": {"secret": "private-file-cell"},
                                "usage": {"inputTokens": 12, "outputTokens": 5, "unknown": "secret"}},
        )
    assert caught.value.usage == {"inputTokens": 12, "outputTokens": 5}
    assert "private-file-cell" not in repr(caught.value)
