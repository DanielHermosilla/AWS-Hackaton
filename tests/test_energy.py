import json

import pandas as pd
import pytest

from ev_routing.energy import (
    fit_distance_rate,
    integrate_eved,
    integrate_eved_csv,
    save_energy_model,
)


def samples():
    return pd.DataFrame(
        {
            "VehId": [10, 10, 10, 10, 455, 455],
            "Trip": [1, 1, 1, 2, 1, 1],
            "Timestamp": [
                "2026-01-01 00:00:00", "2026-01-01 00:00:00.5",
                "2026-01-01 00:00:02", "2026-01-02 00:00:00",
                "2026-01-01 00:00:00", "2026-01-01 00:00:04",
            ],
            "Vehicle Speed[km/h]": [36, 36, 36, 36, 72, 72],
            "HV Battery Current[A]": [-10, -10, 5, -10, -10, -20],
            "HV Battery Voltage[V]": [360] * 6,
        }
    )


def test_integrates_irregular_times_regeneration_and_never_crosses_trip_or_vehicle():
    frame = samples()
    result = integrate_eved(frame.sample(frac=1, random_state=7))
    # Vehicle 10 trip 1: .5*.001 - 1.5*.0005 = -.00025 kWh.
    # Vehicle 455 trip 1: 4*.002 = .008 kWh. Trip 2 contributes nothing.
    assert result.energy_kwh == pytest.approx(0.00775)
    assert result.distance_km == pytest.approx(0.1)
    assert result.integrated_seconds == 6
    assert result.valid_interval_count == 3
    assert result.trip_count == 3
    assert next(t for t in result.trips if t.vehicle_id == "10" and t.trip_id == "1").energy_kwh < 0
    model = fit_distance_rate(result)
    assert model.kwh_per_km == pytest.approx(0.0775)
    assert model.training_summary is result


def test_energy_column_uses_dt_and_matches_battery_power():
    frame = samples()
    frame["Energy_Consumption"] = -frame["HV Battery Current[A]"] * 360 / 3.6e6
    from_column = integrate_eved(frame, energy_source="energy_column")
    assert from_column.energy_kwh == pytest.approx(integrate_eved(frame).energy_kwh)
    assert from_column.energy_kwh != pytest.approx(frame.Energy_Consumption.sum())


def test_gap_and_missing_intervals_excluded_from_both_integrals_without_bridging():
    frame = pd.DataFrame(
        {
            "VehId": ["A"] * 6, "Trip": ["T"] * 6,
            "Timestamp": pd.to_datetime([0, 1, 2, 100, 101, 102], unit="s"),
            "Vehicle Speed[km/h]": [36, 36, 36, 36, 36, None],
            "HV Battery Current[A]": [-10, -10, None, -10, -10, -10],
            "HV Battery Voltage[V]": [360] * 6,
        }
    )
    result = integrate_eved(frame, max_gap_seconds=10)
    assert result.valid_interval_count == 2
    assert result.missing_interval_count == 2
    assert result.dropped_gap_count == 1
    assert result.integrated_seconds == 2
    assert result.energy_kwh == pytest.approx(0.002)
    assert result.distance_km == pytest.approx(0.02)


@pytest.mark.parametrize("gap", [0, -1, float("nan"), float("inf")])
def test_gap_threshold_must_be_finite_and_positive(gap):
    with pytest.raises(ValueError, match="max_gap_seconds"):
        integrate_eved(samples(), max_gap_seconds=gap)


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("Vehicle Speed[km/h]", -1, "velocidad"),
        ("HV Battery Voltage[V]", 0, "voltaje"),
        ("HV Battery Current[A]", float("inf"), "infinito"),
        ("VehId", None, "no pueden faltar"),
        ("Trip", "", "vacío"),
        ("Timestamp", None, "no pueden faltar"),
    ],
)
def test_invalid_samples_report_errors(column, value, message):
    frame = samples()
    frame[column] = frame[column].astype(object)
    frame.loc[1, column] = value
    with pytest.raises(ValueError, match=message):
        integrate_eved(frame)


def test_duplicate_times_and_missing_columns_rejected():
    frame = samples()
    frame.loc[1, "Timestamp"] = frame.loc[0, "Timestamp"]
    with pytest.raises(ValueError, match="duplicado"):
        integrate_eved(frame)
    with pytest.raises(ValueError, match="Faltan columnas"):
        integrate_eved(samples().drop(columns=["HV Battery Current[A]"]))


def test_no_positive_training_energy_does_not_silently_clamp_regeneration():
    frame = samples()
    frame["HV Battery Current[A]"] = 10
    summary = integrate_eved(frame)
    assert summary.energy_kwh < 0
    with pytest.raises(ValueError, match="positivas"):
        fit_distance_rate(summary)


def test_empty_and_zero_distance_cannot_fit():
    with pytest.raises(ValueError, match="No hay registros"):
        integrate_eved(samples().iloc[:0])
    frame = samples()
    frame["Vehicle Speed[km/h]"] = 0
    with pytest.raises(ValueError, match="positivas"):
        fit_distance_rate(integrate_eved(frame))


def test_csv_cache_reuses_integrals_and_invalidates_content_and_policy(tmp_path, monkeypatch):
    path, cache = tmp_path / "ev.csv", tmp_path / "summary.json"
    samples().to_csv(path, index=False)
    first = integrate_eved_csv(path, cache_path=cache)
    original = pd.read_csv
    calls = []

    def read(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(pd, "read_csv", read)
    assert integrate_eved_csv(path, cache_path=cache) == first
    assert calls == []
    changed = integrate_eved_csv(path, cache_path=cache, max_gap_seconds=1)
    assert calls == [1]
    assert changed.valid_interval_count == 1
    frame = samples()
    frame.loc[5, "HV Battery Current[A]"] = -30
    frame.to_csv(path, index=False)
    again = integrate_eved_csv(path, cache_path=cache)
    assert again.source_sha256 != first.source_sha256
    assert again.energy_kwh != first.energy_kwh
    model_path = tmp_path / "energy.json"
    save_energy_model(fit_distance_rate(again), model_path)
    assert json.loads(model_path.read_text())["model_type"] == "distance_only"
