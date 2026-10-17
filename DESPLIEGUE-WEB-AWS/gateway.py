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

Endurecimiento de seguridad (ver ../AUDITORIA-SEGURIDAD.md):
  - CSRF: los POST autenticados por cookie exigen mismo origen (Origin /
    Sec-Fetch-Site) o la cabecera X-Requested-With (fetch no permite forjarla
    entre orígenes sin preflight).  [#3]
  - Backend: el gateway firma cada petición con un secreto compartido y propaga
    el usuario autenticado; el backend puede exigirlo y aislar por usuario.  [#4]
  - Cabeceras de seguridad (CSP, HSTS, X-Frame-Options, nosniff) en todas las
    respuestas.  [#7]
  - Límite de tamaño de cuerpo en /auth/* antes de leerlo.  [#8]
  - Reenvío de cabeceras del cliente por lista BLANCA, no negra.  [#9]
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

# [#8] Cuerpo máximo admitido en los endpoints de autenticación (login/registro
# son objetos JSON pequeños). El backend interno aplica sus propios límites a
# /solve, /prepare, etc.; aquí solo acotamos lo que el gateway lee directamente.
MAX_AUTH_BODY_BYTES = 8 * 1024

# [#4] Secreto compartido gateway→backend. Si está definido (recomendado en el
# contenedor), el gateway firma cada petición reenviada y el backend puede
# exigirlo para no confiar ciegamente en cualquier conexión al loopback.
GATEWAY_SHARED_SECRET = os.getenv("GATEWAY_SHARED_SECRET", "")

# [#9] Cabeceras del cliente que SÍ se reenvían al backend interno. Todo lo demás
# (incluidas X-Forwarded-*, X-Real-IP, cookies, Origin…) se descarta.
FORWARD_ALLOWLIST = {
    "content-type", "accept", "accept-language", "user-agent",
    "x-history-filename",
}

# [#7] Cabeceras de seguridad añadidas a toda respuesta del gateway.
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data: https:; "
        "style-src 'self' 'unsafe-inline'; "
        "connect-src 'self' https:; frame-ancestors 'none'; base-uri 'self'; "
        "form-action 'self'"
    ),
}
# HSTS solo tiene sentido si el borde entrega HTTPS (API Gateway/ALB). Se activa
# cuando la cookie es Secure (mismo supuesto de despliegue en producción).
if auth.COOKIE_SECURE:
    SECURITY_HEADERS["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

app = FastAPI(title="ZMD Mobility Gateway", docs_url=None, redoc_url=None)
_client = httpx.AsyncClient(base_url=BACKEND, timeout=130.0)


@app.middleware("http")
async def _cabeceras_seguridad(request: Request, call_next):
    response = await call_next(request)
    for clave, valor in SECURITY_HEADERS.items():
        response.headers.setdefault(clave, valor)
    return response


def _sesion(request: Request) -> dict | None:
    return auth.usuario_de_sesion(request.cookies.get(auth.SESSION_COOKIE))


def _es_publica(path: str) -> bool:
    return any(path == p or path.startswith(p) for p in PUBLIC_PREFIXES)


def _origen_confiable(request: Request) -> bool:
    """[#3] ¿La petición proviene del mismo origen o de nuestra propia webapp?

    Acepta si:
      - Sec-Fetch-Site es 'same-origin'/'same-site'/'none' (navegadores modernos), o
      - el Origin coincide con el host de la petición, o
      - trae X-Requested-With (fetch no puede añadirla entre orígenes sin
        preflight CORS, que no habilitamos).
    Rechaza explícitamente Sec-Fetch-Site: cross-site.
    """
    sec_fetch = request.headers.get("sec-fetch-site")
    if sec_fetch:
        return sec_fetch in {"same-origin", "same-site", "none"}
    origin = request.headers.get("origin")
    if origin is not None:
        host = request.headers.get("host", "")
        return origin.split("://", 1)[-1] == host
    # Sin Sec-Fetch-Site ni Origin: exige la cabecera personalizada del cliente.
    return request.headers.get("x-requested-with") == "zmd-webapp"


async def _leer_json_limitado(request: Request, limite: int):
    """[#8] Lee el cuerpo JSON rechazando lo que exceda `limite` bytes."""
    longitud = request.headers.get("content-length")
    if longitud is not None and longitud.isdigit() and int(longitud) > limite:
        return None, "payload_too_large"
    body = await request.body()
    if len(body) > limite:
        return None, "payload_too_large"
    try:
        import json

        return json.loads(body or b"{}"), None
    except Exception:
        return None, "invalid_json"


def _rechazo_csrf() -> JSONResponse:
    return JSONResponse(
        {"ok": False, "error": "Origen no permitido para esta acción."}, 403
    )


# ── Autenticación ──────────────────────────────────────────────────────────────
@app.post("/auth/register")
async def register(request: Request, response: Response):
    if not _origen_confiable(request):
        return _rechazo_csrf()
    ip = request.client.host if request.client else "?"
    if not auth.rate_limit(f"reg:{ip}", 5, 600):
        return JSONResponse({"ok": False, "error": "Demasiados intentos. Espera unos minutos."}, 429)
    body, err = await _leer_json_limitado(request, MAX_AUTH_BODY_BYTES)
    if err == "payload_too_large":
        return JSONResponse({"ok": False, "error": "Solicitud demasiado grande."}, 413)
    if err or not isinstance(body, dict):
        return JSONResponse({"ok": False, "error": "Solicitud inválida."}, 400)
    data, err = auth.validar_registro(body)
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
    if not _origen_confiable(request):
        return _rechazo_csrf()
    ip = request.client.host if request.client else "?"
    if not auth.rate_limit(f"log:{ip}", 10, 600):
        return JSONResponse({"ok": False, "error": "Demasiados intentos. Espera unos minutos."}, 429)
    body, err = await _leer_json_limitado(request, MAX_AUTH_BODY_BYTES)
    if err == "payload_too_large":
        return JSONResponse({"ok": False, "error": "Solicitud demasiado grande."}, 413)
    if err or not isinstance(body, dict):
        return JSONResponse({"ok": False, "error": "Solicitud inválida."}, 400)
    data, err = auth.validar_login(body)
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
    # El logout solo borra la sesión del propio navegador; exigir mismo origen
    # evita que un sitio ajeno cierre la sesión del usuario (CSRF de logout).
    if not _origen_confiable(request):
        return _rechazo_csrf()
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
    user = None
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
        # [#3] Las acciones con efectos (POST autenticado) exigen mismo origen.
        if request.method == "POST" and not _origen_confiable(request):
            return _rechazo_csrf()

    # Reenvía al backend interno con lista BLANCA de cabeceras. [#9]
    body = await request.body()
    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() in FORWARD_ALLOWLIST
    }
    backend_host = BACKEND.split("://", 1)[-1]
    headers["host"] = backend_host
    # [#4] Firma del gateway + identidad del usuario para que el backend confíe
    # solo en peticiones que pasaron por aquí y pueda aislar datos por usuario.
    if GATEWAY_SHARED_SECRET:
        headers["x-gateway-auth"] = GATEWAY_SHARED_SECRET
    if user is not None:
        headers["x-gateway-user"] = user["email"]
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
