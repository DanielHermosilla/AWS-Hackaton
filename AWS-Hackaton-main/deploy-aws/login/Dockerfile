# Backend de login (FastAPI + DynamoDB) para AWS Lambda, imagen de contenedor.
FROM public.ecr.aws/lambda/python:3.12

# Dependencias.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Código del backend.
COPY app.py ./app.py
COPY lambda_handler.py ./lambda_handler.py

# Webapp estática que sirve el backend.
# IMPORTANTE: antes de 'sam build', copia aquí la carpeta de la webapp:
#   deploy-aws/login/webapp/   (login.html, index.html, plan.html, assets, ...)
COPY webapp/ ./webapp/

# La app usa WEBAPP_DIR; en Lambda el código vive en /var/task.
ENV WEBAPP_DIR=/var/task/webapp

CMD ["lambda_handler.handler"]
