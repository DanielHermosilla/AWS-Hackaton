# FastAPI wrapper of the ev_routing solver (API 3.0) for ECS Fargate.
#
# IMPORTANT: the build CONTEXT must be the REPO ROOT (same as the Streamlit
# Dockerfile), because we need pyproject.toml, src/ and backend/ from the root:
#
#   docker build -f deploy-aws/solver-api/Dockerfile -t zmd-solver-api:latest .
#
FROM python:3.12-slim

WORKDIR /app

# SCIP (shipped inside the pyscipopt==6.0.0 wheel) typically links against the
# GNU OpenMP runtime. Install libgomp1 as a safety net so the solver loads.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade pip

# 1) Install the engine package (ev_routing) in editable mode.
#    Copy only what the install needs first, to keep the layer cache warm.
COPY pyproject.toml ./
COPY README.md ./README.md
COPY src/ ./src/
RUN pip install --no-cache-dir -e .

# 2) Install the API + remaining runtime deps (pinned, see requirements.txt).
COPY deploy-aws/solver-api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 3) Copy the engine's transport-agnostic service layer (`from backend import service`)
#    and this wrapper. server.py lives at /app so it is importable as `server:app`.
COPY backend/ ./backend/
COPY deploy-aws/solver-api/server.py ./server.py

# The API listens on 0.0.0.0:$PORT (default 8080). SOLVER_INTERNAL_TOKEN is
# injected by the ECS task definition; an empty token means open/dev mode.
ENV PORT=8080 \
    PYTHONUNBUFFERED=1

EXPOSE 8080

# uvicorn imports `server:app` from WORKDIR /app. backend/ and the installed
# ev_routing package are both importable from here.
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
