# CONTINUAR DESDE CASA — Respaldo completo (rama `respaldo-max`)

Guía para reconstruir y seguir trabajando el proyecto en otra máquina.
Este respaldo contiene **todo el código, documentos y datos pequeños**. Los
datasets grandes (eVED, GB) y los entornos virtuales NO están aquí (se bajan /
se recrean). Fecha del respaldo: 2026-10-15.

> Lectura previa recomendada: `web-test` (bitácora unificada del proyecto) y
> `ANALISIS-PROYECTO.md` (análisis técnico, algoritmos, mapa).

---

## 1. Qué incluye y qué NO este respaldo

**Incluido:**
- Todo el código: los 4 subproyectos + `web-login/` (v1 y v2).
- Documentación (`*.md`), configs, y los **CSV pequeños** del desafío
  (`competition_routing_nodes.csv`, `evaluation_routing_nodes.csv`,
  `vehicle_types.csv`).
- `web-test`, `ANALISIS-PROYECTO.md`, `analyze_instance.py`.

**NO incluido (hay que recrear/descargar):**
- `Electromovilidad/eVED_ICE.csv` (2.7 GB), `eVED_PHEV_HEV.csv` (2.1 GB),
  `eVED_EV.csv` (97 MB) — superan el límite de GitHub. Ver sección 4.
- `.venv/` de cada subproyecto — se recrean (sección 3).
- Bases de datos de auth (`server/data/zmd.db`), cachés, resultados.

---

## 2. Subproyectos (mapa rápido)

| Carpeta | Qué es | Entorno |
|---|---|---|
| `AWS-Hackaton-main/` | App A: Streamlit del solver + backend serverless (`backend/`) | Python 3.12 `.venv` |
| `AWS-Hackaton-modelamiento/` | Motor MILP fiel al PDF (Pyomo + Gurobi/SCIP) | uv / pyproject |
| `AWS-Hackaton-codex-optimizacion-contraida/` | Motor `evrp` 2 capas (Dijkstra + MILP HiGHS) + IA Bedrock | uv `.venv` (3.12) |
| `AWS-Hackaton-codex-ui/` | Exploraciones de UI (mapas, login v1) | estático |
| `web-login/` | Login v1 (exploraciones) y v2 (webapp + login/registro + backend auth) | v2/server: FastAPI |
| `Electromovilidad/` | Datos CSV (los grandes se bajan aparte) | — |
| `Diccionario/` | Glosario eVED | — |

---

## 3. Reconstruir entornos

### App A — Streamlit del solver (`AWS-Hackaton-main/`)
```powershell
cd AWS-Hackaton-main
python -m venv .venv              # usar Python 3.12
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt   # o: pip install -e . && pip install streamlit boto3
$env:AWS_PROFILE = "hackaton"     # solo si se usará Bedrock
streamlit run app.py              # http://localhost:8501
# Backend serverless local:  python -m backend.local_server  (http://127.0.0.1:8000/health)
```

### Motor contraído `evrp` (`AWS-Hackaton-codex-optimizacion-contraida/`)
```powershell
cd AWS-Hackaton-codex-optimizacion-contraida
uv sync --extra ia                # requiere uv; + --extra elevacion para Copernicus
uv run pytest -q -m "not bedrock"
uv run evrp solve --nodes data/competition_routing_nodes.csv --perfil ev_routing --out results/comp
```
(Copiar los CSV del desafío a `data/` si no están.)

### Motor `modelamiento` (`AWS-Hackaton-modelamiento/`)
```powershell
cd AWS-Hackaton-modelamiento
uv sync         # Pyomo; necesita Gurobi o SCIP para resolver
uv run pytest -q
```

### Webapp + login/registro con backend real (`web-login/v2/server/`)
```powershell
cd web-login/v2/server
python -m pip install -r requirements.txt    # fastapi, uvicorn, bcrypt
python -m uvicorn app:app --host 127.0.0.1 --port 4173
# abrir http://127.0.0.1:4173/login.html
```
> La BD `server/data/zmd.db` se crea sola al arrancar. Nota: el backend de auth
> funciona bien en Python 3.12; en 3.10 se quitó pydantic por incompatibilidad.

---

## 4. Descargar los datasets eVED (los que faltan)

Los CSV grandes vienen del dataset público **eVED** (Extended Vehicle Energy
Dataset). Colocarlos en `Electromovilidad/`:
- `eVED_EV.csv`, `eVED_ICE.csv`, `eVED_PHEV_HEV.csv`.

Fuente: repositorio público eVED (GitHub `gsoh/VED` / eVED). Si tienes el ZIP
original del desafío, descomprímelo ahí. El motor `evrp` también trae un GraphML
de Ann Arbor empaquetado, así que puede correr sin estos CSV para rutas; los
eVED solo se usan para **calibrar** el consumo (`evrp calibrar`, o la pestaña de
energía). Los CSV pequeños de nodos SÍ están en el respaldo.

---

## 5. Git / GitHub

Repo: `https://github.com/DanielHermosilla/AWS-Hackaton` (SSH como `maximar77`).
Esta rama de respaldo: **`respaldo-max`**.

```powershell
# clonar y situarse en el respaldo
git clone git@github.com:DanielHermosilla/AWS-Hackaton.git
cd AWS-Hackaton
git checkout respaldo-max
```

Otras ramas útiles: `codex/webapp` (webapp real), `test/login-webapp`
(webapp+login+auth), `test/login-web` (login v1/v2), `codex/optimizacion-contraida`,
`modelamiento`, `main`.

---

## 6. AWS (opcional, para Bedrock)

- Perfil `hackaton` en `~/.aws/`. Identidad del rol de la hackatón:
  `WSParticipantRole/Participant`. Permisos: S3, Lambda, API Gateway, DynamoDB,
  Amplify, CloudFront, Step Functions (no EC2).
- Bedrock verificado con `amazon.nova-lite-v1:0`.
- Las credenciales AWS NO están en el respaldo (nunca versionar `.aws/`).

---

## 7. Puertos usados

| Puerto | Servicio |
|---|---|
| 8501 | Streamlit del solver (App A) |
| 8000 | backend serverless local (App A2) |
| 4173 | backend FastAPI de auth + webapp (App B) |

Un servicio por puerto. Para exponer en red: `--host 0.0.0.0` y abrir el puerto
en el firewall; o túnel con `cloudflared tunnel --url http://127.0.0.1:<puerto>`.

---

## 8. Próximos pasos sugeridos (ver web-test §9)

1. Conectar la webapp con login (B) al backend del solver (A2) vía la API v1.0
   (`AWS-Hackaton-main/backend/API_CONTRACT.md`).
2. Opcional: poner login delante del Streamlit.
3. Preferir el motor `evrp` (2 capas) para que el solver cierre en tiempo; el
   MILP sobre red completa no cierra con H alto (ver ANALISIS-PROYECTO.md).
