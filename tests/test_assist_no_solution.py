"""Assistant summaries distinguish missing incumbents from valid empty plans."""

from copy import deepcopy

import pytest

from ev_routing.assist import Asistente, Sesion
from ev_routing.assist.assistant import _resumen_plan
from ev_routing.assist.explainer import explicar
from ev_routing.assist.facts import extraer_hechos


NO_SOLUTION = {
    "status": "no_solution",
    "solve": {
        "status": "time_limit",
        "solution": None,
        "phases": [{
            "name": "deliveries", "sense": "maximize", "status": "time_limit",
            "proven_optimal": False, "incumbent": None, "best_bound": 5,
            "relative_gap": None, "runtime_seconds": 2,
        }],
    },
    "validation": {"feasible": None},
    "kpis": {"served_deliveries": None, "total_deliveries": 5},
}

EMPTY_PLAN = {
    "status": "ok",
    "solve": {
        "status": "feasible",
        "lexicographic_optimal": False,
        "solution": {
            "served_visit_ids": [],
            "unserved_visit_ids": ["C1", "C2", "C3", "C4", "C5"],
            "net_energy_kwh": 0,
            "routes": [{
                "vehicle_id": "V1",
                "steps": [{"node_id": "BASE", "delivered_visit_ids": [],
                           "charged_to_battery_kwh": 0}],
            }],
        },
    },
    "validation": {"feasible": True},
}


def test_missing_incumbent_keeps_counts_unknown_and_phase_bound_available():
    facts = extraer_hechos(NO_SOLUTION)
    summary = _resumen_plan(NO_SOLUTION)

    assert facts.hay_solucion is False
    assert facts.a_dict()["hay_solucion"] is False
    assert summary["hay_solucion"] is False
    assert summary["entregas"] is None
    assert summary["paradas_recarga"] is None
    assert summary["vehiculos_usados"] is None
    assert summary["energia_kwh"] is None
    assert summary["sin_atender"] == []  # IDs remain a compatible list, not a count.
    assert summary["fases"][0]["cota"] == 5
    assert summary["fases"][0]["incumbente"] is None
    assert summary["fases"][0]["gap_relativo"] is None
    assert summary["fases"][0]["optima_probada"] is False


def test_missing_incumbent_explanation_does_not_invent_completed_deliveries():
    text = explicar(NO_SOLUTION).texto

    assert "No se encontro una solucion" in text
    assert "no disponibles" in text
    assert "Se atendieron 0" not in text
    assert "no quedaron entregas pendientes" not in text
    assert "optimalidad no probada" in text
    assert "gap relativo reportado 0" not in text


def test_local_solve_without_incumbent_does_not_offer_a_ready_plan():
    assistant = Asistente(Sesion(resolutor=lambda cfg: deepcopy(NO_SOLUTION)))

    response = assistant.turno("calcula")

    assert response.resolvio is True  # The calculation ran and remains available.
    assert "No se encontro una solucion" in response.respuesta
    assert "Plan listo" not in response.respuesta
    assert "0 entregas" not in response.respuesta
    assert "0 recarga" not in response.respuesta
    assert "No se encontro una solucion" in assistant._sistema()
    assert "None entregas" not in assistant._sistema()


@pytest.mark.parametrize("candidate", [False, True])
def test_unavailable_plan_uses_diagnostic_without_remote_rewording(candidate):
    class UnexpectedClient:
        def conversar(self, *args, **kwargs):
            raise AssertionError("An unavailable plan needs the deterministic diagnostic.")

    result = deepcopy(EMPTY_PLAN if candidate else NO_SOLUTION)
    if candidate:
        result["validation"]["feasible"] = False
    explanation = explicar(result, cliente=UnexpectedClient())

    assert explanation.fuente == "plantilla"
    assert "no disponibles" in explanation.texto
    assert "Se atendieron" not in explanation.texto


def test_valid_empty_plan_keeps_legitimate_zero_counts_without_optimality_claim():
    summary = _resumen_plan(EMPTY_PLAN)
    assistant = Asistente(Sesion(resolutor=lambda cfg: deepcopy(EMPTY_PLAN)))

    assert summary["hay_solucion"] is True
    assert summary["entregas"] == 0
    assert summary["paradas_recarga"] == 0
    assert summary["vehiculos_usados"] == 0
    assert summary["energia_kwh"] == 0
    assert "Se atendieron 0 entregas; quedaron 5 sin atender." in summary["resumen"]
    assert "optima (lexicografica)" not in summary["resumen"]
    response = assistant.turno("calcula")
    assert "Plan listo: 0 entregas, 5 sin atender, 0 recarga(s)" in response.respuesta


@pytest.mark.parametrize("feasible", [False, None])
def test_unvalidated_candidate_is_not_presented_as_a_ready_plan(feasible):
    result = deepcopy(EMPTY_PLAN)
    result["status"] = "validation_failed"
    result["validation"]["feasible"] = feasible
    result["solve"]["lexicographic_optimal"] = True  # A solver flag is insufficient.
    assistant = Asistente(Sesion(resolutor=lambda cfg: deepcopy(result)))

    summary = _resumen_plan(result)
    assert summary["hay_solucion"] is True
    assert summary["entregas"] is None
    assert summary["paradas_recarga"] is None
    assert "validacion" in summary["resumen"]
    assert "optima (lexicografica)" not in summary["resumen"]
    assert "Se atendieron" not in summary["resumen"]
    assert not extraer_hechos(result).optimo_lexicografico
    response = assistant.turno("calcula")
    assert response.resolvio is True
    assert "Plan listo" not in response.respuesta
    assert "validacion" in response.respuesta
