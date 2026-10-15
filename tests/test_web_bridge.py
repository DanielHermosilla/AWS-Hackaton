"""Regression contract for the local beta bridge; no AWS or map downloads."""
from __future__ import annotations

import copy
import importlib.util
import json
import math
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from backend import service


def request():
    return {
        "api_version": "2.0-beta.1",
        "nodes": [
            {"node_id": "Base|ñ", "node_type": "base", "latitude": 0, "longitude": 0},
            {"node_id": "Base|ñ#fin", "node_type": "visit", "latitude": 0, "longitude": .001},
        ],
        "fleet": {"num_vehicles": 2, "battery_capacity_kwh": 10, "reserve_kwh": 1,
                  "initial_soc": .6, "consumption_kwh_km": 1},
        "solver": {"time_limit_seconds": 2}, "network_mode": "haversine",
    }


def prepared_request():
    p = request()
    del p["network_mode"]
    nodes = p.pop("nodes")
    p["prepared"] = {
        "esquema": "evrp.instancia_preparada/1",
        "nodos": [{"id": n["node_id"], "tipo": "base" if i == 0 else "cliente",
                   "lat": n["latitude"], "lon": n["longitude"], "fila": i,
                   "conectores": [], "puertos": None, "potencia_kw": None,
                   "direccion": "", "operador": ""} for i, n in enumerate(nodes)],
        "tramos": {f'{nodes[0]["node_id"]}|{nodes[1]["node_id"]}': [[1, 0]],
                   f'{nodes[1]["node_id"]}|{nodes[0]["node_id"]}': [[1, 0]]},
        "geometrias": {}, "red": {"tipo": "haversine", "vial": False}, "origen": {},
        "energia_caminos": {"usar_pendiente": False, "consumo_kwh_km": 1,
                            "masa_kg": 1590, "eta_traccion": .9, "eta_regeneracion": .6},
    }
    return p


def precision_request(capacity=10.00006, reserve=1):
    p = prepared_request()
    p["fleet"].update(battery_capacity_kwh=capacity, reserve_kwh=reserve)
    prep = p["prepared"]
    prep["nodos"] = [
        {"id": nid, "tipo": kind, "lat": 0, "lon": i / 1000, "fila": i,
         "conectores": ["CHADEMO"] if kind == "cargador" else [], "puertos": 1}
        for i, (nid, kind) in enumerate((("BASE", "base"), ("C1", "cargador"), ("V1", "cliente")))
    ]
    prep["tramos"] = {a["id"] + "|" + b["id"]: [[100, 0]] for a in prep["nodos"] for b in prep["nodos"] if a != b}
    prep["tramos"].update({"BASE|C1": [[1, 0]], "C1|V1": [[6, 0]], "V1|BASE": [[2, 0]]})
    return p


class RequestTests(unittest.TestCase):
    def test_required_explicit_energy_and_network(self):
        for field in ("battery_capacity_kwh", "reserve_kwh", "consumption_kwh_km"):
            p = request(); del p["fleet"][field]
            with self.subTest(field=field), self.assertRaises(service.SolveRequestError):
                service.validate_request(p)
        p = request(); del p["network_mode"]
        with self.assertRaises(service.SolveRequestError): service.validate_request(p)

    def test_unsupported_and_ambiguous_inputs_rejected(self):
        for field in ("movement_limit", "network", "config", "path"):
            p = request(); p[field] = 1
            with self.subTest(field=field), self.assertRaises(service.SolveRequestError):
                service.validate_request(p)
        p = prepared_request(); p["nodes"] = request()["nodes"]
        with self.assertRaises(service.SolveRequestError): service.validate_request(p)

    def test_numeric_and_node_validation(self):
        for value in (True, float("nan"), float("inf"), -91):
            p = request(); p["nodes"][0]["latitude"] = value
            with self.subTest(value=value), self.assertRaises(service.SolveRequestError):
                service.validate_request(p)
        p = request(); p["nodes"][1]["node_id"] = p["nodes"][0]["node_id"]
        with self.assertRaises(service.SolveRequestError): service.validate_request(p)
        p = request(); p["fleet"]["num_vehicles"] = 2.5
        with self.assertRaises(service.SolveRequestError): service.validate_request(p)
        p = request(); p["fleet"]["reserve_kwh"] = 7
        with self.assertRaises(service.SolveRequestError): service.validate_request(p)

    def test_exclusions_are_explicit_and_cannot_remove_base(self):
        for excluded in (["unknown"], ["Base|ñ"], ["Base|ñ#fin", "Base|ñ#fin"]):
            p = request(); p["exclude_node_ids"] = excluded
            with self.subTest(excluded=excluded), self.assertRaises(service.SolveRequestError):
                service.validate_request(p)

    def test_prepared_paths_refs_and_energy_mismatch_rejected(self):
        p = request(); del p["nodes"]; p["prepared"] = "/etc/passwd"
        with self.assertRaises(service.SolveRequestError): service.validate_request(p)
        p = prepared_request(); p["prepared"]["tramos"]["unknown|base"] = [[1, 0]]
        with self.assertRaises(service.SolveRequestError): service.validate_request(p)
        p = prepared_request(); p["fleet"]["consumption_kwh_km"] = 2
        with self.assertRaises(service.SolveRequestError): service.validate_request(p)
        p = prepared_request(); p["prepared"]["tramos"] = {}
        with self.assertRaises(service.SolveRequestError): service.validate_request(p)

    def test_opaque_ids_survive_normalization(self):
        normalized = service.validate_request(prepared_request())
        self.assertEqual([n["node_id"] for n in normalized["nodes"]], ["Base|ñ", "Base|ñ#fin"])

    def test_ambiguous_native_serialization_is_rejected(self):
        p = prepared_request()
        p["prepared"]["nodos"] = [
            {"id": key, "tipo": "base" if i == 0 else "cliente", "lat": 0, "lon": i / 100,
             "fila": i, "conectores": []} for i, key in enumerate(["A|B", "C", "A", "B|C"])]
        with self.assertRaisesRegex(service.SolveRequestError, "ambigua"):
            service.validate_request(p)


class RealProviderTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec("evrp") and importlib.util.find_spec("highspy"),
                         "Use the pinned provider uv environment for the real HiGHS smoke")
    def test_real_highs_ids_geometry_and_raw_export(self):
        envelope = service.solve(request())
        r = envelope["result"]
        self.assertEqual(envelope["api_version"], "2.0-beta.1")
        self.assertEqual(r["served_count"], 1)
        self.assertTrue(r["validation"]["feasible"])
        self.assertEqual(r["raw"]["result"]["kpis"]["origen_solucion"], "milp")
        self.assertEqual(r["metadata"]["provider_commit"], service.PROVIDER_COMMIT)
        self.assertEqual(r["raw"]["input"], request())
        self.assertEqual(r["total_energy_kwh"], None)
        self.assertEqual(len(r["routes"]), 2)
        active = next(route for route in r["routes"] if route["served_visit_ids"])
        self.assertEqual([s["node_id"] for s in active["steps"]], ["Base|ñ", "Base|ñ#fin", "Base|ñ"])
        self.assertEqual(active["geometry"]["coordinates"], [[0, 0], [.001, 0], [0, 0]])
        self.assertFalse(r["network"]["vial"])
        self.assertGreaterEqual(r["runtime_seconds"]["total"], r["runtime_seconds"]["solver"])
        json.dumps(envelope, allow_nan=False)

    @unittest.skipUnless(importlib.util.find_spec("evrp") and importlib.util.find_spec("highspy"),
                         "Requires pinned provider")
    def test_real_prepared_without_geometry_and_empty_demand(self):
        p = prepared_request()
        result = service.solve(p)["result"]
        self.assertTrue(all(r["geometry"] is None for r in result["routes"]))
        p["exclude_node_ids"] = ["Base|ñ#fin"]
        result = service.solve(p)["result"]
        self.assertEqual(result["total_visits"], 0)
        self.assertEqual(result["served_count"], 0)
        self.assertTrue(result["validation"]["feasible"])

class HttpTests(unittest.TestCase):
    def setUp(self):
        from backend.local_server import make_server
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "index.html").write_text("<h1>Beta</h1>")
        (self.root / "README.md").write_text("private")
        (self.root / "tests").mkdir()
        (self.root / "tests" / "hidden.json").write_text('{"private":true}')
        self.server = make_server(port=0, static_root=self.root)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        self.temp.cleanup()

    def fetch(self, path, data=None, headers=None):
        req = Request(self.origin + path, data=data, headers=headers or {})
        try:
            response = urlopen(req, timeout=10)
        except HTTPError as e:
            response = e
        return response.status, response.headers, response.read()

    def test_exact_endpoints_and_static_allowlist(self):
        status, _, body = self.fetch("/")
        self.assertEqual(status, 200); self.assertIn(b"Beta", body)
        for path in ("/anything/health", "/health/", "/anything/solve", "/AGENTS.md",
                     "/README.md", "/tests/hidden.json", "/%2e%2e/AGENTS.md", "/.git/config"):
            with self.subTest(path=path): self.assertEqual(self.fetch(path)[0], 404)
        status, headers, body = self.fetch("/health")
        self.assertEqual(status, 200)
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        self.assertEqual(json.loads(body)["api_version"], "2.0-beta.1")

    def test_cross_origin_and_dns_rebinding_are_rejected(self):
        self.assertEqual(self.fetch("/health", headers={"Host": "evil.example"})[0], 403)
        self.assertEqual(self.fetch("/solve", b"{}", {"Content-Type": "application/json", "Origin": "https://evil.example"})[0], 403)
        self.assertEqual(self.fetch("/health", headers={"Sec-Fetch-Site": "cross-site"})[0], 403)

    def test_json_duplicate_nonfinite_and_limit(self):
        headers = {"Content-Type": "application/json"}
        for raw in (b'{"api_version":NaN}', b'{"a":1,"a":2}', b'{invalid', b'[]'):
            with self.subTest(raw=raw): self.assertEqual(self.fetch("/solve", raw, headers)[0], 400)
        self.assertEqual(self.fetch("/solve", b"{}", {"Content-Type": "text/plain"})[0], 415)
        with patch("backend.local_server.MAX_BODY_BYTES", 10):
            self.assertEqual(self.fetch("/solve", b"x" * 11, headers)[0], 413)

    def test_ephemeral_run_retrieval_and_errors_do_not_leak(self):
        import uuid
        from backend.local_server import RunStore
        rid = str(uuid.uuid4())
        envelope = {"api_version": service.API_VERSION, "result": {"run_id": rid}}
        with patch.object(service, "solve", return_value=envelope):
            status, _, body = self.fetch("/solve", b"{}", {"Content-Type": "application/json"})
            self.assertEqual(status, 200)
            self.assertEqual(self.fetch("/solve?run_id=" + rid)[2], body)
        self.assertEqual(self.fetch("/solve?run_id=" + str(uuid.uuid4()))[0], 404)
        self.assertEqual(self.fetch("/solve?run_id=../../etc/passwd")[0], 400)
        with patch.object(service, "solve", side_effect=RuntimeError("SECRET /Users/private")):
            status, _, body = self.fetch("/solve", b"{}", {"Content-Type": "application/json"})
            self.assertEqual(status, 500); self.assertNotIn(b"SECRET", body); self.assertNotIn(b"/Users", body)
        store = RunStore(max_runs=1, max_bytes=1000)
        other = str(uuid.uuid4())
        store.put(rid, b"one"); store.put(other, b"two")
        self.assertIsNone(store.get(rid)); self.assertEqual(store.get(other), b"two")

    def test_concurrent_solver_calls_report_busy(self):
        self.server.solve_lock.acquire()
        try:
            self.assertEqual(self.fetch("/solve", b"{}", {"Content-Type": "application/json"})[0], 409)
        finally:
            self.server.solve_lock.release()

    @unittest.skipUnless(importlib.util.find_spec("evrp") and importlib.util.find_spec("highspy"), "Requires pinned provider")
    def test_real_http_highs_solve_and_retrieval(self):
        status, _, body = self.fetch("/solve", json.dumps(request()).encode(), {"Content-Type": "application/json", "Origin": self.origin})
        self.assertEqual(status, 200, body)
        data = json.loads(body)
        self.assertEqual(data["result"]["served_count"], 1)
        self.assertEqual(data["result"]["raw"]["result"]["kpis"]["origen_solucion"], "milp")
        self.assertEqual(self.fetch("/solve?run_id=" + data["result"]["run_id"])[2], body)

class RobustBoundaryTests(unittest.TestCase):
    def test_wrong_json_types_are_actionable_input_errors(self):
        for field, value in (("node_type", []), ("address", 0), ("connector_types", False)):
            p = request(); p["nodes"][0][field] = value
            with self.subTest(field=field), self.assertRaises(service.SolveRequestError):
                service.validate_request(p)
        p = prepared_request(); p["prepared"]["red"]["tipo"] = []
        with self.assertRaises(service.SolveRequestError): service.validate_request(p)

    def test_prepared_empty_path_and_self_loop_not_silently_ignored(self):
        p = prepared_request()
        p["prepared"]["tramos"][next(iter(p["prepared"]["tramos"]))] = []
        with self.assertRaises(service.SolveRequestError): service.validate_request(p)
        p = prepared_request()
        base = p["prepared"]["nodos"][0]["id"]
        p["prepared"]["tramos"][base + "|" + base] = [[1, 0]]
        with self.assertRaises(service.SolveRequestError): service.validate_request(p)

    def test_unavailable_statistics_do_not_hide_physical_nonfinite_data(self):
        from backend.evrp_adapter import strict_provider_result
        raw = {"kpis": {"solver": {"fase2": {"cota": math.inf, "gap": math.inf}}}}
        clean, reasons = strict_provider_result(raw)
        self.assertIsNone(clean["kpis"]["solver"]["fase2"]["cota"])
        self.assertEqual(len(reasons), 2)
        with self.assertRaises(service.ProviderError):
            strict_provider_result({"detalle": {"1": [{"bateria_llegada_kwh": math.nan}]}})

    @unittest.skipUnless(importlib.util.find_spec("evrp") and importlib.util.find_spec("highspy"), "Requires pinned provider")
    def test_network_hash_ignores_run_timings(self):
        payload = prepared_request()
        payload["prepared"]["origen"]["tiempo_s"] = 100
        first = service.solve(payload)["result"]
        payload["prepared"]["origen"]["tiempo_s"] = 200
        second = service.solve(payload)["result"]
        self.assertEqual(first["metadata"]["network_hash"], second["metadata"]["network_hash"])
        self.assertNotEqual(first["run_id"], second["run_id"])

    @unittest.skipUnless(importlib.util.find_spec("evrp") and importlib.util.find_spec("highspy"), "Requires pinned provider")
    def test_disconnected_saved_geometries_never_create_fake_edges(self):
        p = prepared_request()
        keys = list(p["prepared"]["tramos"])
        p["prepared"]["geometrias"] = {keys[0]: [[0, 0], [0, .001]],
                                        keys[1]: [[0, .002], [0, 0]]}
        result = service.solve(p)["result"]
        active = next(r for r in result["routes"] if r["served_visit_ids"])
        self.assertIsNone(active["geometry"])

    @unittest.skipUnless(importlib.util.find_spec("evrp") and importlib.util.find_spec("highspy"), "Requires pinned provider")
    def test_provider_energy_conflict_revokes_feasibility_claim(self):
        from evrp.api import Resultado
        r = service.solve(request())["result"]["raw"]["result"]
        r["kpis"]["energia_efectiva_kwh"] = -999
        with patch("evrp.resolver_preparada", return_value=Resultado(**r)):
            response = service.solve(request())["result"]
        self.assertIsNone(response["validation"]["feasible"])
        self.assertIsNone(response["total_energy_kwh"])
        self.assertTrue(any("no coincide" in w for w in response["warnings"]))

    @unittest.skipUnless(importlib.util.find_spec("evrp") and importlib.util.find_spec("highspy"), "Requires pinned provider")
    def test_partial_result_is_retained_and_not_called_infeasible(self):
        p = request()
        p["nodes"].append({"node_id": "unreachable", "node_type": "visit", "latitude": 0, "longitude": 1})
        result = service.solve(p)["result"]
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["served_count"], 1)
        self.assertEqual(result["unserved_visit_ids"], ["unreachable"])
        self.assertTrue(result["validation"]["feasible"])

    @unittest.skipUnless(importlib.util.find_spec("evrp") and importlib.util.find_spec("highspy"), "Requires pinned provider")
    def test_real_regeneration_charge_policy_conflict_is_not_certified(self):
        p = prepared_request()
        prep = p["prepared"]
        prep["nodos"] = [
            {"id": nid, "tipo": kind, "lat": 0, "lon": i / 1000, "fila": i,
             "conectores": ["CHADEMO"] if kind == "cargador" else [], "puertos": 1}
            for i, (nid, kind) in enumerate((("BASE", "base"), ("C1", "cargador"), ("V1", "cliente")))
        ]
        prep["tramos"] = {a["id"] + "|" + b["id"]: [[100, 0]] for a in prep["nodos"] for b in prep["nodos"] if a != b}
        prep["tramos"].update({"BASE|C1": [[1, 0]], "C1|V1": [[1, -5], [1, 0]], "V1|BASE": [[1, 0]]})
        prep["energia_caminos"].update(usar_pendiente=True, masa_kg=3.6e6 / 9.81, eta_traccion=1., eta_regeneracion=1.)
        result = service.solve(p)["result"]
        self.assertEqual(result["served_count"], 1)
        self.assertIsNone(result["validation"]["feasible"])
        self.assertIsNone(result["total_energy_kwh"])
        route = next(r for r in result["routes"] if r["served_visit_ids"])
        self.assertEqual([s["node_id"] for s in route["steps"]], ["BASE", "C1", "V1", "BASE"])
        self.assertEqual(sum(s["charge_kwh"] for s in route["steps"]), 5)
        self.assertEqual(route["steps"][-1]["departure_energy_kwh"], 8)
        self.assertEqual(result["raw"]["result"]["kpis"]["energia_efectiva_kwh"], -1)

    @unittest.skipUnless(importlib.util.find_spec("evrp") and importlib.util.find_spec("highspy"), "Requires pinned provider")
    def test_saved_geometry_on_another_continent_is_suppressed(self):
        p = prepared_request()
        prep = p["prepared"]
        prep["red"] = {"tipo": "osm", "vial": True}
        keys = list(prep["tramos"])
        prep["geometrias"] = {keys[0]: [[40, 10], [40, 10.001]],
                               keys[1]: [[40, 10.001], [40, 10]]}
        result = service.solve(p)["result"]
        active = next(r for r in result["routes"] if r["served_visit_ids"])
        self.assertIsNone(active["geometry"])
        self.assertTrue(result["validation"]["feasible"])
        self.assertEqual(result["served_count"], 1)
        self.assertTrue(any("extremos" in w and "preparar" in w for w in result["warnings"]))
        self.assertEqual(result["raw"]["input"]["prepared"]["geometrias"], prep["geometrias"])

    @unittest.skipUnless(importlib.util.find_spec("evrp") and importlib.util.find_spec("highspy"), "Requires pinned provider")
    def test_saved_osm_geometry_accepts_provider_rounding_and_interior_snaps(self):
        p = prepared_request()
        prep = p["prepared"]
        prep["red"] = {"tipo": "osm", "vial": True}
        for i, n in enumerate(prep["nodos"]):
            n["lat"], n["lon"] = 10.12345649 + i / 1000, 20.12345649 + i / 1000
        start = [round(prep["nodos"][0][k], 6) for k in ("lat", "lon")]
        end = [round(prep["nodos"][1][k], 6) for k in ("lat", "lon")]
        interior = [10.1235, 20.1236]
        keys = list(prep["tramos"])
        prep["geometrias"] = {keys[0]: [start, interior, end], keys[1]: [end, interior, start]}
        result = service.solve(p)["result"]
        active = next(r for r in result["routes"] if r["served_visit_ids"])
        self.assertIsNotNone(active["geometry"])
        self.assertEqual(active["geometry"]["coordinates"][1], interior[::-1])
        self.assertFalse(any("extremos" in w for w in result["warnings"]))


    @unittest.skipUnless(importlib.util.find_spec("evrp") and importlib.util.find_spec("highspy"), "Requires pinned provider")
    def test_provider_rounding_at_upper_battery_boundary_is_explicitly_unavailable(self):
        p = precision_request()
        result = service.solve(p)["result"]
        active = next(r for r in result["routes"] if r["served_visit_ids"])
        charge_stop = active["steps"][1]
        self.assertIsNone(charge_stop["departure_energy_kwh"])
        self.assertEqual(charge_stop["arrival_energy_kwh"], 5)
        self.assertIsNone(result["validation"]["feasible"])
        self.assertEqual(result["validation"]["violations"], [])
        self.assertTrue(any("precisión" in w.lower() and "redonde" in w for w in result["warnings"]))
        raw = result["raw"]["result"]["detalle"][active["vehicle_id"]][0]
        self.assertEqual(raw["bateria_salida_kwh"], 10.0001)
        self.assertEqual(result["raw"]["input"], p)

    @unittest.skipUnless(importlib.util.find_spec("evrp") and importlib.util.find_spec("highspy"), "Requires pinned provider")
    def test_provider_rounding_at_reserve_boundary_is_explicitly_unavailable(self):
        p = precision_request(capacity=10.00004, reserve=2.00004)
        result = service.solve(p)["result"]
        active = next(r for r in result["routes"] if r["served_visit_ids"])
        final_stop = active["steps"][-1]
        self.assertIsNone(final_stop["arrival_energy_kwh"])
        self.assertIsNone(final_stop["departure_energy_kwh"])
        self.assertIsNone(result["validation"]["feasible"])
        self.assertEqual(result["validation"]["violations"], [])
        raw = result["raw"]["result"]["detalle"][active["vehicle_id"]][-1]
        self.assertEqual(raw["bateria_llegada_kwh"], 2)
        self.assertTrue(any("precisión" in w.lower() and "redonde" in w for w in result["warnings"]))

    @unittest.skipUnless(importlib.util.find_spec("evrp") and importlib.util.find_spec("highspy"), "Requires pinned provider")
    def test_physical_battery_violation_is_not_excused_as_rounding(self):
        from evrp.api import Resultado
        p = precision_request(capacity=10, reserve=1)
        original = service.solve(p)["result"]["raw"]["result"]
        active_id = next(k for k, route in original["rutas"].items() if len(route) > 2)
        for field, invalid in (("bateria_salida_kwh", 10.0001), ("bateria_llegada_kwh", .9999)):
            with self.subTest(field=field):
                raw = copy.deepcopy(original)
                raw["detalle"][active_id][0][field] = invalid
                if field == "bateria_llegada_kwh":
                    raw["detalle"][active_id][0]["carga_kwh"] = 10 - invalid
                with patch("evrp.resolver_preparada", return_value=Resultado(**raw)):
                    result = service.solve(p)["result"]
                self.assertFalse(result["validation"]["feasible"])
                self.assertTrue(any("reserva" in v for v in result["validation"]["violations"]))
                self.assertEqual(result["raw"]["result"]["detalle"][active_id][0][field], invalid)
