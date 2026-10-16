# 🚀 DESPLIEGUE-WEB-AWS — Web completa (ZMD Mobility) con login, en AWS

Esta carpeta contiene **todo lo necesario** para subir la web completa a AWS:
la webapp avanzada (mapa, escenarios, historial, asistente IA), el solver, y un
**login con base de datos de usuarios** — todo en un único contenedor en ECS
Fargate, detrás de tu API Gateway.

> **Base del código:** rama `deploy-full` (= `feat/ia-asistente-explicacion`,
> la más completa: webapp de `main` + chat asistente de IA).

---

## ¿Qué es cada archivo de esta carpeta?

| Archivo | Para qué sirve |
|---|---|
| **GUIA-CLOUD-CONSOLE.md** | 👉 **EMPIEZA AQUÍ.** Pasos con clics en la consola de AWS para re-subir la web. |
| `gateway.py` | El "portero": sirve login/registro, valida la sesión (cookie) y deja pasar al backend real. |
| `auth.py` | Lógica de usuarios: contraseñas (bcrypt), sesiones, validación. |
| `db.py` | Base de datos de usuarios/sesiones en DynamoDB. |
| `Dockerfile` | Receta para construir la imagen del contenedor (web + solver + login juntos). |
| `start.sh` | Arranca el backend real y el portero dentro del contenedor. |
| `infra.yaml` | Plantilla CloudFormation: crea las tablas, el servicio Fargate y la red. |
| `requirements-gateway.txt` | Dependencias Python del portero. |
| `webapp-login/` | Páginas de login/registro que se copian dentro de la webapp. |

---

## La idea en una imagen

```
Tu navegador
     │   (https://1arb0zuuwj.execute-api.us-east-1.amazonaws.com/...)
     ▼
API Gateway  ──►  ECS Fargate: UN contenedor
                    ├─ gateway.py (puerto 8080)  ← login + cookie de sesión
                    │     │  si hay sesión válida, reenvía a ▼
                    │     ▼
                    └─ backend de main (puerto 8000, solo localhost)
                          webapp + /solve + /history + /bedrock + /assist...
                    DynamoDB: usuarios y sesiones
```

- Sin sesión → te manda a `/login.html`.
- Con sesión → ves la web completa y funciona todo (solver, IA, historial).
- El solver y el estado (grafo vial, sesiones IA) viven en el MISMO proceso, así
  que no se pierden entre peticiones (por eso va todo junto en Fargate, no en Lambda).

---

## Lo que tú harás (resumen)

1. Subir este código a tu entorno AWS (Cloud Console / CloudShell).
2. Construir la imagen Docker y subirla a ECR.
3. Desplegar `infra.yaml` (crea tablas + servicio Fargate).
4. Apuntar tu API Gateway (`1arb0zuuwj`) al nuevo servicio.

**Todo esto está explicado clic a clic en `GUIA-CLOUD-CONSOLE.md`.**
