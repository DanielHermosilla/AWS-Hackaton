#!/usr/bin/env bash
# Despliegue de UN comando para ZMD Mobility en AWS.
#
# Construye la imagen, la sube a ECR y despliega el stack CloudFormation
# (ECS Fargate + ALB interno + API Gateway HTTP API con VPC Link). Al final
# imprime la URL HTTPS estable. Idempotente: re-ejecutar actualiza el servicio.
#
# Uso (desde la RAÍZ del repo, con las variables mínimas):
#   VPC_ID=vpc-xxxx SUBNET_IDS=subnet-a,subnet-b ./DESPLIEGUE-WEB-AWS/deploy.sh
#
# Variables opcionales:
#   AWS_REGION   (def. us-east-1)   STACK        (def. zmd-web)
#   REPO         (def. zmd-web)     BEDROCK_MODEL (def. amazon.nova-lite-v1:0)
#   GW_SECRET    (def. autogenerado por el stack)
set -euo pipefail

AWS_REGION="${AWS_REGION:-us-east-1}"
STACK="${STACK:-zmd-web}"
REPO="${REPO:-zmd-web}"
BEDROCK_MODEL="${BEDROCK_MODEL:-amazon.nova-lite-v1:0}"

: "${VPC_ID:?Define VPC_ID=vpc-xxxx}"
: "${SUBNET_IDS:?Define SUBNET_IDS=subnet-a,subnet-b (dos AZs)}"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${HERE}/.." && pwd)"
cd "${ROOT}"

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
ECR="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
IMAGE_URI="${ECR}/${REPO}:latest"

echo "== Cuenta ${ACCOUNT_ID} · región ${AWS_REGION} · stack ${STACK} =="

echo "[1/4] Asegurando repositorio ECR '${REPO}'…"
aws ecr describe-repositories --repository-names "${REPO}" --region "${AWS_REGION}" >/dev/null 2>&1 \
  || aws ecr create-repository --repository-name "${REPO}" --region "${AWS_REGION}" >/dev/null

echo "[2/4] Login + build + push de la imagen…"
aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin "${ECR}"
docker build -f DESPLIEGUE-WEB-AWS/Dockerfile -t "${REPO}:latest" .
docker tag "${REPO}:latest" "${IMAGE_URI}"
docker push "${IMAGE_URI}"

echo "[3/4] Desplegando infraestructura (CloudFormation)…"
PARAMS=(
  ImageUri="${IMAGE_URI}"
  VpcId="${VPC_ID}"
  PrivateSubnetIds="${SUBNET_IDS}"
  BedrockModelId="${BEDROCK_MODEL}"
)
[ -n "${GW_SECRET:-}" ] && PARAMS+=(GatewaySharedSecret="${GW_SECRET}")

aws cloudformation deploy \
  --region "${AWS_REGION}" \
  --template-file DESPLIEGUE-WEB-AWS/infra.yaml \
  --stack-name "${STACK}" \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides "${PARAMS[@]}"

echo "[4/4] Forzando despliegue nuevo del servicio (imagen fresca)…"
SERVICE="$(aws cloudformation describe-stacks --region "${AWS_REGION}" --stack-name "${STACK}" \
  --query "Stacks[0].Outputs[?OutputKey=='ServiceName'].OutputValue" --output text)"
CLUSTER="$(aws cloudformation describe-stacks --region "${AWS_REGION}" --stack-name "${STACK}" \
  --query "Stacks[0].Outputs[?OutputKey=='ClusterName'].OutputValue" --output text)"
aws ecs update-service --region "${AWS_REGION}" --cluster "${CLUSTER}" \
  --service "${SERVICE}" --force-new-deployment >/dev/null || true

URL="$(aws cloudformation describe-stacks --region "${AWS_REGION}" --stack-name "${STACK}" \
  --query "Stacks[0].Outputs[?OutputKey=='URL'].OutputValue" --output text)"

echo
echo "================================================================"
echo "  Listo. La web queda en (URL HTTPS estable):"
echo "    ${URL}"
echo "  (La tarea tarda ~2-3 min en quedar 'healthy' tras el deploy.)"
echo "  Logs:  aws logs tail /ecs/${STACK} --region ${AWS_REGION} --follow"
echo "================================================================"
