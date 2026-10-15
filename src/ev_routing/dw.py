"""Dos fases lexicográficas con el branch-price-and-cut nativo de GCG."""

from __future__ import annotations

from importlib.metadata import version
from pathlib import Path
from time import monotonic
from typing import Any

from pyomo.opt import TerminationCondition

from ev_routing.contracts import (
    PhaseResult,
    ProblemInstance,
    Solution,
    SolverConfig,
    SolveResult,
    finite_or_none,
)
from ev_routing.dw_bridge import translate_model
from ev_routing.model import activate_energy_phase, build_model, extract_solution
from ev_routing.search_policy import PolicyProvider, SearchConfig, SearchController
from ev_routing.solve import (
    DELIVERY_BUDGET_FRACTION,
    _gaps,
    _load_initial_values,
    _proven_optimal,
)
from ev_routing.validation import validate_solution


def _finite_bound(native) -> float | None:
    bound = finite_or_none(native.getDualbound())
    return bound if bound is not None and abs(bound) < native.infinity() else None


def solve_dantzig_wolfe(
    instance: ProblemInstance,
    config: SolverConfig,
    search_config: SearchConfig | None = None,
    *,
    initial_solution: Solution | None = None,
    policy_provider: PolicyProvider | None = None,
) -> SolveResult:
    """Conservar el problema y recuperar soluciones en las variables originales."""
    from ev_routing.dw_callbacks import install_callbacks, master_statistics

    started = monotonic()
    deadline = started + config.time_limit_seconds
    search_config = search_config or SearchConfig()
    if initial_solution is not None:
        report = validate_solution(instance, initial_solution)
        if not report.feasible:
            raise ValueError(f"Arranque DW inválido: {report.violations}")
    controller = SearchController(search_config, deadline, policy_provider)
    best, origin = initial_solution, "initial_solution" if initial_solution else None
    phases, statistics = [], []
    source = build_model(instance)
    model_seconds = monotonic() - started
    engine_versions = {
        "pygcgopt": version("pygcgopt"), "pyscipopt": version("pyscipopt"),
        "gcg": "4.0.0", "scip": "10.0.0",
    }
    # Las versiones binarias están fijadas en el extra dw y se verifican antes
    # de usar APIs cuyos campos de certificación no son intercambiables.
    if engine_versions["pygcgopt"] != "1.0.0b0" or engine_versions["pyscipopt"] != "6.0.0":
        raise RuntimeError("Usar uv sync --extra dw para instalar las versiones compatibles")
    try:
        for name in ("deliveries", "energy"):
            phase_started = monotonic()
            if name == "energy":
                if best is None:
                    break
                activate_energy_phase(source, len(best.served_visit_ids))
            if deadline <= monotonic():
                phases.append(PhaseResult(
                    name=name, sense="maximize" if name == "deliveries" else "minimize",
                    status="time_limit", termination_condition="budget_exhausted",
                    has_solution=best is not None, proven_optimal=False,
                    incumbent=(len(best.served_visit_ids) if name == "deliveries"
                               else best.net_energy_kwh) if best else None,
                    incumbent_source="provided_incumbent" if best else None,
                ))
                break
            native = None
            submitted = False
            candidate = None
            bound = None
            error_message = ""
            stat: dict[str, Any] = {"name": name}
            try:
                translating = monotonic()
                bridge = translate_model(source, instance)
                stat["translation_seconds"] = monotonic() - translating
                native = bridge.native
                controller.start_phase(name, bridge.profile)
                # q, batería y relojes son continuos. Usar convexificación,
                # no la discretización experimental de bloques mixtos de GCG.
                # Esta elección matemática es idéntica para las tres políticas.
                native.setBoolParam("relaxing/gcg/discretization", False)
                native.setBoolParam("relaxing/gcg/mipdiscretization", False)
                decomposition = bridge.decompose(
                    controller.policy.decomposition, instance.vehicle_ids,
                )
                native.setIntParam("parallel/maxnthreads", config.threads)
                native.setIntParam("lp/threads", config.threads)
                native.setIntParam("randomization/randomseedshift", config.seed)
                native.setRealParam("limits/gap", config.relative_gap)
                native.hideOutput(not config.tee)
                master = native.getMasterProb()
                master.setIntParam("parallel/maxnthreads", config.threads)
                master.setIntParam("lp/threads", config.threads)
                master.setIntParam("randomization/randomseedshift", config.seed)
                if search_config.log_directory:
                    directory = Path(search_config.log_directory)
                    directory.mkdir(parents=True, exist_ok=True)
                    native.setLogfile(str(directory / f"{name}.gcg.log"))
                    master.setLogfile(str(directory / f"{name}.master.log"))
                callbacks = install_callbacks(native, controller, config.threads)
                if best is not None:
                    _load_initial_values(source, instance, best)
                    submitted = bridge.submit_start()
                remaining = max(0, deadline - monotonic())
                if name == "deliveries":
                    remaining *= DELIVERY_BUDGET_FRACTION
                stat.update(
                    structure=bridge.profile, decomposition=decomposition,
                    dw_approach="convexification",
                    initial_solution_stored=submitted,
                    native_time_limit_seconds=remaining,
                )
                if remaining <= 0:
                    termination = "budget_exhausted"
                else:
                    native.setRealParam("limits/time", remaining)
                    optimizing = monotonic()
                    native.optimize()
                    stat["native_optimize_seconds"] = monotonic() - optimizing
                    termination = str(native.getStatus())
                    bound = _finite_bound(native)
                    # PySCIPOpt puede envolver un SCIP_SOL* nulo en Solution.
                    # El conteo nativo, no la identidad Python, acredita incumbente.
                    solution = native.getBestSol() if native.getNSols() > 0 else None
                    if solution is not None:
                        bridge.load_solution(solution)
                        extracted = extract_solution(source, instance)
                        report = validate_solution(instance, extracted)
                        if not report.feasible:
                            raise ValueError(f"Solución DW inválida: {report.violations}")
                        if (
                            name == "energy" and best is not None
                            and len(extracted.served_visit_ids) != len(best.served_visit_ids)
                        ):
                            raise ValueError("La fase energética cambió el cumplimiento fijado")
                        candidate = extracted
                    stat.update(
                        **master_statistics(master),
                        native_gap=finite_or_none(native.getGap()),
                        gcg_dual_bound=bound,
                    )
                    if stat["native_gap"] is not None and stat["native_gap"] >= 1e19:
                        stat["native_gap"] = None
                stat.update(
                    policy_applications=callbacks.changes,
                    callback_errors=callbacks.errors,
                    pricing_heuristic_callbacks=callbacks.pricing_heuristic_calls,
                    pricing_exact_callbacks=callbacks.pricing_exact_calls,
                )
                if callbacks.errors:
                    termination, bound = "callback_error", None
                    error_message = "Error en callback; no se emite certificado de esta fase."
                if termination == "infeasible" and best is not None:
                    raise ValueError("GCG declaró infactible una fase con incumbente validado")
            except Exception as error:
                termination, bound = "error", None
                error_message = f"{type(error).__name__}: {error}"
                stat["error"] = error_message
            controller.collect(apply=False)
            previous = best
            if candidate is not None and (
                best is None
                or len(candidate.served_visit_ids) > len(best.served_visit_ids)
                or (
                    len(candidate.served_visit_ids) == len(best.served_visit_ids)
                    and candidate.net_energy_kwh <= best.net_energy_kwh + 1e-7
                )
            ):
                best, origin = candidate, "solver"
            incumbent = None if best is None else (
                float(len(best.served_visit_ids)) if name == "deliveries" else best.net_energy_kwh
            )
            tc = TerminationCondition.optimal if termination == "optimal" else None
            proven = (
                termination not in {"error", "callback_error", "infeasible", "inforunbd", "unbounded"}
                and _proven_optimal(name, tc, incumbent, bound, config.relative_gap)
            )
            absolute, relative = _gaps(incumbent, bound)
            status = "optimal" if proven else "feasible" if best is not None else (
                "infeasible" if termination == "infeasible" else
                "time_limit" if termination in {"timelimit", "budget_exhausted"} else
                "error" if termination in {"error", "callback_error"} else "no_solution"
            )
            phases.append(PhaseResult(
                name=name, sense="maximize" if name == "deliveries" else "minimize",
                status=status, termination_condition=termination,
                has_solution=best is not None, proven_optimal=bool(proven),
                incumbent=incumbent, best_bound=bound, absolute_gap=absolute,
                relative_gap=relative, runtime_seconds=monotonic() - phase_started,
                warm_start="submitted" if submitted else "not_requested",
                incumbent_source=("solver" if best is candidate else "provided_incumbent")
                if best else None,
                message=error_message or (
                    "Se conserva el incumbente validado anterior."
                    if best is previous and best is not None else ""
                ),
            ))
            statistics.append(stat)
            if termination in {"error", "callback_error", "infeasible", "inforunbd", "unbounded"}:
                break
    finally:
        controller.close()
    lexicographic_optimal = len(phases) == 2 and all(p.proven_optimal for p in phases)
    status = "optimal" if lexicographic_optimal else "feasible" if best else (
        phases[-1].status if phases else "time_limit"
    )
    return SolveResult(
        requested_solver="gcg", used_solver="gcg", solver_version="GCG 4.0.0 / SCIP 10.0.0",
        phases=phases, solution=best, solution_source=origin,
        lexicographic_optimal=lexicographic_optimal, status=status,
        runtime_seconds=monotonic() - started,
        message=(
            "Dantzig–Wolfe de la misma formulación Pyomo; certificado condicionado "
            "a los caminos, H y opciones del snapshot. La energía es condicionada "
            "al cumplimiento encontrado si la primera fase no prueba su máximo."
        ),
        search={
            "engine": "gcg_branch_price_and_cut", "versions": engine_versions,
            "model_seconds": model_seconds,
            "configuration": search_config.model_dump(), "phases": statistics,
            "controller": controller.report(),
            "certificate_source": "GCG.getDualbound; never the restricted-master LP alone",
        },
    )
