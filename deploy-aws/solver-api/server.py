"""FastAPI wrapper around backend.service for ECS Fargate (Plan B solver API).

This is the network transport for the native API 3.0 engine (``backend/service.py``).
It replicates the semantics of ``backend/local_server.py`` (8 MiB body limit, one
solve at a time via a non-blocking lock -> 409 ``solver_busy``, an in-memory
``RunStore`` keeping up to 4 runs for ``GET /solve?run_id=...``, and the error
mapping of the service layer) but WITHOUT the same-origin/loopback restriction,
because it now runs on Fargate behind the Lambda proxy. Instead it authenticates
every ``/prepare`` and ``/solve`` call with a constant-time check of the
``X-Solver-Token`` header against ``SOLVER_INTERNAL_TOKEN``. ``/health`` is left
unauthenticated for the ECS container health check.
"""

from __future__ import annotations

import hmac
import logging
import os
import sys
import threading
import uuid
from collections import OrderedDict
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

# ---------------------------------------------------------------------------
# Make ``backend`` importable.
#
# In the container we `pip install -e .` the engine package and COPY backend/ to
# /app/backend, so ``from backend import service`` resolves against /app. When
# running from a source checkout (e.g. local dev / tests), add the repo root to
# sys.path so the same import works. The repo root is the parent of backend/.
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend import service  # noqa: E402  (import after sys.path tweak)

logger = logging.getLogger("solver_api")
logging.basicConfig(level=logging.INFO)

MAX_BODY_BYTES = 8 * 1024 * 1024  # 8 MiB, matches local_server.py
TOKEN_HEADER = "X-Solver-Token"


# ---------------------------------------------------------------------------
# RunStore: in-memory, bounded ephemeral storage of solve results.
# Direct port of backend/local_server.py RunStore (OrderedDict, max 4 runs,
# 32 MiB cap, LRU-style eviction, raises ProviderError 413 if a single result
# is larger than the whole budget).
# ---------------------------------------------------------------------------
class RunStore:
    def __init__(self, max_runs: int = 4, max_bytes: int = 32 * 1024 * 1024):
        self.max_runs, self.max_bytes = max_runs, max_bytes
        self.runs: "OrderedDict[str, bytes]" = OrderedDict()
        self.size = 0
        self.lock = threading.Lock()

    def put(self, run_id: str, data: bytes) -> None:
        if len(data) > self.max_bytes:
            raise service.ProviderError(
                "El resultado excede el almacenamiento temporal de esta beta.",
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

    def get(self, run_id: str) -> bytes | None:
        with self.lock:
            return self.runs.get(run_id)


# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------
_RUNS = RunStore()
_SOLVE_LOCK = threading.Lock()  # one solve at a time (non-blocking acquire -> 409)


def _internal_token() -> str:
    return os.environ.get("SOLVER_INTERNAL_TOKEN", "") or ""


# Warn once at import time if auth is disabled (dev/local open mode).
if not _internal_token():
    logger.warning(
        "SOLVER_INTERNAL_TOKEN is empty: solver API running in OPEN mode "
        "(no X-Solver-Token required). Do NOT use this in a shared/public deployment."
    )


# ---------------------------------------------------------------------------
# Helpers for consistent JSON responses (service.json_bytes -> allow_nan=False)
# ---------------------------------------------------------------------------
_SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}


def _json_response(status: int, payload) -> Response:
    """Serialize with the service's canonical encoder (ensures finite JSON)."""
    body = service.json_bytes(payload)
    return Response(
        content=body,
        status_code=status,
        media_type="application/json",
        headers=dict(_SECURITY_HEADERS),
    )


def _error(status: int, code: str, message: str) -> Response:
    return _json_response(
        status,
        {"api_version": service.API_VERSION, "error": {"code": code, "message": message}},
    )


def _check_auth(request: Request) -> Response | None:
    """Return an error Response if auth fails, else None.

    Open mode (empty SOLVER_INTERNAL_TOKEN) accepts everything. Otherwise the
    X-Solver-Token header must match in constant time.
    """
    expected = _internal_token()
    if not expected:
        return None  # open mode (dev)
    provided = request.headers.get(TOKEN_HEADER, "") or ""
    if not hmac.compare_digest(provided, expected):
        return _error(
            401,
            "unauthorized",
            "Falta o no coincide el encabezado X-Solver-Token.",
        )
    return None


async def _read_body_limited(request: Request) -> bytes:
    """Read the request body enforcing the 8 MiB limit.

    Raises ``service.ProviderError('payload_too_large', 413)`` if exceeded. We
    check Content-Length when present (fast reject) and also enforce while
    streaming so a lying/absent length cannot bypass the cap.
    """
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise service.ProviderError(
            "La petición supera el límite de 8 MiB.", "payload_too_large", 413
        )
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_BODY_BYTES:
            raise service.ProviderError(
                "La petición supera el límite de 8 MiB.", "payload_too_large", 413
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _run_engine(request_body: bytes, kind: str) -> Response:
    """Shared body for POST /prepare and POST /solve.

    kind is "prepare" or "solve". Parses JSON strictly, runs the engine, maps
    errors to the service's status/code contract, and (for solve) stores the
    result in the RunStore.
    """
    try:
        payload = service.strict_loads(request_body)
        if not isinstance(payload, dict):
            raise service.SolveRequestError("La petición debe ser un objeto JSON.")
    except service.SolveRequestError as exc:
        return _error(400, "invalid_request", str(exc))

    # One solve/prepare at a time (the engine holds a single SCIP process worth
    # of memory). Non-blocking acquire -> 409 busy, matching local_server.py.
    if not _SOLVE_LOCK.acquire(blocking=False):
        return _error(
            409,
            "solver_busy",
            "Hay un cálculo en curso. Espere a que termine antes de volver a calcular.",
        )
    try:
        if kind == "prepare":
            response_obj = service.prepare(payload)
        else:
            response_obj = service.solve(payload)
        encoded = service.json_bytes(response_obj)
        if kind == "solve":
            _RUNS.put(response_obj["result"]["run_id"], encoded)
        return Response(
            content=encoded,
            status_code=200,
            media_type="application/json",
            headers=dict(_SECURITY_HEADERS),
        )
    except service.SolveRequestError as exc:
        return _error(400, "invalid_request", str(exc))
    except service.ProviderError as exc:
        return _error(exc.status, exc.code, str(exc))
    except Exception:  # noqa: BLE001 - last-resort provider failure
        logger.exception("Unhandled error during %s", kind)
        return _error(
            502,
            "provider_error",
            "No se pudo completar el cálculo. Revise los datos y el entorno del proveedor.",
        )
    finally:
        _SOLVE_LOCK.release()


# ---------------------------------------------------------------------------
# App + routes
# ---------------------------------------------------------------------------
app = FastAPI(title="ZMD Solver API", version=service.API_VERSION)


@app.get("/health")
async def health() -> Response:
    """Unauthenticated: used by the ECS container health check."""
    return _json_response(200, service.health())


@app.post("/prepare")
async def prepare_endpoint(request: Request) -> Response:
    auth_error = _check_auth(request)
    if auth_error is not None:
        return auth_error
    try:
        body = await _read_body_limited(request)
    except service.ProviderError as exc:
        return _error(exc.status, exc.code, str(exc))
    return _run_engine(body, "prepare")


@app.post("/solve")
async def solve_post(request: Request) -> Response:
    auth_error = _check_auth(request)
    if auth_error is not None:
        return auth_error
    try:
        body = await _read_body_limited(request)
    except service.ProviderError as exc:
        return _error(exc.status, exc.code, str(exc))
    return _run_engine(body, "solve")


@app.get("/solve")
async def solve_get(request: Request) -> Response:
    auth_error = _check_auth(request)
    if auth_error is not None:
        return auth_error
    params = request.query_params
    run_id = params.get("run_id")
    # Exactly one run_id param, and it must be a canonical UUID string.
    if run_id is None or len(params.getlist("run_id")) != 1 or set(params) != {"run_id"}:
        return _error(
            400, "invalid_run_id", "Indique un run_id válido para recuperar el resultado."
        )
    try:
        if str(uuid.UUID(run_id)) != run_id:
            raise ValueError
    except ValueError:
        return _error(
            400, "invalid_run_id", "Indique un run_id válido para recuperar el resultado."
        )
    data = _RUNS.get(run_id)
    if data is None:
        return _error(
            404,
            "run_expired",
            "El resultado ya no está disponible; calcule de nuevo o abra su exportación.",
        )
    return Response(
        content=data,
        status_code=200,
        media_type="application/json",
        headers=dict(_SECURITY_HEADERS),
    )


def main() -> None:
    import uvicorn

    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
