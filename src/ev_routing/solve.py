"""Resolución lexicográfica con presupuesto compartido y backends explícitos.

El adaptador consume la plantilla del PDF. No cambia tolerancias físicas,
restricciones ni objetivos, y no utiliza un LLM. La validación independiente de
las rutas corresponde a ``validation.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isclose
from time import monotonic
from typing import Any

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


def _solve_phase(
    model: pyo.ConcreteModel,
    instance: ProblemInstance,
    config: SolverConfig,
    backend: _Backend,
    name: str,
    seconds: float,
) -> tuple[PhaseResult, Solution | None]:
    _set_options(backend, config, seconds)
    try:
        results = backend.solver.solve(model, load_solutions=False, tee=config.tee)
    except Exception as error:
        reason = _unavailable_reason(error, backend.name)
        if reason is not None:
            raise _BackendUnavailable(reason) from error
        return _empty_phase(
            name, "error", "error", f"{backend.name}: error de solver ({type(error).__name__})"
        ), None
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
            return _empty_phase(
                name,
                "error",
                str(termination),
                f"{message}; no se pudo extraer un incumbente completo ({type(error).__name__})",
            ), None
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
    ), solution


def _run_phase(
    model: pyo.ConcreteModel,
    instance: ProblemInstance,
    config: SolverConfig,
    name: str,
    deadline: float,
    backend: _Backend | None,
    fallbacks: list[str],
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
            phase, solution = _solve_phase(model, instance, config, backend, name, remaining)
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
    phase.runtime_seconds = max(0.0, monotonic() - started)
    return phase, solution, backend


def solve_instance(instance: ProblemInstance, config: SolverConfig) -> SolveResult:
    """Resolver (16) en dos fases y conservar el mejor incumbente extraído.

    ``auto`` permite fallback Gurobi -> SCIP solo por disponibilidad/licencia.
    Elegir un solver explícitamente fija el backend para una comparación.
    El presupuesto total incluye construcción, intentos fallidos y extracción;
    los límites de los backends son blandos y pueden excederse por sobrecostos.
    """
    started = monotonic()
    deadline = started + config.time_limit_seconds
    outcome = SolveResult(requested_solver=config.solver, status="error")
    backend = None
    fallbacks: list[str] = []
    try:
        model = build_model(instance)
        remaining = max(0.0, deadline - monotonic())
        delivery_deadline = monotonic() + DELIVERY_BUDGET_FRACTION * remaining
        first, solution, backend = _run_phase(
            model, instance, config, "deliveries", delivery_deadline, backend, fallbacks
        )
        if backend is not None:
            outcome.used_solver = backend.name
            outcome.solver_version = backend.version
        outcome.phases.append(first)
        outcome.solution = solution
        if solution is None:
            outcome.status = first.status
            outcome.message = first.message
            return outcome
        outcome.status = "feasible"
        activate_energy_phase(model, len(solution.served_visit_ids))
        second, candidate, backend = _run_phase(
            model, instance, config, "energy", deadline, backend, fallbacks
        )
        outcome.phases.append(second)
        if candidate is not None:
            if len(candidate.served_visit_ids) != len(solution.served_visit_ids):
                second.status = "error"
                second.proven_optimal = False
                second.message += "; cambió el número fijado de entregas: se conserva la fase 1"
            elif candidate.net_energy_kwh <= solution.net_energy_kwh:
                outcome.solution = candidate
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
                "Solución factible del solver; la fase energética está condicionada "
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
