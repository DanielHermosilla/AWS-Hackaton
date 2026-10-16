"""Paired, signed impact estimates for auditable presentation tables."""

from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path
from statistics import mean

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ev_routing.benchmark import _save, _sha
from ev_routing.evidence import write_table


class TokenPrice(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    input: float = Field(ge=0)
    output: float = Field(ge=0)
    max_input_tokens: int = Field(gt=0)
    cache_read: float | None = Field(default=None, ge=0)
    cache_write: float | None = Field(default=None, ge=0)


class ImpactFactors(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    geography: str = Field(min_length=1)
    currency: str = Field(min_length=1)
    electricity_price_per_kwh: float = Field(ge=0)
    diesel_price_per_litre: float = Field(ge=0)
    diesel_litres_per_100km: float = Field(gt=0)
    diesel_kg_co2_per_litre: float = Field(gt=0)
    grid_generation_kg_co2_per_kwh: float = Field(ge=0)
    grid_loss_fraction: float = Field(ge=0, lt=1)
    charging_efficiency: float = Field(gt=0, le=1)
    equivalent_route_days_per_year: int | None = Field(default=None, ge=1, le=366, strict=True)
    usd_to_currency: float = Field(default=1, gt=0)
    bedrock_prices_per_million_tokens_usd: dict[str, TokenPrice] = Field(default_factory=dict)
    sources: dict[str, str]
    assumptions: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def documented(self):
        required = {"electricity", "diesel_price", "diesel_co2", "grid_co2", "checked_date"}
        if self.bedrock_prices_per_million_tokens_usd:
            required.add("bedrock")
        if self.currency != "USD" or self.usd_to_currency != 1:
            required.add("exchange")
        if any(not self.sources.get(key) for key in required):
            raise ValueError("Documente fuente/fecha de factores y del cambio de moneda cuando corresponda.")
        return self

    @property
    def grid_delivered_factor(self):
        return self.grid_generation_kg_co2_per_kwh / (1 - self.grid_loss_fraction)


def llm_cost(result, factors):
    tuning = result.get("tuning") or {}
    calls, decisions = tuning.get("calls", 0), tuning.get("decisions", [])
    if not calls:
        return 0.0
    if calls != len(decisions) or tuning.get("inference_inflight"):
        return None
    cost = 0.0
    for decision in decisions:
        price = factors.bedrock_prices_per_million_tokens_usd.get(decision.get("model_id"))
        usage = decision.get("usage") or {}
        i, o = usage.get("inputTokens"), usage.get("outputTokens")
        read, write = usage.get("cacheReadInputTokens", 0), usage.get("cacheWriteInputTokens", 0)
        if (price is None or not all(type(n) is int and n >= 0 for n in (i, o, read, write))
                or i + read + write > price.max_input_tokens
                or (read and price.cache_read is None) or (write and price.cache_write is None)):
            return None
        # Converse reports uncached input separately in these native records.
        # Reject inconsistent accounting rather than double-charge a prefix.
        if (read or write) and usage.get("totalTokens", i + o + read + write) != i + o + read + write:
            return None
        cost += (i * price.input + o * price.output
                 + read * (price.cache_read or 0) + write * (price.cache_write or 0)) / 1e6
    return cost * factors.usd_to_currency


def estimate_run(row, factors, result):
    values = {
        "llm_cost_estimate": llm_cost(result, factors),
        "electricity_replenishment_kwh": None, "electricity_cost": None,
        "electricity_co2_kg": None, "diesel_same_route_litres": None,
        "electrification_tailpipe_co2_avoided_kg": None,
        "electrification_operational_co2_saved_kg": None,
        "electrification_energy_bill_saved": None,
    }
    if not row["feasible"] or row.get("energy_kwh") is None or row["energy_kwh"] < 0:
        return values
    grid = row["energy_kwh"] / factors.charging_efficiency
    values.update(electricity_replenishment_kwh=grid,
                  electricity_cost=grid * factors.electricity_price_per_kwh,
                  electricity_co2_kg=grid * factors.grid_delivered_factor)
    if row.get("distance_km") is not None:
        litres = row["distance_km"] * factors.diesel_litres_per_100km / 100
        tailpipe = litres * factors.diesel_kg_co2_per_litre
        values.update(
            diesel_same_route_litres=litres,
            electrification_tailpipe_co2_avoided_kg=tailpipe,
            electrification_operational_co2_saved_kg=tailpipe - values["electricity_co2_kg"],
            electrification_energy_bill_saved=litres * factors.diesel_price_per_litre
            - values["electricity_cost"],
        )
    return values


def paired_impact(reference, candidate, factors):
    pair = {k: candidate[k] for k in ("case_id", "family", "solver_seed", "budget_seconds")}
    pair.update(reference=reference["policy"], candidate=candidate["policy"],
                delivery_delta=None, battery_energy_saved_kwh=None, energy_saved_percent=None,
                electricity_saved_kwh=None, vehicle_electricity_co2_saved_kg=None,
                energy_bill_saved=None, money_saved_after_llm=None,
                full_service_speedup=None, certified_gap_speedup=None,
                reason="Falta una pareja factible, con la misma física y presupuesto.")
    if not (reference["feasible"] and candidate["feasible"]
            and reference["physical_sha256"] == candidate["physical_sha256"]
            and reference["budget_seconds"] == candidate["budget_seconds"]):
        return pair
    pair["delivery_delta"] = candidate["deliveries"] - reference["deliveries"]
    for target, field, reached in (
        ("full_service_speedup", "first_full_delivery_solver_seconds", "first_full_within_solver_budget"),
        ("certified_gap_speedup", "time_to_gap_cold_estimate_seconds", "energy_gap_reached"),
    ):
        if reference[reached] and candidate[reached] and reference[field] and candidate[field]:
            pair[target] = reference[field] / candidate[field]
    served = reference.get("served_visit_ids")
    if (served is None or candidate.get("served_visit_ids") is None
            or len(served) != reference["deliveries"]
            or len(candidate["served_visit_ids"]) != candidate["deliveries"]
            or set(served) != set(candidate["served_visit_ids"])):
        pair["reason"] = "Clientes atendidos distintos o no auditables: ahorro energético no comparable."
        return pair
    saving = reference["energy_kwh"] - candidate["energy_kwh"]
    grid = saving / factors.charging_efficiency
    money = grid * factors.electricity_price_per_kwh
    pair.update(
        reason="Mismos clientes; ahorro firmado. Negativo significa empeoramiento.",
        battery_energy_saved_kwh=saving,
        energy_saved_percent=100 * saving / reference["energy_kwh"] if reference["energy_kwh"] > 0 else None,
        electricity_saved_kwh=grid, vehicle_electricity_co2_saved_kg=grid * factors.grid_delivered_factor,
        energy_bill_saved=money,
    )
    a, b = reference["llm_cost_estimate"], candidate["llm_cost_estimate"]
    if a is not None and b is not None:
        pair["money_saved_after_llm"] = money - (b - a)
    days = factors.equivalent_route_days_per_year
    if days is not None:
        for field in ("battery_energy_saved_kwh", "vehicle_electricity_co2_saved_kg",
                      "energy_bill_saved", "money_saved_after_llm"):
            pair[f"annual_projection_{field}"] = pair[field] * days if pair[field] is not None else None
    return pair


def aggregate_pairs(pairs):
    groups = defaultdict(list)
    for pair in pairs:
        groups[pair["family"], pair["reference"], pair["candidate"]].append(pair)
    summaries = []
    for (family, reference, candidate), group in sorted(groups.items()):
        energies = [p for p in group if p["battery_energy_saved_kwh"] is not None]
        by_instance = defaultdict(list)
        for p in energies:
            by_instance[p["case_id"]].append(p["battery_energy_saved_kwh"])
        means = [mean(values) for values in by_instance.values()]
        interval = None
        if len(means) >= 2:
            rng = random.Random(9871)
            samples = sorted(mean(rng.choices(means, k=len(means))) for _ in range(2000))
            interval = [samples[49], samples[1949]]
        summary = {
            "family": family, "reference": reference, "candidate": candidate,
            "pairs": len(group), "comparable_energy_pairs": len(energies),
            "energy_wins": sum(p["battery_energy_saved_kwh"] > 1e-6 for p in energies),
            "energy_losses": sum(p["battery_energy_saved_kwh"] < -1e-6 for p in energies),
            "energy_ties": sum(abs(p["battery_energy_saved_kwh"]) <= 1e-6 for p in energies),
            "energy_saved_mean_by_instance_kwh": mean(means) if means else None,
            "energy_saved_bootstrap_95_by_instance_kwh": interval,
            "bootstrap_scope": "Exploratorio dentro de esta familia dirigida; no demuestra generalización.",
        }
        for field in ("delivery_delta", "energy_saved_percent", "vehicle_electricity_co2_saved_kg",
                      "energy_bill_saved", "money_saved_after_llm"):
            values = [p[field] for p in group if p[field] is not None]
            summary[f"mean_{field}"] = mean(values) if values else None
        summaries.append(summary)
    return summaries


def report_campaign(campaign: Path, factor_path: Path, output: Path):
    """Read native immutable results, retaining failed runs and every comparator."""
    factors = ImpactFactors.model_validate_json(factor_path.read_text())
    rows = json.loads((campaign / "summary.json").read_text())
    for row in rows:
        run = campaign / "runs" / f"{row['case_id']}-{row['policy']}-seed{row['solver_seed']}"
        result_path = run / "result.json"
        execution = json.loads((run / "execution.json").read_text())
        if execution.get("result_sha256") != (_sha(result_path) if result_path.exists() else None):
            raise ValueError(f"Resultado modificado: {result_path}")
        result = json.loads(result_path.read_text()) if result_path.exists() else {}
        solution = (result.get("solve") or {}).get("solution") or {}
        row["served_visit_ids"] = sorted(solution["served_visit_ids"]) if row["feasible"] else None
        row.update(estimate_run(row, factors, result))
        row["result_path"] = str(result_path)
    pairs = []
    grouped = defaultdict(dict)
    for row in rows:
        grouped[row["case_id"], row["solver_seed"]][row["policy"]] = row
    for policies in grouped.values():
        for candidate in ("adaptive", "adaptive_knobs"):
            if candidate in policies:
                for reference in ("standard", "fixed", "rules", "adaptive_knobs"):
                    if reference in policies and reference != candidate:
                        pairs.append(paired_impact(policies[reference], policies[candidate], factors))
        if "standard" in policies:
            for candidate in ("fixed", "rules"):
                if candidate in policies:
                    pairs.append(paired_impact(policies["standard"], policies[candidate], factors))
    output.mkdir(parents=True, exist_ok=True)
    _save(output / "factors.json", factors.model_dump())
    stats = aggregate_pairs(pairs)
    for name, records in (("kpis", rows), ("paired-impact", pairs), ("llm-impact", stats)):
        _save(output / f"{name}.json", records)
        write_table(output / f"{name}.csv", records)
    _save(output / "provenance.json", {
        "campaign": str(campaign), "campaign_manifest_sha256": _sha(campaign / "manifest.json"),
        "factors_sha256": _sha(factor_path), "source_summary_sha256": _sha(campaign / "summary.json"),
        "report_includes_all_completed_runs": True,
    })
    def show(value):
        return "ND" if value is None else f"{value:.4f}"

    lines = [
        "# Resultados para la presentación", "",
        f"Escenario: {factors.geography}. Moneda: {factors.currency}.",
        "Instancias sintéticas dirigidas al reparto global con ventanas y recarga. No son viajes medidos.",
        "Cada cifra es reproducible en kpis.csv y paired-impact.csv. Se conservan pérdidas y fallbacks.",
        "",
        "| Familia | Referencia | Candidato | Pares comparables / todos | Gana / pierde / empata energía | Δ kWh medio | Δ CO₂ kg medio | Δ dinero tras LLM |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for s in stats:
        lines.append(
            f"| {s['family']} | {s['reference']} | {s['candidate']} | {s['comparable_energy_pairs']}/{s['pairs']} | "
            f"{s['energy_wins']}/{s['energy_losses']}/{s['energy_ties']} | "
            f"{show(s['energy_saved_mean_by_instance_kwh'])} | {show(s['mean_vehicle_electricity_co2_saved_kg'])} | "
            f"{show(s['mean_money_saved_after_llm'])} |"
        )
    lines += [
        "", "## KPI del desafío (presentación, diapositivas 5–7)", "",
        "| Caso | Política | Entregas | Factible en calles | Energía kWh | Tiempo frío s | Gap energía % |",
        "|---|---|---:|---|---:|---:|---:|",
    ]
    for r in rows:
        gap = r["energy_relative_gap"]
        lines.append(
            f"| {r['case_id']} | {r['policy']} | {r['deliveries']}/{r['customers']} | {r['feasible']} | "
            f"{show(r['energy_kwh'])} | {show(r['cold_pipeline_estimate_seconds'])} | "
            f"{show(gap * 100 if gap is not None else None)} |"
        )
    lines += [
        "", "## Qué se puede afirmar", "",
        "- Ahorro por LLM: diferencia pareada contra standard, fixed y rules; solo los mismos clientes y presupuesto.",
        "- Electrificación: diésel hipotético sobre la MISMA ruta del EV. No atribuir ese CO₂ al LLM.",
        "- CO₂ del LLM significa aquí cambio en electricidad de los vehículos; no se conocen emisiones de inferencia.",
        "- Coste tras LLM descuenta inferencia estimada con tokens reales. No incluye ordenador, salarios ni inversión.",
        "- ND en dinero neto significa uso/tarifa desconocidos; una llamada fallida no se supone gratuita.",
        "- Tiempo frío = preparación medida una vez + proceso. La inferencia solapada no se suma otra vez.",
        "- Dos timeouts no permiten afirmar speedup. certified_gap_speedup exige alcanzar el mismo gap del 0.5%.",
        "- Se informa tiempo a todas las entregas por separado del tiempo a certificar energía.",
        "- Escalabilidad: comparar los tamaños ejecutados; estas instancias usan dos vehículos, no prueban escala de flota.",
        "- El intervalo bootstrap agrupa semillas del solver por instancia. Es exploratorio, no un test confirmatorio.",
        "- Las semillas usadas durante el desarrollo dejan de ser prueba independiente; congelar antes de la evaluación final.",
        "", "## Fórmulas", "",
        "`ΔE = E_sin_LLM − E_con_LLM` (kWh de batería); `ΔE_red = ΔE / eficiencia`.",
        "`ΔCO₂_vehículos = ΔE_red × factor_red / (1 − pérdidas_red)`.",
        "`Δdinero = ΔE_red × tarifa − (coste_LLM_con − coste_LLM_sin)`.",
        "`CO₂_electrificación = km × L/100km / 100 × kgCO₂/L − E_red × factor_red / (1 − pérdidas_red)`.",
        "Signos positivos son ahorros; los negativos son aumentos. No se suman repeticiones como si fueran días distintos.",
        "", "## Factores y supuestos", "",
        *[f"- {key}: {value}" for key, value in factors.sources.items()],
        *[f"- {value}" for value in factors.assumptions],
        "",
    ]
    (output / "diapositivas.md").write_text("\n".join(lines))
    return stats
