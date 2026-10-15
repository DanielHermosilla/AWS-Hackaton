# Despliegue en AWS — Webapp+Login (público) y Solver (URL secreta)

Paquete listo para desplegar desde el **entorno VS Code de la hackatón**
(que ya tiene permisos del evento, Docker, AWS CLI y SAM CLI).

> Región: `us-east-1`. Todo lo verificado funciona con el rol `WSParticipantRole`.
> Servicios usados (permisos confirmados): DynamoDB, Lambda, API Gateway, ECS,
> ECR, Bedrock. (App Runner está DENEGADO; por eso el solver va en ECS Fargate.)

---

## Arquitectura

```
   Público  → [ HTTP API + Lambda (FastAPI/Mangum) ] → webapp + login
                        └─ DynamoDB (usuarios, sesiones)

   Secreto  → [ ECS Fargate + Streamlit ]  (acceso solo con ?token=SECRETO)
                        └─ Bedrock (explicación IA)
```

---

## Pre-requisitos (en el entorno de la hackatón)

```bash
aws sts get-caller-identity          # confirmar cuenta/rol
docker --version                     # Docker disponible
sam --version                        # AWS SAM CLI
```

---

## PARTE 1 — Webapp + Login (público, serverless)

### 1.1 Copiar la webapp estática dentro del paquete del login
El Dockerfile del login espera la webapp en `deploy-aws/login/webapp/`.
Copia ahí los estáticos (login.html, register.html, index.html, plan.html,
assets, vendor, etc.) desde la carpeta de la webapp:

```bash
cd deploy-aws/login
mkdir -p webapp
cp -r /ruta/a/la/webapp/*  webapp/     # ajustar a la ubicación real de la webapp
```

> La webapp usa `API.base=''` (mismo origen), así que al servirse desde la misma
> Lambda, el login funciona sin cambios de CORS.

### 1.2 Construir y desplegar con SAM
```bash
cd deploy-aws/login
sam build
sam deploy --guided \
  --stack-name zmd-login \
  --capabilities CAPABILITY_IAM \
  --region us-east-1
# En las preguntas: CookieSecure=1 (HTTPS). Confirmar creación de recursos.
```

Al terminar, SAM imprime **`WebappUrl`** → esa es la **URL pública** de la webapp
con login. Ábrela en `.../login.html`.

### 1.3 Verificar
```bash
curl -i https://<WebappUrl>/auth/me        # debe dar 401 (sin sesión) → backend vivo
```

---

## PARTE 2 — Solver Streamlit (URL secreta, ECS Fargate)

### 2.1 Generar un token secreto
```bash
export SOLVER_TOKEN=$(python -c "import secrets;print(secrets.token_urlsafe(24))")
echo "GUARDA ESTE TOKEN: $SOLVER_TOKEN"
```

### 2.2 Construir la imagen y subirla a ECR
El build usa la RAÍZ del proyecto como contexto (necesita `src/`, `app.py`, `data_ejemplo/`).

```bash
# desde la RAÍZ del proyecto (AWS-Hackaton-main/)
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REGION=us-east-1
REPO=zmd-solver

aws ecr create-repository --repository-name $REPO --region $REGION || true
aws ecr get-login-password --region $REGION \
  | docker login --username AWS --password-stdin $ACCOUNT.dkr.ecr.$REGION.amazonaws.com

docker build -f deploy-aws/solver/Dockerfile -t $REPO:latest .
docker tag $REPO:latest $ACCOUNT.dkr.ecr.$REGION.amazonaws.com/$REPO:latest
docker push $ACCOUNT.dkr.ecr.$REGION.amazonaws.com/$REPO:latest
```

### 2.3 Obtener VPC y subred por defecto
```bash
VPC=$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true \
      --query "Vpcs[0].VpcId" --output text)
SUBNET=$(aws ec2 describe-subnets --filters Name=vpc-id,Values=$VPC \
      --query "Subnets[0].SubnetId" --output text)
echo "VPC=$VPC SUBNET=$SUBNET"
```

### 2.4 Desplegar el servicio ECS
```bash
aws cloudformation deploy \
  --template-file deploy-aws/solver/infra-ecs.yaml \
  --stack-name zmd-solver \
  --capabilities CAPABILITY_IAM \
  --region $REGION \
  --parameter-overrides \
     ImageUri=$ACCOUNT.dkr.ecr.$REGION.amazonaws.com/$REPO:latest \
     SolverToken=$SOLVER_TOKEN \
     SubnetId=$SUBNET \
     VpcId=$VPC
```

### 2.5 Obtener la URL secreta del solver
Fargate asigna una IP pública a la tarea. Para obtenerla:

```bash
TASK=$(aws ecs list-tasks --cluster zmd-solver-cluster --query "taskArns[0]" --output text)
ENI=$(aws ecs describe-tasks --cluster zmd-solver-cluster --tasks $TASK \
   --query "tasks[0].attachments[0].details[?name=='networkInterfaceId'].value" --output text)
IP=$(aws ec2 describe-network-interfaces --network-interface-ids $ENI \
   --query "NetworkInterfaces[0].Association.PublicIp" --output text)
echo "URL SECRETA:  http://$IP:8501/?token=$SOLVER_TOKEN"
```

Solo quien tenga esa URL completa (con el token) puede entrar. Sin el token,
el solver muestra "Acceso restringido".

---

## Limpieza (para no gastar recursos al terminar)

```bash
aws cloudformation delete-stack --stack-name zmd-solver --region us-east-1
sam delete --stack-name zmd-login --region us-east-1
aws ecr delete-repository --repository-name zmd-solver --force --region us-east-1
```

---

## Posibles bloqueos (y qué hacer)

- **Creación de roles IAM denegada** (`CAPABILITY_IAM`): algunas cuentas de
  workshop lo restringen. Si `sam deploy`/`cloudformation deploy` falla con
  AccessDenied al crear roles, pídele al organizador un rol de ejecución
  pre-creado y referéncialo en la plantilla en vez de crearlo.
- **Imagen muy grande / timeout en push**: el solver incluye Pyomo+HiGHS; el push
  a ECR puede tardar. Reintentar si corta.
- **Lambda tamaño de imagen**: el login es liviano (FastAPI), no debería dar
  problemas.
- **El MILP no cierra en Fargate**: igual que en local, usar H bajo (4–6) desde
  la UI del solver.
