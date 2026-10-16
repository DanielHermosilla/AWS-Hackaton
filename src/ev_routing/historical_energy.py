"""Historical EV energy: bounded import, directed matching and explicit fallback.

This module estimates constant street profiles, not future telemetry.  It never
changes fleet capacity, reserve, charging infrastructure or the solver objective.
"""

from __future__ import annotations

import csv
import hashlib
import json
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np
import pandas as pd
from pydantic import ConfigDict, Field
from pyproj import CRS, Transformer
from shapely.geometry import LineString, Point
from shapely.strtree import STRtree

from ev_routing.contracts import Arc, Contract, Node, ProblemInstance
from ev_routing.energy import file_sha256

MAX_HISTORY_BYTES = 4 * 1024 * 1024 * 1024
# JSON materializes records before normalization; large telemetry should use CSV.
MAX_HISTORY_JSON_BYTES = 256 * 1024 * 1024
MAX_HISTORY_ROWS = 20_000_000
MODEL_VERSION = "historical-streets-1.2"
_UNITS = {
    "timestamp": {"iso8601", "unix_s", "unix_ms", "elapsed_s"},
    "latitude": {"degrees"}, "longitude": {"degrees"},
    "speed_kph": {"km/h", "m/s", "mph"}, "current_a": {"A"}, "voltage_v": {"V"},
    "power_kw": {"kW", "W"},
    "energy_kwh": {"kWh_interval", "Wh_interval", "kWh_per_second", "Wh_per_second"},
    "soc_pct": {"percent", "fraction"}, "temperature_c": {"C", "F"},
    "auxiliary_power_w": {"W", "kW"}, "match_type": {"eved_code"},
}
_IDENTIFIERS = {"vehicle_id", "trip_id"}
_FIELDS = set(_UNITS) | _IDENTIFIERS
_EVED_REQUIRED = {
    "VehId", "Trip", "Timestamp", "Vehicle Speed[km/h]",
    "HV Battery Current[A]", "HV Battery Voltage[V]", "HV Battery SOC[%]",
    "Matched Latitude[deg]", "Matched Longitude[deg]", "Match Type",
}
_NON_EV_COLUMNS = {
    "Engine RPM[RPM]", "Engine Speed[RPM]", "MAF[g/sec]", "Fuel Rate[L/hr]",
    "Absolute Load[%]", "Short Term Fuel Trim Bank 1[%]",
}
_VEHICLE_CLASS_FIELDS = {
    "vehiclekind", "vehicletype", "powertrain", "fueltype", "tipovehiculo",
}
_EV_CLASSES = {"EV", "BEV", "ELECTRIC"}


class HistoryNeedsMapping(ValueError):
    """The format needs a documented column/unit/vehicle interpretation."""


class HistoryConfig(Contract):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True)
    max_gap_seconds: float = Field(default=10, gt=0)
    max_snap_distance_m: float = Field(default=25, gt=0, le=100)
    min_trip_count: int = Field(default=2, ge=1)
    min_support_distance_km: float = Field(default=0.02, gt=0)
    holdout_fraction: float = Field(default=0.2, ge=0, lt=0.5)
    max_match_blocks: int = Field(default=100_000, ge=1)
    max_path_distance_m: float = Field(default=1500, gt=0)
    max_candidate_edges: int = Field(default=3, ge=1, le=6)
    ambiguity_tolerance_m: float = Field(default=0.75, ge=0)


@dataclass(frozen=True)
class HistoryData:
    """Normalized samples remain server-side; summary contains no raw rows."""

    frame: pd.DataFrame
    summary: dict[str, Any]
    source_sha256: str
    mapping: dict[str, Any]


class ArcEstimate(Contract):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True)
    from_node_id: str
    to_node_id: str
    source_id: str | None
    energy_kwh_per_km: float
    discharge_kwh_per_km: float = Field(ge=0)
    recovery_kwh_per_km: float = Field(ge=0)
    travel_seconds_per_km: float = Field(ge=0)
    trip_count: int
    vehicle_count: int
    support_distance_km: float
    observations: int


class HistoryProfile(Contract):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True)
    schema_version: str = "1.0"
    model_id: str
    source_sha256: str
    network_sha256: str
    config: HistoryConfig
    summary: dict[str, Any]
    validation: dict[str, Any]
    assumptions: tuple[dict[str, Any], ...]
    warnings: tuple[str, ...]
    estimates: tuple[ArcEstimate, ...]


def _check_file(path: str | Path) -> Path:
    source = Path(path)
    if not source.is_file():
        raise ValueError("No se encontró el archivo histórico.")
    if source.stat().st_size > MAX_HISTORY_BYTES:
        raise ValueError("El histórico supera 4 GiB. Divídelo por viajes completos.")
    if source.stat().st_size == 0:
        raise ValueError("El archivo histórico está vacío.")
    return source


def _unique_json_object(pairs):
    content = {}
    for key, value in pairs:
        if key in content:
            raise ValueError(
                "El JSON histórico contiene claves repetidas; corrige el archivo "
                "para evitar interpretaciones contradictorias."
            )
        content[key] = value
    return content


def _read_history(
    path: str | Path, *, preview=False, identifier_columns=(), selected_columns=None,
) -> tuple[pd.DataFrame, dict, str]:
    source = _check_file(path)
    with source.open("r", encoding="utf-8-sig") as handle:
        prefix = handle.read(8192)
    if prefix.lstrip().startswith(("[", "{")):
        if source.stat().st_size > MAX_HISTORY_JSON_BYTES:
            raise ValueError("El JSON histórico supera 256 MiB. Expórtalo como CSV (hasta 4 GiB).")
        with source.open("r", encoding="utf-8-sig") as handle:
            content = json.load(handle, object_pairs_hook=_unique_json_object)
        metadata = content.get("metadata", {}) if isinstance(content, dict) else {}
        records = content.get("records") if isinstance(content, dict) else content
        if not isinstance(records, list) or not all(isinstance(r, dict) for r in records):
            raise ValueError("El JSON histórico necesita una lista de registros en records.")
        if len(records) > MAX_HISTORY_ROWS:
            raise ValueError("El histórico supera veinte millones de muestras.")
        frame = pd.DataFrame(records[:256] if preview else records)
        file_format = "json"
    else:
        try:
            separator = csv.Sniffer().sniff(prefix, delimiters=",;\t").delimiter
        except csv.Error:
            separator = ","
        header = next(csv.reader(prefix.splitlines(), delimiter=separator))
        if len(header) > 200 or any(len(column) > 200 for column in header):
            raise ValueError("El histórico admite hasta 200 columnas con nombres de hasta 200 caracteres.")
        if len(set(header)) != len(header):
            raise ValueError("El histórico contiene nombres de columnas repetidos.")
        frame = pd.read_csv(
            source, sep=separator, encoding="utf-8-sig",
            nrows=256 if preview else MAX_HISTORY_ROWS + 1,
            dtype={name: str for name in ("VehId", "Trip", *identifier_columns)},
            usecols=selected_columns,
        )
        metadata, file_format = {}, "csv"
        if len(frame) > MAX_HISTORY_ROWS:
            raise ValueError("El histórico supera veinte millones de muestras.")
    if frame.empty:
        raise ValueError("El histórico no contiene muestras.")
    if len(frame.columns) > 200:
        raise ValueError("El histórico tiene más de 200 columnas.")
    if any(not isinstance(c, str) or len(c) > 200 for c in frame.columns):
        raise ValueError("Los nombres de columnas deben ser textos de hasta 200 caracteres.")
    if len(set(frame.columns)) != len(frame.columns):
        raise ValueError("El histórico contiene nombres de columnas repetidos.")
    return frame, metadata if isinstance(metadata, dict) else {}, file_format


def _recognized_eved(columns) -> bool:
    return _EVED_REQUIRED <= set(columns) and not (_NON_EV_COLUMNS & set(columns))


def _classification_key(value: str) -> str:
    return "".join(
        character for character in unicodedata.normalize("NFKD", str(value)).casefold()
        if character.isalnum()
    )


def _validate_declared_vehicle_types(frame: pd.DataFrame, metadata: dict) -> None:
    """Check every declared class, including rows outside the AI preview."""
    for column in frame.columns:
        if _classification_key(column) not in _VEHICLE_CLASS_FIELDS:
            continue
        values = frame[column].astype("string").str.strip().str.upper()
        if not values.isin(_EV_CLASSES).all():
            raise ValueError(
                f"La columna «{column}» contiene tipos de vehículo ausentes o no exclusivamente "
                "eléctricos. Todas las filas deben indicar EV, BEV o ELECTRIC; "
                "no se mezclan ni se filtran silenciosamente vehículos híbridos o de combustión."
            )
    for key, value in metadata.items():
        if _classification_key(key) in _VEHICLE_CLASS_FIELDS:
            if not isinstance(value, str) or value.strip().upper() not in _EV_CLASSES:
                raise ValueError(
                    f"Los metadatos «{key}» no identifican vehículos exclusivamente eléctricos "
                    "(EV, BEV o ELECTRIC). Corrige la clasificación antes de calibrar."
                )


def _safe_value(value):
    if value is None or (not isinstance(value, (dict, list)) and pd.isna(value)):
        return None
    if isinstance(value, (bool, int, float)) and (
        not isinstance(value, float) or isfinite(value)
    ):
        return value
    return str(value)[:160]


def inspect_history(path: str | Path) -> dict:
    """Bounded evidence for a Bedrock schema interpretation; no full-file prompt."""
    source = _check_file(path)
    frame, metadata, file_format = _read_history(source, preview=True)
    statistics = {}
    for column in frame.columns:
        values = pd.to_numeric(frame[column], errors="coerce").replace(
            [np.inf, -np.inf], np.nan
        )
        stats = {
            "non_null_count": int(frame[column].notna().sum()),
            "missing_count": int(frame[column].isna().sum()),
        }
        if values.notna().any():
            stats.update(numeric_min=float(values.min()), numeric_max=float(values.max()))
        statistics[column] = stats
    return {
        "schema_version": "1.0", "source_sha256": file_sha256(source),
        "size_bytes": source.stat().st_size, "filename": source.name,
        "file_format": file_format, "columns": list(frame.columns),
        "sample_rows": [
            {key: _safe_value(value) for key, value in row.items()}
            for row in frame.head(8).to_dict("records")
        ],
        "sample_statistics": statistics, "sample_row_count": len(frame),
        "declared_metadata": {
            str(key)[:100]: _safe_value(value) for key, value in list(metadata.items())[:30]
        },
        "recognized_format": "eved_ev" if _recognized_eved(frame.columns) else None,
        "format": (
            "eved" if _recognized_eved(frame.columns)
            else "mapped" if isinstance(metadata.get("mapping"), dict) else "unknown"
        ),
        "sampling": "Primeras 256 muestras; las estadísticas no describen todo el archivo.",
    }


def _eved_mapping(columns) -> dict:
    names = {
        "vehicle_id": "VehId", "trip_id": "Trip", "timestamp": "Timestamp",
        "latitude": "Matched Latitude[deg]", "longitude": "Matched Longitude[deg]",
        "speed_kph": "Vehicle Speed[km/h]", "current_a": "HV Battery Current[A]",
        "voltage_v": "HV Battery Voltage[V]", "soc_pct": "HV Battery SOC[%]",
        "temperature_c": "OAT[DegC]", "match_type": "Match Type",
    }
    units = {
        "timestamp": "iso8601", "latitude": "degrees", "longitude": "degrees",
        "speed_kph": "km/h", "current_a": "A", "voltage_v": "V",
        "soc_pct": "percent", "temperature_c": "C", "match_type": "eved_code",
    }
    return {
        "columns": {key: value for key, value in names.items() if value in columns},
        "units": {key: value for key, value in units.items() if names[key] in columns},
        "vehicle_kind": "EV", "current_sign": "positive_charging",
        "energy_sign": "positive_consumption", "evidence": [],
    }


def _validate_mapping(mapping, columns):
    if not isinstance(mapping, dict) or not isinstance(mapping.get("columns"), dict):
        raise HistoryNeedsMapping("Falta identificar las columnas y sus unidades.")
    if mapping.get("vehicle_kind") != "EV":
        raise HistoryNeedsMapping(
            "Necesitamos confirmar que estas mediciones pertenecen a vehículos eléctricos, "
            "no a vehículos de combustión ni híbridos."
        )
    names, units = mapping["columns"], mapping.get("units", {})
    if not isinstance(units, dict) or set(names) - _FIELDS or set(units) - set(names):
        raise ValueError("El mapeo histórico contiene campos no admitidos.")
    if not {"vehicle_id", "trip_id", "timestamp"} <= set(names):
        raise HistoryNeedsMapping("Faltan vehículo, viaje o fecha para separar las mediciones.")
    if not ({"current_a", "voltage_v"} <= set(names) or {"power_kw", "energy_kwh"} & set(names)):
        raise HistoryNeedsMapping("Faltan corriente y voltaje, potencia o energía eléctrica.")
    if ("latitude" in names) != ("longitude" in names):
        raise HistoryNeedsMapping("Se necesitan latitud y longitud juntas.")
    if any(not isinstance(value, str) or value not in columns for value in names.values()):
        raise ValueError("El mapeo hace referencia a una columna que no existe.")
    if len(set(names.values())) != len(names):
        raise ValueError("Una columna no puede representar dos mediciones diferentes.")
    for field in set(names) - _IDENTIFIERS:
        if units.get(field) not in _UNITS[field]:
            raise HistoryNeedsMapping(f"Falta una unidad válida para {field}.")
    if {"current_a", "voltage_v"} <= set(names) and mapping.get("current_sign") not in {
        "positive_charging", "positive_consumption",
    }:
        raise HistoryNeedsMapping("Falta indicar el signo de la corriente.")
    if {"power_kw", "energy_kwh"} & set(names) and mapping.get("energy_sign") not in {
        "positive_charging", "positive_consumption",
    }:
        raise HistoryNeedsMapping("Falta indicar el signo de potencia o energía.")


def _haversine_vector(lat1, lon1, lat2, lon2):
    a, b, c, d = map(np.radians, (lat1, lon1, lat2, lon2))
    value = np.sin((c - a) / 2) ** 2 + np.cos(a) * np.cos(c) * np.sin((d - b) / 2) ** 2
    return 2 * 6_371_009 * np.arcsin(np.sqrt(np.clip(value, 0, 1)))


def normalize_history(
    path: str | Path, mapping: dict | None = None, *, max_gap_seconds: float = 10,
) -> HistoryData:
    """Normalize only declared units; retain missing readings and signed energy."""
    if not isfinite(max_gap_seconds) or max_gap_seconds <= 0:
        raise ValueError("max_gap_seconds debe ser finito y positivo.")
    # Inspect schema before reading the full CSV: reject ICE/HEV immediately and
    # retain only the signals needed for normalization and descriptive statistics.
    preview, metadata, _ = _read_history(path, preview=True)
    recognized = _recognized_eved(preview.columns)
    if _NON_EV_COLUMNS & set(preview.columns):
        raise ValueError("Este histórico incluye señales de combustión o híbridos; usa datos EV.")
    if mapping is None:
        mapping = _eved_mapping(preview.columns) if recognized else metadata.get("mapping")
    _validate_mapping(mapping, preview.columns)
    columns = mapping["columns"]
    identifier_columns = [
        columns[key] for key in _IDENTIFIERS if key in columns
    ] if isinstance(columns, dict) else []
    selected = set(columns.values()) | {
        column for column in preview.columns
        if _classification_key(column) in _VEHICLE_CLASS_FIELDS
    }
    if recognized:
        selected |= set(preview.columns) & {
            "Air Conditioning Power[Watts]", "Heater Power[Watts]",
            "Gradient", "Elevation Smoothed[m]",
        }
    raw, metadata, file_format = _read_history(
        path, identifier_columns=identifier_columns, selected_columns=list(selected),
    )
    _validate_declared_vehicle_types(raw, metadata)
    _validate_mapping(mapping, raw.columns)
    names, units = mapping["columns"], mapping["units"]
    frame = raw[list(names.values())].rename(columns={v: k for k, v in names.items()}).copy()
    for field in _IDENTIFIERS:
        if frame[field].isna().any() or frame[field].astype(str).str.strip().eq("").any():
            raise ValueError("Cada muestra necesita un vehículo y un viaje.")
        frame[field] = frame[field].astype(str)
    if units["timestamp"] == "iso8601":
        times = pd.to_datetime(frame.timestamp, errors="raise", format="mixed", utc=True)
        frame["timestamp_seconds"] = times.astype("int64") / 1e9
    else:
        frame["timestamp_seconds"] = pd.to_numeric(frame.timestamp, errors="raise")
        if units["timestamp"] == "unix_ms":
            frame["timestamp_seconds"] /= 1000
    if frame.timestamp.isna().any() or not np.isfinite(frame.timestamp_seconds).all():
        raise ValueError("Las fechas no pueden estar vacías o ser infinitas.")
    frame = frame.sort_values(
        ["vehicle_id", "trip_id", "timestamp_seconds"], kind="stable"
    ).reset_index(drop=True)
    if frame.duplicated(["vehicle_id", "trip_id", "timestamp_seconds"]).any():
        raise ValueError("Hay fechas duplicadas dentro de un viaje.")
    for field in set(names) - _IDENTIFIERS - {"timestamp"}:
        frame[field] = pd.to_numeric(frame[field], errors="raise")
        if np.isinf(frame[field]).any():
            raise ValueError(f"Hay valores infinitos en {field}.")
    for field, factor in (
        ("speed_kph", {"km/h": 1, "m/s": 3.6, "mph": 1.609344}),
        ("power_kw", {"kW": 1, "W": .001}),
        ("auxiliary_power_w", {"W": 1, "kW": 1000}),
        ("soc_pct", {"percent": 1, "fraction": 100}),
    ):
        if field in frame:
            frame[field] *= factor[units[field]]
    if "temperature_c" in frame and units["temperature_c"] == "F":
        frame["temperature_c"] = (frame.temperature_c - 32) * 5 / 9
    if "latitude" in frame and (
        frame.latitude.abs().gt(90).any() or frame.longitude.abs().gt(180).any()
    ):
        raise ValueError("El histórico contiene coordenadas fuera del rango geográfico.")
    if "speed_kph" in frame and frame.speed_kph.lt(0).any():
        raise ValueError("La velocidad no puede ser negativa.")
    if "voltage_v" in frame and frame.voltage_v.le(0).any():
        raise ValueError("El voltaje debe ser positivo o estar ausente.")
    group = frame.groupby(["vehicle_id", "trip_id"], sort=False)
    dt = group.timestamp_seconds.diff()
    eligible = dt.gt(0) & dt.le(max_gap_seconds)
    if {"current_a", "voltage_v"} <= set(frame):
        sign = -1 if mapping["current_sign"] == "positive_charging" else 1
        energy = sign * frame.current_a * frame.voltage_v * dt / 3.6e6
        energy_source = "current_voltage"
    elif "power_kw" in frame:
        sign = -1 if mapping["energy_sign"] == "positive_charging" else 1
        energy = sign * frame.power_kw * dt / 3600
        energy_source = "power"
    else:
        sign = -1 if mapping["energy_sign"] == "positive_charging" else 1
        energy = frame.energy_kwh * sign
        if units["energy_kwh"].startswith("Wh"):
            energy = energy / 1000
        if units["energy_kwh"].endswith("per_second"):
            energy = energy * dt
        energy_source = units["energy_kwh"]
    complete = energy.notna()
    if "speed_kph" in frame:
        distance = frame.speed_kph * dt / 3.6
        complete &= frame.speed_kph.notna()
        distance_source = "measured_speed_integral"
    elif "latitude" in frame:
        previous = group[["latitude", "longitude"]].shift()
        distance = _haversine_vector(
            previous.latitude, previous.longitude, frame.latitude, frame.longitude,
        )
        complete &= pd.Series(distance).notna()
        distance_source = "gps_chords_estimate"
    else:
        distance = pd.Series(np.nan, index=frame.index)
        distance_source = "unavailable"
    valid = eligible & complete
    if not valid.any():
        raise ValueError(
            "El histórico no tiene intervalos válidos para estimar energía. "
            "Revisa fechas, duración de los viajes y señales eléctricas."
        )
    frame["dt_seconds"] = dt
    frame["valid_interval"] = valid
    frame["energy_kwh"] = energy.where(valid, np.nan)
    frame["distance_m"] = pd.Series(distance).where(valid, np.nan)
    if "speed_kph" in frame:
        stationary_or_unknown_movement = frame.speed_kph.eq(0)
    elif "latitude" in frame:
        # A repeated GPS reading does not prove a stop, but without speed it
        # cannot establish braking regeneration instead of external charging.
        previous = group[["latitude", "longitude"]].shift()
        stationary_or_unknown_movement = (
            frame.latitude.eq(previous.latitude)
            & frame.longitude.eq(previous.longitude)
        )
    else:
        stationary_or_unknown_movement = pd.Series(True, index=frame.index)
    frame["ambiguous_stationary_recovery"] = (
        valid & energy.lt(0) & stationary_or_unknown_movement
    )
    ambiguous_recovery = float(
        -energy[frame.ambiguous_stationary_recovery].sum()
    )
    assumptions = [
        {
            "key": "energy_integration", "label": "Cómo se calcula el consumo",
            "value": "Energía eléctrica integrada con el tiempo real", "kind": "method",
            "evidence": "Intervalos reales dentro de cada vehículo y viaje.",
            "applied": True,
        },
        {
            "key": "missing_intervals", "label": "Datos incompletos",
            "value": "Se excluyen intervalos sin mediciones suficientes",
            "kind": "method", "applied": True,
            "evidence": f"Huecos mayores de {max_gap_seconds:g} s y señales ausentes.",
        },
        {
            "key": "historical_vehicle_kind", "label": "Tipo de vehículo",
            "value": "Eléctrico", "kind": "declared",
            "evidence": "Esquema eVED EV sin señales de combustión." if recognized else "Mapeo del archivo.",
            "applied": True,
        },
    ]
    for column, unit in (
        ("speed_kph", "km/h"), ("temperature_c", "°C"),
        ("soc_pct", "%"), ("auxiliary_power_w", "W"),
    ):
        if column in frame and frame[column].notna().any():
            values = frame[column].dropna()
            assumptions.append({
                "key": f"historical_{column}", "label": {
                    "speed_kph": "Velocidad observada", "temperature_c": "Temperatura histórica",
                    "soc_pct": "Nivel de batería registrado",
                    "auxiliary_power_w": "Potencia auxiliar observada",
                }[column],
                "value": float(values.median()), "statistics": {
                    "median": float(values.median()), "p10": float(values.quantile(.1)),
                    "p90": float(values.quantile(.9)), "available_rows": len(values),
                }, "unit": unit, "kind": "observed_distribution", "applied": False,
                "evidence": f"Mediana de {names[column]}; describe el pasado, no condiciones futuras.",
            })
    if recognized:
        for column, label, unit in (
            ("Air Conditioning Power[Watts]", "Aire acondicionado observado", "W"),
            ("Heater Power[Watts]", "Calefacción observada", "W"),
            ("Gradient", "Pendiente registrada", "m/m"),
            ("Elevation Smoothed[m]", "Elevación registrada", "m"),
        ):
            if column in raw:
                values = pd.to_numeric(raw[column], errors="coerce").replace(
                    [np.inf, -np.inf], np.nan
                ).dropna()
                if len(values):
                    assumptions.append({
                        "key": f"eved_{column}", "label": label,
                        "value": float(values.median()), "unit": unit,
                        "kind": "observed_distribution", "applied": False,
                        "statistics": {
                            "p10": float(values.quantile(.1)), "p90": float(values.quantile(.9)),
                            "available_rows": len(values),
                        },
                        "evidence": (
                            f"Mediana de {column}. La energía de auxiliares ya está incluida "
                            "en la batería; no se suma otra vez."
                        ) if "Power" in column else f"Mediana de {column}; contexto histórico.",
                    })
    recovery = float(-energy[valid].clip(upper=0).sum())
    stationary = (
        float(energy[valid & frame.speed_kph.eq(0)].sum())
        if "speed_kph" in frame else None
    )
    assumptions.extend((
        {
            "key": "observed_regeneration", "label": "Regeneración observada",
            "value": recovery, "unit": "kWh", "kind": "observed", "applied": False,
            "evidence": "Energía recuperada en intervalos válidos; se conserva su signo.",
        },
        {
            "key": "stationary_energy", "label": "Consumo con vehículo detenido",
            "value": stationary, "unit": "kWh", "kind": "observed", "applied": False,
            "evidence": (
                "Velocidad medida igual a cero; no identifica entregas ni tiempos de servicio."
                if stationary is not None else "Falta velocidad medida para identificar detenciones."
            ),
        },
        {
            "key": "ambiguous_stationary_recovery",
            "label": "Recuperación sin movimiento confirmado",
            "value": ambiguous_recovery, "unit": "kWh", "kind": "observed",
            "applied": False,
            "evidence": (
                "Se conserva en el historial, pero los bloques afectados no calibran calles: "
                "podría ser recarga externa o una lectura que no acredita regeneración al circular."
            ),
        },
    ))
    summary = {
        "schema_version": "1.0", "source_sha256": file_sha256(path),
        "file_format": file_format, "recognized_format": "eved_ev" if recognized else "mapped",
        "row_count": len(frame), "vehicle_count": frame.vehicle_id.nunique(),
        "trip_count": group.ngroups, "valid_interval_count": int(valid.sum()),
        "dropped_gap_count": int(dt.gt(max_gap_seconds).sum()),
        "missing_interval_count": int((eligible & ~complete).sum()),
        "energy_kwh": float(energy[valid].sum()),
        "energy_source": energy_source,
        "discharge_kwh": float(energy[valid].clip(lower=0).sum()),
        "recovery_kwh": recovery,
        "distance_km": float(pd.Series(distance)[valid].sum() / 1000)
        if distance_source != "unavailable" else None,
        "distance_source": distance_source, "max_gap_seconds": max_gap_seconds,
        "stationary_energy_kwh": stationary,
        "ambiguous_stationary_recovery_kwh": ambiguous_recovery,
        "ambiguous_stationary_recovery_interval_count": int(
            frame.ambiguous_stationary_recovery.sum()
        ),
        "assumptions": assumptions,
    }
    return HistoryData(
        frame, summary, summary["source_sha256"],
        json.loads(json.dumps(mapping, ensure_ascii=False, allow_nan=False)),
    )


def _is_access(arc: Arc) -> bool:
    return (arc.source_id or "").startswith("assumed_access:")


def _street_node_ids(road: ProblemInstance) -> set[str]:
    return {
        key for arc in road.arcs if not _is_access(arc)
        for key in (arc.from_node_id, arc.to_node_id)
    }


def historical_network_fingerprint(road: ProblemInstance) -> str:
    """The exact street network used for GPS matching, including cycle-check costs.

    Service locations and their assumed access connectors are excluded: GPS is
    matched only to streets, so changing services reuses the same calibration.
    """
    streets = _street_node_ids(road)
    digest = hashlib.sha256()
    for node in road.nodes:
        if node.node_id not in streets:
            continue
        digest.update(json.dumps(
            [node.node_id, node.node_type, node.latitude, node.longitude],
            separators=(",", ":"), allow_nan=False,
        ).encode())
    for arc in road.arcs:
        if _is_access(arc):
            continue
        digest.update(json.dumps(
            [
                arc.from_node_id, arc.to_node_id, arc.source_id,
                arc.distance_m, arc.energy_kwh, arc.geometry,
            ],
            separators=(",", ":"), allow_nan=False,
        ).encode())
    return digest.hexdigest()


class _StreetIndex:
    def __init__(self, road, config):
        self.config = config
        positions = {
            n.node_id: (n.longitude, n.latitude)
            for n in road.nodes if n.latitude is not None
        }
        # Services do not move the projection, so the matching depends only on streets.
        streets = _street_node_ids(road)
        anchors = [positions[n.node_id] for n in road.nodes if n.node_id in streets and n.node_id in positions]
        center = np.mean(anchors or list(positions.values()), axis=0)
        projection = CRS.from_proj4(
            f"+proj=aeqd +lat_0={center[1]} +lon_0={center[0]} +datum=WGS84 +units=m"
        )
        self.transform = Transformer.from_crs(4326, projection, always_xy=True).transform
        self.arcs, self.lines, self.graph = [], [], nx.DiGraph()
        self.by_pair = {}
        for arc in road.arcs:
            if _is_access(arc) or arc.distance_m <= 0:
                continue
            if arc.geometry:
                coordinates = [(lon, lat) for lat, lon in arc.geometry]
            elif arc.from_node_id in positions and arc.to_node_id in positions:
                coordinates = [positions[arc.from_node_id], positions[arc.to_node_id]]
            else:
                continue
            xy = [self.transform(*position) for position in coordinates]
            if not np.isfinite(xy).all():
                continue
            line = LineString(xy)
            if line.length < 0.01:
                continue
            index = len(self.arcs)
            self.arcs.append(arc)
            self.lines.append(line)
            self.by_pair[arc.from_node_id, arc.to_node_id] = index
            self.graph.add_edge(
                arc.from_node_id, arc.to_node_id, weight=arc.distance_m, index=index,
            )
        self.tree = STRtree(self.lines)

    def candidates(self, point, direction):
        result = []
        for index in self.tree.query(point.buffer(self.config.max_snap_distance_m)):
            line = self.lines[index]
            distance = line.distance(point)
            if distance > self.config.max_snap_distance_m:
                continue
            delta = np.asarray(line.coords[-1]) - line.coords[0]
            length = np.linalg.norm(delta)
            if length == 0:
                continue
            agreement = float(np.dot(delta / length, direction))
            if agreement < .25:
                continue
            fraction = line.project(point) / line.length
            result.append((distance + 4 * (1 - agreement), int(index), fraction))
        return sorted(result)[:self.config.max_candidate_edges]

    def match(self, first, last, expected_distance):
        start, end = Point(self.transform(first[1], first[0])), Point(self.transform(last[1], last[0]))
        chord = start.distance(end)
        if chord < 2:
            return None, "insufficient_displacement"
        direction = (np.asarray(end.coords[0]) - start.coords[0]) / chord
        starts, ends = self.candidates(start, direction), self.candidates(end, direction)
        if not starts or not ends:
            return None, "outside_coverage_or_direction"
        expected = expected_distance if expected_distance > 0 else chord
        maximum = min(
            self.config.max_path_distance_m, max(60, 1.8 * expected + 25, 1.5 * chord),
        )
        candidates, shortest = {}, {}
        for start_cost, a, position_a in starts:
            arc_a = self.arcs[a]
            for end_cost, b, position_b in ends:
                arc_b = self.arcs[b]
                if a == b and position_b > position_a:
                    parts = [(a, arc_a.distance_m * (position_b - position_a))]
                else:
                    origin, target = arc_a.to_node_id, arc_b.from_node_id
                    if origin not in shortest:
                        shortest[origin] = nx.single_source_dijkstra(
                            self.graph, origin, cutoff=maximum, weight="weight",
                        )
                    distances, paths = shortest[origin]
                    if target not in distances:
                        continue
                    parts = [(a, arc_a.distance_m * (1 - position_a))]
                    path = paths[target]
                    parts.extend(
                        (self.by_pair[u, v], self.arcs[self.by_pair[u, v]].distance_m)
                        for u, v in zip(path, path[1:])
                    )
                    parts.append((b, arc_b.distance_m * position_b))
                parts = [(index, distance) for index, distance in parts if distance > .05]
                distance = sum(length for _, length in parts)
                if distance < 2 or distance > maximum:
                    continue
                # No teleportation or long detour hidden inside a GPS interval.
                if distance > expected * 2.5 + 20 or expected > distance * 2.5 + 20:
                    continue
                signature = tuple(index for index, _ in parts)
                score = start_cost + end_cost + .15 * abs(distance - expected)
                existing = candidates.get(signature)
                if existing is None or score < existing[0]:
                    candidates[signature] = score, parts
        ranked = sorted(candidates.values(), key=lambda item: item[0])
        if not ranked:
            return None, "discontinuous_or_implausible_path"
        if len(ranked) > 1 and ranked[1][0] - ranked[0][0] <= self.config.ambiguity_tolerance_m:
            return None, "ambiguous_parallel_paths"
        return ranked[0][1], None


def _blocks(frame):
    """Integrate all repeated GPS readings between distinct, valid GPS anchors."""
    for (vehicle, trip), group in frame.groupby(["vehicle_id", "trip_id"], sort=False):
        group = group.reset_index(drop=True)
        lat, lon = group.latitude.to_numpy(), group.longitude.to_numpy()
        position_valid = np.isfinite(lat) & np.isfinite(lon)
        if "match_type" in group:
            position_valid &= group.match_type.ne(2).to_numpy()
        anchor = None
        for index in range(len(group)):
            if not position_valid[index]:
                anchor = None
                continue
            if anchor is None:
                anchor = index
                continue
            if lat[index] == lat[anchor] and lon[index] == lon[anchor]:
                continue
            interval = group.iloc[anchor + 1:index + 1]
            if interval.valid_interval.all():
                if interval.ambiguous_stationary_recovery.any():
                    yield {"rejection_reason": "ambiguous_stationary_charging"}
                    anchor = index
                    continue
                energy = interval.energy_kwh
                yield {
                    "vehicle": vehicle, "trip": trip,
                    "trip_key": f"{len(vehicle)}:{vehicle}{trip}",
                    "start_time": float(group.timestamp_seconds.iloc[0]),
                    "first": (lat[anchor], lon[anchor]), "last": (lat[index], lon[index]),
                    "energy": float(energy.sum()),
                    "discharge": float(energy.clip(lower=0).sum()),
                    "recovery": float(-energy.clip(upper=0).sum()),
                    "distance": float(interval.distance_m.sum()),
                    "seconds": float(interval.dt_seconds.sum()),
                }
            anchor = index


def _estimate(records, allowed_trips, config, arcs):
    grouped = defaultdict(list)
    for observation in records:
        if observation["trip_key"] in allowed_trips:
            grouped[observation["arc"]].append(observation)
    estimates = {}
    for index, values in grouped.items():
        distance = sum(item["distance"] for item in values) / 1000
        trips = {item["trip_key"] for item in values}
        if len(trips) < config.min_trip_count or distance < config.min_support_distance_km:
            continue
        arc = arcs[index]
        estimates[index] = ArcEstimate(
            from_node_id=arc.from_node_id, to_node_id=arc.to_node_id, source_id=arc.source_id,
            energy_kwh_per_km=sum(item["energy"] for item in values) / distance,
            discharge_kwh_per_km=sum(item["discharge"] for item in values) / distance,
            recovery_kwh_per_km=sum(item["recovery"] for item in values) / distance,
            travel_seconds_per_km=sum(item["seconds"] for item in values) / distance,
            trip_count=len(trips), vehicle_count=len({item["vehicle"] for item in values}),
            support_distance_km=distance, observations=len(values),
        )
    return estimates


def _negative_cycle_estimates(index, estimates):
    """Reject statistically inconsistent negative cycles, without clipping regen."""
    graph = index.graph.copy()
    for u, v, data in graph.edges(data=True):
        item = estimates.get(data["index"])
        arc = index.arcs[data["index"]]
        data["energy"] = (
            item.energy_kwh_per_km * arc.distance_m / 1000 if item else arc.energy_kwh
        )
    # All potentially useful negative cycles must contain a negative calibrated arc.
    negatives = {
        (item.from_node_id, item.to_node_id)
        for item in estimates.values() if item.energy_kwh_per_km < 0
    }
    rejected = set()
    if not negatives:
        return estimates, rejected
    for members in nx.strongly_connected_components(graph):
        if not any(u in members and v in members for u, v in negatives):
            continue
        component = graph.subgraph(members)
        # Bellman-Ford can be quadratic on a city graph. Large SCCs fail closed:
        # keep observations in the report, but do not apply uncertified negative arcs.
        if len(members) > 5000 or component.number_of_edges() > 15000:
            rejected.update(
                data["index"] for u, v, data in component.edges(data=True)
                if (u, v) in negatives
            )
        elif nx.negative_edge_cycle(component.copy(), weight="energy"):
            rejected.update(
                data["index"] for _, _, data in component.edges(data=True)
                if data["index"] in estimates
            )
    return {key: value for key, value in estimates.items() if key not in rejected}, rejected


def fit_historical_energy(
    data: HistoryData, road: ProblemInstance, *, config: HistoryConfig | None = None,
) -> HistoryProfile:
    """Estimate supported directed street costs; unrelated locations stay unknown."""
    config = config or HistoryConfig(max_gap_seconds=data.summary["max_gap_seconds"])
    if config.max_gap_seconds != data.summary["max_gap_seconds"]:
        raise ValueError("La política de huecos debe coincidir con la normalización.")
    network_hash = historical_network_fingerprint(road)
    model_id = hashlib.sha256(json.dumps({
        "version": MODEL_VERSION, "source": data.source_sha256, "network": network_hash,
        "mapping": data.mapping, "config": config.model_dump(),
    }, sort_keys=True, allow_nan=False).encode()).hexdigest()
    warnings = [
        "Los consumos son estimaciones históricas; no garantizan el consumo de una ruta futura.",
        "GPS y sentidos se asocian de forma conservadora; una calle cercana no acredita un recorrido.",
        "No se modifican capacidad, reserva, recargas ni condiciones de entrega.",
    ]
    records, reasons, matched, total = [], Counter(), 0, 0
    index = None
    if not {"latitude", "longitude"} <= set(data.frame):
        reasons["missing_coordinates"] += 1
    elif road.provenance.get("network", {}).get("kind") == "haversine":
        reasons["synthetic_network_has_no_streets"] += 1
    elif not any(node.latitude is not None for node in road.nodes):
        reasons["road_without_coordinates"] += 1
    else:
        index = _StreetIndex(road, config)
        if not index.arcs:
            reasons["road_without_geometries"] += 1
        else:
            for block in _blocks(data.frame):
                total += 1
                if total > config.max_match_blocks:
                    reasons["processing_limit"] += 1
                    continue
                if block.get("rejection_reason"):
                    reasons[block["rejection_reason"]] += 1
                    continue
                parts, error = index.match(block["first"], block["last"], block["distance"])
                if error:
                    reasons[error] += 1
                    continue
                matched += 1
                distance = sum(length for _, length in parts)
                for arc_index, length in parts:
                    ratio = length / distance
                    records.append({
                        **{key: block[key] for key in ("vehicle", "trip_key", "start_time")},
                        "arc": arc_index, "distance": length,
                        **{key: block[key] * ratio for key in ("energy", "discharge", "recovery", "seconds")},
                    })
    trips = {}
    for item in records:
        trips[item["trip_key"]] = item["start_time"]
    ordered = sorted(trips, key=lambda key: (trips[key], key))
    n_holdout = max(1, int(len(ordered) * config.holdout_fraction)) if (
        len(ordered) >= 5 and config.holdout_fraction > 0
    ) else 0
    training = set(ordered[:-n_holdout] if n_holdout else ordered)
    holdout = set(ordered[-n_holdout:] if n_holdout else [])
    estimates = _estimate(records, training, config, index.arcs) if index else {}
    estimates, rejected = _negative_cycle_estimates(index, estimates) if index else ({}, set())
    if rejected:
        reasons["negative_cycle_or_unverified_component"] += len(rejected)
        warnings.append(
            "Algunas estimaciones firmadas no superaron la comprobación de ciclos; "
            "esas calles conservan el consumo supuesto, sin borrar su regeneración observada."
        )
    errors, observed_total = defaultdict(float), defaultdict(float)
    for item in records:
        if item["trip_key"] in holdout and item["arc"] in estimates:
            prediction = estimates[item["arc"]].energy_kwh_per_km * item["distance"] / 1000
            errors[item["trip_key"]] += prediction - item["energy"]
            observed_total[item["trip_key"]] += item["energy"]
    validation = {
        "method": "chronological_complete_trip_holdout",
        "training_trip_count": len(training), "holdout_trip_count": len(holdout),
        "covered_holdout_trip_count": len(errors),
        "covered_holdout_energy_kwh": sum(observed_total.values()) if errors else None,
        "prediction_mae_kwh": float(np.mean(np.abs(list(errors.values())))) if errors else None,
        "bias_kwh": float(np.mean(list(errors.values()))) if errors else None,
        "status": "measured_on_covered_portions" if errors else "insufficient_held_out_coverage",
        "scope": "Solo porciones localizadas y con soporte; no es error de la ruta completa.",
        "production_fit": "training_trips_only",
    }
    road_arcs = index.arcs if index else []
    calibrated_distance = sum(road_arcs[key].distance_m for key in estimates) / 1000
    road_distance = sum(arc.distance_m for arc in road_arcs) / 1000
    summary = {
        **{key: value for key, value in data.summary.items() if key != "assumptions"},
        "matched_block_count": matched, "rejected_block_count": total - matched,
        "calibrated_arc_count": len(estimates), "road_arc_count": len(road_arcs),
        "arc_coverage_fraction": len(estimates) / len(road_arcs) if road_arcs else 0,
        "calibrated_distance_km": calibrated_distance, "road_distance_km": road_distance,
        "distance_coverage_fraction": calibrated_distance / road_distance if road_distance else 0,
        "negative_arc_count": sum(e.energy_kwh_per_km < 0 for e in estimates.values()),
        "mixed_sign_arc_count": sum(
            e.discharge_kwh_per_km > 0 and e.recovery_kwh_per_km > 0 for e in estimates.values()
        ),
        "matched_energy_kwh": sum(record["energy"] for record in records),
        "matched_discharge_kwh": sum(record["discharge"] for record in records),
        "matched_recovery_kwh": sum(record["recovery"] for record in records),
        "unmatched_reasons": dict(reasons),
    }
    if not estimates:
        warnings.append("No hay tramos con evidencia suficiente; se usará el consumo supuesto.")
    if reasons["ambiguous_stationary_charging"]:
        warnings.append(
            "Se excluyeron bloques con recuperación de energía sin movimiento confirmado. "
            "No se usa una posible recarga estacionaria como ahorro al recorrer una calle."
        )
    assumptions = tuple(data.summary["assumptions"]) + ({
        "key": "mixed_sign_order", "label": "Descarga y recuperación",
        "value": "Se supone descarga antes de recuperación",
        "kind": "model_assumption", "applied": True,
        "evidence": (
            "Se conservan descarga y recuperación por separado. Su orden interno se supone; "
            "no reconstruye el orden real ni garantiza una envolvente conservadora con saturación."
        ),
    }, {
        "key": "allocation_between_gps_anchors", "label": "Entre posiciones GPS",
        "value": "Energía repartida según la longitud del recorrido",
        "kind": "model_assumption", "applied": True,
        "evidence": "La batería se muestrea más frecuentemente que el GPS.",
    })
    return HistoryProfile(
        model_id=model_id, source_sha256=data.source_sha256, network_sha256=network_hash,
        config=config, summary=summary, validation=validation, assumptions=assumptions,
        warnings=tuple(warnings), estimates=tuple(estimates.values()),
    )


def _split_line(points):
    line = LineString([(lon, lat) for lat, lon in points])
    middle = line.interpolate(.5, normalized=True)
    distance = line.length / 2
    walked = 0.
    for index, (a, b) in enumerate(zip(line.coords, list(line.coords)[1:])):
        length = Point(a).distance(Point(b))
        if walked + length >= distance:
            midpoint = (middle.y, middle.x)
            return [*points[:index + 1], midpoint], [midpoint, *points[index + 1:]]
        walked += length
    raise ValueError("No se pudo dividir la geometría de una calle histórica.")


def apply_historical_energy(
    road: ProblemInstance, profile: HistoryProfile, fallback_rate: float,
) -> ProblemInstance:
    """Apply before road preprocessing; preserve signed, auditable elementary arcs."""
    if not isfinite(fallback_rate) or fallback_rate <= 0:
        raise ValueError("El consumo supuesto debe ser finito y positivo.")
    if historical_network_fingerprint(road) != profile.network_sha256:
        raise ValueError("El histórico fue calibrado con otra red; vuelve a preparar la entrada.")
    if road.provenance.get("representation", {}).get("kind") in {
        "resource_paths", "service_paths_nonnegative",
    }:
        raise ValueError("Aplica el histórico sobre calles originales antes de preparar caminos.")
    lookup = {(item.from_node_id, item.to_node_id): item for item in profile.estimates}
    nodes, arcs = list(road.nodes), []
    positions = {node.node_id: node for node in nodes}
    subdivisions = []
    for arc in road.arcs:
        item = lookup.get((arc.from_node_id, arc.to_node_id))
        if item is None:
            arcs.append(arc.model_copy(update={
                "energy_kwh": arc.distance_m * fallback_rate / 1000,
            }))
            continue
        distance = arc.distance_m / 1000
        discharge, recovery = item.discharge_kwh_per_km * distance, item.recovery_kwh_per_km * distance
        seconds = item.travel_seconds_per_km * distance
        if discharge > 1e-12 and recovery > 1e-12:
            points = arc.geometry or [
                (positions[key].latitude, positions[key].longitude)
                for key in (arc.from_node_id, arc.to_node_id)
            ]
            first, second = _split_line(points)
            identifier = "history:" + hashlib.sha256(
                f"{profile.model_id}:{arc.from_node_id}:{arc.to_node_id}".encode()
            ).hexdigest()[:24]
            while identifier in positions:
                identifier += "#"
            middle = Node(
                node_id=identifier, node_type="junction",
                latitude=first[-1][0], longitude=first[-1][1],
            )
            nodes.append(middle)
            positions[identifier] = middle
            arcs.extend((
                Arc(
                    from_node_id=arc.from_node_id, to_node_id=identifier,
                    energy_kwh=discharge, distance_m=arc.distance_m / 2,
                    travel_time_seconds=seconds / 2, geometry=first, source_id=arc.source_id,
                ),
                Arc(
                    from_node_id=identifier, to_node_id=arc.to_node_id,
                    energy_kwh=-recovery, distance_m=arc.distance_m / 2,
                    travel_time_seconds=seconds / 2, geometry=second, source_id=arc.source_id,
                ),
            ))
            subdivisions.append({
                "from_node_id": arc.from_node_id, "to_node_id": arc.to_node_id,
                "junction_node_id": identifier, "source_id": arc.source_id,
            })
        else:
            arcs.append(arc.model_copy(update={
                "energy_kwh": discharge - recovery, "travel_time_seconds": seconds,
            }))
    energy = {
        "kind": "historical_directed_streets", "model_id": profile.model_id,
        "source_sha256": profile.source_sha256, "network_sha256": profile.network_sha256,
        "fallback_kwh_per_km": fallback_rate, "summary": profile.summary,
        "validation": profile.validation, "assumptions": list(profile.assumptions),
        "limitations": list(profile.warnings), "mixed_sign_subdivisions": subdivisions,
    }
    provenance = {
        **road.provenance, "energy_model": energy,
        "assumptions": [
            *[
                note for note in road.provenance.get("assumptions", [])
                if "distancia-only" not in str(note)
            ],
            "Consumo histórico estimado en calles con evidencia; consumo supuesto donde falta.",
            "El orden interno de descarga y recuperación es un supuesto declarado del modelo.",
        ],
        "energy": {
            "model_type": "historical_directed_streets", "model_id": profile.model_id,
            "fallback_kwh_per_km": fallback_rate,
            "regeneration_on_osm_arcs": any(arc.energy_kwh < 0 for arc in arcs),
        },
    }
    return ProblemInstance.model_validate({
        **road.model_dump(), "nodes": nodes, "arcs": arcs, "provenance": provenance,
    })
