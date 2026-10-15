"""Backend de autenticación de ZMD Mobility (FastAPI + SQLite + bcrypt).

Sirve la webapp estática existente y añade endpoints reales de cuentas:
  POST /auth/register   crear cuenta (hash bcrypt en el servidor)
  POST /auth/login      iniciar sesión (devuelve cookie de sesión httpOnly)
  POST /auth/logout     cerrar sesión (invalida el token)
  GET  /auth/me         usuario de la sesión actual (401 si no hay)

Seguridad aplicada:
- Contraseñas con **bcrypt** (sal por hash; nunca se guarda la contraseña).
- Sesiones por **token aleatorio** (secrets.token_urlsafe) con expiración,
  guardado como **hash** en la BD; la cookie es httpOnly y SameSite=Lax.
- Validación en el servidor (no se confía en el cliente).
- **Rate limiting** básico por IP para login y registro.
- Las páginas protegidas (index.html, plan.html) exigen sesión; sin ella
  redirigen a /login.html.
"""
from __future__ import annotations

import hashlib
import re
import secrets
import sqlite3
import time
from contextlib import closing
from pathlib import Path

import bcrypt
from fastapi import Cookie, FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse

# ── Rutas ──────────────────────────────────────────────────────────────────
WEBAPP_DIR = Path(__file__).resolve().parent.parent  # carpeta webapp/
DB_PATH = Path(__file__).resolve().parent / "data" / "zmd.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

SESSION_COOKIE = "zmd_session"
SESSION_TTL_S = 60 * 60 * 8  # 8 horas
PROTEGIDAS = {"", "index.html", "plan.html"}  # requieren sesión

app = FastAPI(title="ZMD Mobility Auth", docs_url=None, redoc_url=None)


# ── Base de datos ────────────────────────────────────────────────────────────
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    with closing(db()) as conn, conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                nombre TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL
            )"""
        )


init_db()


# ── Utilidades de seguridad ──────────────────────────────────────────────────
def hash_token(token: str) -> str:
    """Guardamos solo el hash del token de sesión, no el token en claro."""
    return hashlib.sha256(token.encode()).hexdigest()


def crear_sesion(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    with closing(db()) as conn, conn:
        conn.execute(
            "INSERT INTO sessions(token_hash,user_id,created_at,expires_at) VALUES(?,?,?,?)",
            (hash_token(token), user_id, now, now + SESSION_TTL_S),
        )
    return token


def usuario_de_sesion(token: str | None) -> sqlite3.Row | None:
    if not token:
        return None
    now = int(time.time())
    with closing(db()) as conn:
        row = conn.execute(
            """SELECT u.id,u.email,u.nombre FROM sessions s
               JOIN users u ON u.id=s.user_id
               WHERE s.token_hash=? AND s.expires_at>?""",
            (hash_token(token), now),
        ).fetchone()
    return row


def borrar_sesion(token: str | None) -> None:
    if not token:
        return
    with closing(db()) as conn, conn:
        conn.execute("DELETE FROM sessions WHERE token_hash=?", (hash_token(token),))


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


# ── Rate limiting simple en memoria (por IP + acción) ──────────────────────────
_intentos: dict[str, list[float]] = {}


def rate_limit(clave: str, limite: int, ventana_s: int) -> bool:
    now = time.time()
    marcas = [t for t in _intentos.get(clave, []) if now - t < ventana_s]
    marcas.append(now)
    _intentos[clave] = marcas
    return len(marcas) <= limite


# ── Validación de entrada (sin pydantic, compatible con Python 3.10) ──────────
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
    pw_hash = bcrypt.hashpw(data["password"].encode(), bcrypt.gensalt()).decode()
    now = int(time.time())
    try:
        with closing(db()) as conn, conn:
            cur = conn.execute(
                "INSERT INTO users(email,nombre,password_hash,created_at) VALUES(?,?,?,?)",
                (email, data["nombre"], pw_hash, now),
            )
            user_id = cur.lastrowid
    except sqlite3.IntegrityError:
        return JSONResponse({"ok": False, "error": "Ese correo ya está registrado."}, status_code=409)

    token = crear_sesion(user_id)
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
    with closing(db()) as conn:
        row = conn.execute("SELECT id,password_hash FROM users WHERE email=?", (email,)).fetchone()

    # Comparación en tiempo ~constante: siempre verifica un hash aunque no exista.
    hash_ref = row["password_hash"] if row else bcrypt.hashpw(b"x", bcrypt.gensalt()).decode()
    ok = bcrypt.checkpw(data["password"].encode(), hash_ref.encode())
    if not row or not ok:
        return JSONResponse({"ok": False, "error": "Correo o contraseña incorrectos."}, status_code=401)

    token = crear_sesion(row["id"])
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
    # httpOnly: inaccesible desde JS (mitiga XSS). SameSite=Lax: mitiga CSRF básico.
    # secure=False para http://localhost; en producción (HTTPS) poner secure=True.
    response.set_cookie(
        SESSION_COOKIE, token, max_age=SESSION_TTL_S, httponly=True,
        samesite="lax", secure=False, path="/",
    )


# ── Servir la webapp estática con protección de rutas ─────────────────────────
@app.get("/{ruta:path}")
def servir(ruta: str, zmd_session: str | None = Cookie(default=None)):
    # Normaliza y previene traversal.
    objetivo = (WEBAPP_DIR / ruta).resolve()
    if WEBAPP_DIR not in objetivo.parents and objetivo != WEBAPP_DIR:
        return JSONResponse({"error": "ruta no permitida"}, status_code=404)

    nombre = ruta if ruta else "index.html"

    # Páginas protegidas: exigen sesión real.
    if nombre in PROTEGIDAS and not usuario_de_sesion(zmd_session):
        return RedirectToLogin(nombre)

    if objetivo.is_dir():
        objetivo = objetivo / "index.html"
    if not objetivo.exists() or not objetivo.is_file():
        # fallback a index para rutas desconocidas
        objetivo = WEBAPP_DIR / "index.html"
        if nombre in PROTEGIDAS and not usuario_de_sesion(zmd_session):
            return RedirectToLogin(nombre)
    return FileResponse(objetivo)


def RedirectToLogin(nombre: str) -> Response:
    from fastapi.responses import RedirectResponse

    url = "/login.html"
    if nombre and nombre != "index.html":
        url += f"?next={nombre}"
    return RedirectResponse(url, status_code=302)
