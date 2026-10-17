"""Verifica el fix [#4] en el backend: si GATEWAY_SHARED_SECRET está definido,
el backend exige la cabecera X-Gateway-Auth (salvo /health).

Arranca un LocalServer real en 127.0.0.1 con un runtime mínimo simulado y
golpea /health y /scenarios/hackathon con y sin la firma.
"""
import os
import sys
import http.client
from pathlib import Path

os.environ["GATEWAY_SHARED_SECRET"] = "sek-backend-123"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import local_server


class _Bedrock:
    def status(self): return {"model_id": "", "region": "us-east-1", "profile": None}


class _Runtime:
    def __init__(self):
        self.bedrock = _Bedrock()
        self.graphml = None
        self.tee = False
    def close(self): pass


# static_root: usa la webapp si existe; si no, un dir temporal con un index.
static_root = ROOT / "webapp"
if not static_root.is_dir():
    static_root = Path(os.getcwd())

srv = local_server.LocalServer("127.0.0.1", 0, static_root, runtime=_Runtime())
port = srv.server_port

import threading
t = threading.Thread(target=srv.serve_forever, daemon=True)
t.start()


def pedir(path, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    h = {"Host": f"127.0.0.1:{port}"}
    if headers:
        h.update(headers)
    conn.request("GET", path, headers=h)
    r = conn.getresponse()
    r.read()
    conn.close()
    return r.status


try:
    # /health exento: funciona sin firma
    assert pedir("/health") == 200, "health sin firma debería ser 200"
    print("[B1] /health sin firma → 200 (exento) OK")

    # endpoint normal SIN firma → 403
    s = pedir("/bedrock/session")
    assert s == 403, f"sin firma debería 403, fue {s}"
    print("[B2] /bedrock/session sin firma → 403 OK  [#4]")

    # endpoint normal CON firma correcta → 200
    s = pedir("/bedrock/session", {"X-Gateway-Auth": "sek-backend-123"})
    assert s == 200, f"con firma debería 200, fue {s}"
    print("[B3] /bedrock/session con firma correcta → 200 OK  [#4]")

    # firma incorrecta → 403
    s = pedir("/bedrock/session", {"X-Gateway-Auth": "mala"})
    assert s == 403, f"firma mala debería 403, fue {s}"
    print("[B4] /bedrock/session con firma incorrecta → 403 OK  [#4]")

    print("\n==== BACKEND [#4]: TODAS LAS COMPROBACIONES PASARON ====")
finally:
    srv.shutdown()
    srv.server_close()
