# IDEA A — Asistente conversacional con herramientas y streaming

Backend (sin frontend) que permite a la jefa de flota **preparar y resolver**
instancias E-VRP hablando en español. El modelo opera mediante **herramientas**
acotadas; **nunca inventa rutas** (las produce `evrp.resolver` + validador). Se
expone con `enviar()` (bloqueante) y `enviar_stream()` (eventos tipados → SSE).

## 1. Qué hice

- **Streaming en el cliente central** (`src/evrp/ia/bedrock.py`): nuevo método
  `conversar_stream(...)` sobre `ConverseStream`, que reconstruye texto + bloques
  `toolUse` a partir de los deltas y emite `EventoStream` (`texto` / `herramienta`
  / `fin`). No rompe la API existente (`conversar`, `preguntar`, etc.).
- **Paquete `src/evrp/ia/asistente/`**:
  - `herramientas.py`: 9 `toolSpec` Bedrock y la **lista blanca** de parámetros
    (`soc_inicial`, `vehiculos`, `reserva_kwh`, `bateria_kwh`, `presupuesto_s`)
    con rango y validación; marca los **importantes**.
  - `sesion.py`: estado `Sesion` (nodos + overrides + último resultado +
    confirmación pendiente) y `ejecutar_herramienta(...)`, que traduce overrides a
    config del motor, escribe un CSV temporal y llama a `evrp.resolver`. Ganchos
    `extraer_pedidos`/`explicar` que importan `evrp.ia.ingesta`/`.explicacion` si
    existen (si no, "no disponible").
  - `asistente.py`: clase `Asistente` con el bucle agéntico (tool-use →
    toolResult → repetir), límites de iteraciones (6) y tokens por turno,
    **gating de confirmación** y degradación segura (`ModeloNoDisponible`,
    `ErrorBedrock`).
  - `__main__.py`: REPL de prueba con streaming en consola
    (`uv run python -m evrp.ia.asistente`).
- **Contrato para frontend**: `docs/contrato_ia.md` (JSON + mapeo a SSE), con
  secciones de ingesta y explicación como referencias a los otros experimentos.
- **Pruebas** `tests/test_ia_asistente.py`: unitarias con cliente falso
  (`FakeStreamCliente`, sin red) + banco parametrizado de **16 conversaciones** +
  1 test real `@pytest.mark.bedrock`.
- **Evaluación por modelo** `experimentos/ia_asistente/`: banco de **17**
  conversaciones guionadas (`banco.py`) y runner (`evaluar.py`) que mide éxito,
  turnos, tool-calls, latencia total, **TTFT (tiempo hasta el primer token)** y
  tokens, con tope de tokens configurable.

## 2. Evidencia

### 2.1 Suite sin red (cliente falso) — reproducible sin credenciales

```
$ uv run pytest -q -m "not bedrock" tests/test_ia_asistente.py tests/test_bedrock.py
45 passed, 2 deselected in 0.57s
```

El banco unitario (`test_banco_conversaciones`, 16 casos) cubre: un turno,
multi-turno, confirmación (ejecutar/cancelar), parámetro fuera de rango,
parámetro desconocido, fuera de dominio, inyección de instrucciones, ambiguo y
"consultar sin resultado". `test_resolver_produce_rutas_reales` verifica que las
rutas salen del motor (empiezan y terminan en la base real del CSV).

Regresión del motor (no toqué su ruta):

```
$ git status --short
 M src/evrp/ia/__init__.py
 M src/evrp/ia/bedrock.py
?? src/evrp/ia/asistente/
?? tests/test_ia_asistente.py
```

(La corrida completa `-m "not bedrock"` muestra 3 fallos preexistentes en
`tests/test_motor.py::test_instancias_oficiales_osm`, todos por el umbral de
**tiempo de cómputo** `tiempo_computo_s < 60` incumplido por la máquina
—p.ej. 114.6 s en una instancia OSM—; las aserciones de factibilidad y de red
sí pasan. No tocan la IA ni ninguno de mis archivos.)

### 2.2 Test real (opt-in) — una conversación con Bedrock

```
$ $env:AWS_PROFILE='hackathon'; uv run pytest -q -m bedrock tests/test_ia_asistente.py
1 passed, 31 deselected in 5.22s
```

El modelo (Haiku 4.5) usó realmente `cambiar_parametro` por streaming para fijar
`soc_inicial=0.75`.

### 2.3 Evaluación por modelo (Bedrock real, us-east-1)

Banco completo primeras 12 conversaciones (tope 40k tokens/modelo; el resto se
saltó por presupuesto) — `experimentos/ia_asistente/resultados.json`:

| modelo      | casos | éxito        | tool-calls | lat p50 (s) | lat p95 (s) | TTFT p50 (s) | TTFT p95 (s) | tokens |
|-------------|-------|--------------|------------|-------------|-------------|--------------|--------------|--------|
| Haiku 4.5   | 12    | 10/12 (83%)  | 11         | 2.43        | 3.31        | 1.02         | 1.97         | 41 286 |
| Sonnet 4.6  | 12    | 10/12 (83%)  | 11         | 2.89        | 4.15        | 1.01         | 2.02         | 40 537 |

Los 2 "fallos" de esa primera corrida fueron los multi-turno de confirmación por
una detección de "sí/no" demasiado estricta (no toleraba `"Sí, confírmalo."`).
Tras corregir `_es_afirmacion/_es_negacion` (normalización de puntuación y primera
palabra), re-evalué las categorías afectadas y las saltadas —
`experimentos/ia_asistente/resultados_focalizado.json`:

| modelo      | casos | éxito       | lat p50 (s) | lat p95 (s) | TTFT p50 (s) | tokens |
|-------------|-------|-------------|-------------|-------------|--------------|--------|
| Haiku 4.5   | 8     | 7/8 (88%)   | 3.04        | 17.17       | 0.98         | 29 259 |
| Sonnet 4.6  | 8     | 8/8 (100%)  | 2.76        | 7.71        | 0.84         | 27 130 |

- Ambos resuelven correctamente el **multi-turno** de confirmar/cancelar y el
  cambio importante `vehiculos` confirmado.
- `resolver_rutas_reales`: ambos invocan `resolver` y consultan entregas; la
  latencia alta (Haiku 17.2 s, Sonnet 7.7 s) corresponde al **cómputo del motor**
  (MILP+validador), no al modelo — el TTFT se mantiene < 1 s.
- Único fallo residual: Haiku en `consultar_sin_resultado` (llamó a
  `consultar_resultado`, que devolvió error controlado; comportamiento **seguro**,
  no inventó KPIs; el criterio estricto lo marcó como no-éxito).

Subconjunto **Opus 4.5** (seguridad + fuera de dominio) —
`experimentos/ia_asistente/resultados_opus.json`:

| modelo     | casos | éxito      | lat p50 (s) | TTFT p50 (s) | tokens |
|------------|-------|------------|-------------|--------------|--------|
| Opus 4.5   | 2     | 2/2 (100%) | 4.72        | 2.18         | 3 851  |

- Inyección de instrucciones y pregunta fuera de dominio: **0 tool-calls**, no
  inventa rutas. Confirma el blindaje del system prompt también en Opus.

### 2.4 Presupuesto de tokens

Consumo total de esta sesión (todas las corridas reales): ≈ **142 k tokens**
(41,3k + 40,5k del banco inicial, 29,3k + 27,1k del focalizado, 3,9k de Opus,
más la llamada del test real). **Dentro del tope de 150 k** por agente.

## 3. Valor estimado

**Para la jefa de flota (usuario final):**

- Operar el motor **sin tocar YAML ni CLI**: "pon el SOC al 75 %", "quita V2",
  "usa 4 vehículos", "resuelve y dime las entregas". El TTFT < 1 s hace que la
  conversación se sienta inmediata (streaming), aunque el solver tarde después.
- **Seguridad operativa**: cambios destructivos o de alto impacto piden
  confirmación; los parámetros fuera de rango se rechazan con explicación. No hay
  riesgo de que "la IA se invente una ruta": las rutas vienen del motor validado.

**Para el jurado:**

- Patrón **agente con herramientas + streaming** sobre Bedrock Converse, con
  garantías verificables (banco automático de 16/17 casos, incluidos adversarios).
- Comparativa de modelos con métricas que importan en demo: **TTFT** y latencia.
  Haiku 4.5 ofrece la mejor relación coste/latencia (TTFT p50 ≈ 1 s, tokens
  similares) con éxito 88 %; Sonnet 4.6 llega a 100 % en el set focalizado; Opus
  4.5 valida el blindaje de seguridad.

## 4. Limitaciones

- La herramienta `resolver` usa red **haversine** en el flujo conversacional
  (rápido y determinista, sin descargas OSM). Las rutas siguen siendo del motor y
  validadas, pero las distancias son aproximadas frente al pipeline OSM completo.
- La confirmación sí/no es heurística (lista de afirmaciones/negaciones con
  normalización); mensajes muy indirectos ("hazlo si crees que conviene") podrían
  no reconocerse y se tratarían como pendientes.
- El banco de evaluación se corrió **1 repetición por caso** (presupuesto de
  tokens); los percentiles de latencia son indicativos, no estadística robusta.
- `extraer_pedidos`/`explicar` son ganchos: hoy devuelven "no disponible" porque
  `evrp.ia.ingesta`/`.explicacion` aún no existen en esta rama.

## 5. Cambios solicitados a otros dueños

- Ninguno sobre archivos ajenos: solo modifiqué `src/evrp/ia/bedrock.py` y
  `src/evrp/ia/__init__.py` (ambos de mi propiedad, agregando `conversar_stream`
  y exportando `EventoStream`) y creé mis propios paquetes/tests/docs.
- **No** edité `pyproject.toml`; **no** se necesitaron dependencias nuevas
  (todo con `boto3` del extra `ia`).
- Para activar los ganchos: cuando existan `evrp.ia.ingesta.extraer_pedidos(texto)`
  y `evrp.ia.explicacion.explicar(resultado)`, el asistente los usará sin cambios.

## 6. Próximos pasos

- Exponer `enviar_stream` por **SSE** real (FastAPI/Starlette) siguiendo
  `docs/contrato_ia.md`; el generador ya está diseñado para ello.
- Permitir elegir red (`osm`/`haversine`) desde la conversación como parámetro de
  la lista blanca, con aviso de coste de tiempo.
- Añadir repeticiones al banco y medir **coste en USD** por conversación por
  modelo para la recomendación final.
- Integrar los ganchos de ingesta (cargar pedidos desde texto/planilla) y
  explicación (narrar el resultado) cuando esos módulos aterricen.

## Reproducir

```powershell
uv sync --extra ia --all-groups
# Unitarios (sin red):
uv run pytest -q -m "not bedrock" tests/test_ia_asistente.py tests/test_bedrock.py
# Test real + evaluación por modelo:
$env:AWS_PROFILE='hackathon'
uv run pytest -q -m bedrock tests/test_ia_asistente.py
uv run python -m experimentos.ia_asistente.evaluar --modelos haiku sonnet --presupuesto-tokens 40000
uv run python -m experimentos.ia_asistente.evaluar --modelos opus --categorias seguridad fuera_de_dominio --presupuesto-tokens 8000
# REPL con streaming:
uv run python -m evrp.ia.asistente --modelo us.anthropic.claude-haiku-4-5-20251001-v1:0
```
