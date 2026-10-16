# 🧭 Guía paso a paso — Re-subir la web correcta por la Cloud Console de AWS

Esta guía te lleva de la mano para desplegar la **web completa** (webapp + solver
+ asistente IA + login) y que tu URL
`https://1arb0zuuwj.execute-api.us-east-1.amazonaws.com/login.html` muestre la
web nueva y funcional.

> **Importante:** la mayoría de estos pasos se hacen en **AWS CloudShell** (una
> terminal dentro de la consola de AWS), porque hay que construir una imagen
> Docker. CloudShell ya trae `aws`, `docker`, `git` y tus permisos. Lo abres con
> el icono `>_` arriba a la derecha en la consola de AWS.

Datos de tu cuenta (de lo que ya desplegaste antes):
- **Account ID:** `831851703432`
- **Región:** `us-east-1`
- **VPC:** `vpc-09d58ad509fae9ec6`
- **Subnet:** `subnet-077db0eb8c150b3db`

---

## Paso 0 — Prepara variables en CloudShell

Abre **CloudShell** y pega esto (ajusta solo si algún dato cambió):

```bash
export AWS_REGION=us-east-1
export ACCOUNT_ID=831851703432
export VPC_ID=vpc-09d58ad509fae9ec6
export SUBNET_ID=subnet-077db0eb8c150b3db
export ECR=$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com
export REPO=zmd-web
export IMAGE_URI=$ECR/$REPO:latest
aws sts get-caller-identity   # confirma que eres la cuenta correcta
```

---

## Paso 1 — Trae el código (la rama correcta)

```bash
cd ~
git clone git@github.com:DanielHermosilla/AWS-Hackaton.git || (cd AWS-Hackaton && git fetch --all)
cd ~/AWS-Hackaton
git checkout deploy-full
git pull origin deploy-full
```

> Si `git clone` por SSH falla en CloudShell, usa HTTPS:
> `git clone https://github.com/DanielHermosilla/AWS-Hackaton.git`

Comprueba que ves la carpeta del despliegue:
```bash
ls DESPLIEGUE-WEB-AWS
```

---

## Paso 2 — Crea el repositorio de imágenes (ECR) — solo la 1ª vez

```bash
aws ecr create-repository --repository-name "$REPO" --region "$AWS_REGION" \
  || echo "Ya existe, sigo."
```

---

## Paso 3 — Construye la imagen y súbela a ECR

```bash
# Login de Docker contra tu ECR
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$ECR"

# Construye (el contexto es la RAÍZ del repo; el Dockerfile está en la subcarpeta)
docker build -f DESPLIEGUE-WEB-AWS/Dockerfile -t "$REPO:latest" .

# Etiqueta y sube
docker tag "$REPO:latest" "$IMAGE_URI"
docker push "$IMAGE_URI"
```

> La construcción tarda varios minutos (instala SCIP, pandas, numpy, etc.). Es
> normal. Si CloudShell se queda sin espacio, borra imágenes viejas con
> `docker system prune -af` y reintenta.

---

## Paso 4 — Despliega la infraestructura (tablas + Fargate)

```bash
aws cloudformation deploy \
  --region "$AWS_REGION" \
  --template-file DESPLIEGUE-WEB-AWS/infra.yaml \
  --stack-name zmd-web \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    ImageUri="$IMAGE_URI" \
    SubnetId="$SUBNET_ID" \
    VpcId="$VPC_ID"
```

Espera a que termine (`Successfully created/updated stack - zmd-web`).
Esto crea: tablas `zmd_users` y `zmd_sessions`, el cluster `zmd-web-cluster`, la
task y el servicio `zmd-web`.

---

## Paso 5 — Obtén la IP pública del contenedor

```bash
CLUSTER=zmd-web-cluster
TASK_ARN=$(aws ecs list-tasks --cluster "$CLUSTER" --service-name zmd-web \
  --region "$AWS_REGION" --query 'taskArns[0]' --output text)

# Espera a que la tarea esté RUNNING (repite si dice PENDING)
aws ecs describe-tasks --cluster "$CLUSTER" --tasks "$TASK_ARN" \
  --region "$AWS_REGION" --query 'tasks[0].lastStatus' --output text

ENI=$(aws ecs describe-tasks --cluster "$CLUSTER" --tasks "$TASK_ARN" \
  --region "$AWS_REGION" \
  --query "tasks[0].attachments[0].details[?name=='networkInterfaceId'].value | [0]" \
  --output text)

export PUBLIC_IP=$(aws ec2 describe-network-interfaces --network-interface-ids "$ENI" \
  --region "$AWS_REGION" \
  --query 'NetworkInterfaces[0].Association.PublicIp' --output text)

echo "La web está en:  http://$PUBLIC_IP:8080/login.html"
```

**Prueba directa** (antes de tocar el API Gateway):
```bash
curl -s "http://$PUBLIC_IP:8080/salud-gateway"      # debe responder {"ok":true,...}
```
Abre `http://PUBLIC_IP:8080/login.html` en el navegador: deberías ver el login.
Regístrate, entra, y verifica que ves la webapp completa.

---

## Paso 6 — Conecta tu API Gateway (la URL `1arb0zuuwj`)

Tu URL pública es un **API Gateway HTTP API**. Hay que hacer que reenvíe todo al
contenedor Fargate (a `http://PUBLIC_IP:8080`). En la **consola de AWS**:

1. Ve a **API Gateway** → busca la API cuyo endpoint es
   `https://1arb0zuuwj.execute-api.us-east-1.amazonaws.com`. Ábrela.
2. En el menú izquierdo entra en **Routes** (Rutas).
   - Si hay rutas viejas (de la web anterior) que apuntan a una Lambda, las vas a
     reemplazar por una ruta "catch-all" hacia el contenedor.
3. Crea una ruta **`ANY /{proxy+}`** (y también **`ANY /`** si no existe):
   - **Create** → Method: `ANY` → Path: `/{proxy+}`.
4. Crea una **Integration** de tipo **HTTP URI** (proxy HTTP):
   - En **Integrations** → **Create** → Integration type: **HTTP URI**.
   - Method: `ANY`.
   - **URL endpoint:** `http://PUBLIC_IP:8080/{proxy}` (reemplaza `PUBLIC_IP` por
     la IP del Paso 5).
   - Guarda y **adjunta** esa integración a la ruta `ANY /{proxy+}`.
   - Para la ruta `ANY /`, usa `http://PUBLIC_IP:8080/` como URL.
5. **Deploy**: en APIs HTTP el deploy suele ser automático en el stage
   `$default`. Si tienes un stage con nombre, usa **Deploy** y elige ese stage.

Ahora abre:
`https://1arb0zuuwj.execute-api.us-east-1.amazonaws.com/login.html`
→ debe mostrar el login nuevo, y al entrar, la web completa.

> **Nota sobre cookies/HTTPS:** el API Gateway sirve por HTTPS (bien, la cookie
> `Secure` funciona). La integración interna va por HTTP a la IP del contenedor;
> eso es normal para esta arquitectura simple.

> **Nota IP cambiante:** si el servicio Fargate reinicia la tarea, la IP pública
> **cambia** y tendrás que actualizar la URL de la integración (Paso 6.4) con la
> IP nueva. Para algo estable y permanente conviene un Load Balancer (ALB) o
> VPC Link; lo dejo indicado en "Mejoras" abajo.

---

## Paso 7 — Verifica que todo funciona

1. `GET /login.html` → se ve el formulario de acceso.
2. Registra una cuenta (contraseña de 10+ caracteres, con mayúscula, minúscula,
   número y símbolo). Deberías entrar y ver la webapp.
3. Dentro: prueba **Cargar caso histórico** / **Cargar y calcular** → el solver
   responde. Prueba el **asistente IA** (si Bedrock está habilitado en la cuenta).
4. Cierra sesión y confirma que `/index.html` te devuelve a `/login.html`.

---

## Si algo falla (diagnóstico rápido)

Mira los logs del contenedor:
```bash
aws logs tail /ecs/zmd-web --region us-east-1 --follow
```

- **La tarea no llega a RUNNING / se reinicia:** revisa los logs; suele ser falta
  de memoria (sube `Memory` en `infra.yaml` y redeploy) o un error de arranque.
- **502 desde el API Gateway:** la IP del Paso 6 no coincide con la IP actual de
  la tarea (cambió), o el Security Group no permite el 8080. Reobtén la IP (Paso 5).
- **El asistente IA falla:** confirma que Bedrock está habilitado en `us-east-1`
  y que el modelo `amazon.nova-lite-v1:0` está disponible para tu cuenta.
- **El solver dice "no hay red vial":** es esperado si no subiste el graphml. La
  app usará la aproximación sintética; para la red vial real, mira "Mejoras".

---

## Actualizar la web más adelante (nuevo código)

```bash
cd ~/AWS-Hackaton && git pull origin deploy-full
docker build -f DESPLIEGUE-WEB-AWS/Dockerfile -t "$REPO:latest" . \
  && docker tag "$REPO:latest" "$IMAGE_URI" && docker push "$IMAGE_URI"
aws ecs update-service --cluster zmd-web-cluster --service zmd-web \
  --force-new-deployment --region us-east-1
# Luego reobtén la IP (Paso 5) y actualiza el API Gateway (Paso 6) si cambió.
```

---

## Mejoras recomendadas (cuando tengas tiempo, no urgente)

- **IP estable:** poner un **Application Load Balancer** delante del servicio y
  que el API Gateway use **VPC Link** → así la IP deja de cambiar y es HTTPS
  extremo a extremo.
- **Seguridad de red:** restringir el Security Group del 8080 para que solo el
  API Gateway/ALB pueda entrar, en vez de `0.0.0.0/0`.
- **Red vial real:** subir `artifacts/network/competition_delivery.graphml` al
  repo (o a S3 y descargarlo en el arranque) y descomentar la línea del `COPY`
  en el `Dockerfile` para que el solver use calles reales.
- **Bedrock mínimo:** restringir la policy de Bedrock al ARN del modelo concreto
  en `infra.yaml` (hoy es `"*"`).
