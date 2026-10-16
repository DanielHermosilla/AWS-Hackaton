# Auditoría de seguridad — DESPLIEGUE-WEB-AWS

> Revisión estática del código de despliegue web (gateway de login + backend
> ECS Fargate + DynamoDB + Bedrock) que se publicará tras una URL/servicio AWS.
> Fecha: 2026-10-16. Alcance: `DESPLIEGUE-WEB-AWS/` y su interacción con
> `backend/local_server.py`. No se ejecutó la aplicación; es revisión de código.
>
> **Esto es un informe de hallazgos.** No se modificó código de la aplicación.
> Severidades: 🔴 Alta · 🟠 Media · 🟡 Baja · 🔵 Informativo.

---

## Resumen ejecutivo

El diseño de dos capas (gateway de login en 8080, backend solo en loopback) es
razonable y la lógica de contraseñas/sesiones (bcrypt, token de 256 bits, solo
el SHA-256 en BD, cookie `httpOnly`+`SameSite`+`Secure`) está bien resuelta. Los
problemas principales no están en la criptografía sino en **la exposición de red
(HTTP en texto plano, puerto público 0.0.0.0/0 sin TLS en el contenedor), el
alcance IAM de Bedrock (`Resource: "*"`), la ausencia de cabeceras de seguridad
y protección CSRF en el gateway, y la confianza total del backend interno en el
gateway**. Para un despliegue de hackatón detrás de API Gateway varios son
aceptables como riesgo asumido, pero deben quedar documentados.

| # | Severidad | Hallazgo | Archivo |
|---|-----------|----------|---------|
| 1 | 🔴 | Tráfico en texto plano (HTTP :8080) y `Secure` cookie incompatible con HTTP | infra.yaml, Dockerfile, start.sh |
| 2 | 🔴 | IAM de Bedrock con `Resource: "*"` y acciones amplias | infra.yaml |
| 3 | 🟠 | Sin protección CSRF en endpoints `/auth/*` y proxy (cookie `SameSite=Lax`) | gateway.py, auth.py |
| 4 | 🟠 | Backend interno confía en cualquier petición de loopback (sin identidad de usuario) | gateway.py, local_server.py |
| 5 | 🟠 | Rate-limit en memoria por proceso: inútil con varias tareas/reinicios | auth.py |
| 6 | 🟠 | Security Group abre 8080 a `0.0.0.0/0` con IP pública directa (sin ALB/WAF) | infra.yaml |
| 7 | 🟡 | Falta de cabeceras de seguridad en el gateway (CSP, HSTS, X-Frame-Options…) | gateway.py |
| 8 | 🟡 | Sin límite de tamaño de cuerpo en `/auth/*` del gateway | gateway.py |
| 9 | 🟡 | El gateway reenvía cabeceras del cliente sin lista blanca (incluye `X-Forwarded-*`, `X-History-Filename`) | gateway.py |
| 10 | 🟡 | Enumeración de cuentas por código 409 en el registro | gateway.py |
| 11 | 🟡 | Sesiones no se renuevan ni invalidan al cambiar contraseña; sin límite por usuario | auth.py, db.py |
| 12 | 🟡 | Superficie LLM/Bedrock: contenido de usuario llega al modelo sin saneo documentado | assist_service.py |
| 13 | 🔵 | Documentación referencia `GUIA-CLOUD-CONSOLE.md` inexistente; IDs reales en repo | LEEME-PRIMERO.md, infra.yaml |
| 14 | 🔵 | `TaskRole` de DynamoDB incluye `Query` sin tabla con índice que lo use | infra.yaml |

---

## Hallazgos detallados

### 1. 🔴 Tráfico en texto plano y cookie `Secure` sobre HTTP
- **Dónde:** `infra.yaml` (SecurityGroup abre TCP 8080, `AssignPublicIp: ENABLED`,
  salida `http://IP_PUBLICA:8080/login.html`); `Dockerfile`/`start.sh`
  (`uvicorn --host 0.0.0.0 --port 8080`, sin TLS); `auth.py` (`COOKIE_SECURE=1`).
- **Problema:** El contenedor sirve HTTP plano en una IP pública. Las
  credenciales de login y la cookie de sesión viajarían **sin cifrar** si alguien
  accede por IP:8080. Además, la cookie se marca `Secure`, de modo que **no se
  enviará sobre HTTP** — la sesión se rompe salvo que API Gateway termine TLS y
  reescriba a HTTPS. El modelo de seguridad depende enteramente de que el único
  acceso sea vía API Gateway con HTTPS, pero el SG no lo obliga (ver #6).
- **Recomendación:** Garantizar que el acceso directo por IP quede bloqueado
  (SG solo desde el rango/puente de API Gateway o un ALB interno), forzar HTTPS
  extremo a extremo, y documentar que `COOKIE_SECURE=1` **exige** que el borde
  entregue HTTPS. Añadir redirección/ rechazo de HTTP plano.

### 2. 🔴 IAM de Bedrock demasiado amplio (`Resource: "*"`)
- **Dónde:** `infra.yaml`, `TaskRole` → política `ddb-y-bedrock`:
  `Action: [bedrock:InvokeModel, …, bedrock:Converse, bedrock:ConverseStream]`,
  `Resource: "*"`. El propio comentario admite «amplio; restringir en producción».
- **Problema:** La tarea puede invocar **cualquier** modelo de Bedrock de la
  cuenta. Si el contenedor se ve comprometido (p.ej. vía el asistente, #12), el
  atacante usa toda la superficie de Bedrock y genera costos.
- **Recomendación:** Restringir `Resource` al ARN del foundation model /
  inference profile concreto (`arn:aws:bedrock:us-east-1::foundation-model/<id>`)
  y dejar solo las acciones realmente usadas (`Converse`/`InvokeModel`).

### 3. 🟠 Sin protección CSRF en el gateway
- **Dónde:** `gateway.py` (`/auth/login`, `/auth/register`, `/auth/logout`, y el
  proxy `POST /{ruta}`); `auth.py` `set_cookie(..., samesite="lax")`.
- **Problema:** La autenticación se basa en cookie. `SameSite=Lax` mitiga pero
  **no elimina** CSRF para peticiones `POST` de navegación de nivel superior, y
  el proxy acepta cualquier `POST` autenticado por cookie sin token anti-CSRF ni
  verificación de `Origin`/`Sec-Fetch-Site` (el gateway **elimina** esas
  cabeceras antes de reenviar, así que el backend tampoco las ve). Un sitio
  malicioso podría disparar acciones autenticadas (`/solve`, `/history/*`,
  `/bedrock/*`) con la cookie del usuario.
- **Recomendación:** Validar `Origin`/`Sec-Fetch-Site` en el gateway para
  peticiones con cookie, o exigir una cabecera personalizada (`X-Requested-With`
  / token CSRF) en todos los `POST` autenticados. No descartar `Sec-Fetch-Site`
  antes de decidir.

### 4. 🟠 El backend interno confía ciegamente en el loopback
- **Dónde:** `gateway.py` (reescribe `Host` y descarta `Cookie`/`Origin` al
  reenviar) + `local_server.py` (`_same_origin()` valida solo Host/Origin; «No
  authentication»). El backend **no recibe la identidad del usuario**.
- **Problema:** La autorización vive solo en el gateway. Cualquier proceso que
  alcance `127.0.0.1:8000` (otro contenedor sidecar, un SSRF desde el propio
  backend, un fallo que exponga 8000) obtiene acceso total sin login. El backend
  no distingue usuarios: todos comparten los 4 `run` y el historial en memoria
  (fuga de datos entre cuentas).
- **Recomendación:** Añadir un secreto compartido gateway→backend (cabecera
  firmada) que el backend exija, y propagar el identificador de usuario para
  aislar `RunStore`/historial por sesión. Confirmar que 8000 nunca se publica.

### 5. 🟠 Rate-limit en memoria por proceso
- **Dónde:** `auth.py` `_intentos: dict` + `rate_limit()`.
- **Problema:** El límite es por proceso. Con `DesiredCount>1`, reinicios de
  tarea o el reciclado de ECS, el contador se reparte/reinicia y el atacante
  evade el bloqueo de fuerza bruta contra `/auth/login`. Hoy `DesiredCount: 1`
  lo mitiga, pero es frágil y se rompe al escalar.
- **Recomendación:** Mover el rate-limit a un almacén compartido (DynamoDB con
  TTL, o similar) o delegarlo a API Gateway/WAF (throttling + reglas de rate).

### 6. 🟠 Security Group público sin ALB/WAF
- **Dónde:** `infra.yaml` `SecurityGroupIngress: 8080 desde 0.0.0.0/0`,
  `AssignPublicIp: ENABLED`.
- **Problema:** La tarea es accesible desde todo Internet en 8080. El comentario
  dice «el contenido exige login», pero expone directamente el gateway (fuerza
  bruta, escaneo, DoS) y depende de que nadie use la IP en vez de API Gateway.
  Sin ALB/WAF no hay capa de filtrado, TLS gestionado ni reglas de abuso.
- **Recomendación:** Restringir el ingress al origen de API Gateway (VPC Link +
  NLB/ALB interno, o prefix list del servicio) y no asignar IP pública, o al
  menos poner un ALB con ACM + WAF delante.

### 7. 🟡 Faltan cabeceras de seguridad en el gateway
- **Dónde:** `gateway.py` (respuestas `/auth/*` y proxy). El backend interno sí
  pone `X-Content-Type-Options`, `Referrer-Policy`, `Cache-Control: no-store`,
  pero el gateway reenvía tal cual y en sus propias respuestas no añade ninguna.
- **Problema:** Sin `Content-Security-Policy`, `Strict-Transport-Security`,
  `X-Frame-Options`/`frame-ancestors` (clickjacking), la webapp queda más
  expuesta a XSS/encuadre.
- **Recomendación:** Añadir CSP estricta, HSTS (una vez forzado HTTPS),
  `X-Frame-Options: DENY` y `X-Content-Type-Options: nosniff` en el gateway.

### 8. 🟡 Sin límite de tamaño de cuerpo en `/auth/*`
- **Dónde:** `gateway.py` `await request.json()` sin tope previo. El backend
  interno sí aplica `MAX_*_BYTES`, pero el gateway lee el cuerpo completo del
  login/registro sin límite.
- **Problema:** Un `POST` con cuerpo enorme a `/auth/register` consume memoria
  antes de validar (DoS barato). `validar_registro` limita campos **después** de
  parsear todo el JSON.
- **Recomendación:** Rechazar por `Content-Length` por encima de unos KB antes
  de leer el cuerpo en el gateway.

### 9. 🟡 Reenvío de cabeceras del cliente sin lista blanca
- **Dónde:** `gateway.py` proxy: copia **todas** las cabeceras del cliente salvo
  una lista negra pequeña (`host`, `origin`, `cookie`, …).
- **Problema:** Pasan al backend cabeceras como `X-Forwarded-For`,
  `X-History-Filename`, `X-Real-IP` o cualquiera que el cliente invente. El
  backend usa `X-History-Filename` (`unquote(...)`) para nombrar archivos; una
  lista negra es frágil frente a cabeceras no previstas.
- **Recomendación:** Usar lista blanca de cabeceras a reenviar
  (`content-type`, `accept`, `x-history-filename` saneada, `user-agent`) en vez
  de lista negra, y normalizar/validar `X-History-Filename`.

### 10. 🟡 Enumeración de cuentas en el registro
- **Dónde:** `gateway.py` `/auth/register` responde `409 "Ese correo ya está
  registrado."`.
- **Problema:** Permite a un atacante enumerar correos registrados. (El login sí
  usa mensaje genérico y verificación en tiempo constante — bien.)
- **Recomendación:** Responder genérico (p.ej. «si el correo es válido te
  enviamos instrucciones») o aceptar el riesgo si el registro es abierto por
  diseño; documentarlo.

### 11. 🟡 Ciclo de vida de sesiones
- **Dónde:** `auth.py`/`db.py`: no hay rotación de token, ni invalidación de
  sesiones existentes al cambiar contraseña (no hay flujo de cambio aún), ni
  límite de sesiones concurrentes por usuario; TTL fijo de 8 h sin renovación.
- **Problema:** Un token filtrado es válido 8 h completas y no se puede revocar
  salvo borrando la fila concreta. Al añadir «cambiar contraseña» habrá que
  invalidar sesiones.
- **Recomendación:** Prever revocación por usuario (índice `email`→sesiones) y
  rotación de token tras login sensible.

### 12. 🟡 Superficie de prompt/LLM (Bedrock)
- **Dónde:** `assist_service.py` `chat()` → `Asistente(...).turno(mensaje)`; el
  mensaje del usuario y el contenido de archivos adjuntos van al modelo.
- **Problema:** Entrada de usuario no confiable llega al LLM. Riesgo de prompt
  injection para obtener comportamientos no deseados o exfiltrar contexto. Unido
  a #2 (IAM amplio), amplifica el impacto. No se observa saneo/segregación
  explícita del contenido no confiable en esta capa.
- **Recomendación:** Tratar todo el contenido de usuario/archivo como datos no
  confiables, encapsularlo claramente en el prompt, limitar lo que el asistente
  puede accionar y **nunca** ejecutar salidas del modelo (coherente con AGENTS.md).
  Mantener límites de tokens/tiempo (ya existen: `CHAT_TIMEOUT_S`,
  `CHAT_MAX_TOKENS`).

### 13. 🔵 Documentación y datos sensibles en repo
- **Dónde:** `LEEME-PRIMERO.md` referencia `GUIA-CLOUD-CONSOLE.md` (no existe en
  la carpeta). `infra.yaml`/`LEEME-PRIMERO.md` incluyen un **Account ID / ECR**
  (`831851703432…`) y el ID de API Gateway (`1arb0zuuwj`) reales.
- **Problema:** Fricción (guía ausente) y exposición de identificadores de
  cuenta/recursos en un repo que se subirá. No son secretos críticos, pero
  facilitan reconocimiento.
- **Recomendación:** Añadir la guía o quitar la referencia; parametrizar/ocultar
  Account ID y API ID (usar placeholders en ejemplos).

### 14. 🔵 Permiso DynamoDB `Query` sin uso
- **Dónde:** `infra.yaml` `TaskRole` incluye `dynamodb:Query`, pero las tablas
  solo se acceden por clave (`GetItem`/`PutItem`/`DeleteItem`) y no hay GSI.
- **Problema:** Permiso innecesario (mínimo privilegio).
- **Recomendación:** Eliminar `Query` hasta que exista un índice que lo requiera.

---

## Lo que está bien (no cambiar)

- **Contraseñas:** bcrypt con salt por usuario y verificación en tiempo
  ~constante incluso si el usuario no existe (`check_password`): evita oráculo de
  tiempo (`auth.py`).
- **Sesiones:** token aleatorio de 256 bits; en BD solo se guarda su SHA-256; TTL
  también como atributo TTL de DynamoDB; cookie `httpOnly`+`SameSite`+`Secure`.
- **Validación de entrada** de registro/login con límites de longitud y política
  de contraseña fuerte server-side (no solo en el cliente).
- **Separación de capas:** backend solo en loopback, gateway como único puerto
  expuesto; el backend además valida mismo-origen y aplica límites de cuerpo,
  `X-Content-Type-Options`, path traversal en estáticos, etc.
- **Aviso honesto en el cliente** (`webapp-login/auth.js`): deja claro que la
  sesión del navegador es solo de UI y la seguridad real vive en el servidor.

---

## Prioridad sugerida (hackatón)

1. **Antes de publicar la URL:** #1 (HTTPS extremo a extremo + cookie), #6
   (cerrar 8080 al público / forzar paso por API Gateway) y #2 (acotar IAM de
   Bedrock). Son los de mayor impacto y bajo esfuerzo de configuración.
2. **Siguiente:** #3 (CSRF/validación de Origin en el gateway) y #4 (secreto
   gateway→backend + aislamiento por usuario).
3. **Endurecimiento:** #5, #7, #8, #9, #10, #12.
4. **Higiene:** #11, #13, #14.
