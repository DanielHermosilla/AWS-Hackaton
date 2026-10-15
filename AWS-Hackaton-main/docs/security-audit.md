# Auditoría de seguridad inicial - ev-routing

Fecha: 2026-10-15  
Alcance: código local del proyecto `ev-routing` (`src/`, `tests/`, `pyproject.toml`, configuración). No se escanearon redes ni se realizaron pruebas de intrusión externas.

## Resumen ejecutivo

No se encontraron secretos hardcodeados ni uso de `eval`/`exec`/`subprocess` en el código auditado. Las integraciones AWS usan la cadena estándar de credenciales (`boto3.Session`), sin claves incrustadas. El riesgo principal no es hoy inyección de código, sino **validación insuficiente de entradas en la futura capa web/API**, **ausencia de límites de recursos y costo en AWS**, y **falta de logging/auditoría**.

## Activos revisados

- `src/ev_routing/contracts.py`
- `src/ev_routing/config.py`
- `src/ev_routing/inputs.py`
- `src/ev_routing/network.py`
- `src/ev_routing/model.py`
- `src/ev_routing/solve.py`
- `src/ev_routing/validation.py`
- `src/ev_routing/cli.py`
- `src/ev_routing/llm/bedrock.py`
- `src/ev_routing/llm/tuning.py`
- `pyproject.toml`
- `.gitignore`

## Resultados

### Hallazgo S-01 - Sin secretos hardcodeados

- Severidad: informativo / positivo.
- Evidencia: búsqueda de patrones tipo `AKIA`, `aws_secret`, `private_key`, `password`, `token`, `api_key`.
- Observación: solo aparecen términos documentales o variables de configuración. AWS se configura mediante `AWS_DEFAULT_REGION`, `BEDROCK_MODEL_ID` y `AWS_PROFILE`.

### Hallazgo S-02 - Cadena estándar de credenciales AWS

- Severidad: positivo.
- Evidencia: `BedrockClient._get_client()` usa `boto3.Session(profile_name=...)` y `session.client("bedrock-runtime", region_name=...)`.
- Mejor práctica: en despliegue usar rol IAM de la instancia/contenedor en lugar de `AWS_PROFILE`; nunca commitear credenciales. Esto ya está contemplado en la documentación (`AGENTS.md`).

### Hallazgo S-03 - Cliente Bedrock sin timeout, límites ni trazabilidad

- Severidad: media.
- Evidencia: `BedrockClient.converse()` llama a `client.converse(...)` sin `Config` de timeout/retry explícito, ni límite de número de llamadas, ni registro de tokens.
- Riesgo: consumo prolongado, retries no acotados, costos potenciales y ausencia de auditoría de uso.
- Recomendación: añadir timeout de conexión/lectura, retries acotados y un contador/métrica de llamadas y tokens cuando exista tarifa verificada.

### Hallazgo S-04 - Validación de entradas pensada para CLI, no para web/API

- Severidad: media/alta (al integrar UI).
- Evidencia: `cli.py` permite rutas arbitrarias (`--instance`, `--output`) y carga JSON directamente con `json.loads`; `read_nodes_dataframe()` abre cualquier ruta indicada.
- Riesgo: traversal de rutas, consumo excesivo de memoria con archivos CSV/JSON grandes y exposición de errores internos.
- Recomendación: cuando exista web, confinar rutas a carpetas permitidas, validar tamaño de archivo, saneamiento de errores y rate limiting.

### Hallazgo S-05 - `.gitignore` insuficiente

- Severidad: media.
- Evidencia: `.gitignore` contiene únicamente `data/`.
- Riesgo: commits accidentales de `.env`, caches, `__pycache__`, artefactos o resultados sensibles.
- Recomendación: ignorar `.env*`, `artifacts/`, cachés Python, binarios locales y archivos de bloqueo no necesarios.

### Hallazgo S-06 - No hay controles de autenticación/autorización

- Severidad: informativa (aún no hay web).
- Evidencia: no existe módulo de login ni control de acceso. El usuario indica que se añadirá después.
- Riesgo: cuando se agregue la interfaz, todos los endpoints podrían quedar públicos.
- Recomendación: definir login/roles antes de exponer la app, y asociar acciones a usuario/sesión en logs.

### Hallazgo S-07 - Ajuste (tuning) acepta opciones potencialmente no soportadas

- Severidad: baja/media.
- Evidencia: `DEFAULT_ALLOWED` incluye nombres genéricos (`heuristics`, `cuts`, `presolve`, `branching`) y `validate_proposal` solo valida que los parámetros estén en la lista permitida.
- Riesgo: propuestas que no coincidan exactamente con opciones reales de HiGHS; el adaptador las ignora, pero puede generar falsas expectativas.
- Recomendación: documentar la tabla exacta de opciones de HiGHS versión usada y validar por solver/version, no solo por nombre.

### Hallazgo S-08 - Validación independiente no comprueba saturación intermedia estricta

- Severidad: baja para seguridad, media para integridad de resultados.
- Evidencia: en `validation.py`, la comprobación `abs(b_next - expected)` se desactiva con `pass` en lugar de generar violación.
- Recomendación: decidir si esa comprobación debe ser dura o reportada; hoy evita detectar discrepancias silenciosamente.

## Recomendaciones priorizadas

1. Endurecer `BedrockClient` con timeout, retries acotados y límites explícitos.
2. Expandir `.gitignore` para evitar secretos y artefactos.
3. Añadir logging estructurado y trazabilidad (`run_id`, usuario, acción, errores) antes de la web.
4. Diseñar validación de rutas/tamaño de archivos y rate limiting para la capa web.
5. Introducir autenticación/autorización y control de roles antes de exponer endpoints.
6. Documentar opciones de solver permitidas por versión.

## Lo que no se auditó

- Redes, infraestructura real o sistemas externos.
- Dependencias con CVEs (no hay `pip audit` disponible en este entorno).
- UI web, porque aún no está implementada.
- Credenciales reales de AWS; no se inspeccionaron secretos fuera del repositorio.

## Siguiente paso sugerido

Implementar logging y controles de acceso en una siguiente iteración, junto con la futura interfaz web, y añadir pruebas de seguridad para carga de archivos, tamaño de payload y credenciales ausentes.