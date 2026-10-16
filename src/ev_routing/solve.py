"""Resolución lexicográfica con presupuesto compartido y backends explícitos.

El adaptador consume la plantilla del PDF. No cambia tolerancias físicas,
restricciones ni objetivos, y no utiliza un LLM. La validación independiente de
las rutas corresponde a ``validation.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isclose
from time import monotonic
from typing import TYPE_CHECKING, Any

import pyomo.environ as pyo
from pyomo.opt import SolutionStatus, SolverStatus, TerminationCondition

from ev_routing.contracts import (
    PhaseResult,
    ProblemInstance,
    Solution,
    SolverConfig,
    SolveResult,
    finite_or_none,
)
from ev_routing.model import activate_energy_phase, build_model, extract_solution
from ev_routing.operations import arc_energy
from ev_routing.validation import validate_solution

if TYPE_CHECKING:
    from ev_routing.search_policy import SearchConfig

# La fase 2 recibe todo el tiempo restante, incluido el que no usa la fase 1.
DELIVERY_BUDGET_FRACTION = 0.7
_CERTIFICATE_TOLERANCE = 1e-7
_OPTIMAL = {TerminationCondition.optimal, TerminationCondition.globallyOptimal}
_NO_FEASIBLE_SOLUTION = {
    TerminationCondition.infeasible,
    TerminationCondition.unbounded,
    TerminationCondition.infeasibleOrUnbounded,
    TerminationCondition.invalidProblem,
    TerminationCondition.intermediateNonInteger,
    TerminationCondition.noSolution,
}


class _BackendUnavailable(Exception):
    """Disponibilidad/licencia; la única clase que permite fallback automático."""


@dataclass
class _Backend:
    name: str
    solver: Any
    version: str | None

    def close(self) -> None:
        close = getattr(self.solver, "close", None)
        if close is not None:
            try:
                close()
            except Exception:
                # Un error al liberar el entorno no debe borrar un incumbente
                # ni impedir el fallback de una licencia que falló al iniciar.
                pass


def _unavailable_reason(error: Exception, backend: str) -> str | None:
    """Clasificar sin devolver textos que puedan contener detalles de licencia."""
    if isinstance(error, _BackendUnavailable):
        return str(error)
    if isinstance(error, (ImportError, ModuleNotFoundError)):
        return f"{backend}: módulo o dependencia no disponible"
    message = str(error).lower()
    if backend == "gurobi":
        # Gurobi: NO_LICENSE y SIZE_LIMIT_EXCEEDED, respectivamente.
        if getattr(error, "errno", None) == 10010 or "size-limited license" in message:
            return "gurobi: el modelo excede los límites de la licencia"
        if getattr(error, "errno", None) == 10009 or any(
            text in message for text in ("license", "licence", "not licensed")
        ):
            return "gurobi: licencia no disponible o no válida"
        if "gurobipy" in message and any(
            text in message for text in ("not found", "not available", "failed to import")
        ):
            return "gurobi: interfaz gurobipy no disponible"
    if any(
        text in message
        for text in ("no executable found", "failed to set executable", "solver is not available")
    ):
        return f"{backend}: ejecutable no disponible"
    return None


def _make_backend(name: str) -> _Backend:
    solver = None
    try:
        if name == "gurobi":
            # Cada llamada conserva y libera su propio entorno de Gurobi.
            solver = pyo.SolverFactory("gurobi_direct", manage_env=True)
        else:
            solver = pyo.SolverFactory("scip")
        if not solver.available(exception_flag=False):
            raise _BackendUnavailable(f"{name}: interfaz o ejecutable no disponible")
        version = solver.version()
        return _Backend(name, solver, ".".join(map(str, version)) if version else None)
    except Exception as error:
        if solver is not None:
            _Backend(name, solver, None).close()
        reason = _unavailable_reason(error, name)
        if reason is not None:
            raise _BackendUnavailable(reason) from error
        raise


def _set_options(backend: _Backend, config: SolverConfig, seconds: float) -> None:
    if backend.name == "gurobi":
        options = {
            "TimeLimit": seconds,
            "MIPGap": config.relative_gap,
            "Threads": config.threads,
            "Seed": config.seed,
        }
    else:
        options = {
            "limits/time": seconds,
            "limits/gap": config.relative_gap,
            "parallel/maxnthreads": config.threads,
            "randomization/randomseedshift": config.seed,
        }
    for key, value in options.items():
        backend.solver.options[key] = value


def _attribute(container: Any, name: str) -> Any:
    # Pyomo devuelve UndefinedData o AttributeError para estadísticas ausentes.
    return getattr(container, name, None)


def _has_solution(results: Any) -> bool:
    if results.solver.termination_condition in _NO_FEASIBLE_SOLUTION:
        return False
    if results.solver.status == SolverStatus.error:
        return False
    count = finite_or_none(_attribute(results.problem, "number_of_solutions"))
    if count == 0 or not len(results.solution):
        return False
    candidate = results.solution(0)
    if candidate.status in {SolutionStatus.infeasible, SolutionStatus.unbounded, SolutionStatus.error}:
        return False
    # gurobi_direct inserta un registro vacío incluso cuando SolCount == 0.
    # No reutilizar valores que quedaron en Pyomo de una fase anterior.
    return bool(candidate.variable)


def _best_bound(results: Any, backend: str, sense: str) -> float | None:
    bound = None
    if backend == "scip":
        # El plugin solo llena problem.lower/upper_bound al terminar óptimo.
        bound = finite_or_none(_attribute(results.solver, "dual_bound"))
    if bound is None:
        field = "upper_bound" if sense == "maximize" else "lower_bound"
        bound = finite_or_none(_attribute(results.problem, field))
    infinity = 1e20 if backend == "scip" else 1e100
    return None if bound is not None and abs(bound) >= infinity else bound


def _gaps(incumbent: float | None, bound: float | None) -> tuple[float | None, float | None]:
    if incumbent is None or bound is None:
        return None, None
    absolute = abs(incumbent - bound)
    # Gap normalizado común, documentado; no confundirlo con el gap nativo.
    return absolute, absolute / max(1.0, abs(incumbent), abs(bound))


def _proven_optimal(
    name: str,
    termination: Any,
    incumbent: float | None,
    bound: float | None,
    relative_gap: float,
) -> bool:
    if incumbent is None:
        return False
    if name == "deliveries" and bound is not None:
        integer_value = round(incumbent)
        return (
            abs(incumbent - integer_value) <= 1e-5
            and bound >= incumbent - _CERTIFICATE_TOLERANCE
            and bound < integer_value + 1 - _CERTIFICATE_TOLERANCE
        )
    if termination not in _OPTIMAL:
        return False
    if bound is None:
        # Un estado OPTIMAL con MIPGap > 0 no prueba óptimo lexicográfico.
        return relative_gap == 0
    return abs(incumbent - bound) <= _CERTIFICATE_TOLERANCE


def _phase_status(termination: Any, has_solution: bool, proven: bool) -> str:
    if proven:
        return "optimal"
    if has_solution:
        return "feasible"
    mapping = {
        TerminationCondition.infeasible: "infeasible",
        TerminationCondition.unbounded: "unbounded",
        TerminationCondition.infeasibleOrUnbounded: "infeasible_or_unbounded",
        TerminationCondition.maxTimeLimit: "time_limit",
        TerminationCondition.error: "error",
        TerminationCondition.solverFailure: "error",
        TerminationCondition.internalSolverError: "error",
        TerminationCondition.invalidProblem: "error",
    }
    return mapping.get(termination, "no_solution")


def _empty_phase(name: str, status: str, termination: str, message: str) -> PhaseResult:
    return PhaseResult(
        name=name,
        sense="maximize" if name == "deliveries" else "minimize",
        status=status,
        termination_condition=termination,
        has_solution=False,
        proven_optimal=False,
        message=message,
    )


def _load_initial_values(
    model: pyo.ConcreteModel, instance: ProblemInstance, solution: Solution
) -> None:
    """Dar valores iniciales, nunca fijar variables ni añadir restricciones.

    ``solve_instance`` valida la ruta antes de llegar aquí. Las auxiliares
    reproducen (11)–(15), incluida saturación, también para otros incumbentes
    válidos que no provengan de nuestra heurística sin recarga.
    """
    for component in (model.y, model.z, model.x, model.a, model.gamma):
        for variable in component.values():
            variable.set_value(0)
    energies = {
        (a.from_node_id, a.to_node_id): arc_energy(a, instance.operations) for a in instance.arcs
    }
    if hasattr(model, "station_charge"):
        for variable in model.station_charge.values():
            variable.set_value(0)
    energies[instance.depot_id, instance.depot_id] = 0.0
    for customer in solution.served_visit_ids:
        model.y[customer].set_value(1)
    for route in solution.routes:
        k = route.vehicle_id
        for r, step in enumerate(route.steps):
            model.z[step.node_id, k, r].set_value(1)
            model.b[k, r].set_value(step.battery_arrival_kwh)
            if hasattr(model, "arrival_time"):
                model.arrival_time[k, r].set_value(step.arrival_seconds)
            if r == instance.parameters.movement_limit:
                continue
            if hasattr(model, "activity_start"):
                model.activity_start[k, r].set_value(step.service_start_seconds)
            if hasattr(model, "station_charge") and (step.node_id, k) in model.charging_pairs:
                model.station_charge[step.node_id, k, r].set_value(step.charged_to_battery_kwh)
            model.x[step.node_id, step.next_node_id, k, r].set_value(1)
            for customer in step.delivered_visit_ids:
                model.a[customer, k, r].set_value(1)
            model.q[k, r].set_value(step.charged_to_battery_kwh)
            model.b_departure[k, r].set_value(step.battery_departure_kwh)
            unsaturated = step.battery_departure_kwh - energies[step.node_id, step.next_node_id]
            model.u[k, r].set_value(unsaturated)
            model.gamma[k, r].set_value(int(unsaturated > instance.parameters.battery_capacity_kwh))
            model.E[k, r].set_value(
                step.battery_departure_kwh - route.steps[r + 1].battery_arrival_kwh
            )
    model.E_total.set_value(solution.net_energy_kwh)


def _retain_incumbent(
    phase: PhaseResult, candidate: Solution | None, initial: Solution, config: SolverConfig
) -> tuple[PhaseResult, Solution]:
    """No perder un testigo validado por timeout, backend sin arranque o error."""
    count_mismatch = (
        phase.name == "energy" and candidate is not None
        and len(candidate.served_visit_ids) != len(initial.served_visit_ids)
    )
    if count_mismatch:
        phase.message += "; cambió el número fijado de entregas: se conserva el incumbente"
        phase.best_bound = None
        phase.proven_optimal = False
        candidate = None
    better = candidate is None or (
        phase.name == "deliveries"
        and len(initial.served_visit_ids) > len(candidate.served_visit_ids)
    ) or (
        candidate is not None
        and len(initial.served_visit_ids) == len(candidate.served_visit_ids)
        and initial.net_energy_kwh < candidate.net_energy_kwh
    )
    if not better:
        return phase, candidate
    old_incumbent = phase.incumbent
    old_proof = phase.proven_optimal
    phase.incumbent = (
        float(len(initial.served_visit_ids)) if phase.name == "deliveries"
        else initial.net_energy_kwh
    )
    phase.has_solution = True
    phase.incumbent_source = "provided_incumbent"
    phase.message += "; se conserva el incumbente proporcionado y validado"
    contradicted_proof = old_proof and old_incumbent is not None and (
        (phase.name == "deliveries" and phase.incumbent > old_incumbent + _CERTIFICATE_TOLERANCE)
        or (phase.name == "energy" and phase.incumbent < old_incumbent - _CERTIFICATE_TOLERANCE)
    )
    bound = phase.best_bound
    if bound is not None and (
        (phase.name == "deliveries" and bound < phase.incumbent - _CERTIFICATE_TOLERANCE)
        or (phase.name == "energy" and bound > phase.incumbent + _CERTIFICATE_TOLERANCE)
    ):
        phase.best_bound = None
        phase.message += "; cota incompatible con el incumbente conservado"
    try:
        termination = TerminationCondition(phase.termination_condition)
    except ValueError:
        termination = TerminationCondition.unknown
    phase.proven_optimal = _proven_optimal(
        phase.name, termination, phase.incumbent, phase.best_bound, config.relative_gap
    )
    if phase.best_bound is None:
        # OPTIMAL sin vector/cota no prueba que el testigo externo sea óptimo.
        # Solo se puede conservar la prueba sin cota de un incumbente nativo
        # completo cuyo valor objetivo coincide con el que estamos reteniendo.
        phase.proven_optimal = (
            phase.proven_optimal and old_proof and old_incumbent is not None
            and abs(old_incumbent - phase.incumbent) <= _CERTIFICATE_TOLERANCE
        )
    if "cota incompatible" in phase.message or contradicted_proof or count_mismatch:
        phase.proven_optimal = False
    if contradicted_proof:
        phase.message += "; certificado anterior incompatible con el incumbente conservado"
    phase.status = "optimal" if phase.proven_optimal else "feasible"
    phase.absolute_gap, phase.relative_gap = _gaps(phase.incumbent, phase.best_bound)
    return phase, initial


def _solve_phase(
    model: pyo.ConcreteModel,
    instance: ProblemInstance,
    config: SolverConfig,
    backend: _Backend,
    name: str,
    seconds: float,
    initial_solution: Solution | None = None,
) -> tuple[PhaseResult, Solution | None]:
    _set_options(backend, config, seconds)
    warm_start = "not_requested"
    try:
        kwargs = {"load_solutions": False, "tee": config.tee}
        if initial_solution is not None:
            if backend.solver.warm_start_capable():
                _load_initial_values(model, instance, initial_solution)
                kwargs["warmstart"] = True
                warm_start = "submitted"
            else:
                warm_start = "unsupported"
        results = backend.solver.solve(model, **kwargs)
    except Exception as error:
        reason = _unavailable_reason(error, backend.name)
        if reason is not None:
            raise _BackendUnavailable(reason) from error
        failed = _empty_phase(
            name, "error", "error", f"{backend.name}: error de solver ({type(error).__name__})"
        )
        failed.warm_start = warm_start
        return failed, None
    termination = results.solver.termination_condition
    if termination == TerminationCondition.licensingProblems:
        raise _BackendUnavailable(f"{backend.name}: licencia no disponible o no válida")
    sense = "maximize" if name == "deliveries" else "minimize"
    bound = _best_bound(results, backend.name, sense)
    incumbent = None
    solution = None
    message = f"backend={backend.name}; version={backend.version or 'desconocida'}"
    if _has_solution(results):
        try:
            for variable in model.component_data_objects(pyo.Var):
                if not variable.fixed:
                    variable.set_value(None)
            model.solutions.load_from(results)
            expression = model.served_count if name == "deliveries" else model.E_total
            incumbent = finite_or_none(pyo.value(expression))
            if incumbent is None:
                raise ValueError("objetivo no finito")
            solution = extract_solution(model, instance)
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            failed = _empty_phase(
                name,
                "error",
                str(termination),
                f"{message}; no se pudo extraer un incumbente completo ({type(error).__name__})",
            )
            failed.warm_start = warm_start
            return failed, None
    if incumbent is not None and bound is not None:
        wrong_direction = (
            bound < incumbent - _CERTIFICATE_TOLERANCE
            if sense == "maximize"
            else bound > incumbent + _CERTIFICATE_TOLERANCE
        )
        if wrong_direction:
            bound = None
            message += "; cota incompatible con el incumbente: no se certifica optimalidad"
    proven = _proven_optimal(name, termination, incumbent, bound, config.relative_gap)
    if "cota incompatible" in message:
        proven = False
    absolute_gap, relative_gap = _gaps(incumbent, bound)
    return PhaseResult(
        name=name,
        sense=sense,
        status=_phase_status(termination, solution is not None, proven),
        termination_condition=str(termination),
        has_solution=solution is not None,
        proven_optimal=proven,
        incumbent=incumbent,
        best_bound=bound,
        absolute_gap=absolute_gap,
        relative_gap=relative_gap,
        message=message,
        warm_start=warm_start,
        incumbent_source="solver" if solution is not None else None,
    ), solution


def _run_phase(
    model: pyo.ConcreteModel,
    instance: ProblemInstance,
    config: SolverConfig,
    name: str,
    deadline: float,
    backend: _Backend | None,
    fallbacks: list[str],
    initial_solution: Solution | None = None,
) -> tuple[PhaseResult, Solution | None, _Backend | None]:
    started = monotonic()
    while True:
        remaining = deadline - monotonic()
        if remaining <= 0:
            phase = _empty_phase(
                name, "time_limit", "maxTimeLimit", "Presupuesto compartido agotado."
            )
            solution = None
            break
        requested = (
            backend.name
            if backend is not None
            else ("scip" if config.solver == "scip" or fallbacks else "gurobi")
        )
        try:
            if backend is None:
                backend = _make_backend(requested)
            remaining = deadline - monotonic()
            if remaining <= 0:
                continue
            phase, solution = _solve_phase(
                model, instance, config, backend, name, remaining, initial_solution
            )
            break
        except _BackendUnavailable as error:
            if backend is not None:
                backend.close()
                backend = None
            if config.solver == "auto" and requested == "gurobi":
                fallbacks.append(str(error))
                continue
            phase = _empty_phase(name, "unavailable", "unavailable", str(error))
            solution = None
            break
        except Exception as error:
            phase = _empty_phase(
                name, "error", "error", f"{requested}: error de interfaz ({type(error).__name__})"
            )
            solution = None
            break
    if initial_solution is not None:
        phase, solution = _retain_incumbent(phase, solution, initial_solution, config)
    phase.runtime_seconds = max(0.0, monotonic() - started)
    return phase, solution, backend


def solve_instance(
    instance: ProblemInstance, config: SolverConfig, *, initial_solution: Solution | None = None,
    search_config: SearchConfig | None = None,
) -> SolveResult:
    """Resolver (16) en dos fases y conservar el mejor incumbente extraído.

    ``auto`` permite fallback Gurobi -> SCIP solo por disponibilidad/licencia.
    Elegir un solver explícitamente fija el backend para una comparación.
    El presupuesto total incluye construcción, intentos fallidos y extracción;
    los límites de los backends son blandos y pueden excederse por sobrecostos.
    """
    if config.solver != "scip-routes" and instance.provenance.get("representation", {}).get("kind") == "resource_paths":
        raise ValueError("resource_paths requiere scip-routes; conservar la red vial para backends posicionales")
    if config.solver == "scip-routes":
        try:
            from ev_routing.route_solver import solve_routes
        except ImportError as error:
            raise RuntimeError("Instalar el backend por rutas con uv sync --extra dw") from error
        return solve_routes(instance, config, search_config, initial_solution=initial_solution)
    if config.solver == "gcg":
        try:
            from ev_routing.dw import solve_dantzig_wolfe
            return solve_dantzig_wolfe(
                instance, config, search_config, initial_solution=initial_solution,
            )
        except ImportError as error:
            raise RuntimeError("Instalar el backend DW con uv sync --extra dw") from error
    if search_config is not None:
        raise ValueError("Las políticas de búsqueda requieren solver='scip-routes' o 'gcg'")
    started = monotonic()
    if initial_solution is not None:
        report = validate_solution(instance, initial_solution)
        if not report.feasible:
            raise ValueError(f"Solución inicial inválida: {report.violations}")
    deadline = started + config.time_limit_seconds
    outcome = SolveResult(requested_solver=config.solver, status="error")
    if initial_solution is not None:
        outcome.solution = initial_solution
        outcome.solution_source = "initial_solution"
    backend = None
    fallbacks: list[str] = []
    try:
        model = build_model(instance)
        remaining = max(0.0, deadline - monotonic())
        delivery_deadline = monotonic() + DELIVERY_BUDGET_FRACTION * remaining
        first, solution, backend = _run_phase(
            model, instance, config, "deliveries", delivery_deadline, backend, fallbacks,
            initial_solution,
        )
        if backend is not None:
            outcome.used_solver = backend.name
            outcome.solver_version = backend.version
        outcome.phases.append(first)
        outcome.solution = solution
        if solution is not None and first.incumbent_source != "provided_incumbent":
            outcome.solution_source = "solver"
        if solution is None:
            outcome.status = first.status
            outcome.message = first.message
            return outcome
        outcome.status = "feasible"
        activate_energy_phase(model, len(solution.served_visit_ids))
        second, candidate, backend = _run_phase(
            model, instance, config, "energy", deadline, backend, fallbacks,
            solution if initial_solution is not None else None,
        )
        outcome.phases.append(second)
        if candidate is not None:
            if len(candidate.served_visit_ids) != len(solution.served_visit_ids):
                second.status = "error"
                second.proven_optimal = False
                second.message += "; cambió el número fijado de entregas: se conserva la fase 1"
            elif candidate.net_energy_kwh <= solution.net_energy_kwh:
                outcome.solution = candidate
                if second.incumbent_source != "provided_incumbent":
                    outcome.solution_source = "solver"
            else:
                second.message += "; se conserva el incumbente de fase 1, de menor energía"
                if second.proven_optimal and not isclose(
                    candidate.net_energy_kwh, solution.net_energy_kwh, abs_tol=1e-7, rel_tol=0
                ):
                    second.proven_optimal = False
                    second.status = "error"
        outcome.lexicographic_optimal = first.proven_optimal and second.proven_optimal
        if outcome.lexicographic_optimal:
            outcome.status = "optimal"
            outcome.message = "Óptimo lexicográfico numérico para el modelo y H configurados."
        elif not first.proven_optimal:
            outcome.message = (
                "Incumbente factible; la fase energética está condicionada "
                "al cumplimiento encontrado, sin demostrar el máximo de entregas."
            )
        else:
            outcome.message = (
                "Máximo de entregas demostrado; sin certificado de energía mínima. "
                "Se conserva el mejor incumbente disponible."
            )
        return outcome
    except Exception as error:
        outcome.status = "feasible" if outcome.solution is not None else "error"
        outcome.message = f"Error de resolución ({type(error).__name__}); se conserva el incumbente."
        return outcome
    finally:
        outcome.fallback_reason = "; ".join(fallbacks) or None
        if backend is not None:
            outcome.used_solver = backend.name
            outcome.solver_version = backend.version
            backend.close()
        outcome.runtime_seconds = max(0.0, monotonic() - started)
