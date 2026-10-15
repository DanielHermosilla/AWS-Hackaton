"""Handler Lambda para API Gateway (HTTP API, payload v2).

Es un adaptador fino: traduce el evento HTTP a una llamada al núcleo
(`backend.service`) y devuelve una respuesta HTTP. Sin lógica de negocio aquí.

Rutas:
    GET  /health   -> estado del servicio
    POST /solve    -> resuelve una instancia (cuerpo JSON, ver API_CONTRACT.md)
"""
from __future__ import annotations

import json
from typing import Any, Dict

from backend import service

# CORS abierto para que cualquier UI (vieja o nueva) pueda llamar la API.
# Si luego fijas un dominio concreto, cambia "*" por esa URL.
_CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Content-Type": "application/json",
}


def _resp(status: int, body: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "statusCode": status,
        "headers": _CORS,
        "body": json.dumps(body, ensure_ascii=False, default=str),
    }


def _route(event: Dict[str, Any]) -> tuple[str, str]:
    """Extrae (metodo, path) soportando API Gateway HTTP API v2 y REST v1."""
    ctx = event.get("requestContext", {})
    http = ctx.get("http", {})
    method = http.get("method") or event.get("httpMethod", "GET")
    path = http.get("path") or event.get("rawPath") or event.get("path", "/")
    return method.upper(), path


def handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    method, path = _route(event)

    # Preflight CORS
    if method == "OPTIONS":
        return _resp(200, {"ok": True})

    if path.endswith("/health") and method == "GET":
        return _resp(200, service.health())

    if path.endswith("/solve") and method == "POST":
        raw = event.get("body") or "{}"
        if event.get("isBase64Encoded"):
            import base64

            raw = base64.b64decode(raw).decode("utf-8")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as e:
            return _resp(400, {"error": "JSON inválido", "detail": str(e)})

        try:
            return _resp(200, service.solve(payload))
        except service.SolveRequestError as e:
            return _resp(400, {"error": "Petición inválida", "detail": str(e)})
        except Exception as e:  # noqa: BLE001
            return _resp(500, {"error": "Error interno", "detail": str(e)})

    return _resp(404, {"error": "Ruta no encontrada", "path": path, "method": method})
