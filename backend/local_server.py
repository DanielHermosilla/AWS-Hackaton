"""Loopback-only synchronous beta HTTP transport and webapp static root.

Serves one origin, exact endpoints, bounded bodies and four ephemeral runs.
API 3.0 adds explicit synthetic preparation before the native solve.
No authentication, deployment, filesystem input paths, or cross-origin API.
"""

from __future__ import annotations

import argparse
import threading
import uuid
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, unquote, urlsplit

from . import assist_service, service

MAX_BODY_BYTES = 64 * 1024 * 1024
MAX_CONNECTION_BYTES = 16 * 1024
STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
}


class RunStore:
    def __init__(self, max_runs=4, max_bytes=256 * 1024 * 1024):
        self.max_runs, self.max_bytes = max_runs, max_bytes
        self.runs = OrderedDict()
        self.size = 0
        self.lock = threading.Lock()

    def put(self, run_id, data):
        if len(data) > self.max_bytes:
            raise service.ProviderError(
                "El resultado excede el almacenamiento temporal del servidor.",
                "result_too_large",
                413,
            )
        with self.lock:
            if run_id in self.runs:
                self.size -= len(self.runs.pop(run_id))
            while self.runs and (
                len(self.runs) >= self.max_runs or self.size + len(data) > self.max_bytes
            ):
                _, old = self.runs.popitem(last=False)
                self.size -= len(old)
            self.runs[run_id] = data
            self.size += len(data)

    def get(self, run_id):
        with self.lock:
            return self.runs.get(run_id)


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, host, port, static_root, runtime=None):
        if host not in {"127.0.0.1", "localhost"}:
            raise ValueError("El servidor local solo admite 127.0.0.1 o localhost.")
        self.static_root = Path(static_root).resolve(strict=True)
        self.solve_lock = threading.Lock()
        self.runs = RunStore()
        if runtime is None:
            from .runtime import Runtime

            runtime = Runtime()
        self.runtime = runtime
        super().__init__((host, port), Handler)
        self.allowed_hosts = {f"127.0.0.1:{self.server_port}", f"localhost:{self.server_port}"}

    def server_close(self):
        super().server_close()
        self.runtime.close()


class Handler(BaseHTTPRequestHandler):
    server_version = "ZMDLocalBeta"
    sys_version = ""

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def _send(self, status, data, content_type="application/json; charset=utf-8"):
        if not isinstance(data, bytes):
            data = service.json_bytes(data)
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        if self.command != "HEAD":
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass  # leaving the browser does not cancel the provider solve

    def _error(self, status, code, message):
        self._send(
            status,
            {"api_version": service.API_VERSION, "error": {"code": code, "message": message}},
        )

    def _same_origin(self):
        hosts = self.headers.get_all("Host", [])
        origin = self.headers.get("Origin")
        if (
            len(hosts) != 1
            or hosts[0] not in self.server.allowed_hosts
            or (origin is not None and origin != "http://" + hosts[0])
            or self.headers.get("Sec-Fetch-Site") == "cross-site"
        ):
            self._error(
                403, "origin_not_allowed", "Esta aplicación solo admite el origen local del servidor."
            )
            return False
        return True

    def do_GET(self):  # noqa: N802
        if not self._same_origin():
            return
        parts = urlsplit(self.path)
        if parts.scheme or parts.netloc or parts.fragment:
            self._error(404, "not_found", "Recurso no encontrado.")
            return
        if parts.path == "/health" and not parts.query:
            self._send(200, service.health(runtime=self.server.runtime))
            return
        if parts.path == "/scenarios/hackathon":
            from .scenarios import hackathon_scenario

            try:
                params = parse_qs(parts.query, strict_parsing=True)
                if set(params) != {"dataset"} or len(params["dataset"]) != 1:
                    raise service.SolveRequestError("Indica un único dataset de la hackatón.")
                scenario = hackathon_scenario(params["dataset"][0])
                self._send(200, {"api_version": service.API_VERSION, "scenario": scenario})
            except service.ProviderError as error:
                self._error(error.status, error.code, str(error))
            except ValueError as error:
                self._error(400, "invalid_scenario", str(error))
            return
        if parts.path == "/bedrock/session" and not parts.query:
            self._send(200, {
                "api_version": service.API_VERSION, "status": self.server.runtime.bedrock.status(),
            })
            return
        if parts.path == "/history":
            try:
                params = parse_qs(parts.query, strict_parsing=True)
                if set(params) != {"profile_id"} or len(params["profile_id"]) != 1:
                    raise ValueError
                profile = self.server.runtime.histories.get(params["profile_id"][0]).public()
                self._send(200, {"api_version": service.API_VERSION, "profile": profile})
            except service.ProviderError as error:
                self._error(error.status, error.code, str(error))
            except ValueError:
                self._error(400, "invalid_profile", "Indica el histórico que deseas recuperar.")
            return
        if parts.path == "/solve":
            try:
                params = parse_qs(parts.query, strict_parsing=True)
                if set(params) != {"run_id"} or len(params["run_id"]) != 1:
                    raise ValueError
                run_id = params["run_id"][0]
                if str(uuid.UUID(run_id)) != run_id:
                    raise ValueError
            except ValueError:
                self._error(
                    400, "invalid_run_id", "Indique un run_id válido para recuperar el resultado."
                )
                return
            data = self.server.runs.get(run_id)
            if data is None:
                self._error(
                    404,
                    "run_expired",
                    "El resultado ya no está disponible; calcule de nuevo o abra su exportación.",
                )
            else:
                self._send(200, data)
            return
        if parts.path == "/assist/schema" and not parts.query:
            self._send(200, assist_service.schema())
            return
        self._static(parts.path)

    def _static(self, raw_path):
        decoded = unquote(raw_path)
        parts = PurePosixPath(decoded).parts
        if (
            "\\" in decoded
            or "\x00" in decoded
            or any(p.startswith(".") or p == "tests" for p in parts)
        ):
            self._error(404, "not_found", "Recurso no encontrado.")
            return
        relative = "index.html" if decoded == "/" else decoded.lstrip("/")
        path = (self.server.static_root / relative).resolve()
        if (
            not path.is_relative_to(self.server.static_root)
            or path.suffix not in STATIC_TYPES
            or not path.is_file()
        ):
            self._error(404, "not_found", "Recurso no encontrado.")
            return
        try:
            data = path.read_bytes()
        except OSError:
            self._error(404, "not_found", "Recurso no encontrado.")
            return
        self._send(200, data, STATIC_TYPES[path.suffix])

    def do_POST(self):  # noqa: N802
        if not self._same_origin():
            return
        endpoints = {
            "/solve", "/prepare", "/history/upload", "/history/analyze", "/history/remove",
            "/bedrock/session", "/bedrock/disconnect", "/scenarios/hackathon",
            "/assist/chat",
        }
        if self.path not in endpoints:
            self._error(404, "not_found", "Recurso no encontrado.")
            return
        upload = self.path == "/history/upload"
        if upload and self.headers.get_content_type() != "application/octet-stream":
            self._error(415, "unsupported_media_type", "Adjunta el archivo histórico CSV o JSON.")
            return
        if not upload and self.headers.get_content_type() != "application/json":
            self._error(415, "unsupported_media_type", "Use Content-Type: application/json.")
            return
        lengths = self.headers.get_all("Content-Length", [])
        if self.headers.get("Transfer-Encoding") or len(lengths) != 1:
            self._error(
                411,
                "content_length_required",
                "Se requiere un único Content-Length sin Transfer-Encoding.",
            )
            return
        try:
            if not lengths[0].isdigit():
                raise ValueError
            length = int(lengths[0])
        except ValueError:
            self._error(400, "invalid_content_length", "Content-Length inválido.")
            return
        from .history_store import MAX_HISTORY_BYTES

        limit = MAX_HISTORY_BYTES if upload else (
            MAX_BODY_BYTES if self.path in {"/prepare", "/solve", "/assist/chat"}
            else MAX_CONNECTION_BYTES
        )
        if length > limit:
            message = (
                "El histórico supera los 4 GiB admitidos para CSV."
                if upload else
                "La petición supera el tamaño admitido para esta operación."
            )
            self._error(413, "payload_too_large", message)
            return
        payload = None
        if not upload:
            try:
                data = self.rfile.read(length)
                if len(data) != length:
                    raise service.SolveRequestError("Cuerpo JSON incompleto.")
                payload = service.strict_loads(data)
                del data  # do not retain a second copy of credential request bytes
                if not isinstance(payload, dict):
                    raise service.SolveRequestError("La petición debe ser un objeto JSON.")
            except (service.SolveRequestError, TimeoutError) as exc:
                self._error(
                    400, "invalid_request",
                    str(exc) if isinstance(exc, service.SolveRequestError)
                    else "Se agotó la espera del cuerpo JSON.",
                )
                return
        # El chat toma el candado del solver solo mientras calcula (dentro de
        # assist_service); los turnos de conversacion no deben responder 409.
        if self.path == "/assist/chat":
            try:
                self._send(200, assist_service.chat(
                    payload, solve_lock=self.server.solve_lock,
                    runtime=self.server.runtime, runs=self.server.runs,
                ))
            except service.SolveRequestError as exc:
                self._error(400, "invalid_request", str(exc))
            except service.ProviderError as exc:
                self._error(exc.status, exc.code, str(exc))
            except Exception:
                self._error(502, "provider_error", "No se pudo completar el turno del asistente.")
            return
        # Connection changes have their own session lock. Disconnect remains
        # available during a solve and invalidates future remote calls.
        connection_action = self.path in {"/bedrock/session", "/bedrock/disconnect"}
        locked = False if connection_action else self.server.solve_lock.acquire(blocking=False)
        if not connection_action and not locked:
            self._error(
                409,
                "solver_busy",
                "Hay un cálculo o análisis en curso. Espera a que termine.",
            )
            return
        try:
            runtime = self.server.runtime
            if self.path == "/scenarios/hackathon":
                from .scenarios import load_historical_case

                response = {
                    "api_version": service.API_VERSION,
                    **load_historical_case(payload, runtime),
                }
            elif self.path == "/history/upload":
                # Socket timeout measures inactivity, not total upload duration.
                self.connection.settimeout(120)
                profile = runtime.histories.upload(
                    self.rfile, length, unquote(self.headers.get("X-History-Filename", "")),
                )
                response = {"api_version": service.API_VERSION, "profile": profile}
            elif self.path in {"/history/analyze", "/history/remove"}:
                service.object_fields(payload, {"profile_id"}, "histórico", ("profile_id",))
                if self.path == "/history/analyze":
                    response = {
                        "api_version": service.API_VERSION,
                        "profile": runtime.histories.analyze(payload["profile_id"]),
                    }
                else:
                    response = {
                        "api_version": service.API_VERSION,
                        **runtime.histories.remove(payload["profile_id"]),
                    }
            elif self.path == "/bedrock/session":
                response = {"api_version": service.API_VERSION, "status": runtime.bedrock.connect(payload)}
            elif self.path == "/bedrock/disconnect":
                service.object_fields(payload, set(), "desconexión")
                response = {"api_version": service.API_VERSION, "status": runtime.bedrock.disconnect()}
            else:
                response = service.prepare(payload, runtime=runtime) if self.path == "/prepare" \
                    else service.solve(payload, runtime=runtime)
            encoded = service.json_bytes(response)
            if self.path == "/solve":
                self.server.runs.put(response["result"]["run_id"], encoded)
            self._send(200, encoded)
        except service.SolveRequestError as exc:
            self._error(400, "invalid_request", str(exc))
        except service.ProviderError as exc:
            self._error(exc.status, exc.code, str(exc))
        except (ValueError, TimeoutError) as exc:
            from .bedrock_session import BedrockSessionError

            if isinstance(exc, BedrockSessionError):
                self._error(400, exc.code, str(exc))
            else:
                self._error(400, "invalid_history", (
                    "No se pudo leer el histórico. Revisa el formato, las unidades y "
                    "que la carga se haya completado."
                ))
        except Exception:
            self._error(
                502,
                "provider_error",
                "No se pudo completar el cálculo. Revise los datos y el entorno del proveedor.",
            )
        finally:
            if connection_action and isinstance(payload, dict):
                payload.clear()
            if locked:
                self.server.solve_lock.release()

    def do_OPTIONS(self):  # noqa: N802
        self._error(
            405, "method_not_allowed", "La API admite GET y POST desde el mismo origen."
        )

    def log_message(self, *args):
        pass


def make_server(host="127.0.0.1", port=8000, static_root=None, *, runtime=None):
    root = (
        static_root if static_root is not None else Path(__file__).resolve().parents[1] / "webapp"
    )
    return LocalServer(host, port, root, runtime)


def main():
    parser = argparse.ArgumentParser(description="ZMD beta local, webapp + núcleo nativo de Daniel")
    parser.add_argument("--port", type=int, default=8000)
    default_graph = Path(__file__).resolve().parents[1] / "artifacts/network/competition_delivery.graphml"
    parser.add_argument(
        "--graphml", type=Path, default=default_graph if default_graph.is_file() else None,
        help="Red dirigida local; por defecto usa competition_delivery.graphml si existe. No se descarga.",
    )
    parser.add_argument("--network-profile", choices=["drive", "delivery"], default="delivery")
    parser.add_argument("--max-snap-distance-m", type=float, default=100)
    parser.add_argument("--log-directory", type=Path, default=Path("artifacts/webapp"))
    parser.add_argument("--tee", action="store_true", help="Mostrar logs SCIP y decisiones LLM.")
    args = parser.parse_args()
    from .runtime import Runtime

    runtime = Runtime(
        graphml=args.graphml, network_profile=args.network_profile,
        max_snap_distance_m=args.max_snap_distance_m, log_directory=args.log_directory,
        tee=args.tee,
    )
    server = make_server(port=args.port, runtime=runtime)
    print(f"ZMD Integración Beta: http://127.0.0.1:{server.server_port}", flush=True)
    print(
        "Los resultados temporales expiran al reiniciar; salir de la página no cancela el cálculo.",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
