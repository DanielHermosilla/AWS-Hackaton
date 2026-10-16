"""Lógica de autenticación de ZMD Mobility (FastAPI + DynamoDB + bcrypt).

La lógica de seguridad es idéntica a la del backend de referencia
(deploy-aws/login/app.py): hash de token SHA-256, sesiones con TTL, bcrypt para
contraseñas, rate-limit en memoria, validación de entrada y política de
contraseña fuerte. El almacenamiento se delega en `db.py` (DynamoDB).

Expone las utilidades para que `app.py` las use directamente.
"""
from __future__ import annotations

import hashlib
import os
import re
import secrets
import time

import bcrypt

import db

# ── Config de sesión / cookie ─────────────────────────────────────────────────
SESSION_COOKIE = "zmd_session"
SESSION_TTL_S = 60 * 60 * 8  # 8 horas
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "1") == "1"


# ── Utilidades de seguridad (idénticas al original) ───────────────────────────
def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def crear_sesion(email: str) -> str:
    token = secrets.token_urlsafe(32)
    db.create_session(hash_token(token), email, SESSION_TTL_S)
    return token


def usuario_de_sesion(token: str | None) -> dict | None:
    if not token:
        return None
    now = int(time.time())
    sess = db.get_session(hash_token(token))
    if not sess or int(sess.get("expires_at", 0)) <= now:
        return None
    user = db.get_user(sess["email"])
    if not user:
        return None
    return {"email": user["email"], "nombre": user.get("nombre", ""), "prefs": user.get("prefs", {})}


def borrar_sesion(token: str | None) -> None:
    if not token:
        return
    db.delete_session(hash_token(token))


# ── Política de contraseña fuerte ─────────────────────────────────────────────
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
EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def validar_registro(body: dict) -> tuple[dict | None, str | None]:
    nombre = str(body.get("nombre", "")).strip()
    email = str(body.get("email", "")).strip().lower()
    password = str(body.get("password", ""))
    if not nombre or len(nombre) > 80:
        return None, "El nombre es obligatorio (máx. 80 caracteres)."
    if not EMAIL.match(email) or len(email) > 254:
        return None, "El correo no es válido."
    if not password or len(password) > 200:
        return None, "La contraseña no es válida."
    return {"nombre": nombre, "email": email, "password": password}, None


def validar_login(body: dict) -> tuple[dict | None, str | None]:
    email = str(body.get("email", "")).strip().lower()
    password = str(body.get("password", ""))
    if not EMAIL.match(email) or not password:
        return None, "Correo o contraseña incorrectos."
    return {"email": email, "password": password}, None


# ── bcrypt helpers ─────────────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def check_password(password: str, hash_ref: str | None) -> bool:
    # Comparación en tiempo ~constante: siempre verifica un hash aunque no exista.
    ref = hash_ref if hash_ref else bcrypt.hashpw(b"x", bcrypt.gensalt()).decode()
    try:
        return bcrypt.checkpw(password.encode(), ref.encode())
    except ValueError:
        return False


# ── Cookie ─────────────────────────────────────────────────────────────────────
def _set_cookie(response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE, token, max_age=SESSION_TTL_S, httponly=True,
        samesite="lax", secure=COOKIE_SECURE, path="/",
    )
