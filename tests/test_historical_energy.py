import json

import pandas as pd
import pytest

from ev_routing.contracts import Arc, ModelParameters, Node, ProblemInstance
from ev_routing.historical_energy import (
    HistoryConfig,
    HistoryNeedsMapping,
    apply_historical_energy,
    fit_historical_energy,
    inspect_history,
    normalize_history,
)


def road(reverse=True, parallel=False):
    nodes = [
        Node(node_id="B", node_type="base", latitude=42, longitude=-83),
        Node(node_id="J", node_type="junction", latitude=42, longitude=-82.999),
        Node(node_id="V", node_type="visit", latitude=42, longitude=-82.998),
    ]
    arcs = []
    pairs = [(0, 1), (1, 2)] + ([(1, 0), (2, 1)] if reverse else [])
    for a, b in pairs:
        first, second = nodes[a], nodes[b]
        arcs.append(Arc(
            from_node_id=first.node_id, to_node_id=second.node_id,
            source_id=f"street:{first.node_id}:{second.node_id}", distance_m=82.85,
            energy_kwh=.01657,
            geometry=[(first.latitude, first.longitude), (second.latitude, second.longitude)],
        ))
    if parallel:
        nodes += [
            Node(node_id="P", node_type="junction", latitude=42.00001, longitude=-83),
            Node(node_id="Q", node_type="junction", latitude=42.00001, longitude=-82.999),
        ]
        arcs.append(Arc(
            from_node_id="P", to_node_id="Q", source_id="parallel", distance_m=82.85,
            energy_kwh=.01657, geometry=[(42.00001, -83), (42.00001, -82.999)],
        ))
    return ProblemInstance(
        name="streets", nodes=nodes, arcs=arcs, parameters=ModelParameters(movement_limit=20),
    )


def eved(trips=5, reverse=False, second_rate=2, regeneration=False):
    records = []
    for trip in range(trips):
        positions = [-83, -82.9995, -82.999, -82.9985, -82.998]
        if reverse:
            positions.reverse()
        for i, longitude in enumerate(positions):
            current = -100 if i < 3 else -100 * second_rate
            if regeneration and i == 1:
                current = 30
            records.append({
                "VehId": "car", "Trip": str(trip),
                "Timestamp": f"2026-01-{trip + 1:02} 00:00:{i:02}",
                "Matched Latitude[deg]": 42, "Matched Longitude[deg]": longitude,
                "Match Type": 0, "Vehicle Speed[km/h]": 149.13,
                "HV Battery Current[A]": current, "HV Battery Voltage[V]": 360,
                "HV Battery SOC[%]": 60, "OAT[DegC]": 12,
            })
    return pd.DataFrame(records)


def write_csv(tmp_path, frame):
    path = tmp_path / "renamed-history.csv"
    frame.to_csv(path, index=False)
    return path


def fitted(tmp_path, frame=None, streets=None, **options):
    source = write_csv(tmp_path, eved() if frame is None else frame)
    data = normalize_history(source)
    streets = road() if streets is None else streets
    profile = fit_historical_energy(
        data, streets, config=HistoryConfig(min_support_distance_km=.001, **options),
    )
    return data, streets, profile


def test_eved_detection_uses_schema_and_preview_is_bounded(tmp_path):
    source = write_csv(tmp_path, eved(trips=20))
    inspection = inspect_history(source)
    assert inspection["recognized_format"] == "eved_ev"
    assert inspection["format"] == "eved"
    assert len(inspection["sample_rows"]) == 8
    assert inspection["sample_statistics"]["HV Battery Voltage[V]"]["numeric_max"] == 360
    assert inspection["source_sha256"] == normalize_history(source).source_sha256


def test_supported_directed_streets_have_different_energy_and_holdout(tmp_path):
    data, streets, profile = fitted(tmp_path)
    estimates = {(e.from_node_id, e.to_node_id): e for e in profile.estimates}
    assert set(estimates) == {("B", "J"), ("J", "V")}
    assert estimates["J", "V"].energy_kwh_per_km == pytest.approx(
        2 * estimates["B", "J"].energy_kwh_per_km, rel=.001,
    )
    assert profile.validation["training_trip_count"] == 4
    assert profile.validation["holdout_trip_count"] == 1
    assert profile.validation["prediction_mae_kwh"] == pytest.approx(0, abs=1e-7)
    assert profile.summary["arc_coverage_fraction"] == .5
    result = apply_historical_energy(streets, profile, .21)
    by_pair = {(a.from_node_id, a.to_node_id): a for a in result.arcs}
    assert by_pair["J", "B"].energy_kwh == pytest.approx(82.85 * .21 / 1000)
    assert by_pair["B", "J"].energy_kwh != pytest.approx(by_pair["J", "V"].energy_kwh)
    assert data.summary["trip_count"] == 5
    assert json.loads(profile.model_dump_json())["summary"]["calibrated_arc_count"] == 2


def test_reverse_direction_does_not_train_forward_streets(tmp_path):
    _, _, profile = fitted(tmp_path, eved(reverse=True))
    assert {(e.from_node_id, e.to_node_id) for e in profile.estimates} == {
        ("J", "B"), ("V", "J"),
    }
    _, _, against_oneway = fitted(tmp_path, eved(reverse=True), road(reverse=False))
    assert against_oneway.estimates == ()


def test_repeated_gps_preserves_energy_between_updates(tmp_path):
    frame = eved()
    frame.loc[frame.groupby("Trip").cumcount().eq(1), "Matched Longitude[deg]"] = -83
    frame.loc[frame.groupby("Trip").cumcount().eq(1), "Match Type"] = 1
    _, _, profile = fitted(tmp_path, frame)
    assert profile.summary["matched_block_count"] == 15
    first = next(e for e in profile.estimates if e.from_node_id == "B")
    assert first.energy_kwh_per_km * .08285 == pytest.approx(.02, rel=.001)


def test_irregular_dt_missing_and_gaps_are_not_bridged(tmp_path):
    frame = eved(trips=1)
    frame["Timestamp"] = [
        "2026-01-01 00:00:00", "2026-01-01 00:00:00.5",
        "2026-01-01 00:00:02", "2026-01-01 00:00:30", "2026-01-01 00:00:31",
    ]
    frame.loc[2, "HV Battery Current[A]"] = None
    data = normalize_history(write_csv(tmp_path, frame))
    assert data.summary["energy_kwh"] == pytest.approx(.025)
    assert data.summary["valid_interval_count"] == 2
    assert data.summary["dropped_gap_count"] == 1
    assert data.summary["missing_interval_count"] == 1


def test_no_intervals_cross_vehicle_or_trip_boundaries(tmp_path):
    frame = eved(trips=2)
    frame.loc[frame.Trip.eq("1"), "VehId"] = "other"
    data = normalize_history(write_csv(tmp_path, frame.sample(frac=1, random_state=2)))
    assert data.summary["valid_interval_count"] == 8
    assert data.summary["energy_kwh"] == pytest.approx(.12)


def test_mixed_sign_street_is_split_and_cannot_hide_prefix_deficit(tmp_path):
    data, streets, profile = fitted(tmp_path, eved(regeneration=True))
    result = apply_historical_energy(streets, profile, .2)
    first = [a for a in result.arcs if a.source_id == "street:B:J"]
    assert len(first) == 2
    assert first[0].energy_kwh > 0 > first[1].energy_kwh
    assert first[0].to_node_id == first[1].from_node_id
    assert sum(a.energy_kwh for a in first) == pytest.approx(.007, rel=.001)
    assert sum(a.distance_m for a in first) == 82.85
    assert data.summary["recovery_kwh"] > 0
    assert result.provenance["energy_model"]["mixed_sign_subdivisions"]
    assert any(a["key"] == "mixed_sign_order" for a in profile.assumptions)


def test_unrelated_geography_produces_explicit_manual_fallback(tmp_path):
    frame = eved()
    frame["Matched Latitude[deg]"] = -33.4
    frame["Matched Longitude[deg]"] = -70.6
    _, streets, profile = fitted(tmp_path, frame)
    assert not profile.estimates
    assert profile.summary["calibrated_arc_count"] == 0
    result = apply_historical_energy(streets, profile, .3)
    assert all(a.energy_kwh == pytest.approx(a.distance_m * .0003) for a in result.arcs)


def test_unknown_schema_needs_mapping_and_sign_units_are_required(tmp_path):
    frame = eved().rename(columns={"VehId": "vehicle", "Trip": "journey"})
    source = write_csv(tmp_path, frame)
    assert inspect_history(source)["format"] == "unknown"
    with pytest.raises(HistoryNeedsMapping):
        normalize_history(source)
    mapping = custom_mapping()
    mapping["current_sign"] = None
    with pytest.raises(HistoryNeedsMapping, match="signo"):
        normalize_history(source, mapping)


def custom_mapping():
    return {
        "vehicle_kind": "EV", "current_sign": "positive_charging",
        "energy_sign": "positive_consumption",
        "columns": {
            "vehicle_id": "vehicle", "trip_id": "journey", "timestamp": "Timestamp",
            "latitude": "Matched Latitude[deg]", "longitude": "Matched Longitude[deg]",
            "speed_kph": "Vehicle Speed[km/h]", "current_a": "HV Battery Current[A]",
            "voltage_v": "HV Battery Voltage[V]",
        },
        "units": {
            "timestamp": "iso8601", "latitude": "degrees", "longitude": "degrees",
            "speed_kph": "km/h", "current_a": "A", "voltage_v": "V",
        },
    }


def test_json_metadata_mapping_matches_eved_and_is_traceable(tmp_path):
    original = eved()
    frame = original.rename(columns={"VehId": "vehicle", "Trip": "journey"})
    source = tmp_path / "history.json"
    source.write_text(json.dumps({
        "metadata": {"vehicle_kind": "EV", "mapping": custom_mapping()},
        "records": frame.to_dict("records"),
    }))
    data = normalize_history(source)
    assert inspect_history(source)["format"] == "mapped"
    expected = normalize_history(write_csv(tmp_path, original))
    assert data.summary["energy_kwh"] == expected.summary["energy_kwh"]


@pytest.mark.parametrize("kind", ["ICE", "PHEV", "HEV", "unknown"])
def test_non_ev_or_unconfirmed_vehicle_types_cannot_be_calibrated(tmp_path, kind):
    frame = eved().rename(columns={"VehId": "vehicle", "Trip": "journey"})
    mapping = custom_mapping()
    mapping["vehicle_kind"] = kind
    with pytest.raises(HistoryNeedsMapping, match="eléctricos"):
        normalize_history(write_csv(tmp_path, frame), mapping)


def test_combustion_signals_cannot_be_overridden_with_ev_mapping(tmp_path):
    frame = eved()
    frame["MAF[g/sec]"] = 10
    with pytest.raises(ValueError, match="combustión"):
        normalize_history(write_csv(tmp_path, frame))


@pytest.mark.parametrize(
    "column", ["vehicle_kind", " Vehicle Type ", "POWERTRAIN", "Fuel_Type", " tipo_vehículo "],
)
@pytest.mark.parametrize("invalid_type", ["HEV", "ICE", "PHEV", "mixed", None, " "])
def test_every_declared_vehicle_class_is_checked_before_signal_selection(
    tmp_path, column, invalid_type,
):
    frame = eved().rename(columns={"VehId": "vehicle", "Trip": "journey"})
    frame[column] = "EV"
    frame.loc[len(frame) - 1, column] = invalid_type
    with pytest.raises(ValueError, match="Todas las filas deben indicar"):
        normalize_history(write_csv(tmp_path, frame), custom_mapping())


def test_hybrid_beyond_ai_preview_cannot_be_hidden_by_first_ev_sample(tmp_path):
    frame = pd.concat([eved()] * 41, ignore_index=True).rename(
        columns={"VehId": "vehicle", "Trip": "journey"}
    )
    frame["journey"] = (frame.index // 5).astype(str)
    frame["vehicle_kind"] = "EV"
    frame.loc[1000, "vehicle_kind"] = "HEV"
    source = write_csv(tmp_path, frame)
    inspection = inspect_history(source)
    assert inspection["sample_row_count"] == 256
    assert all(row["vehicle_kind"] == "EV" for row in inspection["sample_rows"])
    with pytest.raises(ValueError, match="Todas las filas deben indicar"):
        normalize_history(source, custom_mapping())


def test_equivalent_ev_class_labels_accept_case_and_surrounding_spaces(tmp_path):
    frame = eved().rename(columns={"VehId": "vehicle", "Trip": "journey"})
    frame[" Vehicle Kind "] = [" ev ", "BEV", "electric", "EV", "  Electric  "] * 5
    data = normalize_history(write_csv(tmp_path, frame), custom_mapping())
    assert data.summary["row_count"] == len(frame)


def test_explicit_non_ev_metadata_alias_cannot_override_ev_mapping(tmp_path):
    frame = eved().rename(columns={"VehId": "vehicle", "Trip": "journey"})
    source = tmp_path / "history.json"
    source.write_text(json.dumps({
        "metadata": {" Vehicle Type ": "HEV", "mapping": custom_mapping()},
        "records": frame.to_dict("records"),
    }))
    with pytest.raises(ValueError, match="metadatos"):
        normalize_history(source)


def test_csv_duplicate_headers_cannot_be_silently_renamed(tmp_path):
    source = tmp_path / "duplicate.csv"
    source.write_text("vehicle_kind,vehicle_kind,power_kw\nEV,HEV,1\n")
    with pytest.raises(ValueError, match="columnas repetidos"):
        inspect_history(source)
    with pytest.raises(ValueError, match="columnas repetidos"):
        normalize_history(source, custom_mapping())


def test_json_duplicate_keys_cannot_hide_conflicting_vehicle_classes(tmp_path):
    source = tmp_path / "duplicate.json"
    source.write_text(
        '{"metadata":{"vehicle_kind":"HEV","vehicle_kind":"EV"},"records":[{"power_kw":1}]}'
    )
    with pytest.raises(ValueError, match="claves repetidas"):
        inspect_history(source)
    with pytest.raises(ValueError, match="claves repetidas"):
        normalize_history(source, custom_mapping())


def test_duplicate_timestamps_fail_without_silent_sensor_merging(tmp_path):
    frame = eved()
    frame.loc[1, "Timestamp"] = frame.loc[0, "Timestamp"]
    with pytest.raises(ValueError, match="duplicadas"):
        normalize_history(write_csv(tmp_path, frame))


def test_no_valid_intervals_reports_missing_evidence_not_zero_consumption(tmp_path):
    frame = eved().iloc[[0]]
    with pytest.raises(ValueError, match="no tiene intervalos válidos"):
        normalize_history(write_csv(tmp_path, frame))


def test_synthetic_geometry_is_not_mistaken_for_observed_streets(tmp_path):
    streets = road().model_copy(update={"provenance": {
        "network": {"kind": "haversine", "vial": False},
    }})
    _, _, profile = fitted(tmp_path, streets=streets)
    assert profile.estimates == ()
    assert profile.summary["unmatched_reasons"]["synthetic_network_has_no_streets"] == 1


def test_zero_speed_energy_is_integrated_not_discarded(tmp_path):
    frame = eved()
    frame.loc[frame.groupby("Trip").cumcount().eq(1), "Vehicle Speed[km/h]"] = 0
    data = normalize_history(write_csv(tmp_path, frame))
    assert data.summary["stationary_energy_kwh"] == pytest.approx(.05)
    assert data.summary["energy_kwh"] == pytest.approx(.30)


@pytest.mark.parametrize("speed_available", [True, False])
def test_stationary_charging_does_not_become_regeneration_of_the_next_street(
    tmp_path, speed_available,
):
    frame = eved()
    charging = frame.groupby("Trip").cumcount().eq(1)
    frame.loc[charging, "Matched Longitude[deg]"] = -83
    frame.loc[charging, "Match Type"] = 1
    frame.loc[charging, "Vehicle Speed[km/h]"] = 0
    frame.loc[charging, "HV Battery Current[A]"] = 150  # 15 Wh received while stopped.
    # Next sample travels to J and consumes 10 Wh. Netting the two used to
    # invent a -5 Wh nominal street and charge the route while driving.
    if speed_available:
        data = normalize_history(write_csv(tmp_path, frame))
    else:
        frame = frame.rename(columns={"VehId": "vehicle", "Trip": "journey"}).drop(
            columns=["Vehicle Speed[km/h]"]
        )
        mapping = custom_mapping()
        del mapping["columns"]["speed_kph"]
        del mapping["units"]["speed_kph"]
        data = normalize_history(write_csv(tmp_path, frame), mapping)
    streets = road()
    profile = fit_historical_energy(
        data, streets, config=HistoryConfig(min_support_distance_km=.001),
    )
    assert data.summary["recovery_kwh"] == pytest.approx(.075)
    assert data.summary["ambiguous_stationary_recovery_kwh"] == pytest.approx(.075)
    assert data.summary["ambiguous_stationary_recovery_interval_count"] == 5
    assert profile.summary["unmatched_reasons"]["ambiguous_stationary_charging"] == 5
    assert profile.summary["matched_recovery_kwh"] == 0
    assert all(estimate.from_node_id != "B" for estimate in profile.estimates)
    assert any(estimate.from_node_id == "J" for estimate in profile.estimates)
    result = apply_historical_energy(streets, profile, .2)
    first = next(a for a in result.arcs if a.from_node_id == "B" and a.to_node_id == "J")
    assert first.energy_kwh == pytest.approx(.01657)
    assert not result.provenance["energy_model"]["mixed_sign_subdivisions"]


def test_ambiguous_parallel_streets_are_rejected(tmp_path):
    frame = eved().iloc[:3].copy()
    frame["Matched Latitude[deg]"] = 42.000005
    _, _, profile = fitted(tmp_path, frame, road(parallel=True), min_trip_count=1)
    assert not profile.estimates
    assert profile.summary["unmatched_reasons"]["ambiguous_parallel_paths"] == 2


def test_custom_identifier_columns_keep_leading_zeroes(tmp_path):
    frame = eved(trips=2).rename(columns={"VehId": "vehicle", "Trip": "journey"})
    frame.loc[frame.journey.eq("0"), "vehicle"] = "001"
    frame.loc[frame.journey.eq("1"), "vehicle"] = "1"
    data = normalize_history(write_csv(tmp_path, frame), custom_mapping())
    assert set(data.frame.vehicle_id) == {"001", "1"}


def test_source_mapping_policy_and_network_invalidate_profile_identity(tmp_path):
    data, streets, profile = fitted(tmp_path)
    changed = streets.model_copy(update={"arcs": [
        streets.arcs[0].model_copy(update={"distance_m": 90}), *streets.arcs[1:],
    ]})
    with pytest.raises(ValueError, match="otra red"):
        apply_historical_energy(changed, profile, .2)
    new_profile = fit_historical_energy(data, streets, config=HistoryConfig(min_trip_count=3))
    assert new_profile.model_id != profile.model_id
    frame = eved()
    frame.loc[1, "HV Battery Current[A]"] = -101
    changed_data = normalize_history(write_csv(tmp_path, frame))
    assert changed_data.source_sha256 != data.source_sha256


def test_holdout_never_leaks_into_calibration(tmp_path):
    frame = eved()
    frame.loc[frame.Trip.eq("4"), "HV Battery Current[A]"] *= 10
    _, _, profile = fitted(tmp_path, frame)
    original_data, original_road, original = fitted(tmp_path, eved())
    assert profile.estimates == original.estimates
    assert profile.validation["prediction_mae_kwh"] > .1


def test_negative_cycle_is_rejected_without_clipping_observed_regeneration(tmp_path):
    forward, backward = eved(), eved(reverse=True)
    backward["Trip"] = backward.Trip.astype(int).add(10).astype(str)
    forward["HV Battery Current[A]"] = 100
    backward["HV Battery Current[A]"] = 100
    frame = pd.concat([forward, backward], ignore_index=True)
    _, streets, profile = fitted(tmp_path, frame, holdout_fraction=0)
    assert profile.summary["recovery_kwh"] > 0
    assert not profile.estimates
    assert profile.summary["unmatched_reasons"]["negative_cycle_or_unverified_component"] > 0
    assert all(a.energy_kwh > 0 for a in apply_historical_energy(streets, profile, .2).arcs)
