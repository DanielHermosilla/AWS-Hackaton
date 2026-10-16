#!/usr/bin/env bash
# Arranca el backend completo de la app (solo localhost) y el gateway de login
# (expuesto en el puerto 8080). Si cualquiera de los dos muere, el contenedor
# termina para que ECS lo reinicie.
set -euo pipefail

PORT="${PORT:-8080}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
GRAPHML="${GRAPHML:-/app/artifacts/network/competition_delivery.graphml}"

echo "[start] Lanzando backend interno en 127.0.0.1:${BACKEND_PORT}"
# El grafo vial es opcional: si no existe el archivo, el backend arranca igual
# y la preparación vial pedirá usar la aproximación sintética.
if [ -f "${GRAPHML}" ]; then
  python -m backend.local_server --port "${BACKEND_PORT}" --graphml "${GRAPHML}" &
else
  echo "[start] (aviso) No se encontró ${GRAPHML}; arranco sin red vial."
  python -m backend.local_server --port "${BACKEND_PORT}" &
fi
BACKEND_PID=$!

echo "[start] Lanzando gateway de login en 0.0.0.0:${PORT}"
export BACKEND_URL="http://127.0.0.1:${BACKEND_PORT}"
uvicorn gateway:app --host 0.0.0.0 --port "${PORT}" --app-dir /app/gateway &
GATEWAY_PID=$!

# Si uno cae, bajamos el otro y salimos (ECS reinicia la tarea).
wait -n "${BACKEND_PID}" "${GATEWAY_PID}"
echo "[start] Un proceso terminó; cerrando el contenedor."
kill "${BACKEND_PID}" "${GATEWAY_PID}" 2>/dev/null || true
exit 1
