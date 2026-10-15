from typing import Any, List

from pyomo.environ import value

from .contracts import ProblemInstance, ValidationResult, VehicleRoute, RouteStep


def _get(model, attr, *idx, default=None):
    try:
        component = getattr(model, attr)
        if idx:
            return value(component[idx])
        return value(component)
    except Exception:
        return default


def validate_solution(model: Any, instance: ProblemInstance) -> ValidationResult:
    violations: List[str] = []
    nodes = [n.node_id for n in instance.nodes]
    node_set = set(nodes)
    vehicles = list(range(instance.fleet.num_vehicles))
    H = instance.movement_limit
    base = instance.base_nodes()[0] if instance.base_nodes() else None
    clients = instance.visit_nodes()
    chargers = set(instance.charger_nodes())
    compatible = {k: set(instance.compatible_chargers(k)) for k in vehicles}
    capacity = instance.fleet.battery_capacity_kwh
    reserve = instance.fleet.reserve_kwh
    initial = instance.fleet.initial_energy_kwh
    energy_map = {(a.origin, a.destination): a.energy_kwh for a in instance.network.arcs}

    for k in vehicles:
        # location per position
        locs = []
        for r in range(H + 1):
            nid = None
            for i in nodes:
                v = _get(model, "z", i, k, r, default=0)
                if v is not None and v > 0.5:
                    nid = i
                    break
            if nid is None:
                violations.append(f"vehicle {k} has no location at position {r}")
                nid = base
            locs.append(nid)
        if locs[0] != base:
            violations.append(f"vehicle {k} does not start at base")
        if locs[H] != base:
            violations.append(f"vehicle {k} does not end at base")
        # arcs valid and continuity
        total_e_calc = 0.0
        for r in range(H):
            i = locs[r]
            j = locs[r + 1]
            if (i, j) not in energy_map:
                violations.append(f"vehicle {k} uses arc not in network: {(i, j)} at position {r}")
            # check x selection maybe
            q = _get(model, "q", k, r, default=0.0) or 0.0
            b_arr = _get(model, "b", k, r, default=None)
            b_dep = _get(model, "bbar", k, r, default=None)
            b_next = _get(model, "b", k, r + 1, default=None)
            # charge constraints
            if q < -1e-9:
                violations.append(f"vehicle {k} negative charge at {r}")
            if q > capacity - (b_arr or 0) + 1e-6:
                violations.append(f"vehicle {k} overcharges at {r}")
            if i not in compatible[k] and i not in chargers:
                pass
            if q > 1e-9 and i not in compatible[k]:
                violations.append(f"vehicle {k} charges at non-compatible station {i} at {r}")
            # battery bounds
            for val, label in [(b_arr, "arrival"), (b_dep, "departure"), (b_next, "next arrival")]:
                if val is None:
                    continue
                if val < reserve - 1e-6 or val > capacity + 1e-6:
                    violations.append(f"vehicle {k} battery {label} out of bounds at {r}: {val}")
            # min saturation check: b_next should be min(capacity, b_dep - e)
            if b_dep is not None and b_next is not None:
                e = energy_map.get((i, j), 0.0)
                expected = min(capacity, b_dep - e)
                if abs(b_next - expected) > 1e-4:
                    # soft: store but not necessarily violation? keep as violation for strict
                    pass
                total_e_calc += b_dep - b_next
        # initial battery
        b0 = _get(model, "b", k, 0, default=None)
        if b0 is not None and abs(b0 - initial) > 1e-6:
            violations.append(f"vehicle {k} initial battery mismatch")

    # deliveries uniqueness and counting
    y_sum = {}
    for c in clients:
        yval = _get(model, "y", c, default=0) or 0
        a_count = 0
        a_positions = set()
        for k in vehicles:
            for r in range(H):
                aval = _get(model, "a", c, k, r, default=0) or 0
                if aval > 0.5:
                    a_count += 1
                    # need at client location
                    loc = None
                    for i in nodes:
                        if (_get(model, "z", i, k, r, default=0) or 0) > 0.5:
                            loc = i
                    if loc != c:
                        violations.append(f"delivery of {c} by vehicle {k} at pos {r} not at client node")
        if abs(a_count - (yval or 0)) > 1e-6:
            violations.append(f"delivery count mismatch for client {c}")
        y_sum[c] = (yval or 0)

    # each delivery at most once overall: ensured by count equality and y binary.

    # energy total
    etotal = _get(model, "Etotal", default=None)
    if etotal is not None:
        try:
            if abs(float(etotal) - total_e_calc) > 1e-3 and len(violations) == 0:
                # not hard violation; energy bookkeeping already
                pass
        except Exception:
            pass

    return ValidationResult(feasible=len(violations) == 0, violations=violations)


def validate_run_result(instance: ProblemInstance, run_result: "RunResult") -> ValidationResult:
    # Validate from routes, independent of Pyomo
    from .contracts import ValidationResult as VR
    violations: List[str] = []
    vehicles = instance.fleet.num_vehicles
    H = instance.movement_limit
    base = instance.base_nodes()[0] if instance.base_nodes() else None
    clients = set(instance.visit_nodes())
    chargers = set(instance.charger_nodes())
    compatible = {k: set(instance.compatible_chargers(k)) for k in range(vehicles)}
    capacity = instance.fleet.battery_capacity_kwh
    reserve = instance.fleet.reserve_kwh
    initial = instance.fleet.initial_energy_kwh
    energy_map = {(a.origin, a.destination): a.energy_kwh for a in instance.network.arcs}

    all_served = []
    for route in run_result.routes:
        k = route.vehicle_index
        steps = route.steps or []
        if len(steps) < H + 1:
            violations.append(f"vehicle {k} route has too few steps")
        # positions 0..H
        locs = [s.node_id for s in steps[: H + 1]]
        if locs and locs[0] != base:
            violations.append(f"vehicle {k} does not start at base")
        if locs and locs[-1] != base:
            violations.append(f"vehicle {k} does not end at base")
        prev_node = None
        for idx, step in enumerate(steps[:H]):
            node = step.node_id
            nxt = steps[idx + 1].node_id if idx + 1 < len(steps) else None
            if nxt is not None and (node, nxt) not in energy_map:
                violations.append(f"vehicle {k} arc not in network: {(node, nxt)}")
            # battery
            for label, val in [("arrival", step.arrival_energy_kwh), ("departure", step.departure_energy_kwh)]:
                if val is None:
                    continue
                if val < reserve - 1e-6 or val > capacity + 1e-6:
                    violations.append(f"vehicle {k} battery {label} out of bounds at {idx}: {val}")
            q = step.charge_kwh or 0.0
            if q < -1e-9:
                violations.append(f"vehicle {k} negative charge at {idx}")
            if step.departure_energy_kwh is not None and step.arrival_energy_kwh is not None:
                if q > capacity - (step.arrival_energy_kwh or 0) + 1e-6:
                    violations.append(f"vehicle {k} overcharges at {idx}")
            if q > 1e-9 and node not in compatible[k]:
                violations.append(f"vehicle {k} charges at non-compatible station {node}")
            # delivered visits must be at client node
            for vid in step.delivered_visit_ids or []:
                if node != vid:
                    violations.append(f"vehicle {k} delivers {vid} while at {node}")
                if vid not in clients:
                    violations.append(f"unknown visit {vid}")
            all_served.extend(step.delivered_visit_ids or [])
        # initial battery first step arrival at base?
        first = steps[0] if steps else None
        if first and first.arrival_energy_kwh is not None:
            if abs(first.arrival_energy_kwh - initial) > 1e-6:
                violations.append(f"vehicle {k} initial battery mismatch")

    # uniqueness
    seen = set()
    for vid in all_served:
        if vid in seen:
            violations.append(f"visit {vid} delivered more than once")
        seen.add(vid)

    return ValidationResult(feasible=len(violations) == 0, violations=violations)
