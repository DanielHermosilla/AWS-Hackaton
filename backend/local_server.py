"""Servidor HTTP local que expone la MISMA API que la Lambda.

Permite desarrollar y probar la UI nueva contra un backend real sin desplegar
en AWS. Usa solo la librería estándar (http.server), sin dependencias extra.

Uso:
    python -m backend.local_server
    # luego: POST http://localhost:8000/solve  con el JSON de la instancia

El contrato (rutas y cuerpos) es idéntico al de la Lambda, así que cuando
cambies de local a AWS la UI no necesita cambios salvo la URL base.
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from backend import service

_CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Content-Type": "application/json",
}


class _Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: dict) -> None:
        data = json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        for k, v in _CORS.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):  # noqa: N802
        self._send(200, {"ok": True})

    def do_GET(self):  # noqa: N802
        if self.path.rstrip("/").endswith("/health") or self.path == "/health":
            self._send(200, service.health())
        else:
            self._send(404, {"error": "Ruta no encontrada", "path": self.path})

    def do_POST(self):  # noqa: N802
        if not self.path.rstrip("/").endswith("/solve"):
            self._send(404, {"error": "Ruta no encontrada", "path": self.path})
            return
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as e:
            self._send(400, {"error": "JSON inválido", "detail": str(e)})
            return
        try:
            self._send(200, service.solve(payload))
        except service.SolveRequestError as e:
            self._send(400, {"error": "Petición inválida", "detail": str(e)})
        except Exception as e:  # noqa: BLE001
            self._send(500, {"error": "Error interno", "detail": str(e)})

    def log_message(self, *args):  # silenciar logs ruidosos
        pass


def main(host: str = "127.0.0.1", port: int = 8000) -> None:
    srv = ThreadingHTTPServer((host, port), _Handler)
    print(f"Backend local escuchando en http://{host}:{port}")
    print("  GET  /health")
    print("  POST /solve")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nDetenido.")
        srv.shutdown()


if __name__ == "__main__":
    main()
