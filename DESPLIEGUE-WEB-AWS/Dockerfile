# Imagen única: backend completo de ZMD Mobility (webapp + solver + IA) MÁS el
# gateway de login. El contexto de build DEBE ser la RAÍZ del repo:
#
#   docker build -f DESPLIEGUE-WEB-AWS/Dockerfile -t zmd-web:latest .
#
FROM python:3.12-slim

WORKDIR /app

# libgomp1: SCIP (wheel de pyscipopt) enlaza con la runtime de OpenMP.
# tini: PID 1 ligero que reenvía señales (SIGTERM de ECS → apagado ordenado).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 tini \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade pip

# 1) Instala el paquete del motor (ev_routing) y sus dependencias desde la raíz.
#    Incluye el extra "assist" para el chat IA (boto3 + Bedrock).
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir -e ".[assist]"

# 2) Dependencias del gateway de login.
COPY DESPLIEGUE-WEB-AWS/requirements-gateway.txt ./gw-requirements.txt
RUN pip install --no-cache-dir -r gw-requirements.txt

# 3) Código del backend de la app.
COPY backend/ ./backend/

# 4) Webapp estática. Primero la webapp de la app; luego superponemos las
#    páginas de login/registro para que se sirvan desde el mismo origen.
COPY webapp/ ./webapp/
COPY DESPLIEGUE-WEB-AWS/webapp-login/ ./webapp/

# 5) El gateway (en su propia carpeta para --app-dir).
COPY DESPLIEGUE-WEB-AWS/gateway.py DESPLIEGUE-WEB-AWS/auth.py DESPLIEGUE-WEB-AWS/db.py ./gateway/
COPY DESPLIEGUE-WEB-AWS/start.sh ./start.sh
RUN chmod +x ./start.sh

# 6) (Opcional) Red vial de la competencia, si está en el repo. Si no existe,
#    el contenedor arranca igual y usa la aproximación sintética.
#    Descomenta la siguiente línea si subes el graphml al repo:
# COPY artifacts/network/competition_delivery.graphml ./artifacts/network/competition_delivery.graphml

# Usuario sin privilegios: el contenedor no corre como root.
RUN useradd --create-home --uid 10001 zmd \
    && chown -R zmd:zmd /app
USER zmd

ENV PORT=8080 \
    BACKEND_PORT=8000 \
    APP_DIR=/app \
    COOKIE_SECURE=1 \
    GATEWAY_SHARED_SECRET="" \
    PYTHONUNBUFFERED=1 \
    AWS_DEFAULT_REGION=us-east-1

EXPOSE 8080

# tini como PID 1 para un apagado limpio ante la parada de ECS.
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["./start.sh"]
