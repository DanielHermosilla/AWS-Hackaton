# 🚀 DESPLIEGUE-WEB-AWS — Web completa (ZMD Mobility) con login, en AWS

Esta carpeta contiene **todo lo necesario** para subir la web completa a AWS:
la webapp avanzada (mapa, escenarios, historial, asistente IA), el solver y un
**login con base de datos de usuarios** — en un único contenedor en ECS Fargate,
detrás de un **ALB interno + API Gateway (HTTP API) con VPC Link**, lo que da una
**URL HTTPS estable** que no cambia al reiniciar la tarea.

> **Base del código:** rama `deploy-full` (webapp de `main` + chat asistente IA).

---

## Arquitectura (estable y segura)

```
Navegador
   │  https://<api-id>.execute-api.us-east-1.amazonaws.com/login.html   (URL fija)
   ▼
API Gateway (HTTP API, $default, TLS)        ← HTTPS extremo a extremo, cookie Secure
   │  VPC Link (privado)
   ▼
ALB interno (solo acepta el VPC Link)
   │  HTTP :8080
   ▼
ECS Fargate · 1 contenedor
   ├─ gateway.py (8080)  ← login + cookie de sesión + CSRF + cabeceras seguras
   │     │  firma X-Gateway-Auth + usuario, reenvía a ▼
   │     ▼
   └─ backend (127.0.0.1:8000, solo loopback)  ← webapp + /solve + /history + IA
DynamoDB: zmd_users, zmd_sessions (cifradas, TTL)      Bedrock: asistente IA
```

- Sin sesión → `/login.html`. Con sesión → la web completa.
- La tarea **no tiene IP pública de entrada**: solo el ALB la alcanza, y al ALB
  solo lo alcanza el VPC Link del API Gateway.
- El secreto gateway→backend se **autogenera** (Secrets Manager) si no lo pasas.

---

## ¿Qué es cada archivo?

| Archivo | Para qué sirve |
|---|---|
| **GUIA-CLOUD-CONSOLE.md** | Guía paso a paso (incluye el despliegue de un solo comando). |
| `deploy.sh` | 👉 **Despliegue de UN comando**: build + push a ECR + CloudFormation. |
| `infra.yaml` | CloudFormation: DynamoDB + Fargate + ALB + VPC Link + HTTP API. |
| `gateway.py` | Portero: login/registro, sesión, CSRF, cabeceras de seguridad, proxy. |
| `auth.py` | Usuarios: contraseñas (bcrypt), sesiones, validación. |
| `db.py` | Tablas de usuarios/sesiones en DynamoDB. |
| `Dockerfile` | Imagen del contenedor (web + solver + login), no-root, con `tini`. |
| `start.sh` | Arranca backend + gateway con espera de readiness y apagado ordenado. |
| `requirements-gateway.txt` | Dependencias Python del portero. |
| `webapp-login/` | Páginas de login/registro que se superponen a la webapp. |
| `_verify.py` | Prueba local del gateway (17 checks, sin AWS). |
| `../AUDITORIA-SEGURIDAD.md` | Auditoría de seguridad consolidada (hallazgos, estado y pruebas). |

---

## Despliegue en un comando

Desde la **raíz del repo** (en CloudShell o con tu CLI de AWS configurada):

```bash
VPC_ID=vpc-xxxxxxxx \
SUBNET_IDS=subnet-aaaa,subnet-bbbb \
./DESPLIEGUE-WEB-AWS/deploy.sh
```

Al terminar imprime la **URL HTTPS estable**. La tarea tarda ~2-3 min en quedar
`healthy`. Para actualizar la web más adelante, vuelve a ejecutar el mismo comando.

Detalle clic a clic (y alternativa por consola) en **`GUIA-CLOUD-CONSOLE.md`**.
