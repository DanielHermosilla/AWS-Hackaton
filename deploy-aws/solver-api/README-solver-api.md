# Solver API (FastAPI + ECS Fargate) — build / push / deploy

Wrapper FastAPI del motor `ev_routing` (API 3.0, SCIP) que sirve `/prepare`,
`/solve` y `/health`. Es el servicio al que la **Lambda-proxy** reenvia las
peticiones del navegador, anadiendo el header interno `X-Solver-Token`.

**Servicio independiente** del stack Streamlit `zmd-solver`. Aqui todo se llama
`zmd-solver-api` y el puerto es **8080**.

## Datos de la cuenta de la hackaton

| Dato        | Valor                       |
|-------------|-----------------------------|
| Account ID  | `831851703432`              |
| Region      | `us-east-1`                 |
| VPC         | `vpc-09d58ad509fae9ec6`     |
| Subnet      | `subnet-077db0eb8c150b3db`  |
| ECR repo    | `zmd-solver-api`            |
| Stack       | `zmd-solver-api`            |

Variables de conveniencia para la terminal:

```bash
export AWS_REGION=us-east-1
export ACCOUNT_ID=831851703432
export ECR=$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com
export REPO=zmd-solver-api
export IMAGE_URI=$ECR/$REPO:latest
```

## 1) Crear el repositorio ECR (una sola vez)

```bash
aws ecr create-repository \
  --repository-name "$REPO" \
  --region "$AWS_REGION" \
  || echo "El repo ya existe, continuo."
```

## 2) Login de Docker contra ECR

```bash
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$ECR"
```

## 3) Build de la imagen

> El **contexto de build es la RAIZ del repo** (`AWS-Hackaton/`), porque el
> Dockerfile copia `pyproject.toml`, `src/` y `backend/` desde la raiz.
> Ejecuta este comando **desde la raiz del repo**.

```bash
docker build \
  -f deploy-aws/solver-api/Dockerfile \
  -t "$REPO:latest" \
  .
```

## 4) Tag + push a ECR

```bash
docker tag "$REPO:latest" "$IMAGE_URI"
docker push "$IMAGE_URI"
```

## 5) Deploy del stack CloudFormation

Elige/define el token interno. **Debe ser el mismo** valor que use la Lambda de
la app en su variable `SOLVER_INTERNAL_TOKEN`:

```bash
export SOLVER_INTERNAL_TOKEN='pon-aqui-un-token-largo-y-secreto'
```

```bash
aws cloudformation deploy \
  --region "$AWS_REGION" \
  --template-file deploy-aws/solver-api/infra-ecs.yaml \
  --stack-name zmd-solver-api \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    ImageUri="$IMAGE_URI" \
    SolverInternalToken="$SOLVER_INTERNAL_TOKEN" \
    SubnetId=subnet-077db0eb8c150b3db \
    VpcId=vpc-09d58ad509fae9ec6
```

> **Seguridad del Security Group.** Por defecto `AllowedCidr=0.0.0.0/0`, es
> decir el puerto 8080 queda abierto a todo Internet. El contenedor exige
> `X-Solver-Token`, asi que es defensa en profundidad, pero lo ideal es
> restringirlo. Si conoces el CIDR de salida de la Lambda (o la metes en la
> VPC), anade `AllowedCidr=<cidr>/32` al `--parameter-overrides`.

## 6) Obtener la IP publica de la tarea

```bash
CLUSTER=zmd-solver-api-cluster

TASK_ARN=$(aws ecs list-tasks --cluster "$CLUSTER" \
  --service-name zmd-solver-api --region "$AWS_REGION" \
  --query 'taskArns[0]' --output text)

ENI=$(aws ecs describe-tasks --cluster "$CLUSTER" --tasks "$TASK_ARN" \
  --region "$AWS_REGION" \
  --query "tasks[0].attachments[0].details[?name=='networkInterfaceId'].value | [0]" \
  --output text)

PUBLIC_IP=$(aws ec2 describe-network-interfaces --network-interface-ids "$ENI" \
  --region "$AWS_REGION" \
  --query 'NetworkInterfaces[0].Association.PublicIp' --output text)

echo "Solver API: http://$PUBLIC_IP:8080"
```

Verifica el health check (no requiere token):

```bash
curl -s "http://$PUBLIC_IP:8080/health"
```

Prueba de auth (debe devolver 401 sin token, 200 con el token correcto):

```bash
# 401 esperado (sin header)
curl -s -o /dev/null -w '%{http_code}\n' -X POST "http://$PUBLIC_IP:8080/prepare"
# con token
curl -s -X POST "http://$PUBLIC_IP:8080/prepare" \
  -H "X-Solver-Token: $SOLVER_INTERNAL_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"api_version":"3.0","nodes":[],"fleet":{},"network_mode":"haversine"}'
```

## 7) Conectar la Lambda al solver

La Lambda de la app (`deploy-aws/app/`) necesita:

- `SOLVER_API_URL = http://IP_PUBLICA:8080`  (la IP obtenida arriba)
- `SOLVER_INTERNAL_TOKEN = <el mismo token del paso 5>`

Actualiza la Lambda de una de estas formas:

- **Redeploy del stack de la app** (SAM/CloudFormation) pasando los nuevos
  parametros `SOLVER_API_URL` y `SOLVER_INTERNAL_TOKEN`, **o**
- **Update directo de la env var** (si solo cambia la IP):

  ```bash
  aws lambda update-function-configuration \
    --function-name <NOMBRE_LAMBDA_APP> \
    --region "$AWS_REGION" \
    --environment "Variables={SOLVER_API_URL=http://$PUBLIC_IP:8080,SOLVER_INTERNAL_TOKEN=$SOLVER_INTERNAL_TOKEN}"
  ```

  > Ojo: `update-function-configuration` **reemplaza** el bloque `Variables`
  > completo; incluye todas las env vars que la Lambda necesite, no solo estas
  > dos.

## Notas

- La IP publica de Fargate **cambia** si se recrea la tarea (p. ej. al
  redeployar). Tras cualquier redeploy del servicio, repite los pasos 6 y 7.
- `Cpu=2048`/`Memory=4096` por SCIP. Si una instancia grande agota memoria,
  sube `Memory` (y `Cpu` segun las combinaciones validas de Fargate).
- Actualizar el codigo del solver: repite pasos 3–4 (nuevo push) y fuerza el
  redeploy del servicio:
  `aws ecs update-service --cluster zmd-solver-api-cluster --service zmd-solver-api --force-new-deployment --region us-east-1`.

## Redeploy rapido (resumen)

```bash
docker build -f deploy-aws/solver-api/Dockerfile -t "$REPO:latest" .
docker tag "$REPO:latest" "$IMAGE_URI" && docker push "$IMAGE_URI"
aws ecs update-service --cluster zmd-solver-api-cluster \
  --service zmd-solver-api --force-new-deployment --region "$AWS_REGION"
# luego repetir pasos 6 y 7 (IP nueva -> Lambda)
```
