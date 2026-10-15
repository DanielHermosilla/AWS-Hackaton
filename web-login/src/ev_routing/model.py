from typing import Any, Dict, List

from pyomo.environ import (
    Binary,
    ConcreteModel,
    Constraint,
    NonNegativeReals,
    Objective,
    Reals,
    Set,
    Var,
    value,
)

from .contracts import ProblemInstance


def _energy_map(instance: ProblemInstance) -> Dict[tuple[str, str], float]:
    out: Dict[tuple[str, str], float] = {}
    for arc in instance.network.arcs:
        if not arc.allowed:
            continue
        key = (arc.origin, arc.destination)
        if key not in out:
            out[key] = float(arc.energy_kwh)
    return out


def build_model(instance: ProblemInstance) -> ConcreteModel:
    nodes = [n.node_id for n in instance.nodes]
    vehicles = list(range(instance.fleet.num_vehicles))
    H = instance.movement_limit
    R = list(range(H + 1))
    Rm = list(range(H))

    bases = instance.base_nodes()
    if len(bases) != 1:
        raise ValueError(f"expected exactly one base node, found {len(bases)}")
    base = bases[0]
    clients = instance.visit_nodes()
    chargers = instance.charger_nodes()

    capacity = float(instance.fleet.battery_capacity_kwh)
    reserve = float(instance.fleet.reserve_kwh)
    initial_energy = float(instance.fleet.initial_energy_kwh)

    energy = _energy_map(instance)
    arcs_list = list({(a.origin, a.destination) for a in instance.network.arcs if a.allowed})
    # ensure artificial (base,base) arc for inactivity/representation (PDF)
    if (base, base) not in arcs_list:
        arcs_list.append((base, base))
    energy.setdefault((base, base), 0.0)
    arcs_list = sorted(set(arcs_list))

    out_arcs: dict[str, list[tuple[str, str]]] = {n: [] for n in nodes}
    in_arcs: dict[str, list[tuple[str, str]]] = {n: [] for n in nodes}
    for (i, j) in arcs_list:
        out_arcs.setdefault(i, []).append((i, j))
        in_arcs.setdefault(j, []).append((i, j))

    max_abs_e = max((abs(v) for v in energy.values()), default=0.0)
    M = capacity + max_abs_e + 1.0

    # compatible chargers per vehicle
    compat_chargers = {k: instance.compatible_chargers(k) for k in vehicles}

    m = ConcreteModel()
    m.NODES = Set(initialize=nodes)
    m.VEHS = Set(initialize=vehicles)
    m.R = Set(initialize=R)
    m.RM = Set(initialize=Rm)
    m.ARCS = Set(initialize=arcs_list, dimen=2)
    m.CLIENTS = Set(initialize=clients)

    # Variables
    m.y = Var(m.CLIENTS, within=Binary)
    m.z = Var(m.NODES, m.VEHS, m.R, within=Binary)
    m.x = Var(m.ARCS, m.VEHS, m.RM, within=Binary)
    m.a = Var(m.CLIENTS, m.VEHS, m.RM, within=Binary)
    m.q = Var(m.VEHS, m.RM, within=NonNegativeReals, bounds=(0, capacity))
    m.b = Var(m.VEHS, m.R, within=Reals, bounds=(reserve, capacity))
    m.bbar = Var(m.VEHS, m.RM, within=Reals, bounds=(reserve, capacity))
    m.u = Var(m.VEHS, m.RM, within=Reals)
    m.E = Var(m.VEHS, m.RM, within=Reals)
    m.gamma = Var(m.VEHS, m.RM, within=Binary)
    m.Etotal = Var(within=Reals)

    # 1 location unique
    def loc_unique_rule(mm, k, r):
        return sum(mm.z[i, k, r] for i in nodes) == 1

    m.loc_unique = Constraint(m.VEHS, m.R, rule=loc_unique_rule)

    # 2 depot start/end
    def depot_start_rule(mm, k):
        return mm.z[base, k, 0] == 1

    def depot_end_rule(mm, k):
        return mm.z[base, k, H] == 1

    m.depot_start = Constraint(m.VEHS, rule=depot_start_rule)
    m.depot_end = Constraint(m.VEHS, rule=depot_end_rule)

    # 3/4 continuity
    def outflow_rule(mm, i, k, r):
        return sum(mm.x[arc, k, r] for arc in out_arcs.get(i, [])) == mm.z[i, k, r]

    def inflow_rule(mm, j, k, r):
        return sum(mm.x[arc, k, r] for arc in in_arcs.get(j, [])) == mm.z[j, k, r + 1]

    m.outflow = Constraint(m.NODES, m.VEHS, m.RM, rule=outflow_rule)
    m.inflow = Constraint(m.NODES, m.VEHS, m.RM, rule=inflow_rule)

    # deliveries: a <= z
    def delivery_link_rule(mm, i, k, r):
        return mm.a[i, k, r] <= mm.z[i, k, r]

    m.delivery_link = Constraint(m.CLIENTS, m.VEHS, m.RM, rule=delivery_link_rule)

    def delivery_count_rule(mm, i):
        return sum(mm.a[i, k, r] for k in vehicles for r in Rm) == mm.y[i]

    m.delivery_count = Constraint(m.CLIENTS, rule=delivery_count_rule)

    # battery initial
    def battery_init_rule(mm, k):
        return mm.b[k, 0] == initial_energy

    m.battery_init = Constraint(m.VEHS, rule=battery_init_rule)

    def q_init_rule(mm, k):
        return mm.q[k, 0] == 0

    # q indexed k,r; r=0 included in RM
    m.q_init = Constraint(m.VEHS, rule=q_init_rule)

    # recarga
    def recharge_balance_rule(mm, k, r):
        return mm.bbar[k, r] == mm.b[k, r] + mm.q[k, r]

    m.recharge_balance = Constraint(m.VEHS, m.RM, rule=recharge_balance_rule)

    def q_capacity_rule(mm, k, r):
        return mm.q[k, r] <= capacity - mm.b[k, r]

    m.q_capacity = Constraint(m.VEHS, m.RM, rule=q_capacity_rule)

    def q_charger_rule(mm, k, r):
        compatible = compat_chargers.get(k, [])
        if not compatible:
            return mm.q[k, r] <= 0
        lhs = mm.q[k, r]
        rhs = capacity * sum(mm.z[f, k, r] for f in compatible)
        return lhs <= rhs

    m.q_charger = Constraint(m.VEHS, m.RM, rule=q_charger_rule)

    # consumption u
    def energy_coeff(arc_key):
        return energy.get(arc_key, 0.0)

    def consumption_rule(mm, k, r):
        arc_term = sum(energy_coeff(arc) * mm.x[arc, k, r] for arc in arcs_list)
        return mm.u[k, r] == mm.bbar[k, r] - arc_term

    m.consumption = Constraint(m.VEHS, m.RM, rule=consumption_rule)

    # linearization min
    def dom1(mm, k, r):
        return mm.b[k, r + 1] <= mm.u[k, r]

    def dom2(mm, k, r):
        return mm.b[k, r + 1] <= capacity

    def lin1(mm, k, r):
        return mm.b[k, r + 1] >= mm.u[k, r] - M * mm.gamma[k, r]

    def lin2(mm, k, r):
        return mm.b[k, r + 1] >= capacity - M * (1 - mm.gamma[k, r])

    m.dom1 = Constraint(m.VEHS, m.RM, rule=dom1)
    m.dom2 = Constraint(m.VEHS, m.RM, rule=dom2)
    m.lin1 = Constraint(m.VEHS, m.RM, rule=lin1)
    m.lin2 = Constraint(m.VEHS, m.RM, rule=lin2)

    # E
    def E_rule(mm, k, r):
        return mm.E[k, r] == mm.bbar[k, r] - mm.b[k, r + 1]

    m.E_def = Constraint(m.VEHS, m.RM, rule=E_rule)

    def Etotal_rule(mm):
        return mm.Etotal == sum(mm.E[k, r] for k in vehicles for r in Rm)

    m.Etotal_def = Constraint(rule=Etotal_rule)

    # default objective minimize Etotal (phase 2 style)
    m.objective = Objective(expr=m.Etotal, sense=1)

    # attach for convenience
    m._instance = instance  # type: ignore[attr-defined]
    m._base = base  # type: ignore[attr-defined]
    return m


build_pyomo_model = build_model


def set_phase_objective(model: Any, phase: str, target_deliveries: int | None = None) -> None:
    # remove old objective
    try:
        model.del_component(model.objective)
    except Exception:
        pass
    clients = list(model.CLIENTS)
    if phase == "max_deliveries":
        expr = -sum(model.y[i] for i in clients)
    else:
        expr = model.Etotal
        if target_deliveries is not None:
            # fixed deliveries constraint added separately; still no objective change
            pass
    model.objective = Objective(expr=expr, sense=1)
    if phase == "min_energy" and target_deliveries is not None:
        # add (or replace) fixed delivery constraint
        if hasattr(model, "fixed_delivery"):
            model.del_component(model.fixed_delivery)
        model.fixed_delivery = Constraint(expr=sum(model.y[i] for i in clients) == target_deliveries)
