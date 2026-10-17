"""Base de datos de usuarios y sesiones en DynamoDB (para el gateway de login).

Dos tablas (nombres configurables por variables de entorno):
  zmd_users    PK email       — {email, nombre, password_hash, created_at}
  zmd_sessions PK token_hash  — {token_hash, email, created_at, expires_at(TTL)}

El resto del estado de la app (escenarios, historial, sesiones Bedrock, planes)
lo gestiona el backend de la aplicación en memoria; aquí SOLO viven las cuentas.
"""
from __future__ import annotations

import os
import time

import boto3
from boto3.dynamodb.conditions import Key  # noqa: F401 (disponible para extensiones)

USERS_TABLE = os.getenv("DDB_USERS_TABLE", "zmd_users")
SESSIONS_TABLE = os.getenv("DDB_SESSIONS_TABLE", "zmd_sessions")

_ddb = None
_cache: dict[str, object] = {}


def _table(name: str):
    global _ddb
    if _ddb is None:
        _ddb = boto3.resource("dynamodb")
    if name not in _cache:
        _cache[name] = _ddb.Table(name)
    return _cache[name]


def _now() -> int:
    return int(time.time())


# ── Usuarios ──────────────────────────────────────────────────────────────────
def get_user(email: str) -> dict | None:
    return _table(USERS_TABLE).get_item(Key={"email": email}).get("Item")


def put_user(email: str, nombre: str, password_hash: str) -> dict:
    """Crea un usuario; lanza ConditionalCheckFailedException si el email existe."""
    item = {
        "email": email,
        "nombre": nombre,
        "password_hash": password_hash,
        "created_at": _now(),
    }
    _table(USERS_TABLE).put_item(
        Item=item, ConditionExpression="attribute_not_exists(email)"
    )
    return item


# ── Sesiones ──────────────────────────────────────────────────────────────────
def create_session(token_hash: str, email: str, ttl_s: int) -> None:
    now = _now()
    _table(SESSIONS_TABLE).put_item(
        Item={
            "token_hash": token_hash,
            "email": email,
            "created_at": now,
            "expires_at": now + ttl_s,  # también es el atributo TTL de DynamoDB
        }
    )


def get_session(token_hash: str) -> dict | None:
    return _table(SESSIONS_TABLE).get_item(Key={"token_hash": token_hash}).get("Item")


def delete_session(token_hash: str) -> None:
    _table(SESSIONS_TABLE).delete_item(Key={"token_hash": token_hash})
