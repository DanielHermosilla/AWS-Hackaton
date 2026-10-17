"""Verificación local del gateway endurecido (sin DynamoDB ni backend reales).

Cubre la funcionalidad original (registro/login/logout/sesión/proxy/protección)
MÁS los fixes de seguridad:
  [#3] CSRF: POST de distinto origen (Sec-Fetch-Site: cross-site) → 403.
  [#7] Cabeceras de seguridad presentes en toda respuesta.
  [#8] Cuerpo de /auth/* por encima del límite → 413.
  [#9] El proxy reenvía solo cabeceras de la lista blanca y añade X-Gateway-*.
  [#4] El gateway firma hacia el backend con X-Gateway-Auth y X-Gateway-User.
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

os.environ["COOKIE_SECURE"] = "0"           # TestClient usa http://, no https
os.environ["GATEWAY_SHARED_SECRET"] = "secreto-de-prueba-123"  # [#4]

# boto3 real pero con resource() mockeado
import boto3
_store = {"users": {}, "sessions": {}}
class _T:
    def __init__(self, n): self.n = n
    def _d(self): return _store["users"] if "user" in self.n else _store["sessions"]
    def _key_attr(self): return "email" if "user" in self.n else "token_hash"
    def get_item(self, Key):
        k = list(Key.values())[0]; d = self._d()
        return {"Item": d[k]} if k in d else {}
    def put_item(self, Item, ConditionExpression=None):
        d = self._d(); key = Item[self._key_attr()]
        if ConditionExpression and key in d:
            raise type("ConditionalCheckFailedException", (Exception,), {})()
        d[key] = Item
    def delete_item(self, Key):
        self._d().pop(list(Key.values())[0], None)
class _DDB:
    def Table(self, n): return _T(n)
boto3.resource = lambda *a, **k: _DDB()

import gateway
from fastapi.testclient import TestClient

# Mock del cliente httpx hacia el backend interno: captura las cabeceras que el
# gateway reenvía, para verificar lista blanca y firma.
_ultimas = {"headers": None, "method": None, "path": None}
class _FakeResp:
    def __init__(self): self.status_code=200; self.content=b'{"ok":"backend"}'; self.headers={"content-type":"application/json"}
async def _fake_request(method, path, **kw):
    _ultimas["headers"] = {k.lower(): v for k, v in (kw.get("headers") or {}).items()}
    _ultimas["method"], _ultimas["path"] = method, path
    return _FakeResp()
gateway._client.request = _fake_request

# Cabecera que hace que el TestClient parezca mismo origen (fetch de la webapp).
MISMO_ORIGEN = {"X-Requested-With": "zmd-webapp"}

c = TestClient(gateway.app)

# ── Funcionalidad original ───────────────────────────────────────────────────
assert c.get("/salud-gateway").status_code == 200
print("[1] /salud-gateway OK")

r = c.post("/auth/register",
           json={"nombre":"Max","email":"max@test.com","password":"Clave-Fuerte99"},
           headers=MISMO_ORIGEN)
assert r.status_code == 200, (r.status_code, r.text)
print("[2] register OK")

assert c.get("/auth/me").status_code == 200
print("[3] /auth/me con sesión (post-registro) OK")

assert c.post("/auth/logout", headers=MISMO_ORIGEN).status_code == 200
assert c.get("/auth/me").status_code == 401
print("[4] logout → /auth/me 401 OK")

r2 = c.post("/auth/login", json={"email":"max@test.com","password":"Clave-Fuerte99"},
            headers=MISMO_ORIGEN)
assert r2.status_code == 200, (r2.status_code, r2.text)
assert c.get("/auth/me").status_code == 200
print("[5] login OK")

assert c.post("/auth/register",
              json={"nombre":"x","email":"a@b.com","password":"corta"},
              headers=MISMO_ORIGEN).status_code == 400
print("[6] password débil rechazada OK")

r6 = c.get("/solve?run_id=x", follow_redirects=False)
assert r6.status_code == 200, r6.status_code
print("[7] /solve con sesión → proxy al backend OK")

# cliente NUEVO sin sesión
c2 = TestClient(gateway.app)
assert c2.get("/auth/me").status_code == 401
r3 = c2.get("/index.html", follow_redirects=False)
assert r3.status_code == 302 and "/login.html" in r3.headers.get("location",""), r3.status_code
print("[8] /index.html sin sesión → 302 a /login.html OK")
r4 = c2.get("/plan.html", follow_redirects=False)
assert r4.status_code == 302 and "next=plan.html" in r4.headers.get("location",""), r4.headers.get("location")
print("[9] /plan.html sin sesión → 302 con next OK")
r5 = c2.get("/solve", follow_redirects=False)
assert r5.status_code == 401, r5.status_code
print("[10] /solve sin sesión → 401 OK")

# ── Fixes de seguridad ───────────────────────────────────────────────────────

# [#3] CSRF: login desde origen cruzado → 403
rc = c2.post("/auth/login", json={"email":"max@test.com","password":"Clave-Fuerte99"},
             headers={"Sec-Fetch-Site": "cross-site"})
assert rc.status_code == 403, (rc.status_code, rc.text)
print("[11] CSRF: login cross-site → 403 OK  [#3]")

# [#3] CSRF: POST autenticado al proxy desde origen cruzado → 403
rc2 = c.post("/history/analyze", json={"profile_id":"x"},
             headers={"Sec-Fetch-Site": "cross-site", "Content-Type": "application/json"})
assert rc2.status_code == 403, (rc2.status_code, rc2.text)
print("[12] CSRF: proxy POST cross-site → 403 OK  [#3]")

# [#3] Mismo origen (same-origin) sí pasa
rc3 = c.post("/history/analyze", json={"profile_id":"x"},
             headers={"Sec-Fetch-Site": "same-origin", "Content-Type": "application/json"})
assert rc3.status_code == 200, (rc3.status_code, rc3.text)
print("[13] proxy POST same-origin → 200 OK  [#3]")

# [#7] Cabeceras de seguridad presentes
h = c.get("/salud-gateway").headers
for clave in ("x-content-type-options", "x-frame-options", "content-security-policy", "referrer-policy"):
    assert clave in {k.lower() for k in h.keys()}, clave
print("[14] cabeceras de seguridad presentes OK  [#7]")

# [#8] Cuerpo de /auth/* demasiado grande → 413
grande = "A" * (gateway.MAX_AUTH_BODY_BYTES + 100)
rb = c.post("/auth/login", json={"email":"max@test.com","password":grande},
            headers=MISMO_ORIGEN)
assert rb.status_code == 413, (rb.status_code, rb.text)
print("[15] /auth/login cuerpo gigante → 413 OK  [#8]")

# [#9] + [#4] El proxy reenvía solo lista blanca y añade firma + usuario
_ultimas["headers"] = None
c.get("/health", headers={"X-Forwarded-For": "1.2.3.4", "X-Evil": "1",
                          "Accept": "application/json"})
fw = _ultimas["headers"]
assert "x-forwarded-for" not in fw and "x-evil" not in fw, fw
assert fw.get("accept") == "application/json", fw
assert "cookie" not in fw, fw
print("[16] proxy reenvía solo lista blanca OK  [#9]")
assert fw.get("x-gateway-auth") == "secreto-de-prueba-123", fw
assert fw.get("x-gateway-user") == "max@test.com", fw
print("[17] proxy firma X-Gateway-Auth + X-Gateway-User OK  [#4]")

print("\n==== GATEWAY ENDURECIDO: TODAS LAS COMPROBACIONES PASARON ====")
