#!/usr/bin/env bash
# Arranca el backend completo de la app (solo localhost:8000) y el gateway de
# login (expuesto en 0.0.0.0:8080). Si cualquiera de los dos muere, el
# contenedor termina para que ECS reinicie la tarea con estado limpio.
set -euo pipefail

PORT="${PORT:-8080}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
APP_DIR="${APP_DIR:-/app}"
GRAPHML="${GRAPHML:-${APP_DIR}/artifacts/network/competition_delivery.graphml}"

# El gateway y el backend comparten el mismo secreto por herencia de entorno.
export BACKEND_URL="http://127.0.0.1:${BACKEND_PORT}"
export GATEWAY_SHARED_SECRET="${GATEWAY_SHARED_SECRET:-}"

BACKEND_PID=""
GATEWAY_PID=""

# Apagado ordenado: baja ambos procesos ante SIGTERM/SIGINT (parada de ECS).
apagar() {
  echo "[start] Señal recibida; cerrando procesos."
  [ -n "${GATEWAY_PID}" ] && kill "${GATEWAY_PID}" 2>/dev/null || true
  [ -n "${BACKEND_PID}" ] && kill "${BACKEND_PID}" 2>/dev/null || true
  wait 2>/dev/null || true
  exit 0
}
trap apagar SIGTERM SIGINT

echo "[start] Lanzando backend interno en 127.0.0.1:${BACKEND_PORT}"
# El grafo vial es opcional: si no existe, el backend arranca igual y la
# preparación vial usa la aproximación sintética.
if [ -f "${GRAPHML}" ]; then
  echo "[start] Usando red vial: ${GRAPHML}"
  python -m backend.local_server --port "${BACKEND_PORT}" --graphml "${GRAPHML}" &
else
  echo "[start] (aviso) Sin ${GRAPHML}; arranco sin red vial."
  python -m backend.local_server --port "${BACKEND_PORT}" &
fi
BACKEND_PID=$!

# Espera activa a que el backend escuche antes de abrir el gateway (evita que
# las primeras peticiones reciban 502 durante el arranque en frío).
echo "[start] Esperando al backend interno…"
for _ in $(seq 1 60); do
  if python -c "import socket,sys; s=socket.socket(); s.settimeout(1); sys.exit(0 if s.connect_ex(('127.0.0.1', int('${BACKEND_PORT}')))==0 else 1)"; then
    echo "[start] Backend interno listo."
    break
  fi
  if ! kill -0 "${BACKEND_PID}" 2>/dev/null; then
    echo "[start] El backend murió durante el arranque; abortando."
    exit 1
  fi
  sleep 1
done

echo "[start] Lanzando gateway de login en 0.0.0.0:${PORT}"
uvicorn gateway:app --host 0.0.0.0 --port "${PORT}" --app-dir "${APP_DIR}/gateway" \
  --no-access-log &
GATEWAY_PID=$!

# Si uno cae, bajamos el otro y salimos (ECS reinicia la tarea).
wait -n "${BACKEND_PID}" "${GATEWAY_PID}"
echo "[start] Un proceso terminó; cerrando el contenedor."
kill "${BACKEND_PID}" "${GATEWAY_PID}" 2>/dev/null || true
wait 2>/dev/null || true
exit 1
