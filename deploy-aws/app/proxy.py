"""Reenvío autenticado hacia el solver (ECS Fargate) para /prepare y /solve.

El navegador llama a la Lambda; la Lambda reenvía el cuerpo *tal cual* al solver
real añadiendo el header interno `X-Solver-Token`. El token nunca llega al
navegador (contrato de ARQUITECTURA-PLAN-B.md).

Se usa `urllib.request` de la stdlib para no añadir dependencias extra.

Config por variables de entorno:
  SOLVER_API_URL         base del solver, p.ej. http://zmd-solver-api.internal:8000
  SOLVER_INTERNAL_TOKEN  token compartido que autoriza a la Lambda ante el solver
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

TIMEOUT_S = 120
API_VERSION = "3.0"


def _solver_url() -> str | None:
    url = os.getenv("SOLVER_API_URL", "").strip()
    return url.rstrip("/") if url else None


def _token() -> str:
    return os.getenv("SOLVER_INTERNAL_TOKEN", "")


def _error(code: str, message: str) -> bytes:
    return json.dumps(
        {"api_version": API_VERSION, "error": {"code": code, "message": message}}
    ).encode()


def _unconfigured() -> tuple[int, bytes, str]:
    return (
        503,
        _error("solver_not_configured", "El solver no está configurado (falta SOLVER_API_URL)."),
        "application/json",
    )


def _do_request(req: urllib.request.Request) -> tuple[int, bytes, str]:
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            body = resp.read()
            ctype = resp.headers.get("Content-Type", "application/json")
            return resp.status, body, ctype
    except urllib.error.HTTPError as e:
        # El solver respondió con un error HTTP: propagamos su cuerpo y estado.
        body = e.read() if hasattr(e, "read") else b""
        ctype = e.headers.get("Content-Type", "application/json") if e.headers else "application/json"
        if not body:
            body = _error("solver_error", f"El solver devolvió un error {e.code}.")
            ctype = "application/json"
        return e.code, body, ctype
    except urllib.error.URLError as e:
        return (
            502,
            _error("solver_unreachable", f"No se pudo contactar al solver: {e.reason}."),
            "application/json",
        )
    except TimeoutError:
        return (
            502,
            _error("solver_unreachable", "El solver no respondió a tiempo (timeout)."),
            "application/json",
        )


def _post(path: str, body_bytes: bytes) -> tuple[int, bytes, str]:
    base = _solver_url()
    if not base:
        return _unconfigured()
    req = urllib.request.Request(
        f"{base}{path}",
        data=body_bytes,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Solver-Token": _token(),
        },
    )
    return _do_request(req)


def forward_prepare(body_bytes: bytes) -> tuple[int, bytes, str]:
    return _post("/prepare", body_bytes)


def forward_solve_post(body_bytes: bytes) -> tuple[int, bytes, str]:
    return _post("/solve", body_bytes)


def forward_solve_get(run_id: str) -> tuple[int, bytes, str]:
    base = _solver_url()
    if not base:
        return _unconfigured()
    from urllib.parse import urlencode

    url = f"{base}/solve?{urlencode({'run_id': run_id})}"
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Content-Type": "application/json",
            "X-Solver-Token": _token(),
        },
    )
    return _do_request(req)
