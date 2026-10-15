"""Callbacks de control sobre algoritmos nativos de GCG.

El observador de pricing nunca produce columnas, cotas ni certificados: devuelve
NOTAPPLICABLE y -infinito para que GCG ejecute sus solvers exactos/heurísticos.
Los cortes provienen exclusivamente de separadores GCG compatibles con columnas.
"""

from __future__ import annotations

from math import isfinite
from typing import Any

from pygcgopt import GCG_PRICINGSTATUS, PricingSolver
from pyscipopt import SCIP_EVENTTYPE, SCIP_RESULT, SCIP_STAGE, Eventhdlr
from pyscipopt.scip import Cutsel

from ev_routing.search_policy import SearchController


def _finite(value):
    return float(value) if isfinite(float(value)) and abs(value) < 1e19 else None


def master_statistics(master) -> dict[str, int]:
    # El problema original puede resolverse antes de comenzar el maestro.
    # SCIP rechaza consultas de iteraciones LP en etapa TRANSFORMED.
    searched = master.getStage() in (SCIP_STAGE.SOLVING, SCIP_STAGE.SOLVED)
    return {
        "master_variables": master.getNVars(),
        "master_rows": master.getNConss(),
        "branch_nodes": master.getNNodes() if searched else 0,
        "lp_iterations": master.getNLPIterations() if searched else 0,
        "native_cuts_applied": master.getNCutsApplied() if searched else 0,
    }


class CallbackState:
    def __init__(self, native, controller: SearchController, threads: int):
        self.native, self.controller, self.threads = native, controller, threads
        self.master = native.getMasterProb()
        self.applied_revision = -1
        self.changes: list[dict[str, Any]] = []
        self.errors: list[str] = []
        self.pricing_heuristic_calls = 0
        self.pricing_exact_calls = 0
        self.original_defaults = native.getParams()

    def snapshot(self) -> dict[str, Any]:
        statistics = master_statistics(self.master)
        return {
            **statistics,
            "nodes": statistics["branch_nodes"],
            "dual_bound": _finite(self.native.getDualbound()),
            "pricing_callbacks": self.controller.pricing_calls,
            "pricing_heuristic_callbacks": self.pricing_heuristic_calls,
            "pricing_exact_callbacks": self.pricing_exact_calls,
            "cut_candidates": self.controller.candidate_cuts,
            "policy_selected_cuts": self.controller.selected_cuts,
        }

    def apply_policy(self) -> None:
        c = self.controller
        if self.applied_revision == c.revision:
            return
        p = c.policy
        values = {}
        if c.active_policy != "standard":
            if p.pricing == "native":
                for key in (
                    "pricing/masterpricer/heurpricingiters",
                    "pricingsolver/mip/heurenabled",
                    "pricingsolver/mip/startnodelimit",
                ):
                    values[key] = self.original_defaults[key]
            else:
                values.update({
                    "pricing/masterpricer/heurpricingiters": int(p.pricing != "exact"),
                    "pricingsolver/mip/heurenabled": p.pricing != "exact",
                    "pricingsolver/mip/startnodelimit": p.pricing_heuristic_nodes,
                })
            values.update({
                "pricing/masterpricer/maxcolsroundredcostroot": p.columns_per_round,
                "pricing/masterpricer/maxcolsroundredcost": p.columns_per_round,
                "pricing/masterpricer/stabilization": p.stabilization,
            })
            if p.cut_family == "native":
                for key in ("sepa/original/enable", "sepa/basis/enable", "sepa/subsetrow/enable"):
                    values[key] = self.original_defaults[key]
            else:
                values.update({
                    "sepa/original/enable": True,
                    "sepa/basis/enable": p.cut_family == "original_basis",
                    "sepa/subsetrow/enable": False,
                })
        if not self.native.getParam("pricingsolver/mip/exactenabled"):
            raise RuntimeError("El pricing MIP exacto debe permanecer habilitado")
        for key, value in values.items():
            self.native.setParam(key, value)
        self.changes.append({
            "revision": c.revision, "phase": c.phase,
            "policy": p.model_dump(), "effective_parameters": values,
            "exact_pricing_enabled": True,
        })
        self.applied_revision = c.revision

    def tick(self, event: str) -> None:
        try:
            self.controller.observe(event, self.snapshot())
            self.apply_policy()
        except Exception as error:
            # No propagar excepciones a una frontera Cython noexcept.
            self.errors.append(type(error).__name__)
            self.master.interruptSolve()


class PricingObserver(PricingSolver):
    def __init__(self, state: CallbackState):
        self.state = state

    def _observe(self, pricingprob, *, heuristic: bool):
        state = self.state
        state.controller.pricing_calls += 1
        if heuristic:
            state.pricing_heuristic_calls += 1
        else:
            state.pricing_exact_calls += 1
        try:
            pricingprob.setIntParam("parallel/maxnthreads", state.threads)
            pricingprob.setIntParam("lp/threads", state.threads)
            pricingprob.setIntParam(
                "randomization/randomseedshift",
                state.native.getParam("randomization/randomseedshift"),
            )
        except Exception as error:
            state.errors.append(type(error).__name__)
            state.master.interruptSolve()
        state.tick("pricing")
        return {
            "status": GCG_PRICINGSTATUS.NOTAPPLICABLE,
            "lowerbound": -pricingprob.infinity(),
        }

    def solve(self, pricingprob, probnr, dualsolconv):
        return self._observe(pricingprob, heuristic=False)

    def solveHeuristic(self, pricingprob, probnr, dualsolconv):
        return self._observe(pricingprob, heuristic=True)


class PolicyCutSelector(Cutsel):
    def __init__(self, state: CallbackState):
        self.state = state

    def cutselselect(self, cuts, forcedcuts, root, maxnselectedcuts):
        state, c = self.state, self.state.controller
        c.cut_calls += 1
        c.candidate_cuts += len(cuts)
        state.tick("cut_selection")
        if c.active_policy == "standard" or c.policy.cut_selection == "native":
            return {"result": SCIP_RESULT.DIDNOTRUN}
        try:
            def score(cut):
                efficacy = state.master.getCutEfficacy(cut)
                if c.policy.cut_selection == "sparse":
                    return efficacy / max(1, cut.getNNonz()) ** 0.5
                return efficacy
            ordered = sorted(cuts, key=score, reverse=True)
            count = min(len(ordered), maxnselectedcuts, c.policy.max_selected_cuts)
            c.selected_cuts += count
            return {
                "cuts": ordered, "nselectedcuts": count, "result": SCIP_RESULT.SUCCESS,
            }
        except Exception as error:
            state.errors.append(type(error).__name__)
            state.master.interruptSolve()
            return {"result": SCIP_RESULT.DIDNOTRUN}


class ProgressEvents(Eventhdlr):
    def __init__(self, state: CallbackState):
        self.state = state

    def eventinit(self):
        self.model.catchEvent(SCIP_EVENTTYPE.LPSOLVED, self)

    def eventexit(self):
        self.model.dropEvent(SCIP_EVENTTYPE.LPSOLVED, self)

    def eventexec(self, event):
        self.state.tick("lp_solved")


def install_callbacks(native, controller: SearchController, threads: int) -> CallbackState:
    state = CallbackState(native, controller, threads)
    state.apply_policy()
    native.includePricingSolver(
        PricingObserver(state), "policy_observer",
        "Observe pricing, preserve native exact solvers and Farkas pricing",
        priority=1_000_000, heuristicEnabled=True, exactEnabled=True,
    )
    state.master.includeCutsel(
        PolicyCutSelector(state), "policy_cut_selector",
        "Rank native GCG-compatible optional cuts", priority=1_000_000,
    )
    state.master.includeEventhdlr(
        ProgressEvents(state), "policy_progress", "Poll validated search policy",
    )
    return state
