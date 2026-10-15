"""El perfil futuro de tuning es local, no muta el modelo y no invoca AWS."""

import json
import socket
import sys
from types import SimpleNamespace

import pyomo.environ as pyo
import pytest

from ev_routing.contracts import SolverConfig
from ev_routing.llm.tuning import build_tuning_request, propose_tuning


@pytest.fixture(autouse=True)
def forbid_network_and_aws(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("El esqueleto de tuning no debe abrir conexiones ni clientes AWS")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=forbidden, Session=forbidden))


@pytest.fixture
def model():
    result = pyo.ConcreteModel(name="dirección privada que no debe enviarse")
    result.x = pyo.Var(["a", "b"], domain=pyo.Binary)
    result.energy = pyo.Var(bounds=(-10, 24), initialize=3)
    result.service = pyo.Constraint(expr=result.x["a"] + result.x["b"] <= 1)
    result.energy_balance = pyo.Constraint(expr=result.energy == result.x["a"])
    result.inactive = pyo.Constraint(expr=result.energy <= 5)
    result.inactive.deactivate()
    result.objective = pyo.Objective(expr=result.energy)
    result.hidden = pyo.Block()
    result.hidden.variable = pyo.Var(domain=pyo.Binary)
    result.hidden.constraint = pyo.Constraint(expr=result.hidden.variable <= 1)
    result.hidden.deactivate()
    result.private_address = "Calle privada 123"
    return result


def snapshot(model):
    return [
        (
            item.name,
            item.active,
            str(getattr(item, "expr", None)),
            str(getattr(item, "domain", None)),
            getattr(item, "value", None),
        )
        for item in model.component_data_objects(active=None, descend_into=True)
    ]


def test_profile_counts_active_structure_without_disclosing_names_or_addresses(model):
    request = build_tuning_request(model, SolverConfig(solver="scip", threads=2))
    assert request["variable_count"] == 3
    assert request["binary_variable_count"] == 2
    assert request["constraint_count"] == 2
    assert request["status"] == "disabled"
    assert request["allowed_parameters"] == {}
    assert request["solver_config"]["solver"] == "scip"
    serialized = json.dumps(request, ensure_ascii=False, allow_nan=False)
    assert model.name not in serialized
    assert model.private_address not in serialized
    assert "energy_balance" not in serialized


def test_building_profile_preserves_values_domains_constraints_and_objective(model):
    before = snapshot(model)
    build_tuning_request(model, SolverConfig())
    assert snapshot(model) == before
    assert model.objective.active
    assert not model.inactive.active
    assert not model.hidden.active


def test_profile_reflects_current_active_phase_without_activating_components(model):
    before = build_tuning_request(model, SolverConfig())
    model.inactive.activate()
    after = build_tuning_request(model, SolverConfig())
    assert after["constraint_count"] == before["constraint_count"] + 1
    assert after["variable_count"] == before["variable_count"]
    assert after["allowed_parameters"] == {}


def test_profile_does_not_share_solver_config_mutable_storage(model):
    config = SolverConfig(threads=2, time_limit_seconds=19, relative_gap=0.1)
    request = build_tuning_request(model, config)
    request["solver_config"]["threads"] = 999
    request["allowed_parameters"]["movement_limit"] = 1
    assert config.threads == 2
    next_request = build_tuning_request(model, config)
    assert next_request["solver_config"]["threads"] == 2
    assert next_request["allowed_parameters"] == {}


@pytest.mark.parametrize(
    "proposal_request",
    [
        {},
        {"status": "enabled", "model_id": "arbitrary"},
        {"parameters": {"movement_limit": 1, "reserve_kwh": 0}},
        {"code": "__import__('boto3').client('bedrock-runtime')"},
    ],
)
def test_proposals_remain_explicitly_unimplemented_for_every_input(proposal_request):
    with pytest.raises(NotImplementedError, match="LLM desactivado.*no se realizan llamadas"):
        propose_tuning(proposal_request)
