"""Backend de autenticación de ZMD Mobility — versión AWS (FastAPI + DynamoDB + bcrypt).

Adaptación del backend original (SQLite) para desplegar en AWS, donde Lambda/
contenedores no tienen disco persistente. La lógica de seguridad es idéntica a
la original; solo cambia la capa de almacenamiento a DynamoDB.

Endpoints:
  POST /auth/register   crear cuenta (hash bcrypt)
  POST /auth/login      iniciar sesión (cookie httpOnly)
  POST /auth/logout     cerrar sesión (invalida token)
  GET  /auth/me         usuario de la sesión actual (401 si no hay)
  GET  /{ruta}          sirve la webapp estática con protección de rutas

Variables de entorno:
  DDB_USERS_TABLE      nombre de la tabla DynamoDB de usuarios (def. zmd_users)
  DDB_SESSIONS_TABLE   nombre de la tabla DynamoDB de sesiones (def. zmd_sessions)
  WEBAPP_DIR           carpeta con los estáticos de la webapp (def. ../webapp)
  COOKIE_SECURE        "1" para exigir HTTPS en la cookie (producción). Def. "1".
"""
from __future__ import annotations

import hashlib
import os
import re
import secrets
import time
from pathlib import Path

import bcrypt
import boto3
from boto3.dynamodb.conditions import Key
from fastapi import Cookie, FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

# ── Config ──────────────────────────────────────────────────────────────────
WEBAPP_DIR = Path(os.getenv("WEBAPP_DIR", Path(__file__).resolve().parent.parent / "webapp")).resolve()
USERS_TABLE = os.getenv("DDB_USERS_TABLE", "zmd_users")
SESSIONS_TABLE = os.getenv("DDB_SESSIONS_TABLE", "zmd_sessions")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "1") == "1"

SESSION_COOKIE = "zmd_session"
SESSION_TTL_S = 60 * 60 * 8  # 8 horas
PROTEGIDAS = {"", "index.html", "plan.html"}  # requieren sesión

app = FastAPI(title="ZMD Mobility Auth (AWS)", docs_url=None, redoc_url=None)

_ddb = boto3.resource("dynamodb")
_users = _ddb.Table(USERS_TABLE)
_sessions = _ddb.Table(SESSIONS_TABLE)


# ── Utilidades de seguridad (idénticas al original) ───────────────────────────
def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def crear_sesion(email: str) -> str:
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    _sessions.put_item(
        Item={
            "token_hash": hash_token(token),
            "email": email,
            "created_at": now,
            "expires_at": now + SESSION_TTL_S,  # también sirve como TTL de DynamoDB
        }
    )
    return token


def usuario_de_sesion(token: str | None) -> dict | None:
    if not token:
        return None
    now = int(time.time())
    sess = _sessions.get_item(Key={"token_hash": hash_token(token)}).get("Item")
    if not sess or int(sess.get("expires_at", 0)) <= now:
        return None
    user = _users.get_item(Key={"email": sess["email"]}).get("Item")
    if not user:
        return None
    return {"email": user["email"], "nombre": user["nombre"]}


def borrar_sesion(token: str | None) -> None:
    if not token:
        return
    _sessions.delete_item(Key={"token_hash": hash_token(token)})


PASS_RE = [
    (r".{10,}", "al menos 10 caracteres"),
    (r"[A-Z]", "una mayúscula"),
    (r"[a-z]", "una minúscula"),
    (r"\d", "un número"),
    (r"[^A-Za-z0-9]", "un símbolo"),
]


def password_debil(p: str) -> str | None:
    for patron, desc in PASS_RE:
        if not re.search(patron, p):
            return f"La contraseña necesita {desc}."
    return None


# ── Rate limiting en memoria (por IP + acción) ────────────────────────────────
_intentos: dict[str, list[float]] = {}


def rate_limit(clave: str, limite: int, ventana_s: int) -> bool:
    now = time.time()
    marcas = [t for t in _intentos.get(clave, []) if now - t < ventana_s]
    marcas.append(now)
    _intentos[clave] = marcas
    return len(marcas) <= limite


# ── Validación de entrada ──────────────────────────────────────────────────────
EMAIL_SERVER_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def validar_registro(body: dict) -> tuple[dict | None, str | None]:
    nombre = str(body.get("nombre", "")).strip()
    email = str(body.get("email", "")).strip().lower()
    password = str(body.get("password", ""))
    if not nombre or len(nombre) > 80:
        return None, "El nombre es obligatorio (máx. 80 caracteres)."
    if not EMAIL_SERVER_RE.match(email) or len(email) > 254:
        return None, "El correo no es válido."
    if not password or len(password) > 200:
        return None, "La contraseña no es válida."
    return {"nombre": nombre, "email": email, "password": password}, None


def validar_login(body: dict) -> tuple[dict | None, str | None]:
    email = str(body.get("email", "")).strip().lower()
    password = str(body.get("password", ""))
    if not EMAIL_SERVER_RE.match(email) or not password:
        return None, "Correo o contraseña incorrectos."
    return {"email": email, "password": password}, None


# ── Endpoints de autenticación ────────────────────────────────────────────────
@app.post("/auth/register")
async def register(request: Request, response: Response):
    ip = request.client.host if request.client else "?"
    if not rate_limit(f"reg:{ip}", limite=5, ventana_s=600):
        return JSONResponse({"ok": False, "error": "Demasiados intentos. Espera unos minutos."}, status_code=429)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "Solicitud inválida."}, status_code=400)
    data, err = validar_registro(body if isinstance(body, dict) else {})
    if err:
        return JSONResponse({"ok": False, "error": err}, status_code=400)
    debil = password_debil(data["password"])
    if debil:
        return JSONResponse({"ok": False, "error": debil}, status_code=400)

    email = data["email"]
    # Unicidad: condición de que el email no exista aún.
    pw_hash = bcrypt.hashpw(data["password"].encode(), bcrypt.gensalt()).decode()
    now = int(time.time())
    try:
        _users.put_item(
            Item={"email": email, "nombre": data["nombre"], "password_hash": pw_hash, "created_at": now},
            ConditionExpression="attribute_not_exists(email)",
        )
    except _ddb.meta.client.exceptions.ConditionalCheckFailedException:
        return JSONResponse({"ok": False, "error": "Ese correo ya está registrado."}, status_code=409)

    token = crear_sesion(email)
    _set_cookie(response, token)
    return {"ok": True, "usuario": email}


@app.post("/auth/login")
async def login(request: Request, response: Response):
    ip = request.client.host if request.client else "?"
    if not rate_limit(f"log:{ip}", limite=10, ventana_s=600):
        return JSONResponse({"ok": False, "error": "Demasiados intentos. Espera unos minutos."}, status_code=429)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "Solicitud inválida."}, status_code=400)
    data, err = validar_login(body if isinstance(body, dict) else {})
    if err:
        return JSONResponse({"ok": False, "error": err}, status_code=401)

    email = data["email"]
    user = _users.get_item(Key={"email": email}).get("Item")
    # Comparación en tiempo ~constante: siempre verifica un hash aunque no exista.
    hash_ref = user["password_hash"] if user else bcrypt.hashpw(b"x", bcrypt.gensalt()).decode()
    ok = bcrypt.checkpw(data["password"].encode(), hash_ref.encode())
    if not user or not ok:
        return JSONResponse({"ok": False, "error": "Correo o contraseña incorrectos."}, status_code=401)

    token = crear_sesion(email)
    _set_cookie(response, token)
    return {"ok": True, "usuario": email}


@app.post("/auth/logout")
def logout(response: Response, zmd_session: str | None = Cookie(default=None)):
    borrar_sesion(zmd_session)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@app.get("/auth/me")
def me(zmd_session: str | None = Cookie(default=None)):
    row = usuario_de_sesion(zmd_session)
    if not row:
        return JSONResponse({"ok": False, "error": "Sin sesión."}, status_code=401)
    return {"ok": True, "usuario": row["email"], "nombre": row["nombre"]}


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE, token, max_age=SESSION_TTL_S, httponly=True,
        samesite="lax", secure=COOKIE_SECURE, path="/",
    )


# ── Servir la webapp estática con protección de rutas ─────────────────────────
@app.get("/{ruta:path}")
def servir(ruta: str, zmd_session: str | None = Cookie(default=None)):
    objetivo = (WEBAPP_DIR / ruta).resolve()
    if WEBAPP_DIR not in objetivo.parents and objetivo != WEBAPP_DIR:
        return JSONResponse({"error": "ruta no permitida"}, status_code=404)
    nombre = ruta if ruta else "index.html"
    if nombre in PROTEGIDAS and not usuario_de_sesion(zmd_session):
        return _redirect_login(nombre)
    if objetivo.is_dir():
        objetivo = objetivo / "index.html"
    if not objetivo.exists() or not objetivo.is_file():
        objetivo = WEBAPP_DIR / "index.html"
        if nombre in PROTEGIDAS and not usuario_de_sesion(zmd_session):
            return _redirect_login(nombre)
    return FileResponse(objetivo)


def _redirect_login(nombre: str) -> Response:
    url = "/login.html"
    if nombre and nombre != "index.html":
        url += f"?next={nombre}"
    return RedirectResponse(url, status_code=302)
