# 🧭 Guía de despliegue en AWS — web completa de ZMD Mobility

Despliega la **web completa** (webapp + solver + asistente IA + login) en AWS con
una **URL HTTPS estable**. La arquitectura es: API Gateway (HTTP API, TLS) →
VPC Link → ALB interno → ECS Fargate (un contenedor con gateway + backend) +
DynamoDB + Bedrock. **La IP ya no cambia** al reiniciar la tarea y no hay que
re-cablear nada a mano.

> La mayoría de los pasos se hacen en **AWS CloudShell** (terminal dentro de la
> consola; trae `aws`, `docker`/`finch`, `git`). Ábrela con el icono `>_` arriba
> a la derecha.

Rellena con los datos de tu cuenta (ejemplo entre comillas, reemplázalos):
- **Región:** `us-east-1`
- **VPC:** `vpc-xxxxxxxx`
- **Subredes (2 AZ):** `subnet-aaaa,subnet-bbbb`

---

## Opción A — Despliegue en un comando (recomendada)

```bash
# 1) Trae el código
cd ~ && git clone https://github.com/DanielHermosilla/AWS-Hackaton.git \
  || (cd AWS-Hackaton && git fetch --all)
cd ~/AWS-Hackaton && git checkout deploy-full && git pull origin deploy-full

# 2) Despliega (build + push a ECR + CloudFormation, todo junto)
VPC_ID=vpc-xxxxxxxx \
SUBNET_IDS=subnet-aaaa,subnet-bbbb \
./DESPLIEGUE-WEB-AWS/deploy.sh
```

Al terminar imprime la **URL HTTPS estable**, por ejemplo
`https://<api-id>.execute-api.us-east-1.amazonaws.com/login.html`.
La tarea tarda ~2-3 min en quedar `healthy`.

Variables opcionales del script: `AWS_REGION` (def. `us-east-1`), `STACK`
(def. `zmd-web`), `REPO` (def. `zmd-web`), `BEDROCK_MODEL`
(def. `amazon.nova-lite-v1:0`), `GW_SECRET` (si no lo pasas, el stack lo
autogenera en Secrets Manager).

**Para actualizar la web** más adelante, vuelve a ejecutar el mismo comando.

---

## Opción B — Paso a paso (si prefieres control manual)

```bash
export AWS_REGION=us-east-1
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export VPC_ID=vpc-xxxxxxxx
export SUBNET_IDS=subnet-aaaa,subnet-bbbb
export ECR=$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com
export REPO=zmd-web
export IMAGE_URI=$ECR/$REPO:latest
```

### 1) ECR (solo la 1ª vez)
```bash
aws ecr create-repository --repository-name "$REPO" --region "$AWS_REGION" \
  || echo "Ya existe."
```

### 2) Build + push
```bash
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$ECR"
docker build -f DESPLIEGUE-WEB-AWS/Dockerfile -t "$REPO:latest" .   # contexto = raíz
docker tag "$REPO:latest" "$IMAGE_URI"
docker push "$IMAGE_URI"
```
> El build tarda varios minutos (SCIP, pandas, numpy…). Si CloudShell se llena,
> `docker system prune -af` y reintenta.

### 3) Infraestructura (CloudFormation)
```bash
aws cloudformation deploy \
  --region "$AWS_REGION" \
  --template-file DESPLIEGUE-WEB-AWS/infra.yaml \
  --stack-name zmd-web \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    ImageUri="$IMAGE_URI" \
    VpcId="$VPC_ID" \
    PrivateSubnetIds="$SUBNET_IDS"
```
Crea: tablas `zmd_users`/`zmd_sessions`, el secreto gateway→backend
(autogenerado), el cluster, la task, el servicio, el **ALB interno**, el
**VPC Link** y el **API Gateway HTTP API**.

> **Seguridad:** la tarea no tiene entrada pública; solo el ALB la alcanza y al
> ALB solo lo alcanza el VPC Link ([#6]). La policy de Bedrock queda acotada al
> `BedrockModelId` ([#2]). El secreto nunca se imprime (`NoEcho`).

### 4) Obtén la URL
```bash
aws cloudformation describe-stacks --region "$AWS_REGION" --stack-name zmd-web \
  --query "Stacks[0].Outputs[?OutputKey=='URL'].OutputValue" --output text
```
Abre esa URL: verás el login. Regístrate (contraseña de 10+ con mayúscula,
minúscula, número y símbolo), entra y verás la web completa.

---

## Verifica que todo funciona

1. `GET /login.html` → formulario de acceso.
2. Registra una cuenta → entras y ves la webapp.
3. Dentro: **Cargar caso** / **Cargar y calcular** → el solver responde. Prueba
   el **asistente IA** (si Bedrock está habilitado en la cuenta).
4. Cierra sesión y confirma que `/index.html` te devuelve a `/login.html`.

---

## Diagnóstico rápido

```bash
aws logs tail /ecs/zmd-web --region us-east-1 --follow
```

- **La tarea no llega a RUNNING / se reinicia:** mira los logs; suele ser memoria
  (sube `Cpu`/`Memory` en `infra.yaml`) o un error de arranque.
- **503/504 desde el API Gateway:** la tarea aún no está `healthy` (espera ~3 min)
  o el ALB no la marca sana. Revisa el target group y `/salud-gateway`.
- **El asistente IA falla:** confirma que Bedrock y el modelo
  (`amazon.nova-lite-v1:0`) están habilitados en `us-east-1` para tu cuenta.
- **"No hay red vial":** esperado si no subiste el graphml; la app usa la
  aproximación sintética. Para calles reales, mira "Mejoras".

---

## Mejoras (opcionales)

- **Dominio propio + ACM:** asociar un dominio al API Gateway con certificado
  gestionado (ya es HTTPS; esto solo cambia el nombre).
- **Escalado:** subir `DesiredCount` requiere externalizar el estado del solver
  (hoy es en memoria por tarea). Para la hackatón, `DesiredCount=1`.
- **Rate-limit robusto:** activar throttling/WAF en el API Gateway (el límite en
  memoria del gateway es best-effort, [#5]).
- **Red vial real:** subir `artifacts/network/competition_delivery.graphml` (al
  repo o a S3) y descomentar su `COPY` en el `Dockerfile`.
