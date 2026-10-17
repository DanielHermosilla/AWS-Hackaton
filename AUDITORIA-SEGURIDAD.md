# AUDITORÍA DE SEGURIDAD — ZMD Mobility (despliegue web AWS)

> **PARA LA IA QUE LEA ESTE ARCHIVO:** Este es el documento único y autoritativo
> de la auditoría de seguridad del despliegue web. Contiene (a) los hallazgos
> originales, (b) el estado actual de cada uno, (c) qué se cambió y dónde, (d) la
> evidencia de pruebas ejecutadas y cómo reproducirlas, y (e) lo que queda
> pendiente. No necesitas contexto previo de la conversación. Si vas a continuar
> el trabajo, lee primero las secciones 0, 3 y 7.

- **Fecha de la auditoría:** 2026-10-16
- **Autor:** revisión asistida (Kiro CLI) a petición del equipo.
- **Tipo:** revisión de código estática + pruebas funcionales locales + build de
  contenedor de humo. **No** se desplegó en AWS real.
- **Severidades:** 🔴 Alta · 🟠 Media · 🟡 Baja · 🔵 Informativo.
- **Estados:** `CORREGIDO` (cambio en código, probado) · `DOCUMENTADO` (riesgo
  aceptado o pendiente de decisión, sin cambio de código) · `PENDIENTE`.

---

## 0. Ubicación del código y convenciones

- **Repositorio original (NO modificado):** `/var/home/idk/AWS-Hackaton/`
- **Carpeta de fixes (TODO el trabajo vive aquí):** `/var/home/idk/AWS-Hackaton-SECURITY-FIX/`
  - `DESPLIEGUE-WEB-AWS/` — gateway de login, infra CloudFormation, Dockerfile,
    scripts, páginas de login, y las pruebas del gateway.
  - `backend/` — copia del backend de la app (necesaria para el fix #4), con su
    prueba de enforcement.
  - `AUDITORIA-SEGURIDAD.md` — **este archivo** (fuente de verdad).
- **Entorno Python para pruebas:** `/var/home/idk/AWS-Hackaton/.venv-dev/bin/python`
  (tiene fastapi, httpx, bcrypt, boto3, cfn-lint).
- Los identificadores `[#N]` aparecen como comentarios en el código (p.ej.
  `# [#3] ...`) para rastrear cada cambio hasta su hallazgo.

### Arquitectura del sistema auditado

```
Navegador
   │  HTTPS (URL estable de API Gateway)
   ▼
API Gateway (HTTP API, TLS, $default)
   │  VPC Link (privado)
   ▼
ALB interno  (solo acepta el VPC Link)
   │  HTTP :8080
   ▼
ECS Fargate · 1 contenedor
   ├─ gateway.py (0.0.0.0:8080)  → login, cookie de sesión, CSRF, cabeceras,
   │     │                          firma X-Gateway-Auth + X-Gateway-User
   │     ▼  reenvía al backend
   └─ backend  (127.0.0.1:8000, solo loopback)  → webapp + /solve + /history + IA
DynamoDB: zmd_users, zmd_sessions (SSE + TTL)     Bedrock: asistente IA
```

---

## 1. Resumen ejecutivo

El diseño de dos capas (gateway de login en 8080, backend solo en loopback) es
razonable y la lógica de contraseñas/sesiones (bcrypt, token de 256 bits, solo el
SHA-256 en BD, cookie `httpOnly`+`SameSite`+`Secure`) está bien resuelta. Los
problemas originales no estaban en la criptografía sino en la exposición de red,
el alcance IAM de Bedrock, la ausencia de cabeceras de seguridad y protección
CSRF en el gateway, y la confianza total del backend en el gateway.

**Estado tras los fixes:** 10 de 14 hallazgos `CORREGIDO` (incluidos los 2 de
severidad Alta y 3 de 4 de severidad Media). Los 4 restantes son 🟡/🟠 de menor
impacto, quedan `DOCUMENTADO` como riesgo aceptado para la hackatón o pendientes
de una decisión de producto. Además se endureció la infraestructura para que sea
estable y presentable en AWS (ver sección 4).

| # | Sev | Hallazgo | Estado |
|---|-----|----------|--------|
| 1 | 🔴 | Tráfico en texto plano (HTTP :8080) y cookie `Secure` incompatible con HTTP | **CORREGIDO** |
| 2 | 🔴 | IAM de Bedrock con `Resource: "*"` | **CORREGIDO** |
| 3 | 🟠 | Sin protección CSRF en `/auth/*` y proxy | **CORREGIDO** |
| 4 | 🟠 | Backend confía en cualquier petición de loopback (sin identidad) | **CORREGIDO** |
| 5 | 🟠 | Rate-limit en memoria por proceso (se evade al escalar) | DOCUMENTADO |
| 6 | 🟠 | Security Group abre 8080 a `0.0.0.0/0` con IP pública directa | **CORREGIDO** |
| 7 | 🟡 | Faltan cabeceras de seguridad en el gateway (CSP, HSTS, …) | **CORREGIDO** |
| 8 | 🟡 | Sin límite de tamaño de cuerpo en `/auth/*` | **CORREGIDO** |
| 9 | 🟡 | Reenvío de cabeceras del cliente por lista negra, no blanca | **CORREGIDO** |
| 10 | 🟡 | Enumeración de cuentas por 409 en el registro | DOCUMENTADO |
| 11 | 🟡 | Sesiones sin rotación/revocación; TTL fijo 8 h | DOCUMENTADO |
| 12 | 🟡 | Prompt injection: contenido de usuario llega al LLM sin saneo explícito | DOCUMENTADO |
| 13 | 🔵 | Docs con IDs reales de cuenta/API y guía ausente | **CORREGIDO** |
| 14 | 🔵 | `TaskRole` con `dynamodb:Query` sin uso | **CORREGIDO** |

---

## 2. Hallazgos detallados (con problema, dónde, y qué se hizo)

### 1. 🔴 Tráfico en texto plano y cookie `Secure` sobre HTTP — CORREGIDO
- **Problema original:** el contenedor servía HTTP plano en IP pública; las
  credenciales y la cookie viajarían sin cifrar, y la cookie `Secure` no se
  enviaría sobre HTTP (sesión rota). El modelo dependía de que el único acceso
  fuese API Gateway con HTTPS, pero nada lo obligaba.
- **Dónde:** `infra.yaml`, `Dockerfile`, `start.sh`, `auth.py` (`COOKIE_SECURE`).
- **Fix:** nueva arquitectura HTTPS extremo a extremo: API Gateway (TLS) → VPC
  Link → ALB interno → tarea. La tarea ya no expone puerto público a Internet;
  `COOKIE_SECURE=1` es coherente porque el borde entrega HTTPS. HSTS se emite
  solo cuando `COOKIE_SECURE` está activo.

### 2. 🔴 IAM de Bedrock demasiado amplio — CORREGIDO
- **Problema original:** `TaskRole` permitía `bedrock:*Model/Converse*` con
  `Resource: "*"` → invocar cualquier modelo de la cuenta; amplifica un
  compromiso (ver #12) y el costo.
- **Dónde:** `infra.yaml`, política `ddb-y-bedrock`.
- **Fix:** `Resource` acotado al modelo configurado:
  `arn:aws:bedrock:<region>::foundation-model/<BedrockModelId>` y el
  `inference-profile` equivalente. Acciones restringidas a las usadas.

### 3. 🟠 Sin protección CSRF en el gateway — CORREGIDO
- **Problema original:** autenticación por cookie con `SameSite=Lax`; el proxy
  aceptaba cualquier POST autenticado sin verificar origen (y descartaba
  `Sec-Fetch-Site`). Un sitio ajeno podía disparar `/solve`, `/history/*`, etc.
- **Dónde:** `gateway.py`, `auth.py` (`set_cookie(..., samesite="lax")`).
- **Fix:** `gateway._origen_confiable()` valida en todos los POST autenticados
  (`/auth/*` y proxy): acepta `Sec-Fetch-Site` same-origin/same-site/none, o
  `Origin` == host, o la cabecera `X-Requested-With: zmd-webapp`. Rechaza
  cross-site con 403. El `fetch` del cliente (`webapp-login/auth.js`) ahora envía
  `X-Requested-With: zmd-webapp`.

### 4. 🟠 El backend confía ciegamente en el loopback — CORREGIDO
- **Problema original:** la autorización vivía solo en el gateway; cualquier
  proceso que alcanzara `127.0.0.1:8000` tenía acceso total sin login. El backend
  no recibía identidad de usuario (los `run` y el historial en memoria se
  comparten entre cuentas).
- **Dónde:** `gateway.py`, `backend/local_server.py`.
- **Fix:** secreto compartido `GATEWAY_SHARED_SECRET`. El gateway firma cada
  petición reenviada con `X-Gateway-Auth` y propaga `X-Gateway-User`. El backend
  (`_same_origin`) exige la firma con `hmac.compare_digest` (tiempo constante)
  salvo en `/health`. En `infra.yaml` el secreto se autogenera en Secrets Manager
  si no se pasa. **Compatible hacia atrás:** sin secreto definido, el backend se
  comporta como antes.
  - *Nota para quien continúe:* la propagación de `X-Gateway-User` ya existe en
    la cabecera, pero el backend **todavía no aísla** `RunStore`/historial por
    usuario. El aislamiento real por usuario queda PENDIENTE (ver sección 7).

### 5. 🟠 Rate-limit en memoria por proceso — DOCUMENTADO
- **Problema:** `auth._intentos` es por proceso; con `DesiredCount>1` o reinicios
  se evade la fuerza bruta contra `/auth/login`.
- **Estado:** sin cambio de código. Mitigado por `DesiredCount=1` (estado del
  solver en memoria lo exige igualmente). **Recomendación:** throttling/WAF en
  API Gateway, o almacén compartido (DynamoDB con TTL) si se escala.

### 6. 🟠 Security Group público sin ALB/WAF — CORREGIDO
- **Problema original:** `SecurityGroupIngress` 8080 desde `0.0.0.0/0` con IP
  pública directa.
- **Dónde:** `infra.yaml`.
- **Fix:** Security Groups encadenados: el VPC Link solo entra al ALB y el ALB
  solo entra a la tarea:8080 (`SourceSecurityGroupId`). No hay ruta de entrada
  desde Internet a la tarea.

### 7. 🟡 Faltan cabeceras de seguridad en el gateway — CORREGIDO
- **Problema original:** el gateway no añadía CSP/HSTS/X-Frame-Options.
- **Dónde:** `gateway.py`.
- **Fix:** middleware `_cabeceras_seguridad` que añade `Content-Security-Policy`
  (con `frame-ancestors 'none'`), `X-Frame-Options: DENY`,
  `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`,
  `Cross-Origin-Opener-Policy: same-origin`, y `Strict-Transport-Security`
  cuando `COOKIE_SECURE` está activo.

### 8. 🟡 Sin límite de tamaño de cuerpo en `/auth/*` — CORREGIDO
- **Problema original:** el gateway leía el cuerpo de login/registro sin tope
  (DoS por memoria).
- **Dónde:** `gateway.py`.
- **Fix:** `MAX_AUTH_BODY_BYTES = 8 KiB` + `_leer_json_limitado()` que rechaza por
  `Content-Length` y por tamaño real antes de parsear → responde 413.

### 9. 🟡 Reenvío de cabeceras sin lista blanca — CORREGIDO
- **Problema original:** el proxy copiaba todas las cabeceras del cliente salvo
  una lista negra pequeña (pasaban `X-Forwarded-*`, `X-History-Filename`, etc.).
- **Dónde:** `gateway.py`.
- **Fix:** `FORWARD_ALLOWLIST` (lista blanca: `content-type`, `accept`,
  `accept-language`, `user-agent`, `x-history-filename`). Todo lo demás se
  descarta; el gateway añade `host`, y `X-Gateway-Auth`/`X-Gateway-User`.

### 10. 🟡 Enumeración de cuentas en el registro — DOCUMENTADO
- **Problema:** `/auth/register` responde 409 «Ese correo ya está registrado»,
  lo que permite enumerar correos. (El login sí usa mensaje genérico y tiempo
  constante.)
- **Estado:** se mantiene por UX. **Decisión pendiente:** respuesta genérica vs.
  aceptar el riesgo si el registro es abierto por diseño.

### 11. 🟡 Ciclo de vida de sesiones — DOCUMENTADO
- **Problema:** sin rotación de token ni revocación por usuario; TTL fijo 8 h sin
  renovación. Un token filtrado vale 8 h.
- **Estado:** no hay flujo de cambio de contraseña aún. **Recomendación:** índice
  `email`→sesiones para revocar, y rotación tras acciones sensibles.

### 12. 🟡 Superficie de prompt/LLM (Bedrock) — DOCUMENTADO
- **Problema:** el mensaje del usuario y archivos adjuntos llegan al modelo
  (`backend/assist_service.py` → `Asistente.turno`). Riesgo de prompt injection;
  unido a #2 amplificaba el impacto (ya mitigado al acotar IAM).
- **Estado:** límites de tokens/tiempo ya existen (`CHAT_TIMEOUT_S`,
  `CHAT_MAX_TOKENS`). **Recomendación:** tratar el contenido como no confiable,
  encapsularlo en el prompt, no ejecutar nunca salidas del modelo.

### 13. 🔵 Docs con IDs reales / guía ausente — CORREGIDO
- **Problema original:** `LEEME-PRIMERO.md` referenciaba una guía ausente;
  `infra.yaml`/docs incluían Account ID y API ID reales.
- **Fix:** guía reescrita (`GUIA-CLOUD-CONSOLE.md`) con el flujo nuevo; Account
  ID de ejemplo genérico; identificadores como placeholders.

### 14. 🔵 Permiso DynamoDB `Query` sin uso — CORREGIDO
- **Problema original:** `TaskRole` incluía `dynamodb:Query` sin GSI que lo use.
- **Fix:** eliminado; solo `GetItem`/`PutItem`/`DeleteItem`.

---

## 3. Inventario de cambios por archivo

| Archivo (en `AWS-Hackaton-SECURITY-FIX/`) | Hallazgos | Resumen del cambio |
|---|---|---|
| `DESPLIEGUE-WEB-AWS/gateway.py` | 3,4,7,8,9 | CSRF, cabeceras de seguridad, límite de cuerpo, lista blanca, firma al backend. |
| `backend/local_server.py` | 4 | Exige `X-Gateway-Auth` (hmac constante) salvo `/health`. |
| `DESPLIEGUE-WEB-AWS/infra.yaml` | 1,2,4,6,13,14 | ALB + VPC Link + HTTP API, SG encadenados, IAM Bedrock acotado, secreto autogenerado, SSE/PITR, sin `Query`. |
| `DESPLIEGUE-WEB-AWS/Dockerfile` | 1,4 | `tini` PID 1, usuario no-root, `APP_DIR`, env del secreto. |
| `DESPLIEGUE-WEB-AWS/start.sh` | — | Espera readiness del backend; apagado ordenado (trap). |
| `DESPLIEGUE-WEB-AWS/deploy.sh` | — | Despliegue de un comando (build+push+CFN+URL). |
| `DESPLIEGUE-WEB-AWS/webapp-login/auth.js` | 3 | Envía `X-Requested-With: zmd-webapp` en los `fetch`. |
| `DESPLIEGUE-WEB-AWS/GUIA-CLOUD-CONSOLE.md`, `LEEME-PRIMERO.md` | 1,2,6,13 | Docs reescritas con la arquitectura nueva y placeholders. |
| `DESPLIEGUE-WEB-AWS/_verify.py` | 3,4,7,8,9 | Suite de pruebas del gateway (17 checks). |
| `backend/_verify_gateway_auth.py` | 4 | Suite de pruebas del enforcement del backend. |

---

## 4. Estabilidad y presentación para AWS (más allá de los hallazgos)

- **URL HTTPS estable:** API Gateway HTTP API + VPC Link + ALB interno → la URL
  no cambia al reiniciar la tarea (antes: IP pública cambiante y re-cableado manual).
- **Contenedor robusto:** `tini` como PID 1 (apagado limpio ante SIGTERM de ECS),
  usuario **no-root** (uid 10001), `start.sh` con espera de readiness y apagado
  ordenado de ambos procesos.
- **Datos protegidos:** DynamoDB con cifrado en reposo (SSE) y PITR en `zmd_users`.
- **Observabilidad:** Container Insights + health checks (ALB `/salud-gateway` y
  health check del contenedor).
- **Despliegue de un comando:** `deploy.sh`.

---

## 5. Lo que ya estaba bien (NO cambiar)

- **Contraseñas:** bcrypt con salt por usuario y verificación en tiempo
  ~constante aunque el usuario no exista (`auth.check_password`) → evita oráculo
  de tiempo.
- **Sesiones:** token aleatorio de 256 bits; en BD solo su SHA-256; TTL también
  como atributo TTL de DynamoDB; cookie `httpOnly`+`SameSite`+`Secure`.
- **Validación de entrada** de registro/login con límites de longitud y política
  de contraseña fuerte del lado servidor.
- **Separación de capas:** backend solo en loopback; el backend valida
  mismo-origen, aplica límites de cuerpo, `nosniff`, y bloquea path traversal en
  estáticos.
- **Aviso honesto en el cliente** (`webapp-login/auth.js`): la sesión del
  navegador es solo de UI; la seguridad real vive en el servidor.

---

## 6. Evidencia de pruebas ejecutadas (local, sin AWS)

Todas pasaron el 2026-10-16 con `/var/home/idk/AWS-Hackaton/.venv-dev/bin/python`.

1. **Suite del gateway** — `DESPLIEGUE-WEB-AWS/_verify.py`: **17/17**.
   Cubre funcionalidad original (registro/login/logout/sesión/proxy/protección)
   y fixes #3 (CSRF cross-site→403, same-origin→200), #7 (cabeceras), #8
   (cuerpo→413), #9 (lista blanca), #4 (firma `X-Gateway-Auth`+`X-Gateway-User`).
2. **Suite del backend** — `backend/_verify_gateway_auth.py`: **4/4**.
   `/health` exento; firma correcta→200; firma ausente→403; firma incorrecta→403.
3. **Compatibilidad hacia atrás:** sin `GATEWAY_SHARED_SECRET`, el backend→200.
4. **cfn-lint** sobre `infra.yaml`: **sin errores** (se ignora `W3037`, falso
   positivo: la spec de cfn-lint no reconoce `bedrock:Converse`/`ConverseStream`,
   que son acciones válidas y requeridas).
5. **`py_compile`** de gateway/auth/db/local_server y **`bash -n`** de
   start.sh/deploy.sh: **OK**.
6. **Build + run de contenedor de humo (Podman)**: imagen construida; en vivo
   `/salud-gateway`→200 con cabeceras de seguridad; `/index.html` sin sesión→302
   a login; CSRF cross-site→403; cuerpo gigante→413; `/solve` sin sesión→401;
   `start.sh` esperó al backend antes de abrir el gateway. Imagen temporal
   eliminada tras la prueba.

### Cómo reproducir

```bash
VENV=/var/home/idk/AWS-Hackaton/.venv-dev/bin
cd /var/home/idk/AWS-Hackaton-SECURITY-FIX
$VENV/python DESPLIEGUE-WEB-AWS/_verify.py
$VENV/python backend/_verify_gateway_auth.py
$VENV/cfn-lint DESPLIEGUE-WEB-AWS/infra.yaml --ignore-checks W3037
bash -n DESPLIEGUE-WEB-AWS/start.sh && bash -n DESPLIEGUE-WEB-AWS/deploy.sh
```

---

## 7. Pendiente / decisiones abiertas (para quien continúe)

1. **Aislamiento por usuario en el backend (deriva de #4):** el backend ya recibe
   `X-Gateway-User` pero NO segrega `RunStore`/historial por usuario; hoy el
   estado en memoria es compartido. Si se habilita multiusuario real, implementar
   el aislamiento. Mientras tanto, es un entorno de un solo equipo.
2. **Parámetros reales de despliegue:** `deploy.sh` necesita `VPC_ID` y
   `SUBNET_IDS` (dos AZ) reales de la cuenta del evento.
3. **#5 / #10 / #11 / #12:** aceptar como riesgo asumido para la hackatón o
   abordar (rate-limit en WAF, respuesta genérica en registro, revocación de
   sesiones, endurecimiento del prompt).
4. **Validación en AWS real:** nada de esto se probó contra Bedrock/DynamoDB/ECS
   ni con el TLS de API Gateway. Hacer un `cloudformation deploy` de prueba antes
   de producción y revisar logs (`aws logs tail /ecs/zmd-web --follow`).
5. **No se ha subido al repositorio original** ni creado rama/PR. El trabajo vive
   solo en `AWS-Hackaton-SECURITY-FIX/`.
