# Imagen base oficial de AWS Lambda para Python.
FROM public.ecr.aws/lambda/python:3.12

# Copia metadatos e instala el proyecto + dependencias del backend.
COPY pyproject.toml ./
COPY src/ ./src/
COPY backend/ ./backend/

# boto3 ya viene en la imagen de Lambda; instalamos el resto.
RUN pip install --no-cache-dir \
    "pydantic>=2.0" "pandas>=2.0" "numpy>=1.24" "pyomo>=6.6" "highspy>=1.5" && \
    pip install --no-cache-dir -e .

# Handler: modulo.funcion
CMD ["backend.lambda_handler.handler"]
