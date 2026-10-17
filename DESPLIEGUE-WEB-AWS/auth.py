"""Autenticación: contraseñas (bcrypt), sesiones (cookie httpOnly), validación.

Lógica de seguridad estándar y probada:
  - Contraseña con bcrypt (salt por usuario), verificación en tiempo ~constante.
  - Token de sesión aleatorio (256 bits); en la BD solo se guarda su SHA-256.
  - Cookie httpOnly + SameSite=Lax + Secure (en HTTPS), TTL 8 h.
  - Política de contraseña fuerte y validación de email.
  - Rate-limit en memoria por proceso (defensa básica; ver nota en la guía).
"""
from __future__ import annotations

import hashlib
import os
import re
import secrets
import time

import bcrypt

import db

SESSION_COOKIE = "zmd_session"
SESSION_TTL_S = 60 * 60 * 8  # 8 horas
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "1") == "1"


# ── Sesiones ──────────────────────────────────────────────────────────────────
def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def crear_sesion(email: str) -> str:
    token = secrets.token_urlsafe(32)
    db.create_session(hash_token(token), email, SESSION_TTL_S)
    return token


def usuario_de_sesion(token: str | None) -> dict | None:
    if not token:
        return None
    sess = db.get_session(hash_token(token))
    if not sess or int(sess.get("expires_at", 0)) <= int(time.time()):
        return None
    user = db.get_user(sess["email"])
    if not user:
        return None
    return {"email": user["email"], "nombre": user.get("nombre", "")}


def borrar_sesion(token: str | None) -> None:
    if token:
        db.delete_session(hash_token(token))


# ── Contraseñas ───────────────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def check_password(password: str, hash_ref: str | None) -> bool:
    # Verifica siempre un hash, exista o no el usuario (evita oráculo de tiempo).
    ref = hash_ref if hash_ref else bcrypt.hashpw(b"x", bcrypt.gensalt()).decode()
    try:
        return bcrypt.checkpw(password.encode(), ref.encode())
    except ValueError:
        return False


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


# ── Rate-limit en memoria (por IP + acción) ───────────────────────────────────
_intentos: dict[str, list[float]] = {}


def rate_limit(clave: str, limite: int, ventana_s: int) -> bool:
    now = time.time()
    marcas = [t for t in _intentos.get(clave, []) if now - t < ventana_s]
    marcas.append(now)
    _intentos[clave] = marcas
    return len(marcas) <= limite


# ── Cookie ─────────────────────────────────────────────────────────────────────
def set_cookie(response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE, token, max_age=SESSION_TTL_S, httponly=True,
        samesite="lax", secure=COOKIE_SECURE, path="/",
    )
