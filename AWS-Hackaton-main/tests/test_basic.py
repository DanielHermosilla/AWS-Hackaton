from ev_routing.contracts import Node, NodeType, FleetConfig, Arc, Network, ProblemInstance
from ev_routing.solve import run_pipeline
from ev_routing.contracts import SolverConfig
from ev_routing.validation import validate_run_result


def make_instance():
    nodes = [
        Node(node_id="B", node_type=NodeType.BASE, latitude=0, longitude=0),
        Node(node_id="V1", node_type=NodeType.VISIT, latitude=0.01, longitude=0),
        Node(node_id="C1", node_type=NodeType.CHARGER, latitude=0.005, longitude=0, total_ports=1),
    ]
    arcs = [
        Arc(origin="B", destination="V1", energy_kwh=2),
        Arc(origin="V1", destination="B", energy_kwh=1.5),
        Arc(origin="B", destination="C1", energy_kwh=0.5),
        Arc(origin="C1", destination="B", energy_kwh=0.4),
        Arc(origin="V1", destination="C1", energy_kwh=0.8),
        Arc(origin="C1", destination="V1", energy_kwh=0.7),
    ]
    net = Network(nodes=["B", "V1", "C1"], arcs=arcs, directed=True, provenance="test")
    return ProblemInstance(nodes=nodes, fleet=FleetConfig(num_vehicles=1, battery_capacity_kwh=10, reserve_kwh=1, initial_soc=0.6), network=net, movement_limit=4)


def test_basic_solve():
    inst = make_instance()
    res = run_pipeline(inst, SolverConfig(time_limit_seconds=30))
    assert res.served_count == 1
    assert res.validation is not None
    assert res.validation.feasible
    vr = validate_run_result(inst, res)
    assert vr.feasible, vr.violations
