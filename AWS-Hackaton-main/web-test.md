# web-test — Bitácora del proyecto

> NOTA (fusión): este archivo se integró en el documento maestro unificado
> `C:\Users\Laptop_2\Desktop\maximo\AWS-Hackaton-main\web-test`, que combina el
> trabajo del solver/serverless (esta bitácora) con el de login/webapp/auth de
> la otra IA. Para el estado completo y actualizado, leer ese `web-test` de la
> raíz. Este archivo se conserva como historial original.

Registro de todo lo que se hace, ejecuta, instala, construye o sube en este proyecto.
Mantenido por el asistente. Última actualización: 2026-10-15.

Proyecto: **Ruteo de vehículos eléctricos (EVRP)** — Hackatón AWS Breaking Barriers Chile 2026.
Ruta: `C:\Users\Laptop_2\Desktop\maximo\AWS-Hackaton-main\AWS-Hackaton-main`

---

## Estado del entorno (verificado)

| Elemento | Estado | Detalle |
|---|---|---|
| Python | ✅ | 3.12 en `.venv` (se descartó el Python roto de Microsoft Store) |
| Dependencias | ✅ | boto3, pandas, numpy, pyomo, streamlit, highspy, pytest |
| Solver MILP | ✅ | HiGHS (`highspy`) instalado; `pytest` pasa (1 passed) |
| Perfil AWS | ✅ | perfil `hackaton` en `C:\Users\Laptop_2\.aws\` |
| Identidad AWS | ✅ | `arn:aws:sts::831851703432:assumed-role/WSParticipantRole/Participant` |
| Bedrock | ✅ | responde con `amazon.nova-lite-v1:0` (verificado) |

### Permisos del rol de la hackatón (solo lectura, verificado)
Permitidos: S3, Lambda, API Gateway (REST y HTTP), DynamoDB, Amplify, CloudFront, Step Functions.
No disponible: EC2 (y el evento es serverless, así que no se usa).

---

## Lo que se ha construido

### App Streamlit (UI actual, local)
- `app.py` — interfaz: carga nodos → resuelve → mapa / rutas / JSON + explicación con Bedrock.
- Verificada con el CSV real del desafío (81 nodos → 6 entregas, factible).
- Correr: `streamlit run app.py` (local, no sube nada).

### Backend serverless (base adaptativa, independiente de la UI)
Diseño: API estable; la UI es intercambiable (para la versión nueva que llegará).
- `backend/service.py` — núcleo `solve(payload)`. Agnóstico a la interfaz. Verificado.
- `backend/lambda_handler.py` — adaptador para AWS Lambda + API Gateway (CORS abierto).
- `backend/local_server.py` — mismo API en local (sin AWS). Verificado por HTTP.
- `backend/API_CONTRACT.md` — contrato estable v1.0 (endpoints y formatos).
- `template.yaml` + `Dockerfile` — infra como código (AWS SAM) para desplegar.

**Endpoints de la API:**
- `GET /health` → `{"status":"ok","api_version":"1.0"}`
- `POST /solve` → recibe JSON de instancia, devuelve la solución.

**Nota importante:** el backend NO se ve en el navegador (no es una web visual).
Es la "cocina" que consume la UI. Para verlo vivo: `http://127.0.0.1:8000/health`.

### Archivos para desplegar (preparados, aún no subidos)
- `requirements.txt` — versiones fijadas + instala el paquete `ev_routing`.
- `.gitignore` — protege credenciales (`.aws/`), `.venv/`, secrets y CSV gigantes.
- `data_ejemplo/competition_routing_nodes.csv` — dataset del desafío dentro del repo.

---

## Comandos útiles

```powershell
# Activar entorno
cd C:\Users\Laptop_2\Desktop\maximo\AWS-Hackaton-main\AWS-Hackaton-main
.\.venv\Scripts\Activate.ps1
$env:AWS_PROFILE = "hackaton"

# UI visual (Streamlit)
streamlit run app.py

# Backend API (local)
python -m backend.local_server      # luego: http://127.0.0.1:8000/health

# Tests
python -m pytest -q
```

---

## Paquete de despliegue AWS (`deploy-aws/`) — PREPARADO, aún no desplegado

Objetivo: webapp+login **pública** + solver Streamlit en **URL secreta** (token).
Verificado qué permite el rol: DynamoDB, Lambda, API Gateway, ECS, ECR, Bedrock ✅.
App Runner DENEGADO → el solver va en **ECS Fargate**.

### `deploy-aws/login/` — webapp + login (serverless, público)
- `app.py` — backend FastAPI adaptado de SQLite → **DynamoDB** (misma seguridad:
  bcrypt, token sesión sha256, rate limit, validación, protección de rutas).
- `lambda_handler.py` — adaptador Mangum para Lambda.
- `requirements.txt`, `Dockerfile` (Lambda contenedor), `template.yaml` (SAM).
- Infra: DynamoDB `zmd_users` + `zmd_sessions` (TTL) + Lambda + HTTP API.
- **Falta** copiar la webapp estática a `deploy-aws/login/webapp/` antes de build.

### `deploy-aws/solver/` — solver Streamlit (URL secreta)
- `solver_gate.py` — gate por token (`?token=...`, var `SOLVER_TOKEN`).
- `app_solver.py` — entrypoint: valida token y carga `app.py`.
- `Dockerfile` — Streamlit + ev_routing + HiGHS (build desde raíz del proyecto).
- `infra-ecs.yaml` — ECS Fargate con IP pública, SG 8501, rol con Bedrock.

### `deploy-aws/README.md`
Comandos exactos para desplegar desde el **VS Code de la hackatón** (Parte 1 login
con SAM, Parte 2 solver con ECR+CloudFormation), limpieza y posibles bloqueos.

Estado: TODO compila y los YAML son válidos. Pendiente: ejecutar el despliegue
en el entorno del evento (donde hay Docker + permisos).

## Pendiente / próximos pasos
- Ejecutar el despliegue siguiendo `deploy-aws/README.md` desde el entorno de la hackatón.
- Conectar la UI nueva (cuando llegue) al contrato de API v1.0.

## Verificación de viabilidad del despliegue (2026-10-15)
- ✅ Webapp estática copiada a `deploy-aws/login/webapp/` (sin backend viejo ni BD).
- ✅ **SIN bloqueo IAM**: el simulador confirma que el rol `WSParticipantRole`
  PUEDE: iam:CreateRole, AttachRolePolicy, PassRole, cloudformation:CreateStack,
  lambda:CreateFunction, dynamodb:CreateTable, ecs:CreateService,
  ecr:CreateRepository, apigateway:POST. Despliegue 100% viable.

---

## Historial de acciones

- 2026-10-15: Reparado venv (Python 3.12), instaladas dependencias, HiGHS.
- 2026-10-15: Configurado perfil AWS `hackaton`; verificada identidad y Bedrock.
- 2026-10-15: Creada app Streamlit `app.py`; verificada con datos reales.
- 2026-10-15: Instalado cloudflared; túnel temporal probado (demo pública).
- 2026-10-15: Preparados requirements.txt, .gitignore, data_ejemplo para despliegue.
- 2026-10-15: Verificados permisos del rol (serverless disponible, EC2 no).
- 2026-10-15: Construido backend serverless (service, lambda_handler, local_server,
  API_CONTRACT, template.yaml, Dockerfile). Verificado end-to-end por HTTP.
- 2026-10-15: Creado este archivo `web-test.md`.
- 2026-10-15: Preparado paquete de despliegue AWS en `deploy-aws/` (login en
  Lambda+DynamoDB+API Gateway; solver Streamlit en ECS Fargate con URL secreta
  por token; plantillas SAM/CloudFormation; README con comandos). Compila y YAML
  válido. Verificados permisos: App Runner denegado, ECS/ECR/DynamoDB permitidos.
