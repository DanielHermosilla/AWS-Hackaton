import math
from typing import Iterable, Optional

import numpy as np
import pandas as pd


def integrate_energy_samples(
    df: pd.DataFrame,
    *,
    group_cols: Iterable[str] = ("VehId", "Trip"),
    time_col: str = "Timestamp",
    energy_col: str = "Energy_Consumption",
) -> pd.Series:
    """Integrate Energy_Consumption using real timestamps (Energy_Consumption * delta_t).

    Returns one value per (group) via summing the integrated per-row energy.
    """
    work = df.copy()
    if time_col in work.columns and not pd.api.types.is_datetime64_any_dtype(work[time_col]):
        work[time_col] = pd.to_datetime(work[time_col], errors="coerce")
    delta = work.groupby(list(group_cols))[time_col].diff().dt.total_seconds()
    delta = delta.fillna(0.0)
    work["_dt"] = delta
    work["_e_int"] = work[energy_col].astype(float) * work["_dt"].astype(float)
    grouped = work.groupby(list(group_cols))["_e_int"].sum()
    return grouped


def estimate_consumption_kwh_per_km_from_ev_samples(
    df: pd.DataFrame,
    *,
    speed_col: str = "Vehicle Speed[km/h]",
    energy_col: str = "Energy_Consumption",
    time_col: str = "Timestamp",
) -> float:
    """Rough consumption estimate (kWh/km) from EV samples (if provided)."""
    if energy_col not in df.columns or speed_col not in df.columns:
        return 0.18
    work = df.copy()
    if not pd.api.types.is_datetime64_any_dtype(work[time_col]):
        work[time_col] = pd.to_datetime(work[time_col], errors="coerce")
    dt = work.groupby(["VehId", "Trip"])[time_col].diff().dt.total_seconds().fillna(0.0) if {"VehId", "Trip"}.issubset(work.columns) else pd.Series(1.0, index=work.index)
    # fallback if no groups
    if not isinstance(dt, pd.Series) or len(dt) != len(work):
        dt = pd.Series(1.0, index=work.index)
    dist_km = (work[speed_col].astype(float).fillna(0.0) * dt.astype(float) / 3600.0)
    energy = work[energy_col].astype(float).fillna(0.0) * dt.astype(float)
    total_dist = float(dist_km.sum())
    total_energy = float(energy.sum())
    if total_dist <= 0:
        return 0.18
    return max(total_energy / total_dist, 0.05)


def physics_arc_energy_kwh(
    distance_km: float,
    speed_kmh: float = 50.0,
    elevation_gain_m: float = 0.0,
    mass_kg: float = 1500.0,
    consumption_kwh_per_km: float = 0.18,
    regeneration_factor: float = 0.3,
) -> float:
    base = distance_km * consumption_kwh_per_km
    # grade work: m*g*h / 3.6e6 (kWh) with efficiency ~0.8; negative gain regenerates partly
    grade_energy = mass_kg * 9.81 * elevation_gain_m / 3.6e6
    if grade_energy > 0:
        base += grade_energy / 0.85
    else:
        base += grade_energy * regeneration_factor
    return float(base)


def saturate_regeneration(battery_before_kwh: float, energy_net_kwh: float, capacity_kwh: float) -> float:
    """Return stored energy after applying a movement: battery' = min(capacity, battery - energy_net)."""
    return min(capacity_kwh, battery_before_kwh - energy_net_kwh)
