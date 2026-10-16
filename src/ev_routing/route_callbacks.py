"""Adaptadores SCIP: todos los accesos nativos ocurren en el hilo de optimize()."""

from __future__ import annotations

from collections import Counter
from itertools import combinations, islice
from math import isfinite
from time import monotonic

from pyscipopt import (
    SCIP_EVENTTYPE,
    SCIP_HEURTIMING,
    SCIP_RESULT,
    SCIP_STAGE,
    Branchrule,
    Eventhdlr,
    Heur,
    Model,
    Nodesel,
    Sepa,
    quicksum,
)


class CallbackHub:
    def __init__(self, model, head, phase, deadline, instance, *, z=None, pricer=None,
                 target_deliveries=None):
        self.model, self.head, self.phase = model, head, phase
        self.deadline, self.instance = deadline, instance
        self.z, self.pricer = z or {}, pricer
        self.target_deliveries = target_deliveries
        self.counts, self.revisions, self.native_changes = Counter(), Counter(), []
        self.errors, self.last_observed, self.last_revision = [], 0.0, -1
        self.metadata = {v.name: instance.customer_ids[i] for (_, i), v in self.z.items()}
        degrees = Counter(a.to_node_id for a in instance.arcs)
        self.scarcity = {i: 1 / max(1, degrees[i]) for i in instance.customer_ids}

    @property
    def policy(self):
        return self.head.policy

    def observe(self, event, extra=None):
        self.counts[event] += 1
        self.head.collect()
        self.revisions[str(self.head.revision)] += 1
        if monotonic() - self.last_observed < .05:
            return
        self.last_observed = monotonic()
        state = {"phase": self.phase, "callbacks": dict(self.counts), **(extra or {})}
        if self.model.getStage() == SCIP_STAGE.SOLVING:
            def finite(value):
                return value if isfinite(value) and abs(value) < self.model.infinity() else None
            state.update(
                nodes=self.model.getNNodes(), depth=self.model.getDepth(),
                lp_solves=self.model.getNLPs(),
                restricted_primal=finite(self.model.getPrimalbound()),
                restricted_dual_not_global_certificate=finite(self.model.getDualbound()),
                solutions=self.model.getNSols(),
            )
        if self.pricer is not None:
            state.update(
                columns=len(self.pricer.columns), pricing_calls=self.pricer.calls,
                labels=self.pricer.dual_labels, completion_bound_prunes=self.pricer.bound_prunes,
                customer_duals=self.pricer.last_rewards,
            )
            if self.pricer.heuristics is not None:
                state.update(self.pricer.heuristics.telemetry())
            best = self.model.getBestSol()
            if best is not None:
                state["incumbent_routes"] = [
                    {"vehicle": k, "weight": self.model.getSolVal(best, var),
                     "customers": [i for step in route.steps for i in step.delivered_visit_ids],
                     "energy_kwh": route.net_energy_kwh,
                     "charging_stops": sum(step.charged_to_battery_kwh > 1e-9
                                           for step in route.steps)}
                    for k, _, route, var in self.pricer.columns
                    if self.model.getSolVal(best, var) > 1e-6
                ]
        self.head.decide(event, state)
        if self.last_revision != self.head.revision and self.model.getStage() == SCIP_STAGE.SOLVING:
            self.last_revision = self.head.revision
            for name, value in self.policy.scip_parameters.items():
                # Otros parámetros se aplican al construir el siguiente maestro.
                if not (name.startswith(("branching/", "nodeselection/")) or
                        name.startswith("heuristics/") and name.endswith("/freq")):
                    continue
                try:
                    previous = self.model.getParam(name)
                    if previous != value:
                        self.model.setParam(name, value)
                        self.native_changes.append({"name": name, "before": previous, "after": value,
                                                    "revision": self.head.revision})
                except (ValueError, LookupError):
                    self.native_changes.append({"name": name, "status": "deferred_to_next_master"})

    def fail(self, error):
        self.errors.append(type(error).__name__)
        if self.pricer:
            self.pricer.incomplete = True
            self.pricer.error = type(error).__name__
        self.model.interruptSolve()

    def report(self):
        return {"callbacks": dict(self.counts), "callbacks_by_policy_revision": dict(self.revisions),
                "runtime_parameter_changes": self.native_changes, "errors": self.errors}


class SearchEvents(Eventhdlr):
    def __init__(self, hub):
        self.hub = hub
        self.events = SCIP_EVENTTYPE.BESTSOLFOUND | SCIP_EVENTTYPE.NODEFOCUSED | SCIP_EVENTTYPE.LPSOLVED

    def eventinit(self):
        self.model.catchEvent(self.events, self)

    def eventexit(self):
        self.model.dropEvent(self.events, self)

    def eventexec(self, event):
        try:
            kind = event.getType()
            name = ("new_incumbent" if kind & SCIP_EVENTTYPE.BESTSOLFOUND else
                    "tree_node" if kind & SCIP_EVENTTYPE.NODEFOCUSED else "lp_solved")
            self.hub.observe(name)
        except Exception as error:
            self.hub.fail(error)


class CustomerBranching(Branchrule):
    def __init__(self, hub):
        self.hub = hub

    def branchexeclp(self, allowaddcons):
        try:
            self.hub.observe("branching")
            policy = self.hub.policy
            if policy.tree_branching == "native":
                return {"result": SCIP_RESULT.DIDNOTRUN}
            variables, values, fractions, count, priority, _ = self.model.getLPBranchCands()
            candidates = []
            focus = set(policy.focus_customers)
            for var, fraction in zip(variables[:priority or count], fractions[:priority or count]):
                customer = self.hub.metadata.get(var.name.removeprefix("t_"))
                if customer is None:
                    continue
                score = min(fraction, 1-fraction)
                if policy.tree_branching in {"resource", "llm_priority"}:
                    score *= 1 + self.hub.scarcity.get(customer, 0)
                if policy.tree_branching == "llm_priority" and customer in focus:
                    score += 1
                candidates.append((score, var.name, var))
            if not candidates:
                return {"result": SCIP_RESULT.DIDNOTRUN}
            self.model.branchVar(max(candidates, key=lambda row: row[:2])[2])
            self.hub.counts["customer_branches"] += 1
            return {"result": SCIP_RESULT.BRANCHED}
        except Exception as error:
            self.hub.fail(error)
            return {"result": SCIP_RESULT.DIDNOTRUN}


class SearchNodes(Nodesel):
    def __init__(self, hub):
        self.hub = hub

    def nodeselect(self):
        try:
            self.hub.observe("node_selection")
            mode = self.hub.policy.node_selection
            node = None
            if mode == "depth_first" or mode == "hybrid" and self.model.getNNodes() % 5:
                node = self.model.getPrioChild()
            return {"selnode": node or self.model.getBestboundNode()}
        except Exception as error:
            self.hub.fail(error)
            return {"selnode": self.model.getBestboundNode()}

    def nodecomp(self, first, second):
        if self.hub.policy.node_selection == "depth_first":
            a, b = (-first.getDepth(), first.getLowerbound()), (-second.getDepth(), second.getLowerbound())
        else:
            a, b = (first.getLowerbound(), -first.getDepth()), (second.getLowerbound(), -second.getDepth())
        return -1 if a < b else int(a > b)


class SubsetRows(Sepa):
    def __init__(self, hub):
        self.hub = hub

    def sepaexeclp(self):
        try:
            self.hub.observe("separation")
            policy, pricer = self.hub.policy, self.hub.pricer
            if policy.route_cuts != "subset_row_triples" or len(pricer.cuts) >= policy.max_subset_rows:
                return {"result": SCIP_RESULT.DIDNOTRUN}
            active = [(mask, self.model.getSolVal(None, var))
                      for _, mask, _, var in pricer.columns]
            active = [(mask, value) for mask, value in active if value > 1e-8]
            scores = Counter()
            for mask, value in active:
                for i in range(len(self.hub.instance.customer_ids)):
                    if mask & (1 << i):
                        scores[i] += min(value, 1-value)
            ranked = sorted(scores, key=lambda i: (-scores[i], i))
            existing = {mask for mask, _ in pricer.cuts}
            added = 0
            for triple in islice(combinations(ranked, 3), policy.cut_candidates):
                mask = sum(1 << i for i in triple)
                if mask in existing:
                    continue
                activity = sum(value * ((served & mask).bit_count() // 2) for served, value in active)
                if activity <= 1 + self.model.feastol():
                    continue
                cons = self.model.addCons(
                    quicksum(((served & mask).bit_count() // 2) * var
                             for _, served, _, var in pricer.columns) <= 1,
                    name=f"subset_dynamic_{len(pricer.cuts)}", modifiable=True,
                    removable=False,
                )
                pricer.cuts.append((mask, cons))
                existing.add(mask)
                added += 1
                if added >= policy.cut_batch or len(pricer.cuts) >= policy.max_subset_rows:
                    break
            self.hub.counts["dynamic_subset_rows"] += added
            return {"result": SCIP_RESULT.CONSADDED if added else SCIP_RESULT.DIDNOTFIND}
        except Exception as error:
            self.hub.fail(error)
            return {"result": SCIP_RESULT.DIDNOTRUN}


class RouteRecombination(Heur):
    """Sub-MIP del pool; nunca transfiere su cota al problema completo."""

    def __init__(self, hub):
        self.hub = hub

    def heurexec(self, heurtiming, nodeinfeasible):
        sub = None
        try:
            self.hub.observe("route_recombination")
            policy, pricer = self.hub.policy, self.hub.pricer
            if (nodeinfeasible or policy.callback_repair_seconds == 0 or
                self.hub.counts["route_recombination"] % policy.callback_frequency != 1 % policy.callback_frequency):
                return {"result": SCIP_RESULT.DIDNOTRUN}
            seconds = min(policy.callback_repair_seconds, self.hub.deadline-monotonic())
            if seconds <= .002:
                return {"result": SCIP_RESULT.DIDNOTRUN}
            sub = Model("route_pool_repair")
            sub.hideOutput()
            sub.setIntParam("parallel/maxnthreads", 1)
            sub.setIntParam("lp/threads", 1)
            sub.setRealParam("limits/time", seconds)
            # A 200-customer pool spent minutes flattening its multi-aggregation
            # graph inside presolve, beyond this heuristic's subsecond budget.
            # This optional primal subproblem needs predictable latency.
            sub.setBoolParam("presolving/donotmultaggr", True)
            sub.setIntParam("presolving/maxrounds", 0)
            choices = []
            for k, mask, route, var in pricer.columns[-policy.pricing_pool_limit:]:
                if var.getUbLocal() <= 0:
                    continue
                permitted = all(
                    (not mask & (1 << i) or z.getUbLocal() > .5)
                    and (mask & (1 << i) or z.getLbLocal() < .5)
                    for (vehicle, i), z in self.hub.z.items() if vehicle == k
                )
                if permitted:
                    choice = sub.addVar(vtype="B", obj=(
                        -mask.bit_count() if self.hub.phase == "deliveries" else route.net_energy_kwh
                    ))
                    choices.append((k, mask, var, choice))
            for k in self.hub.instance.vehicle_ids:
                sub.addCons(quicksum(x for vehicle, _, _, x in choices if vehicle == k) == 1)
            for i in range(len(self.hub.instance.customer_ids)):
                sub.addCons(quicksum(x for _, mask, _, x in choices if mask & (1 << i)) <= 1)
            if self.hub.phase == "energy":
                sub.addCons(quicksum(mask.bit_count() * x for _, mask, _, x in choices)
                            == self.hub.target_deliveries)
            sub.optimizeNogil()
            self.hub.counts["recombination_submips"] += 1
            if sub.getNSols() == 0:
                return {"result": SCIP_RESULT.DIDNOTFIND}
            solution = self.model.createSol(self)
            selected = [(k, mask, var) for k, mask, var, x in choices if sub.getVal(x) > .5]
            for k, mask, var in selected:
                self.model.setSolVal(solution, var, 1)
                for (vehicle, i), z in self.hub.z.items():
                    if vehicle == k:
                        self.model.setSolVal(solution, z, int(bool(mask & (1 << i))))
            accepted = self.model.trySol(solution, printreason=False, completely=True)
            self.hub.counts["recombination_accepted"] += int(accepted)
            return {"result": SCIP_RESULT.FOUNDSOL if accepted else SCIP_RESULT.DIDNOTFIND}
        except Exception as error:
            self.hub.fail(error)
            return {"result": SCIP_RESULT.DIDNOTRUN}
        finally:
            if sub is not None:
                sub.freeProb()


def install_callbacks(model, head, phase, deadline, instance, *, z=None, pricer=None,
                      target_deliveries=None):
    hub = CallbackHub(model, head, phase, deadline, instance, z=z, pricer=pricer,
                      target_deliveries=target_deliveries)
    model.includeEventhdlr(SearchEvents(hub), "llm_events", "Budgeted asynchronous search telemetry")
    model.includeNodesel(SearchNodes(hub), "llm_nodes", "Validated node selection policy", 2000000, 2000000)
    if z:
        model.includeBranchrule(CustomerBranching(hub), "llm_customers", "Resource-aware customer branching",
                                2000000, -1, 1.0)
    if pricer:
        model.includeSepa(SubsetRows(hub), "llm_subset_rows", "Future-column-compatible subset rows",
                          priority=1000000, freq=1)
        model.includeHeur(
            RouteRecombination(hub), "llm_route_repair", "Finite-pool SCIP primal repair", "R",
            priority=1000000, freq=1,
            timingmask=(SCIP_HEURTIMING.DURINGPRICINGLOOP | SCIP_HEURTIMING.AFTERLPLOOP |
                        SCIP_HEURTIMING.AFTERLPNODE), usessubscip=True,
        )
        pricer.hub = hub
    return hub
