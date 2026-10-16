# Auditoría de seguridad — Plan B (webapp + login + DynamoDB + proxy + solver Fargate)

Rama: `plan-b-webapp-solver`. Alcance: componentes recién construidos
(`deploy-aws/app/*`, `deploy-aws/solver-api/*`, `deploy-aws/solver/*`,
`webapp/{auth,login,register,boot}.js`). Fecha de auditoría: automática.

Esta auditoría cubre cookies de sesión, token del solver, security groups,
validación de entrada, CORS, secretos en repo e IAM. Las referencias son a
`archivo:línea` sobre el estado del repo tras aplicar las correcciones de la
sección (c); donde una línea se desplazó por mis ediciones lo indico.

---

## (a) Resumen ejecutivo — semáforo por área

| Área | Estado | Comentario |
|------|:------:|-----------|
| 1. Cookies de sesión (`auth.py`) | 🟢 Verde | httponly + samesite=lax + secure(cfg) + path=/, max_age=TTL coherente, token `token_urlsafe(32)`, solo hash SHA-256 en DynamoDB, logout borra cookie **y** sesión. |
| 2. Token del solver (`server.py`/`proxy.py`) | 🟢 Verde | `hmac.compare_digest` en server; el proxy nunca expone el token al cliente ni a logs. Modo abierto bien avisado. |
| 3. Security Group del solver (`infra-ecs.yaml` x2) | 🔴 Rojo | Puertos 8080 y 8501 abiertos a `0.0.0.0/0`. Defensa en profundidad (token), pero expuestos a Internet. El token Streamlit viaja en query string. |
| 4. Validación de entrada (`app.py`/`auth.py`) | 🟡 Amarillo | Validación de email/password correcta; rate-limit **en memoria** (se pierde entre invocaciones Lambda); límite de tamaño en `/api/plans` **añadido** por esta auditoría. |
| 5. CORS | 🟢 Verde | La Lambda unificada NO abre CORS (mismo origen, correcto). CORS `*` solo en el backend viejo fuera de alcance. |
| 6. Secretos en código/repo | 🟡 Amarillo | No hay secretos hardcodeados en los archivos nuevos. PERO el `SOLVER_TOKEN` se compartió en texto plano por chat → **rotar**. |
| 7. IAM | 🟡 Amarillo | DynamoDB con policy por tabla (bien). `bedrock:InvokeModel`/`Converse` con `Resource:"*"` es amplio. |

**Veredicto global: 🟡 Amarillo con un punto 🔴.** El diseño de autenticación y
sesiones es sólido. El riesgo dominante es la **exposición de los puertos del
solver a Internet** (área 3) y la **rotación del token filtrado** (área 6). Nada
de esto bloquea un deploy de demo, pero debe cerrarse antes de producción.

---

## (b) Hallazgos numerados

### 🔴 ALTA

**H-01 — Puerto 8080 del Solver API abierto a todo Internet.**
`deploy-aws/solver-api/infra-ecs.yaml:34-45` (parámetro `AllowedCidr` default
`0.0.0.0/0`) y `:66-72` (ingress `CidrIp: !Ref AllowedCidr`).
El contenedor exige `X-Solver-Token` (defensa en profundidad real), pero el
puerto queda accesible desde cualquier origen: cualquiera puede sondear `/health`
(sin auth), medir latencias, intentar fuerza bruta sobre el token, o lanzar DoS
contra una tarea Fargate con SCIP (2 vCPU/4 GB, 1 solve a la vez → trivial de
saturar con 409/colapso).
**Recomendación (ideal):** poner la Lambda-proxy **dentro de la VPC** y abrir el
SG del solver **solo al SG de la Lambda** (regla SG-a-SG), eliminando la IP
pública (`AssignPublicIp: DISABLED`, subred privada + NAT o VPC endpoints). Si se
mantiene IP pública temporalmente, restringir `AllowedCidr` a la IP/NAT de salida
del proxy. El parámetro ya está preparado para restringir sin tocar código: basta
pasar `AllowedCidr=<cidr>` en el `deploy`. **No cambié el default** para no romper
el deploy simple (la Lambda hoy sale por NAT dinámica), pero déjalo documentado
como acción obligatoria de producción.

**H-02 — Puerto 8501 del Solver Streamlit abierto a todo Internet + token en query string.**
`deploy-aws/solver/infra-ecs.yaml:40-45` (`CidrIp: 0.0.0.0/0`) y
`deploy-aws/solver/solver_gate.py:38-44` (lee `?token=` de la URL).
El token de acceso viaja en la **query string** (`http://IP:8501/?token=...`,
ver `infra-ecs.yaml:140-144`). Las query strings quedan en: logs de proxys/ALB,
historial del navegador, cabecera `Referer` hacia terceros, y CloudWatch si algo
registra la URL. Es un secreto de larga vida expuesto por diseño.
**Recomendación:** (1) restringir el SG a tu IP de administración; (2) **rotar el
`SolverToken`** y tratarlo como comprometido tras cada demo; (3) a futuro, mover
el gate a un header/cookie en vez de query string, o poner el Streamlit detrás de
la misma Lambda/autenticación de la webapp.

**H-03 — `SOLVER_TOKEN` filtrado en texto plano.**
El valor `SOLVER_TOKEN=db1afd528f4c7f63c04b02dc9329813f` se compartió por chat.
Confirmado que **no** aparece hardcodeado en el repo (grep sin coincidencias; solo
hay un placeholder en `deploy-aws/solver-api/README-solver-api.md:73`), pero el
valor concreto debe considerarse **comprometido**.
**Recomendación:** rotarlo ya (y el `SolverInternalToken` si se derivó del mismo),
generándolo con p. ej. `openssl rand -hex 32` o `python -c "import secrets;
print(secrets.token_urlsafe(32))"`, e inyectarlo solo por parámetro de stack / env
var. Nunca pegarlo en chats, issues ni commits.

### 🟡 MEDIA

**H-04 — Rate-limiting en memoria, inefectivo en Lambda.**
`deploy-aws/app/auth.py:72-80` (`_intentos: dict`) usado en
`deploy-aws/app/app.py:59-61` (register) y `:94-95` (login).
El diccionario vive en el proceso. Lambda escala a N contenedores concurrentes y
los recicla; el límite "5 registros / 10 intentos por 10 min por IP" se evalúa
**por instancia**, no globalmente, así que un atacante con reintentos obtiene
`límite × nº_de_contenedores` y, tras un reciclado, el contador se reinicia. Es
una limitación conocida, no un fallo de código.
**Recomendación:** si se quiere rate-limit robusto, llevar el contador a DynamoDB
con un `UpdateItem` atómico (`ADD count :1`) sobre una clave `IP#acción#ventana`
con TTL, o usar el throttling nativo de API Gateway (límite por ruta/burst) como
primera barrera. Documentar como aceptable solo para demo.

**H-05 — `bedrock:InvokeModel`/`Converse` con `Resource:"*"`.**
`deploy-aws/solver-api/infra-ecs.yaml:102-114` y
`deploy-aws/solver/infra-ecs.yaml:73-82`.
La TaskRole puede invocar **cualquier** modelo Bedrock de la cuenta/región.
Además, en `solver-api` el camino por defecto ("standard") ni siquiera usa
Bedrock (comentario en el propio YAML).
**Recomendación:** restringir `Resource` al ARN del/los modelos concretos, p. ej.
`arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-lite-v1:0` (y los
inference-profile ARN si se usan Converse con perfiles). En `solver-api`, si el
default no usa Bedrock, considerar quitar la policy hasta habilitar "adaptive".

**H-06 — Sin límite de número de planes por usuario.**
`deploy-aws/app/app.py` (`/api/plans` POST) y `deploy-aws/app/db.py:put_plan`.
Añadí un límite de **tamaño por plan** (ver sección c), pero no hay tope de
**cantidad** de planes por usuario: un usuario autenticado puede crear planes sin
fin (coste de almacenamiento/consulta ilimitado; `list_plans` hace `query`
completo sin paginar).
**Recomendación:** aplicar un tope por usuario (p. ej. contar antes de `put_plan`
y rechazar >N, o un `UpdateItem` atómico de contador), y paginar `list_plans`.

### 🟢 BAJA / Confirmaciones positivas

**H-07 — Anti path-traversal del servidor estático: confirmado correcto.**
`deploy-aws/app/app.py` función `servir`: resuelve `objetivo = (WEBAPP_DIR /
ruta).resolve()` y exige `WEBAPP_DIR in objetivo.parents or objetivo ==
WEBAPP_DIR` antes de servir; devuelve 404 si se sale del directorio. Correcto
frente a `../` y rutas absolutas. (Re-confirmado según pedía el encargo.)

**H-08 — Redirección abierta en login: mitigada.**
`webapp/auth.js:destinoTrasLogin()` usa lista blanca `{index.html, plan.html}`;
`webapp/boot.js` y `login.js` solo redirigen a `./login.html` relativo. No hay
redirección abierta explotable vía `?next=`.

**H-09 — Comparación de contraseña en tiempo ~constante: presente.**
`deploy-aws/app/auth.py:check_password` siempre verifica un hash (incluso para
usuario inexistente), evitando oráculo de temporización sobre existencia de
cuenta. `bcrypt.checkpw` es constante respecto al hash. Bien.

**H-10 — Cabeceras de seguridad del Solver API: presentes.**
`deploy-aws/solver-api/server.py:_SECURITY_HEADERS` añade `no-store`,
`nosniff`, `no-referrer` a todas las respuestas. Bien. (La Lambda servía HTML
sin `nosniff`; añadido en sección c.)

---

## Detalle por punto del encargo

### 1. Cookies de sesión — 🟢
`deploy-aws/app/auth.py:_set_cookie` (líneas ~132-137): `httponly=True`,
`samesite="lax"`, `secure=COOKIE_SECURE`, `path="/"`, `max_age=SESSION_TTL_S`
(28800 s = 8 h) — coherente con `SESSION_TTL_S` (línea 30) y con el TTL de la
sesión en DynamoDB (`db.create_session` guarda `expires_at = now + ttl_s`).
`COOKIE_SECURE` default `"1"` (línea 31) → HTTPS en prod. ✔
Token: `secrets.token_urlsafe(32)` (`crear_sesion`, línea ~39) = 32 bytes de
entropía (≈43 chars). En DynamoDB solo se guarda `hash_token()` = SHA-256
(`db.create_session`), nunca el token en claro. ✔
Logout (`app.py` `/auth/logout`): llama `auth.borrar_sesion(zmd_session)` →
`db.delete_session(hash_token(token))` **y** `response.delete_cookie(..., path="/")`.
Borra ambos lados. ✔
Nota menor (baja): SHA-256 simple sobre el token es aceptable porque el token ya
tiene 256 bits de entropía (no es adivinable); no requiere KDF.

### 2. Token del solver — 🟢
`server.py:_check_auth` usa `hmac.compare_digest(provided, expected)` → comparación
en tiempo constante. ✔
`proxy.py`: el token se lee de env (`_token()`), se envía solo en el header
`X-Solver-Token` hacia el solver y **nunca** se incluye en respuestas al cliente
ni en logs (no hay `print`/`logger` en `proxy.py`). Los cuerpos de error que
propaga provienen del solver, no del token. ✔
Modo "token vacío = abierto": en `server.py:96-101` se emite `logger.warning`
explícito al arranque advirtiendo que es solo dev. ✔ El navegador nunca recibe el
token (la Lambda es la única que lo conoce). ✔

### 3. Security groups — 🔴 (ver H-01, H-02)
Ambos SG abren a `0.0.0.0/0`. El parámetro `AllowedCidr` del `solver-api` ya está
listo para restringir sin editar la plantilla. **No cambié el default** para no
romper el deploy simple (la Lambda hoy no está en la VPC, su IP de salida es
dinámica). Mitigación ideal documentada en H-01.

### 4. Validación de entrada — 🟡
Email: regex `EMAIL` + tope 254 chars (`auth.py:validar_registro/validar_login`). ✔
Password: política fuerte (`PASS_RE`: ≥10, mayús/minús/dígito/símbolo) + tope 200
chars. ✔
Rate-limit: en memoria → ver H-04 (limitación conocida).
Tamaño de payload en `/api/plans`: **corregido** (ver sección c, límite 300 KB).
Cantidad de planes: sin tope → H-06.
Path-traversal estático: confirmado seguro → H-07.

### 5. CORS — 🟢
`grep` de `allow_origins|Access-Control-Allow-Origin|CORSMiddleware` sobre
`deploy-aws/app/*.py`: **sin coincidencias**. La Lambda unificada no abre CORS,
correcto porque el navegador y la API comparten origen. El único CORS `*` del
repo está en el backend viejo (`backend/lambda_handler.py:20`), **fuera del
alcance** de esta arquitectura y sin uso en el flujo nuevo. Recomendación: si ese
backend viejo se despliega por separado, fijar el `Access-Control-Allow-Origin` a
un dominio concreto; en Plan B no aplica.

### 6. Secretos en código/repo — 🟡 (ver H-03)
No hay tokens/contraseñas/llaves hardcodeados en los archivos nuevos. Todo viene
de env vars / parámetros CloudFormation (`SolverInternalToken`, `SolverToken`,
`SOLVER_API_URL`, nombres de tabla DDB). Único match del grep: placeholder de
documentación en `README-solver-api.md:73`. El `SOLVER_TOKEN` concreto filtrado
por chat debe rotarse (H-03).

### 7. IAM — 🟡
`template.yaml:109-120`: `DynamoDBCrudPolicy` **por tabla** (5 policies acotadas a
cada `TableName`). Menor privilegio razonable. ✔
`infra-ecs.yaml` (x2): `bedrock:InvokeModel`/`Converse` con `Resource:"*"` → H-05.
`AmazonECSTaskExecutionRolePolicy` gestionada: estándar para pull de ECR + logs,
aceptable.

---

## (c) Correcciones aplicadas directamente en esta auditoría

Todas mínimas, sobre `deploy-aws/app/app.py`, validadas con `python3 -c "import
ast; ast.parse(...)"` → **app.py OK**. No alteran contratos ni rutas; no tocan la
funcionalidad verificada por otros agentes.

1. **Límite de tamaño de payload en `POST /api/plans`.**
   - Nueva constante `MAX_PLAN_BODY_BYTES` (default 300 KB, configurable por env
     `MAX_PLAN_BODY_BYTES`) en la sección de config.
   - `api_create_plan` ahora lee el cuerpo crudo (`await request.body()`), y si
     supera el límite responde `413` con `{"ok": false, "error": "El plan es
     demasiado grande para guardarlo."}`. Si no, parsea el JSON igual que antes.
   - Motivo: un ítem de DynamoDB no puede exceder 400 KB; además evita que un
     usuario autenticado guarde instancias arbitrariamente grandes. Mitiga parte
     de H-06 (tamaño; la **cantidad** sigue pendiente).

2. **Cabecera `X-Content-Type-Options: nosniff` en el servidor estático.**
   - `return FileResponse(objetivo, headers={"X-Content-Type-Options":
     "nosniff"})` en la función `servir`.
   - Motivo: evita MIME-sniffing del navegador en los estáticos que sirve la
     Lambda; alinea el comportamiento con las cabeceras que ya aplica el
     Solver API (`server.py:_SECURITY_HEADERS`).

**No se tocó** ningún YAML de infraestructura (los cambios de SG/CIDR/IAM son
decisiones de despliegue y podrían romper el deploy simple; quedan como
recomendaciones H-01/H-02/H-05 con el parámetro `AllowedCidr` ya preparado).

---

## (d) Checklist de hardening para producción

- [ ] **Red del solver (H-01):** meter la Lambda-proxy en la VPC y abrir el SG del
      `solver-api` solo al SG de la Lambda (SG-a-SG); `AssignPublicIp: DISABLED`,
      subred privada. Si no, pasar `AllowedCidr=<IP/NAT del proxy>` en el deploy.
- [ ] **Red del Streamlit (H-02):** restringir SG 8501 a IP de administración.
- [ ] **Rotar `SOLVER_TOKEN` y `SolverInternalToken` (H-03):** generar con
      `secrets.token_urlsafe(32)` / `openssl rand -hex 32`; nunca en chat/commits.
- [ ] **Mover el token del Streamlit fuera de la query string** (header/cookie) o
      ponerlo detrás de la autenticación de la webapp (H-02).
- [ ] **`COOKIE_SECURE=1`** confirmado en el stack de prod (default ya es `"1"`).
- [ ] **Rate-limit robusto (H-04):** DynamoDB atómico con TTL o throttling de API
      Gateway por ruta.
- [ ] **Límite de cantidad de planes por usuario + paginación de `list_plans` (H-06).**
- [ ] **IAM Bedrock mínimo (H-05):** `Resource` al ARN del modelo concreto; quitar
      la policy del `solver-api` si el camino por defecto no usa Bedrock.
- [ ] **Cabeceras de seguridad en todas las respuestas de la Lambda:** considerar
      `Content-Security-Policy`, `X-Frame-Options: DENY`/`frame-ancestors 'none'`,
      `Strict-Transport-Security` (vía API Gateway o middleware) para las páginas HTML.
- [ ] **Secretos como `NoEcho`/Secrets Manager:** los parámetros `SolverToken`,
      `SolverInternalToken` ya son `NoEcho`; para prod, considerar Secrets Manager
      e inyección por referencia en vez de parámetro de stack.
- [ ] **Logs:** confirmar que ni API Gateway ni ALB registran query strings con
      tokens; retención de CloudWatch ya en 7 días (aceptable).
- [ ] **TTL de DynamoDB:** `zmd_sessions` y `zmd_activity` tienen TTL habilitado
      en `template.yaml` ✔ (verificar que el atributo `expires_at` se puebla
      siempre — confirmado en `db.create_session`/`add_activity`).
