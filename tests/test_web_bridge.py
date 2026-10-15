"""API 3.0 contract tests: Daniel's native instance/result and local transport."""

from __future__ import annotations

import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from backend import service


def native_request():
    """Adapted from Daniel's synthetic test_pipeline_cli example at 6242035."""
    return {
        "api_version": "3.0",
        "instance": {
            "schema_version": "1.0",
            "name": "Prueba sintética de integración nativa",
            "nodes": [
                {"node_id": "Centro|#fin", "node_type": "base"},
                {"node_id": "Visita|ñ", "node_type": "visit"},
                {"node_id": "pendiente", "node_type": "visit"},
            ],
            "arcs": [
                {
                    "from_node_id": "Centro|#fin",
                    "to_node_id": "Visita|ñ",
                    "energy_kwh": 1,
                    "distance_m": 500,
                },
                {
                    "from_node_id": "Visita|ñ",
                    "to_node_id": "Centro|#fin",
                    "energy_kwh": 1,
                    "distance_m": 700,
                },
            ],
            "parameters": {
                "vehicle_count": 2,
                "battery_capacity_kwh": 10,
                "reserve_kwh": 1,
                "initial_soc": 0.6,
                "movement_limit": 2,
            },
            "provenance": {
                "kind": "synthetic_test",
                "source": "Daniel 6242035 test_pipeline_cli example",
                "assumptions": ["Arcos y energía sintéticos; sin coordenadas ni red real."],
            },
        },
        "solver": {"time_limit_seconds": 3},
    }


def prepare_request():
    return {
        "api_version": "3.0",
        "nodes": [
            {"node_id": "B|#fin", "node_type": "base", "latitude": 0, "longitude": 0},
            {"node_id": "V|ñ", "node_type": "visit", "latitude": 0, "longitude": 0.001},
        ],
        "fleet": {
            "num_vehicles": 2,
            "battery_capacity_kwh": 10,
            "reserve_kwh": 1,
            "initial_soc": 0.6,
            "consumption_kwh_km": 1,
        },
        "network_mode": "haversine",
    }


class BoundaryTests(unittest.TestCase):
    def test_old_version_and_old_http_shapes_are_rejected(self):
        for payload in (
            {"api_version": "2.0-beta.1", "instance": {}},
            {"api_version": "3.0", "nodes": []},
            {**native_request(), "movement_limit": 4},
            {**native_request(), "prepared": {}},
            {**native_request(), "fleet": {}},
        ):
            with self.subTest(payload=payload), self.assertRaises(service.SolveRequestError):
                service.validate_request(payload)

    def test_native_json_is_canonical_without_rewriting_physics_or_ids(self):
        p = native_request()
        before = copy.deepcopy(p)
        instance, config = service.validate_request(p)
        self.assertEqual(p, before)
        self.assertEqual(instance.parameters.battery_capacity_kwh, 10)
        self.assertEqual(instance.arcs[0].energy_kwh, 1)
        self.assertEqual(instance.nodes[0].node_id, "Centro|#fin")
        self.assertIsNone(instance.nodes[0].latitude)
        self.assertEqual(config.solver, "scip-routes")
        self.assertEqual((config.threads, config.seed, config.relative_gap), (1, 0, 0))

    def test_service_path_representation_and_nonfinite_values_are_rejected(self):
        for representation in ("service_paths_nonnegative", {"kind": "service_paths_nonnegative"}):
            p = native_request()
            p["instance"]["provenance"]["representation"] = representation
            with self.assertRaises(service.SolveRequestError):
                service.validate_request(p)
        for value in (float("inf"), float("nan"), True):
            p = native_request()
            p["instance"]["arcs"][0]["energy_kwh"] = value
            with self.subTest(value=value), self.assertRaises(service.SolveRequestError):
                service.validate_request(p)

    def test_native_references_and_unapproved_solver_options_rejected(self):
        p = native_request()
        p["instance"]["arcs"][0]["to_node_id"] = "unknown"
        with self.assertRaises(service.SolveRequestError):
            service.validate_request(p)
        for field in ("solver", "relative_gap", "threads", "seed", "policy", "bedrock"):
            p = native_request()
            p["solver"][field] = 1
            with self.subTest(field=field), self.assertRaises(service.SolveRequestError):
                service.validate_request(p)

    def test_prepare_requires_explicit_mode_and_energy(self):
        for field in ("battery_capacity_kwh", "reserve_kwh", "consumption_kwh_km"):
            p = prepare_request()
            del p["fleet"][field]
            with self.subTest(field=field), self.assertRaises(service.SolveRequestError):
                service.prepare(p)
        p = prepare_request()
        del p["network_mode"]
        with self.assertRaises(service.SolveRequestError):
            service.prepare(p)

    def test_prepare_builds_labelled_synthetic_native_instance_without_geometry(self):
        response = service.prepare(prepare_request())
        self.assertEqual(response["api_version"], "3.0")
        i = response["instance"]
        self.assertEqual(i["schema_version"], "1.0")
        self.assertEqual(i["provenance"]["kind"], "synthetic")
        self.assertEqual(i["provenance"]["network"]["kind"], "haversine")
        self.assertEqual(len(i["arcs"]), 2)
        self.assertAlmostEqual(i["arcs"][0]["energy_kwh"], 0.111195, places=5)
        self.assertEqual(i["arcs"][0]["geometry"], [])
        self.assertEqual(i["nodes"][0]["connector_types"], [])
        self.assertEqual(i["nodes"][0]["node_id"], "B|#fin")

    def test_prepare_rejects_bad_nodes_and_port_inconsistencies(self):
        for update in (
            {"node_id": ""},
            {"latitude": 91},
            {"latitude": True},
            {"node_type": "junction"},
            {"total_ports": 1, "dc_fast_ports": 2, "level2_ports": 0},
        ):
            p = prepare_request()
            p["nodes"][1].update(update)
            with self.subTest(update=update), self.assertRaises(service.SolveRequestError):
                service.prepare(p)

    def test_extreme_numeric_budget_is_an_input_error(self):
        p = native_request()
        p["solver"]["time_limit_seconds"] = 10**400
        with self.assertRaises(service.SolveRequestError):
            service.validate_request(p)

    def test_provider_commit_matches_import_manifest(self):
        manifest = json.loads(
            (Path(__file__).resolve().parents[1] / "docs" / "solver-source.json").read_text()
        )
        self.assertEqual(service.PROVIDER_COMMIT, manifest["source_commit"])

    def test_external_core_is_not_accepted_for_preparation(self):
        with patch("ev_routing.__file__", "/tmp/another-provider/ev_routing/__init__.py"):
            with self.assertRaises(service.ProviderError) as error:
                service.prepare(prepare_request())
        self.assertEqual(error.exception.status, 503)

    def test_json_is_strict(self):
        for raw in ('{"a":NaN}', '{"a":1,"a":2}', "invalid"):
            with self.assertRaises(service.SolveRequestError):
                service.strict_loads(raw)


class NativeSolverTests(unittest.TestCase):
    def test_real_scip_partial_preserves_native_result_phases_energy_and_missing_coords(self):
        request = native_request()
        envelope = service.solve(request)
        result = envelope["result"]
        self.assertEqual(envelope["api_version"], "3.0")
        self.assertEqual(result["status"], "partial")
        self.assertTrue(result["has_solution"])
        self.assertTrue(result["validation"]["feasible"])
        self.assertEqual(result["served_count"], 1)
        self.assertEqual(result["unserved_visit_ids"], ["pendiente"])
        self.assertAlmostEqual(result["total_energy_kwh"], 2)
        self.assertEqual(result["metadata"]["provider"], "ev_routing")
        self.assertEqual(result["metadata"]["provider_commit"], service.PROVIDER_COMMIT)
        self.assertEqual(result["metadata"]["native_schema_version"], "1.0")
        self.assertEqual(result["phases"], result["raw"]["result"]["solve"]["phases"])
        self.assertEqual(result["raw"]["input"], request)
        self.assertEqual(result["raw"]["result"]["solve"]["used_solver"], "scip-routes")
        self.assertIsNone(result["nodes"][0]["latitude"])
        self.assertTrue(all(r["geometry"] is None for r in result["routes"]))
        self.assertEqual(result["raw"]["result"]["tuning"]["calls"], 0)
        json.dumps(envelope, allow_nan=False)

    def test_prepare_then_real_scip(self):
        prepared = service.prepare(prepare_request())["instance"]
        result = service.solve(
            {"api_version": "3.0", "instance": prepared, "solver": {"time_limit_seconds": 3}}
        )["result"]
        self.assertEqual(result["status"], "result_available")
        self.assertEqual(result["served_count"], 1)
        self.assertFalse(result["network"]["vial"])
        self.assertTrue(all(r["geometry"] is None for r in result["routes"]))

    def test_native_no_solution_is_complete_result_not_infeasibility_inference(self):
        from ev_routing.contracts import PhaseResult, SolveResult

        phase = PhaseResult(
            name="deliveries",
            sense="maximize",
            status="time_limit",
            termination_condition="budget_exhausted",
            has_solution=False,
            proven_optimal=False,
        )
        solved = SolveResult(
            requested_solver="scip-routes",
            used_solver="scip-routes",
            status="time_limit",
            phases=[phase],
        )
        with patch("ev_routing.pipeline.solve_instance", return_value=solved):
            result = service.solve(native_request())["result"]
        self.assertEqual(result["status"], "no_solution")
        self.assertFalse(result["has_solution"])
        self.assertEqual(result["routes"], [])
        self.assertIsNone(result["served_count"])
        self.assertIsNone(result["total_energy_kwh"])
        self.assertIsNone(result["validation"]["feasible"])
        self.assertEqual(result["unserved_visit_ids"], [])
        self.assertTrue(result["metadata"]["time_limit_reached"])
        self.assertEqual(result["phases"], [phase.model_dump(mode="json")])

    def test_geometry_is_native_lat_lon_and_requires_saved_connected_endpoints(self):
        p = native_request()
        p["instance"]["nodes"][0].update(latitude=0, longitude=0)
        p["instance"]["nodes"][1].update(latitude=0, longitude=0.001)
        p["instance"]["arcs"][0]["geometry"] = [[0, 0], [0.0001, 0.0005], [0, 0.001]]
        p["instance"]["arcs"][1]["geometry"] = [[0, 0.001], [0, 0]]
        r = service.solve(p)["result"]
        active = next(route for route in r["routes"] if route["served_visit_ids"])
        self.assertEqual(
            active["geometry"]["coordinates"], [[0, 0], [0.0005, 0.0001], [0.001, 0], [0, 0]]
        )
        native = next(
            route
            for route in r["raw"]["result"]["solve"]["solution"]["routes"]
            if route["vehicle_id"] == active["vehicle_id"]
        )
        self.assertEqual(
            [s["energy_kwh"] for s in active["steps"]],
            [s["effective_arc_energy_kwh"] for s in native["steps"]],
        )
        p["instance"]["arcs"][0]["geometry"] = [[40, 10], [40, 10.001]]
        r = service.solve(p)["result"]
        self.assertIsNone(
            next(route for route in r["routes"] if route["served_visit_ids"])["geometry"]
        )

    def test_real_daniel_recharge_and_regeneration_examples_keep_effective_energy(self):
        for filename, deliveries, energy in (
            ("toy_recharge.json", 2, 14),
            ("toy_regeneration.json", 1, 2),
        ):
            with self.subTest(filename=filename):
                native = json.loads(
                    (Path(__file__).resolve().parents[1] / "examples" / filename).read_text()
                )
                result = service.solve(
                    {"api_version": "3.0", "instance": native, "solver": {"time_limit_seconds": 3}}
                )["result"]
                self.assertTrue(result["validation"]["feasible"])
                self.assertEqual(result["served_count"], deliveries)
                self.assertAlmostEqual(result["total_energy_kwh"], energy)
                self.assertAlmostEqual(
                    sum(route["energy_kwh"] for route in result["routes"]), energy
                )
                self.assertEqual(result["raw"]["input"]["instance"], native)
                if filename == "toy_recharge.json":
                    self.assertAlmostEqual(
                        sum(
                            step["charge_kwh"]
                            for route in result["routes"]
                            for step in route["steps"]
                        ),
                        9,
                    )
                else:
                    self.assertTrue(
                        any(
                            step["energy_kwh"] == -5
                            for route in result["routes"]
                            for step in route["steps"]
                        )
                    )
                    self.assertTrue(
                        any(
                            node["node_type"] == "junction" and node["latitude"] is None
                            for node in result["nodes"]
                        )
                    )

    def test_unknown_native_provenance_remains_data(self):
        p = native_request()
        p["instance"]["provenance"]["network"] = {"kind": ["not", "a", "type"]}
        result = service.solve(p)["result"]
        self.assertEqual(result["network"]["type"], "native")
        self.assertEqual(result["raw"]["input"], p)

    def test_native_no_incumbent_error_unavailable_and_proof_are_not_fabricated(self):
        from ev_routing.contracts import PhaseResult, SolveResult

        for status in ("error", "unavailable", "infeasible"):
            phase = PhaseResult(
                name="deliveries",
                sense="maximize",
                status=status,
                termination_condition=status,
                has_solution=False,
                proven_optimal=False,
            )
            solved = SolveResult(requested_solver="scip-routes", status=status, phases=[phase])
            with (
                self.subTest(status=status),
                patch("ev_routing.pipeline.solve_instance", return_value=solved),
            ):
                result = service.solve(native_request())["result"]
            self.assertEqual(result["status"], status if status != "infeasible" else "no_solution")
            self.assertIsNone(result["validation"]["feasible"])
            self.assertEqual(result["phases"], [phase.model_dump(mode="json")])
            self.assertEqual(result["metadata"]["native_status"], status)
            self.assertFalse(result["metadata"]["lexicographic_optimal"])
            self.assertIsNone(result["metadata"]["time_limit_reached"])

    def test_simulated_native_timeout_preserves_a_real_validated_incumbent(self):
        from ev_routing.contracts import SolveResult

        baseline = service.solve(native_request())["result"]
        native = copy.deepcopy(baseline["raw"]["result"]["solve"])
        native["status"] = "feasible"
        native["lexicographic_optimal"] = False
        native["phases"][-1].update(
            termination_condition="timelimit", proven_optimal=False, status="feasible"
        )
        with patch(
            "ev_routing.pipeline.solve_instance", return_value=SolveResult.model_validate(native)
        ):
            result = service.solve(native_request())["result"]
        self.assertEqual(result["routes"], baseline["routes"])
        self.assertEqual(result["validation"], baseline["validation"])
        self.assertTrue(result["metadata"]["time_limit_reached"])
        self.assertFalse(result["metadata"]["lexicographic_optimal"])
        self.assertEqual(result["phases"], native["phases"])


class HttpTests(unittest.TestCase):
    def setUp(self):
        from backend.local_server import make_server

        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        (root / "index.html").write_text("<h1>Beta</h1>")
        (root / "README.md").write_text("private")
        self.server = make_server(port=0, static_root=root)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def fetch(self, path, payload=None, headers=None):
        headers = {"Content-Type": "application/json", **(headers or {})}
        data = (
            None
            if payload is None
            else (payload if isinstance(payload, bytes) else json.dumps(payload).encode())
        )
        try:
            response = urlopen(Request(self.origin + path, data=data, headers=headers), timeout=15)
        except HTTPError as error:
            response = error
        return response.status, response.headers, response.read()

    def test_real_prepare_solve_retrieve(self):
        status, _, body = self.fetch("/prepare", prepare_request())
        self.assertEqual(status, 200, body)
        instance = json.loads(body)["instance"]
        status, _, body = self.fetch(
            "/solve",
            {"api_version": "3.0", "instance": instance, "solver": {"time_limit_seconds": 3}},
        )
        self.assertEqual(status, 200, body)
        self.assertEqual(json.loads(body)["result"]["served_count"], 1)
        self.assertEqual(
            self.fetch("/solve?run_id=" + json.loads(body)["result"]["run_id"])[2], body
        )

    def test_exact_paths_static_origin_and_json_limits(self):
        self.assertEqual(self.fetch("/")[0], 200)
        for path in (
            "/anything/health",
            "/health/",
            "/README.md",
            "/AGENTS.md",
            "/%2e%2e/AGENTS.md",
            "/.git/config",
        ):
            self.assertEqual(self.fetch(path)[0], 404)
        self.assertEqual(self.fetch("/health", headers={"Host": "evil.example"})[0], 403)
        self.assertEqual(self.fetch("/prepare", {}, {"Origin": "https://evil.example"})[0], 403)
        for raw in (b'{"a":NaN}', b'{"a":1,"a":2}', b"[]"):
            self.assertEqual(self.fetch("/solve", raw)[0], 400)
        with patch("backend.local_server.MAX_BODY_BYTES", 10):
            self.assertEqual(self.fetch("/solve", b"x" * 11)[0], 413)

    def test_busy_safe_errors_and_health(self):
        self.server.solve_lock.acquire()
        try:
            self.assertEqual(self.fetch("/solve", {})[0], 409)
        finally:
            self.server.solve_lock.release()
        with patch.object(
            service,
            "solve",
            side_effect=service.ProviderError(
                "Proveedor no disponible", "provider_unavailable", 503
            ),
        ):
            self.assertEqual(self.fetch("/solve", {})[0], 503)
        status, headers, body = self.fetch("/health")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["api_version"], "3.0")
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_native_no_solution_http_is_200_and_unexpected_provider_error_is_safe_502(self):
        from ev_routing.contracts import SolveResult

        with patch(
            "ev_routing.pipeline.solve_instance",
            return_value=SolveResult(requested_solver="scip-routes", status="time_limit"),
        ):
            status, _, body = self.fetch("/solve", native_request())
        self.assertEqual(status, 200, body)
        self.assertIsNone(json.loads(body)["result"]["served_count"])
        with patch(
            "ev_routing.pipeline.run_instance", side_effect=RuntimeError("secret /private/path")
        ):
            status, _, body = self.fetch("/solve", native_request())
        self.assertEqual(status, 502, body)
        self.assertNotIn(b"secret", body)
        self.assertNotIn(b"/private", body)
        with patch.object(service, "solve", side_effect=RuntimeError("secret /private/path")):
            status, _, body = self.fetch("/solve", native_request())
        self.assertEqual(status, 502, body)
        self.assertNotIn(b"secret", body)
