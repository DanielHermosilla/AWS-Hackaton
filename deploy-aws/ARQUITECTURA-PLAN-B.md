# Plan B — Webapp nueva + Login + Base de datos + Solver (end-to-end)

Documento de arquitectura y contrato entre componentes. Rama: `plan-b-webapp-solver`.

## Objetivo

1. Servir la **webapp nueva** (de `codex/webapp`, API 3.0) con **login/registro** funcional.
2. **Base de datos por usuario** (DynamoDB): usuarios, sesiones, planes guardados,
   preferencias, flota/estaciones, historial de actividad.
3. **Solver end-to-end** (opción Y): la webapp llama `/prepare` y `/solve`; esas
   rutas las sirve una Lambda que hace de **proxy autenticado** hacia el solver
   real en **ECS Fargate** (wrapper FastAPI del motor `ev_routing`, SCIP).

## Topología

```
Navegador
  │  (mismo origen, cookies de sesión)
  ▼
API Gateway (HTTP API)  ──►  Lambda  "zmd-app"  (FastAPI + Mangum)
                                 ├─ GET  /                     webapp estática (protegida)
                                 ├─ GET  /{static}             webapp estática
                                 ├─ POST /auth/register|login|logout
                                 ├─ GET  /auth/me
                                 ├─ GET/POST/DELETE /api/plans[/{id}]   planes guardados
                                 ├─ GET/PUT        /api/prefs           preferencias
                                 ├─ GET/PUT        /api/fleet           flota/estaciones
                                 ├─ GET            /api/activity        historial
                                 └─ POST /prepare, POST/GET /solve  ─► PROXY ─┐
                                                                              │ (token interno)
DynamoDB: zmd_users, zmd_sessions, zmd_plans, zmd_fleet, zmd_activity         │
                                                                              ▼
                                               ECS Fargate "zmd-solver-api" (FastAPI)
                                                  ├─ POST /prepare   service.prepare()
                                                  ├─ POST /solve     service.solve()  (SCIP)
                                                  └─ GET  /health
                                                  (motor ev_routing + pyscipopt)
```

## Contratos (NO cambiar sin coordinar)

### Solver API 3.0 (ya definido por `backend/service.py`)
- `POST /prepare` body `{api_version:"3.0", nodes, fleet, network_mode:"haversine"}` → `{api_version, instance}`
- `POST /solve`   body `{api_version:"3.0", instance, solver:{time_limit_seconds}}` → `{api_version, result}`
- `GET  /solve?run_id=<uuid>` → run guardado
- `GET  /health`

El proxy de la Lambda **reenvía el cuerpo tal cual** a `SOLVER_API_URL` añadiendo
el header `X-Solver-Token: <SOLVER_INTERNAL_TOKEN>`. El navegador nunca ve el token.

### DynamoDB (tablas)
- `zmd_users`    PK `email`              — {email, nombre, password_hash, created_at, prefs(map)}
- `zmd_sessions` PK `token_hash`         — {token_hash, email, created_at, expires_at(TTL)}
- `zmd_plans`    PK `email`, SK `plan_id`— {email, plan_id, name, created_at, instance(json), result(json), kpis(map)}
- `zmd_fleet`    PK `email`              — {email, vehicles(list), stations(list), updated_at}
- `zmd_activity` PK `email`, SK `ts`     — {email, ts, action, detail, expires_at(TTL 30d)}

### Sesión
- Cookie httpOnly `zmd_session`, SameSite=Lax, Secure (prod), TTL 8h.
- Rutas protegidas de la webapp: `/`, `/index.html`, `/plan.html` → redirigen a `/login.html` sin sesión.
- Endpoints `/api/*` y `/prepare`,`/solve` → 401 sin sesión.

## Layout de archivos (quién escribe qué)

```
deploy-aws/
  app/                     [FUNCIONALIDAD]  Lambda unificada
    app.py                   FastAPI: auth + /api/* + proxy + estáticos
    db.py                    capa DynamoDB (users, sessions, plans, fleet, activity)
    auth.py                  bcrypt, sesiones, validación, rate-limit
    proxy.py                 reenvío a SOLVER_API_URL con token interno
    lambda_handler.py        Mangum
    requirements.txt
    Dockerfile
    template.yaml            SAM: Lambda + 5 tablas DynamoDB + HTTP API
    webapp/                  webapp nueva + login (symlink/copy en build)
  solver-api/              [AWS]  wrapper FastAPI del solver para Fargate
    server.py                FastAPI envolviendo backend.service (prepare/solve/health) + X-Solver-Token
    requirements.txt
    Dockerfile               incluye src/ev_routing + pyscipopt
    infra-ecs.yaml           ECS Fargate service zmd-solver-api (puerto interno)
  SEGURIDAD-PLAN-B.md      [SEGURIDAD]  auditoría + checklist
```
