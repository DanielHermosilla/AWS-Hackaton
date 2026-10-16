"""Capa de acceso a DynamoDB para la Lambda unificada de ZMD Mobility.

Encapsula las 5 tablas del contrato de arquitectura (ARQUITECTURA-PLAN-B.md):

  zmd_users    PK email              — {email, nombre, password_hash, created_at, prefs(map)}
  zmd_sessions PK token_hash         — {token_hash, email, created_at, expires_at(TTL)}
  zmd_plans    PK email, SK plan_id  — {email, plan_id, name, created_at, instance, result, kpis}
  zmd_fleet    PK email              — {email, vehicles, stations, updated_at}
  zmd_activity PK email, SK ts(Number) — {email, ts, action, detail, expires_at(TTL 30d)}

Decisión de diseño sobre tipos: DynamoDB no admite `float` nativo (boto3 exige
`Decimal`). Para evitar la fricción de convertir estructuras anidadas con flotantes
(instancias del solver, resultados, kpis), esas estructuras se serializan con
`json.dumps` y se guardan como atributo *String*; al leer se deserializan con
`json.loads`. Así los números se preservan tal cual sin tocar la precisión.

Los nombres de tabla se leen de variables de entorno con los defaults del contrato.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key

# ── Nombres de tabla (env vars con defaults del contrato) ─────────────────────
USERS_TABLE = os.getenv("DDB_USERS_TABLE", "zmd_users")
SESSIONS_TABLE = os.getenv("DDB_SESSIONS_TABLE", "zmd_sessions")
PLANS_TABLE = os.getenv("DDB_PLANS_TABLE", "zmd_plans")
FLEET_TABLE = os.getenv("DDB_FLEET_TABLE", "zmd_fleet")
ACTIVITY_TABLE = os.getenv("DDB_ACTIVITY_TABLE", "zmd_activity")

ACTIVITY_TTL_S = 60 * 60 * 24 * 30  # 30 días

# ── Recurso / tablas (perezoso para no exigir credenciales al importar) ───────
_ddb = None
_tables: dict[str, Any] = {}


def _resource():
    global _ddb
    if _ddb is None:
        _ddb = boto3.resource("dynamodb")
    return _ddb


def _table(name: str):
    if name not in _tables:
        _tables[name] = _resource().Table(name)
    return _tables[name]


def users():
    return _table(USERS_TABLE)


def sessions():
    return _table(SESSIONS_TABLE)


def plans():
    return _table(PLANS_TABLE)


def fleet():
    return _table(FLEET_TABLE)


def activity():
    return _table(ACTIVITY_TABLE)


# ── Helpers de serialización JSON para atributos grandes con floats ───────────
def _dump(value: Any) -> str:
    return json.dumps(value if value is not None else None, ensure_ascii=False, default=str)


def _load(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


def _now_s() -> int:
    return int(time.time())


def _now_ms() -> int:
    return int(time.time() * 1000)


# ── Usuarios ──────────────────────────────────────────────────────────────────
def get_user(email: str) -> dict | None:
    return users().get_item(Key={"email": email}).get("Item")


def put_user(email: str, nombre: str, password_hash: str, prefs: dict | None = None) -> dict:
    """Crea un usuario. Lanza ConditionalCheckFailedException si el email ya existe."""
    item = {
        "email": email,
        "nombre": nombre,
        "password_hash": password_hash,
        "created_at": _now_s(),
        "prefs": prefs or {},
    }
    users().put_item(Item=item, ConditionExpression="attribute_not_exists(email)")
    return item


def update_user_prefs(email: str, prefs: dict) -> None:
    users().update_item(
        Key={"email": email},
        UpdateExpression="SET prefs = :p",
        ExpressionAttributeValues={":p": prefs or {}},
    )


# ── Sesiones ──────────────────────────────────────────────────────────────────
def create_session(token_hash: str, email: str, ttl_s: int) -> dict:
    now = _now_s()
    item = {
        "token_hash": token_hash,
        "email": email,
        "created_at": now,
        "expires_at": now + ttl_s,  # también sirve como TTL de DynamoDB
    }
    sessions().put_item(Item=item)
    return item


def get_session(token_hash: str) -> dict | None:
    return sessions().get_item(Key={"token_hash": token_hash}).get("Item")


def delete_session(token_hash: str) -> None:
    sessions().delete_item(Key={"token_hash": token_hash})


# ── Planes guardados ────────────────────────────────────────────────────────────
def list_plans(email: str) -> list[dict]:
    resp = plans().query(KeyConditionExpression=Key("email").eq(email))
    items = resp.get("Items", [])
    out = []
    for it in items:
        out.append(
            {
                "email": it.get("email"),
                "plan_id": it.get("plan_id"),
                "name": it.get("name"),
                "created_at": it.get("created_at"),
                "kpis": _load(it.get("kpis")),
            }
        )
    return out


def get_plan(email: str, plan_id: str) -> dict | None:
    it = plans().get_item(Key={"email": email, "plan_id": plan_id}).get("Item")
    if not it:
        return None
    return {
        "email": it.get("email"),
        "plan_id": it.get("plan_id"),
        "name": it.get("name"),
        "created_at": it.get("created_at"),
        "instance": _load(it.get("instance")),
        "result": _load(it.get("result")),
        "kpis": _load(it.get("kpis")),
    }


def put_plan(email: str, plan: dict) -> dict:
    """Guarda un plan nuevo. `plan` = {name, instance, result, kpis}. Devuelve el resumen."""
    plan_id = str(uuid.uuid4())
    now = _now_s()
    item = {
        "email": email,
        "plan_id": plan_id,
        "name": str(plan.get("name") or "Plan sin nombre"),
        "created_at": now,
        "instance": _dump(plan.get("instance")),
        "result": _dump(plan.get("result")),
        "kpis": _dump(plan.get("kpis")),
    }
    plans().put_item(Item=item)
    return {
        "email": email,
        "plan_id": plan_id,
        "name": item["name"],
        "created_at": now,
        "kpis": plan.get("kpis"),
    }


def delete_plan(email: str, plan_id: str) -> None:
    plans().delete_item(Key={"email": email, "plan_id": plan_id})


# ── Flota / estaciones ──────────────────────────────────────────────────────────
def get_fleet(email: str) -> dict | None:
    it = fleet().get_item(Key={"email": email}).get("Item")
    if not it:
        return None
    return {
        "email": it.get("email"),
        "vehicles": _load(it.get("vehicles")) or [],
        "stations": _load(it.get("stations")) or [],
        "updated_at": it.get("updated_at"),
    }


def put_fleet(email: str, data: dict) -> dict:
    now = _now_s()
    item = {
        "email": email,
        "vehicles": _dump(data.get("vehicles") or []),
        "stations": _dump(data.get("stations") or []),
        "updated_at": now,
    }
    fleet().put_item(Item=item)
    return {
        "email": email,
        "vehicles": data.get("vehicles") or [],
        "stations": data.get("stations") or [],
        "updated_at": now,
    }


# ── Historial de actividad ────────────────────────────────────────────────────
def add_activity(email: str, action: str, detail: Any = None) -> dict:
    now_ms = _now_ms()
    item = {
        "email": email,
        "ts": now_ms,
        "action": str(action),
        "detail": _dump(detail) if detail is not None else "",
        "expires_at": _now_s() + ACTIVITY_TTL_S,
    }
    activity().put_item(Item=item)
    return item


def list_activity(email: str, limit: int = 50) -> list[dict]:
    resp = activity().query(
        KeyConditionExpression=Key("email").eq(email),
        ScanIndexForward=False,  # más recientes primero
        Limit=limit,
    )
    out = []
    for it in resp.get("Items", []):
        out.append(
            {
                "ts": int(it.get("ts", 0)),
                "action": it.get("action"),
                "detail": _load(it.get("detail")) if it.get("detail") else None,
            }
        )
    return out
