# Imagen de la Lambda unificada de ZMD Mobility (FastAPI vía Mangum).
# Base oficial del runtime de Lambda para Python 3.12.
FROM public.ecr.aws/lambda/python:3.12

# Dependencias Python.
COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

# Código de la función.
COPY app.py db.py auth.py proxy.py lambda_handler.py ${LAMBDA_TASK_ROOT}/

# Webapp estática (ya integrada con el login). En el build real,
# ./webapp se genera con build-webapp.sh copiando ../../webapp aquí.
COPY webapp/ ${LAMBDA_TASK_ROOT}/webapp/

ENV WEBAPP_DIR=${LAMBDA_TASK_ROOT}/webapp

CMD ["lambda_handler.handler"]
