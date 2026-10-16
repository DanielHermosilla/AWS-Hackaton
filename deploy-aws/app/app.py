"""Lambda unificada de ZMD Mobility — FastAPI (vía Mangum).

Sirve la webapp estática con login, gestiona cuentas/sesiones/datos por usuario
en DynamoDB y hace de proxy autenticado hacia el solver (ECS Fargate).

Endpoints (contrato en ARQUITECTURA-PLAN-B.md):
  POST /auth/register | /auth/login | /auth/logout
  GET  /auth/me
  GET/POST/DELETE /api/plans[/{plan_id}]
  GET/PUT /api/prefs
  GET/PUT /api/fleet
  GET     /api/activity
  POST /prepare, POST/GET /solve   → proxy al solver
  GET  /{ruta:path}                → webapp estática con protección de rutas

Variables de entorno relevantes:
  DDB_*_TABLE            nombres de tabla (ver db.py)
  COOKIE_SECURE          "1" exige HTTPS en la cookie (producción). Def. "1".
  WEBAPP_DIR             carpeta de estáticos. Def. /var/task/webapp.
  SOLVER_API_URL         base del solver (ver proxy.py)
  SOLVER_INTERNAL_TOKEN  token interno hacia el solver
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import Cookie, FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

import auth
import db
import proxy

# ── Config ──────────────────────────────────────────────────────────────────
WEBAPP_DIR = Path(os.getenv("WEBAPP_DIR", "/var/task/webapp")).resolve()
PROTEGIDAS = {"", "index.html", "plan.html"}  # requieren sesión en la webapp

# Límite de tamaño por plan guardado. Un ítem de DynamoDB no puede superar 400 KB
# en total; serializamos instance/result/kpis a JSON, así que capamos el cuerpo
# bien por debajo para dejar margen a las claves y a la codificación. Evita que
# un usuario autenticado guarde instancias arbitrariamente grandes.
MAX_PLAN_BODY_BYTES = int(os.getenv("MAX_PLAN_BODY_BYTES", str(300 * 1024)))

app = FastAPI(title="ZMD Mobility", docs_url=None, redoc_url=None)


# ── Helper de sesión ──────────────────────────────────────────────────────────
def current_user(request: Request) -> dict | None:
    """Lee la cookie de sesión del request y devuelve {email, nombre, prefs} o None."""
    token = request.cookies.get(auth.SESSION_COOKIE)
    return auth.usuario_de_sesion(token)


def _require(request: Request) -> tuple[dict | None, JSONResponse | None]:
    user = current_user(request)
    if not user:
        return None, JSONResponse({"ok": False, "error": "Sin sesión."}, status_code=401)
    return user, None


# ── Autenticación ──────────────────────────────────────────────────────────────
@app.post("/auth/register")
async def register(request: Request, response: Response):
    ip = request.client.host if request.client else "?"
    if not auth.rate_limit(f"reg:{ip}", limite=5, ventana_s=600):
        return JSONResponse({"ok": False, "error": "Demasiados intentos. Espera unos minutos."}, status_code=429)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "Solicitud inválida."}, status_code=400)
    data, err = auth.validar_registro(body if isinstance(body, dict) else {})
    if err:
        return JSONResponse({"ok": False, "error": err}, status_code=400)
    debil = auth.password_debil(data["password"])
    if debil:
        return JSONResponse({"ok": False, "error": debil}, status_code=400)

    email = data["email"]
    pw_hash = auth.hash_password(data["password"])
    try:
        db.put_user(email, data["nombre"], pw_hash, prefs={})
    except Exception as e:
        if type(e).__name__ == "ConditionalCheckFailedException":
            return JSONResponse({"ok": False, "error": "Ese correo ya está registrado."}, status_code=409)
        raise

    token = auth.crear_sesion(email)
    auth._set_cookie(response, token)
    try:
        db.add_activity(email, "register", {"nombre": data["nombre"]})
    except Exception:
        pass
    return {"ok": True, "usuario": email}


@app.post("/auth/login")
async def login(request: Request, response: Response):
    ip = request.client.host if request.client else "?"
    if not auth.rate_limit(f"log:{ip}", limite=10, ventana_s=600):
        return JSONResponse({"ok": False, "error": "Demasiados intentos. Espera unos minutos."}, status_code=429)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "Solicitud inválida."}, status_code=400)
    data, err = auth.validar_login(body if isinstance(body, dict) else {})
    if err:
        return JSONResponse({"ok": False, "error": err}, status_code=401)

    email = data["email"]
    user = db.get_user(email)
    ok = auth.check_password(data["password"], user.get("password_hash") if user else None)
    if not user or not ok:
        return JSONResponse({"ok": False, "error": "Correo o contraseña incorrectos."}, status_code=401)

    token = auth.crear_sesion(email)
    auth._set_cookie(response, token)
    try:
        db.add_activity(email, "login", None)
    except Exception:
        pass
    return {"ok": True, "usuario": email}


@app.post("/auth/logout")
def logout(response: Response, zmd_session: str | None = Cookie(default=None)):
    auth.borrar_sesion(zmd_session)
    response.delete_cookie(auth.SESSION_COOKIE, path="/")
    return {"ok": True}


@app.get("/auth/me")
def me(zmd_session: str | None = Cookie(default=None)):
    row = auth.usuario_de_sesion(zmd_session)
    if not row:
        return JSONResponse({"ok": False, "error": "Sin sesión."}, status_code=401)
    return {"ok": True, "usuario": row["email"], "nombre": row["nombre"]}


# ── Planes guardados ────────────────────────────────────────────────────────────
@app.get("/api/plans")
def api_list_plans(request: Request):
    user, err = _require(request)
    if err:
        return err
    return {"ok": True, "plans": db.list_plans(user["email"])}


@app.post("/api/plans")
async def api_create_plan(request: Request):
    user, err = _require(request)
    if err:
        return err
    raw = await request.body()
    if len(raw) > MAX_PLAN_BODY_BYTES:
        return JSONResponse(
            {"ok": False, "error": "El plan es demasiado grande para guardarlo."},
            status_code=413,
        )
    try:
        body = json.loads(raw) if raw else None
    except Exception:
        return JSONResponse({"ok": False, "error": "Solicitud inválida."}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"ok": False, "error": "Solicitud inválida."}, status_code=400)
    saved = db.put_plan(
        user["email"],
        {
            "name": body.get("name"),
            "instance": body.get("instance"),
            "result": body.get("result"),
            "kpis": body.get("kpis"),
        },
    )
    try:
        db.add_activity(user["email"], "plan_saved", {"plan_id": saved["plan_id"], "name": saved["name"]})
    except Exception:
        pass
    return {"ok": True, "plan": saved}


@app.get("/api/plans/{plan_id}")
def api_get_plan(plan_id: str, request: Request):
    user, err = _require(request)
    if err:
        return err
    plan = db.get_plan(user["email"], plan_id)
    if not plan:
        return JSONResponse({"ok": False, "error": "Plan no encontrado."}, status_code=404)
    return {"ok": True, "plan": plan}


@app.delete("/api/plans/{plan_id}")
def api_delete_plan(plan_id: str, request: Request):
    user, err = _require(request)
    if err:
        return err
    db.delete_plan(user["email"], plan_id)
    try:
        db.add_activity(user["email"], "plan_deleted", {"plan_id": plan_id})
    except Exception:
        pass
    return {"ok": True}


# ── Preferencias ────────────────────────────────────────────────────────────────
@app.get("/api/prefs")
def api_get_prefs(request: Request):
    user, err = _require(request)
    if err:
        return err
    return {"ok": True, "prefs": user.get("prefs") or {}}


@app.put("/api/prefs")
async def api_put_prefs(request: Request):
    user, err = _require(request)
    if err:
        return err
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "Solicitud inválida."}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"ok": False, "error": "Solicitud inválida."}, status_code=400)
    prefs = {
        "theme": body.get("theme"),
        "solidSurfaces": body.get("solidSurfaces"),
        "reducedMotion": body.get("reducedMotion"),
        "organizationName": body.get("organizationName"),
    }
    prefs = {k: v for k, v in prefs.items() if v is not None}
    db.update_user_prefs(user["email"], prefs)
    return {"ok": True, "prefs": prefs}


# ── Flota / estaciones ──────────────────────────────────────────────────────────
@app.get("/api/fleet")
def api_get_fleet(request: Request):
    user, err = _require(request)
    if err:
        return err
    data = db.get_fleet(user["email"]) or {"vehicles": [], "stations": []}
    return {"ok": True, "fleet": data}


@app.put("/api/fleet")
async def api_put_fleet(request: Request):
    user, err = _require(request)
    if err:
        return err
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "Solicitud inválida."}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"ok": False, "error": "Solicitud inválida."}, status_code=400)
    saved = db.put_fleet(
        user["email"],
        {"vehicles": body.get("vehicles") or [], "stations": body.get("stations") or []},
    )
    return {"ok": True, "fleet": saved}


# ── Historial ────────────────────────────────────────────────────────────────────
@app.get("/api/activity")
def api_activity(request: Request):
    user, err = _require(request)
    if err:
        return err
    return {"ok": True, "activity": db.list_activity(user["email"], limit=50)}


# ── Proxy al solver (requieren sesión) ─────────────────────────────────────────
@app.post("/prepare")
async def prepare(request: Request):
    user, err = _require(request)
    if err:
        return err
    raw = await request.body()
    status, body, ctype = proxy.forward_prepare(raw)
    return Response(content=body, status_code=status, media_type=ctype)


@app.post("/solve")
async def solve_post(request: Request):
    user, err = _require(request)
    if err:
        return err
    raw = await request.body()
    status, body, ctype = proxy.forward_solve_post(raw)
    if status == 200:
        try:
            db.add_activity(user["email"], "solve", None)
        except Exception:
            pass
    return Response(content=body, status_code=status, media_type=ctype)


@app.get("/solve")
def solve_get(request: Request, run_id: str = ""):
    user, err = _require(request)
    if err:
        return err
    status, body, ctype = proxy.forward_solve_get(run_id)
    return Response(content=body, status_code=status, media_type=ctype)


# ── Webapp estática con protección de rutas ────────────────────────────────────
@app.get("/{ruta:path}")
def servir(ruta: str, zmd_session: str | None = Cookie(default=None)):
    objetivo = (WEBAPP_DIR / ruta).resolve()
    # Anti path-traversal: el objetivo debe estar dentro de WEBAPP_DIR.
    if WEBAPP_DIR not in objetivo.parents and objetivo != WEBAPP_DIR:
        return JSONResponse({"error": "ruta no permitida"}, status_code=404)
    nombre = ruta if ruta else "index.html"
    if nombre in PROTEGIDAS and not auth.usuario_de_sesion(zmd_session):
        return _redirect_login(nombre)
    if objetivo.is_dir():
        objetivo = objetivo / "index.html"
    if not objetivo.exists() or not objetivo.is_file():
        objetivo = WEBAPP_DIR / "index.html"
        if nombre in PROTEGIDAS and not auth.usuario_de_sesion(zmd_session):
            return _redirect_login(nombre)
    return FileResponse(objetivo, headers={"X-Content-Type-Options": "nosniff"})


def _redirect_login(nombre: str) -> Response:
    url = "/login.html"
    if nombre and nombre != "index.html":
        url += f"?next={nombre}"
    return RedirectResponse(url, status_code=302)
