"""Native output parity through the real local HTTP boundary; no AWS or maps."""

from __future__ import annotations

import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request, urlopen

from backend import daniel_adapter, service
from backend.local_server import make_server
from ev_routing.contracts import PhaseResult, SolveResult
from ev_routing.pipeline import run_instance

ROOT = Path(__file__).resolve().parents[1]
STEP_FIELDS = (
    "next_node_id",
    "predicted_arc_energy_kwh",
    "effective_arc_energy_kwh",
    "arrival_seconds",
    "service_start_seconds",
    "departure_seconds",
    "service_duration_seconds",
    "charging_duration_seconds",
    "travel_time_seconds",
)
SOLVER_FIELDS = (
    "requested_solver",
    "used_solver",
    "solver_version",
    "fallback_reason",
    "solution_source",
    "message",
)


def read_json(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def request_for(instance):
    return {"api_version": "3.0", "instance": instance, "solver": {"time_limit_seconds": 3}}


def operations_request():
    instance = read_json("examples/toy_recharge.json")
    instance["operations"] = {
        "service_seconds": 60,
        "service_seconds_by_customer": {"B": 120},
        "max_route_seconds": 10000,
        "assumed_speed_kph": 36,
        "include_charging_time": True,
        "charging_power_kw": 18,
        "charging_efficiency": 0.9,
        "final_reserve_soc": 0.1,
    }
    return request_for(instance)


class NativeOutputParityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = make_server(port=0, static_root=Path(self.temp.name))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def post_captured(self, request, extend=None):
        captured = []

        def capture(*args, **kwargs):
            native = run_instance(*args, **kwargs)
            if extend is not None:
                extend(native)
            captured.append(service.json_bytes(native))
            return native

        before = copy.deepcopy(request)
        with patch("ev_routing.pipeline.run_instance", side_effect=capture):
            with urlopen(
                Request(
                    self.origin + "/solve",
                    data=service.json_bytes(request),
                    headers={"Content-Type": "application/json"},
                ),
                timeout=15,
            ) as response:
                self.assertEqual(response.status, 200)
                body = response.read()
        envelope = service.strict_loads(body)
        result = envelope["result"]
        self.assertEqual(len(captured), 1)
        self.assertEqual(service.json_bytes(result["raw"]["result"]), captured[0])
        self.assertEqual(result["raw"]["input"], before)
        self.assertEqual(request, before)
        with urlopen(self.origin + "/solve?run_id=" + result["run_id"], timeout=5) as response:
            self.assertEqual(response.read(), body)
        return result

    def assert_native_projection(self, result):
        native = result["raw"]["result"]
        for field in ("kpis", "operations", "tuning"):
            self.assertEqual(result[field], native[field], field)
        self.assertEqual(result["phases"], native["solve"]["phases"])
        self.assertEqual(
            result["validation"]["checks"],
            native["validation"]["checks"] if native["validation"] is not None else {},
        )
        self.assertEqual(
            result["metadata"]["native_solver"],
            {field: native["solve"][field] for field in SOLVER_FIELDS},
        )
        for field in ("validation", "initial_solution_validation", "llm"):
            self.assertEqual(result["runtime_seconds"][field], native["runtime_seconds"][field])
        self.assertEqual(
            result["runtime_seconds"]["native_resolution_including_model"],
            native["runtime_seconds"]["resolution_including_model"],
        )
        self.assertEqual(
            result["runtime_seconds"]["native_total"], native["runtime_seconds"]["total"]
        )
        solution = native["solve"]["solution"]
        self.assertEqual(len(result["routes"]), len(solution["routes"]) if solution else 0)
        for route, original in zip(result["routes"], solution["routes"] if solution else []):
            self.assertEqual(route["vehicle_id"], original["vehicle_id"])
            self.assertEqual(route["duration_seconds"], original["duration_seconds"])
            self.assertEqual(len(route["steps"]), len(original["steps"]))
            for step, native_step in zip(route["steps"], original["steps"]):
                for field in STEP_FIELDS:
                    self.assertEqual(step[field], native_step[field], field)

    def test_real_http_preserves_full_output_for_operations_regeneration_partial_and_defaults(self):
        regeneration = read_json("examples/toy_regeneration.json")
        regeneration["parameters"]["vehicle_count"] = 3
        cases = {
            "operations": (operations_request(), 2, 14, 2),
            "regeneration": (request_for(regeneration), 1, 2, 3),
            "partial": (read_json("backend/fixtures/native-request.json"), 1, 2, 2),
            "defaults": (
                request_for(
                    {
                        "schema_version": "1.0",
                        "nodes": [{"node_id": " depósito|ñ#fin ", "node_type": "base"}],
                        "arcs": [],
                    }
                ),
                0,
                0,
                2,
            ),
        }
        for label, (request, deliveries, energy, fleet_count) in cases.items():
            with self.subTest(label=label):
                result = self.post_captured(request)
                self.assert_native_projection(result)
                self.assertTrue(result["validation"]["feasible"])
                self.assertEqual(result["kpis"]["served_deliveries"], deliveries)
                self.assertAlmostEqual(result["kpis"]["net_battery_energy_kwh"], energy)
                self.assertEqual(len(result["fleet"]), fleet_count)
                if label == "operations":
                    self.assertEqual(result["kpis"]["charged_to_battery_kwh"], 9)
                    self.assertEqual(result["kpis"]["grid_energy_kwh"], 10)
                    self.assertEqual(result["kpis"]["operational_duration_seconds"], 3580)
                    self.assertEqual(
                        sorted(r["duration_seconds"] for r in result["routes"]), [0, 3580]
                    )
                if label == "regeneration":
                    regenerative = [
                        step
                        for route in result["routes"]
                        for step in route["steps"]
                        if step["predicted_arc_energy_kwh"] == -8
                    ]
                    self.assertTrue(regenerative)
                    self.assertEqual(regenerative[0]["effective_arc_energy_kwh"], -5)
                if label == "defaults":
                    self.assertEqual(
                        result["raw"]["instance"]["parameters"]["battery_capacity_kwh"], 24
                    )

    def test_http_no_incumbent_and_error_preserve_null_kpis_and_native_certificates(self):
        for status in ("time_limit", "error"):
            with self.subTest(status=status):
                phase = PhaseResult(
                    name="deliveries",
                    sense="maximize",
                    status=status,
                    termination_condition="budget_exhausted" if status == "time_limit" else "error",
                    has_solution=False,
                    proven_optimal=False,
                    message="Terminación simulada para comprobar el transporte del contrato.",
                )
                solved = SolveResult(
                    requested_solver="scip-routes",
                    status=status,
                    phases=[phase],
                    message=phase.message,
                )
                with patch("ev_routing.pipeline.solve_instance", return_value=solved):
                    result = self.post_captured(operations_request())
                self.assert_native_projection(result)
                self.assertIsNone(result["validation"]["feasible"])
                self.assertEqual(result["routes"], [])
                self.assertIsNone(result["kpis"]["served_deliveries"])
                self.assertIsNone(result["kpis"]["net_battery_energy_kwh"])
                self.assertFalse(result["metadata"]["lexicographic_optimal"])

    def test_invalid_incumbent_keeps_native_null_kpis_and_failed_checks(self):
        fixture = read_json("backend/fixtures/native-operations-response.json")["result"]
        solved = SolveResult.model_validate(fixture["raw"]["result"]["solve"])
        # Simulate an invalid provider incumbent, then run the real native checker.
        solved.solution.routes[0].steps[0].battery_departure_kwh = 20
        with patch("ev_routing.pipeline.solve_instance", return_value=solved):
            result = self.post_captured(operations_request())
        self.assert_native_projection(result)
        self.assertEqual(result["status"], "validation_failed")
        self.assertFalse(result["validation"]["feasible"])
        self.assertTrue(result["validation"]["violations"])
        self.assertIsNone(result["kpis"]["net_battery_energy_kwh"])
        self.assertIsNone(result["kpis"]["served_deliveries"])
        self.assertIsNone(result["total_energy_kwh"])
        self.assertTrue(
            all(step["energy_kwh"] is None for r in result["routes"] for step in r["steps"])
        )

    def test_future_native_output_fields_survive_http_without_projection_recalculation(self):
        extension = {"future": [None, 0, False, {"opaque": "ñ|#fin"}]}

        def extend(native):
            native["future_output"] = copy.deepcopy(extension)
            native["kpis"]["future_metric"] = copy.deepcopy(extension)
            native["tuning"]["future_controller"] = copy.deepcopy(extension)
            native["solve"]["search"]["future_diagnostic"] = copy.deepcopy(extension)

        result = self.post_captured(operations_request(), extend)
        self.assert_native_projection(result)
        self.assertEqual(result["raw"]["result"]["future_output"], extension)
        self.assertEqual(result["kpis"]["future_metric"], extension)
        self.assertEqual(result["tuning"]["future_controller"], extension)
        self.assertEqual(result["raw"]["result"]["solve"]["search"]["future_diagnostic"], extension)

    def test_projected_native_dicts_do_not_alias_the_export_original(self):
        fixture = read_json("backend/fixtures/native-operations-response.json")["result"]
        native = fixture["raw"]["result"]
        before = copy.deepcopy(native)
        instance, config = service.validate_request(fixture["raw"]["input"])
        result = daniel_adapter.project_result(instance, config, native)
        result["kpis"]["unavailable_reasons"].clear()
        result["operations"]["service_seconds_by_customer"].clear()
        result["tuning"]["decisions"].append({"presentation": "only"})
        self.assertEqual(native, before)

    def test_native_network_source_is_declared_road_without_external_verification(self):
        request = read_json("backend/fixtures/native-request.json")
        native = read_json("backend/fixtures/native-response.json")["result"]["raw"]["result"]
        cases = (
            ({"network": {"source": "directed_road_graph"}}, "directed_road_graph", True),
            (
                {"network": {"kind": "haversine", "source": "directed_road_graph"}},
                "haversine",
                False,
            ),
            (
                {"kind": "synthetic", "network": {"source": "directed_road_graph"}},
                "directed_road_graph",
                False,
            ),
            ({"network": {"source": "unknown_future_source"}}, "native", False),
        )
        for provenance, network_type, vial in cases:
            with self.subTest(provenance=provenance):
                request["instance"]["provenance"] = provenance
                instance, config = service.validate_request(request)
                result = daniel_adapter.project_result(instance, config, native)
                self.assertEqual(result["network"]["type"], network_type)
                self.assertEqual(result["network"]["vial"], vial)
                self.assertFalse(result["network"]["provenance_verified"])


if __name__ == "__main__":
    unittest.main()
