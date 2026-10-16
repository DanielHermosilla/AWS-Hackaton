"""Gateway de login delante del backend completo de ZMD Mobility.

Corre en el mismo contenedor que el backend de la app (backend.local_server,
escuchando en 127.0.0.1:8000). Este gateway (puerto 8080) es el ÚNICO expuesto:

  1. Sirve /login.html, /register.html, /auth/* y los estáticos del login.
  2. Verifica la cookie de sesión en cada petición.
  3. Si hay sesión válida  → reenvía la petición al backend interno (localhost).
  4. Si no hay sesión y la ruta está protegida → redirige a /login.html.

El backend interno solo acepta peticiones de 127.0.0.1 con el mismo Host, así que
el gateway las reescribe para que las acepte (Host 127.0.0.1:8000, sin Origin
cruzado). El navegador nunca habla directo con el backend interno.
"""
from __future__ import annotations

import os

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

import auth

BACKEND = os.getenv("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
# Rutas que NO requieren sesión (login/registro y sus recursos).
PUBLIC_PREFIXES = (
    "/login.html", "/register.html", "/login.css", "/login.js",
    "/register.js", "/auth.js", "/assets/", "/vendor/", "/favicon",
)
# Páginas HTML que, sin sesión, redirigen a login (en vez de 401).
PROTECTED_PAGES = {"", "/", "/index.html", "/plan.html"}

app = FastAPI(title="ZMD Mobility Gateway", docs_url=None, redoc_url=None)
_client = httpx.AsyncClient(base_url=BACKEND, timeout=130.0)


def _sesion(request: Request) -> dict | None:
    return auth.usuario_de_sesion(request.cookies.get(auth.SESSION_COOKIE))


def _es_publica(path: str) -> bool:
    return any(path == p or path.startswith(p) for p in PUBLIC_PREFIXES)


# ── Autenticación ──────────────────────────────────────────────────────────────
@app.post("/auth/register")
async def register(request: Request, response: Response):
    ip = request.client.host if request.client else "?"
    if not auth.rate_limit(f"reg:{ip}", 5, 600):
        return JSONResponse({"ok": False, "error": "Demasiados intentos. Espera unos minutos."}, 429)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "Solicitud inválida."}, 400)
    data, err = auth.validar_registro(body if isinstance(body, dict) else {})
    if err:
        return JSONResponse({"ok": False, "error": err}, 400)
    debil = auth.password_debil(data["password"])
    if debil:
        return JSONResponse({"ok": False, "error": debil}, 400)
    try:
        db_put(data)
    except _Exists:
        return JSONResponse({"ok": False, "error": "Ese correo ya está registrado."}, 409)
    token = auth.crear_sesion(data["email"])
    auth.set_cookie(response, token)
    return {"ok": True, "usuario": data["email"]}


class _Exists(Exception):
    pass


def db_put(data: dict) -> None:
    import db
    try:
        db.put_user(data["email"], data["nombre"], auth.hash_password(data["password"]))
    except Exception as e:  # noqa: BLE001
        if type(e).__name__ == "ConditionalCheckFailedException":
            raise _Exists from e
        raise


@app.post("/auth/login")
async def login(request: Request, response: Response):
    ip = request.client.host if request.client else "?"
    if not auth.rate_limit(f"log:{ip}", 10, 600):
        return JSONResponse({"ok": False, "error": "Demasiados intentos. Espera unos minutos."}, 429)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "Solicitud inválida."}, 400)
    data, err = auth.validar_login(body if isinstance(body, dict) else {})
    if err:
        return JSONResponse({"ok": False, "error": err}, 401)
    import db
    user = db.get_user(data["email"])
    ok = auth.check_password(data["password"], user.get("password_hash") if user else None)
    if not user or not ok:
        return JSONResponse({"ok": False, "error": "Correo o contraseña incorrectos."}, 401)
    token = auth.crear_sesion(data["email"])
    auth.set_cookie(response, token)
    return {"ok": True, "usuario": data["email"]}


@app.post("/auth/logout")
async def logout(request: Request):
    auth.borrar_sesion(request.cookies.get(auth.SESSION_COOKIE))
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(auth.SESSION_COOKIE, path="/")
    return resp


@app.get("/auth/me")
async def me(request: Request):
    user = _sesion(request)
    if not user:
        return JSONResponse({"ok": False, "error": "Sin sesión."}, 401)
    return {"ok": True, "usuario": user["email"], "nombre": user["nombre"]}


@app.get("/salud-gateway")
async def salud_gateway():
    """Health check del gateway (sin tocar el backend ni requerir sesión)."""
    return {"ok": True, "service": "zmd-gateway"}


# ── Proxy de todo lo demás al backend interno ──────────────────────────────────
@app.api_route("/{ruta:path}", methods=["GET", "POST", "HEAD"])
async def proxy(ruta: str, request: Request):
    path = "/" + ruta
    # Recursos y páginas de login: pasan sin sesión.
    if not _es_publica(path):
        user = _sesion(request)
        if not user:
            # Páginas HTML protegidas → redirige a login; API → 401.
            if path in PROTECTED_PAGES or path.endswith(".html"):
                destino = "/login.html"
                nombre = path.lstrip("/") or "index.html"
                if nombre != "index.html":
                    destino += f"?next={nombre}"
                return RedirectResponse(destino, status_code=302)
            return JSONResponse({"ok": False, "error": "Sin sesión."}, 401)

    # Reenvía al backend interno reescribiendo Host/Origin para el mismo origen.
    body = await request.body()
    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in {"host", "origin", "cookie", "content-length", "connection",
                             "sec-fetch-site", "sec-fetch-mode", "accept-encoding"}
    }
    backend_host = BACKEND.split("://", 1)[-1]
    headers["host"] = backend_host
    try:
        upstream = await _client.request(
            request.method,
            path,
            params=dict(request.query_params),
            content=body,
            headers=headers,
        )
    except httpx.RequestError as e:
        return JSONResponse(
            {"api_version": "3.0",
             "error": {"code": "backend_unreachable", "message": f"Backend no disponible: {e}"}},
            status_code=502,
        )
    resp_headers = {
        k: v for k, v in upstream.headers.items()
        if k.lower() not in {"content-length", "connection", "transfer-encoding"}
    }
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=resp_headers,
        media_type=upstream.headers.get("content-type"),
    )
