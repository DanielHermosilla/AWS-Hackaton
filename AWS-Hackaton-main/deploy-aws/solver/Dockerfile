# Solver Streamlit (ruteo EV) con gate por URL secreta, para ECS Fargate.
FROM python:3.12-slim

WORKDIR /app

# Dependencias del sistema mínimas (HiGHS viene por highspy, no necesita extra).
RUN pip install --no-cache-dir --upgrade pip

# Instalar el paquete del proyecto (ev_routing) + dependencias de la app.
# El contexto de build debe ser la RAÍZ del proyecto (AWS-Hackaton-main/).
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir \
    "pydantic>=2.0" "pandas>=2.0" "numpy>=1.24" "pyomo>=6.6" \
    "streamlit>=1.30" "highspy>=1.5" "boto3>=1.34" && \
    pip install --no-cache-dir -e .

# App del solver + gate + datos de ejemplo.
COPY app.py ./app.py
COPY deploy-aws/solver/solver_gate.py ./solver_gate.py
COPY deploy-aws/solver/app_solver.py ./app_solver.py
COPY data_ejemplo/ ./data_ejemplo/

# Streamlit escucha en 8501. El token secreto se pasa por SOLVER_TOKEN.
ENV STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_SERVER_ENABLE_CORS=false \
    STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION=false

EXPOSE 8501

CMD ["streamlit", "run", "app_solver.py"]
