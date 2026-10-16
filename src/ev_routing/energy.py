"""Calibración EV simple y reproducible; no pronostica señales de viajes futuros."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import Field

from ev_routing.contracts import Contract


class TripEnergy(Contract):
    vehicle_id: str
    trip_id: str
    valid_intervals: int
    duration_seconds: float
    energy_kwh: float
    distance_km: float


class EnergySummary(Contract):
    """Integrales sobre los mismos intervalos válidos para energía y distancia."""

    row_count: int
    trip_count: int
    valid_interval_count: int
    dropped_gap_count: int
    missing_interval_count: int
    integrated_seconds: float
    energy_kwh: float
    distance_km: float
    max_gap_seconds: float
    energy_source: str
    quadrature: str = "right_endpoint"
    gap_policy: str = "exclude_interval_without_interpolation"
    trips: list[TripEnergy]
    source_sha256: str | None = None
    source_path: str | None = None
    cache_version: str = "1.0"


class DistanceEnergyModel(Contract):
    """Referencia distancia-only: razón de integrales, no media de razones."""

    model_type: str = "distance_only"
    kwh_per_km: float = Field(gt=0)
    training_summary: EnergySummary
    limitations: list[str] = Field(
        default_factory=lambda: [
            "Calibración descriptiva; no es una evaluación fuera de muestra.",
            "No representa pendiente, aceleración, tráfico, clima ni auxiliares por tramo.",
            "No recupera energía en arcos OSM; los perfiles firmados se importan como instancia.",
            "La factibilidad depende de este estimador determinista, no es una garantía física.",
        ]
    )


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def integrate_eved(
    frame: pd.DataFrame,
    *,
    max_gap_seconds: float = 10.0,
    energy_source: Literal["current_voltage", "energy_column"] = "current_voltage",
) -> EnergySummary:
    """Integrar EV con Δt real, ordenando y separando (VehId, Trip).

    La cuadratura usa la lectura del extremo derecho, como el diccionario.
    Los primeros registros no aportan duración. Huecos grandes y lecturas
    ausentes excluyen el intervalo tanto de energía como de distancia; no se
    borran filas antes de calcular Δt ni se interpolan sus sensores.
    """
    if not np.isfinite(max_gap_seconds) or max_gap_seconds <= 0:
        raise ValueError("max_gap_seconds debe ser finito y positivo")
    if energy_source not in {"current_voltage", "energy_column"}:
        raise ValueError("energy_source debe ser current_voltage o energy_column")
    signals = (
        ["HV Battery Current[A]", "HV Battery Voltage[V]"]
        if energy_source == "current_voltage"
        else ["Energy_Consumption"]
    )
    columns = ["VehId", "Trip", "Timestamp", "Vehicle Speed[km/h]", *signals]
    missing = set(columns) - set(frame.columns)
    if missing:
        raise ValueError(f"Faltan columnas eVED: {sorted(missing)}")
    if frame.empty:
        raise ValueError("No hay registros eVED")
    data = frame[columns].copy()
    if data[["VehId", "Trip", "Timestamp"]].isna().any().any():
        raise ValueError("VehId, Trip y Timestamp no pueden faltar")
    for column in ["VehId", "Trip"]:
        data[column] = data[column].astype(str)
        if data[column].str.strip().eq("").any():
            raise ValueError(f"{column} no puede estar vacío")
    data["Timestamp"] = pd.to_datetime(data["Timestamp"], errors="raise", format="mixed")
    if data["Timestamp"].isna().any():
        raise ValueError("Timestamp no puede faltar")
    if data.duplicated(["VehId", "Trip", "Timestamp"]).any():
        raise ValueError("Timestamp duplicado dentro de un viaje")
    data = data.sort_values(["VehId", "Trip", "Timestamp"], kind="stable")
    for column in ["Vehicle Speed[km/h]", *signals]:
        data[column] = pd.to_numeric(data[column], errors="raise")
        if np.isinf(data[column]).any():
            raise ValueError(f"Valor infinito en {column}")
    if data["Vehicle Speed[km/h]"].lt(0).any():
        raise ValueError("La velocidad no puede ser negativa")
    if energy_source == "current_voltage":
        if data["HV Battery Voltage[V]"].le(0).any():
            raise ValueError("El voltaje debe ser positivo o ausente")
        unit_energy = -data[signals[0]] * data[signals[1]] / 3.6e6
    else:
        unit_energy = data["Energy_Consumption"]
    dt = data.groupby(["VehId", "Trip"], sort=False)["Timestamp"].diff().dt.total_seconds()
    eligible = dt.gt(0) & dt.le(max_gap_seconds)
    complete = unit_energy.notna() & data["Vehicle Speed[km/h]"].notna()
    valid = eligible & complete
    data["valid_intervals"] = valid.astype(int)
    data["duration_seconds"] = dt.where(valid, 0.0)
    data["energy_kwh"] = (unit_energy * dt).where(valid, 0.0)
    data["distance_km"] = (data["Vehicle Speed[km/h]"] * dt / 3600).where(valid, 0.0)
    metrics = ["valid_intervals", "duration_seconds", "energy_kwh", "distance_km"]
    grouped = data.groupby(["VehId", "Trip"], sort=False)[metrics].sum()
    trips = [
        TripEnergy(vehicle_id=vehicle, trip_id=trip, **values)
        for (vehicle, trip), values in grouped.to_dict("index").items()
    ]
    return EnergySummary(
        row_count=len(data),
        trip_count=len(trips),
        valid_interval_count=int(valid.sum()),
        dropped_gap_count=int(dt.gt(max_gap_seconds).sum()),
        missing_interval_count=int((eligible & ~complete).sum()),
        integrated_seconds=float(data.duration_seconds.sum()),
        energy_kwh=float(data.energy_kwh.sum()),
        distance_km=float(data.distance_km.sum()),
        max_gap_seconds=max_gap_seconds,
        energy_source=energy_source,
        trips=trips,
    )


def integrate_eved_csv(
    path: str | Path,
    *,
    max_gap_seconds: float = 10.0,
    energy_source: Literal["current_voltage", "energy_column"] = "current_voltage",
    cache_path: str | Path | None = None,
) -> EnergySummary:
    """Leer solo las señales necesarias; caché invalidada por contenido/política."""
    source = Path(path)
    digest = file_sha256(source)
    if cache_path and Path(cache_path).exists():
        cached = EnergySummary.model_validate_json(Path(cache_path).read_text(encoding="utf-8"))
        if (
            cached.source_sha256 == digest
            and cached.max_gap_seconds == max_gap_seconds
            and cached.energy_source == energy_source
            and cached.cache_version == "1.0"
        ):
            return cached.model_copy(update={"source_path": str(source.resolve())})
    columns = [
        "VehId", "Trip", "Timestamp", "Vehicle Speed[km/h]",
        *(
            ["HV Battery Current[A]", "HV Battery Voltage[V]"]
            if energy_source == "current_voltage"
            else ["Energy_Consumption"]
        ),
    ]
    frame = pd.read_csv(source, usecols=columns, dtype={"VehId": str, "Trip": str})
    summary = integrate_eved(
        frame, max_gap_seconds=max_gap_seconds, energy_source=energy_source
    ).model_copy(update={"source_sha256": digest, "source_path": str(source.resolve())})
    if cache_path:
        target = Path(cache_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(summary.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return summary


def fit_distance_rate(summary: EnergySummary) -> DistanceEnergyModel:
    """Ajustar kWh/km como energía neta total / distancia sobre intervalos válidos."""
    if summary.valid_interval_count == 0 or summary.distance_km <= 0 or summary.energy_kwh <= 0:
        raise ValueError("Se requieren intervalos válidos con distancia y energía neta positivas")
    return DistanceEnergyModel(
        kwh_per_km=summary.energy_kwh / summary.distance_km,
        training_summary=summary,
    )


def save_energy_model(model: DistanceEnergyModel, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(model.model_dump(mode="json"), ensure_ascii=False, indent=2, allow_nan=False)
        + "\n", encoding="utf-8"
    )
