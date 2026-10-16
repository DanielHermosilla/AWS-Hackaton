# Motor eléctrico con LLM: uso e integración futura con webapp

Esta rama, `codex/evrp-llm-search`, contiene el motor, el preprocesamiento y
la CLI. **Este cambio no fusiona ni modifica la webapp.** El punto de conexión
es `ev_routing.pipeline.run_instance`; el navegador no debe ejecutar el solver
ni llamar a AWS.

Se contrastó esta guía con `origin/codex/webapp` en
`a372d03efc270b0ac23769e5d4334c2d3f4144ff`. Esa rama contiene una importación
parcial del motor de `624203573bffdeec334a9e07a64b361a515f9725`, documentada
en `docs/integration-beta.md` y `docs/solver-source.json`. El merge posterior
debe revisar cambios producidos desde estas revisiones.

## 1. Qué ejecuta el motor

```text
CSV + red vial + estimación energética
  -> ProblemInstance vial
  -> prepare_service_graph
  -> instancia de pricing + PathArchive ligado mediante SHA-256
  -> incumbentes físicos, ALNS y búsqueda memética
  -> maestro por rutas completas + pricing + cortes en SCIP
  -> expansión a calles + validación independiente
  -> resultado JSON
          ^
          | políticas validadas, nunca cambios de física
       LLMHead <-> Bedrock
```

La preparación permanece separada de la búsqueda. En el caso simple usa
Dijkstra; con regeneración o restricciones temporales conserva alternativas
con perfiles de batería y tiempo, e intersecciones que no conviene comprimir.
`arc_id` identifica cada alternativa del multigrafo. El límite de trabajo del
preprocesamiento no es un límite de movimientos de la ruta.

El maestro selecciona rutas completas sin H. El pricing heurístico busca
columnas rápidamente; el pricing exacto conserva recursos continuos y el
alcance de los certificados. ALNS destruye y repara soluciones; la búsqueda
memética combina órdenes de clientes y los repara físicamente; los sub-SCIP
recomponen rutas del pool. Una cota de ese pool restringido no certifica el
problema completo. [Detalles y API de SCIP](llm-head-search.md).

El LLM recibe el perfil de la instancia, un extracto físico declarado, la
política actual, telemetría y las acciones implementadas. Puede configurar
heurísticas, lotes de pricing, branching, selección de nodos, cortes compatibles
y parámetros nativos admitidos. Su respuesta JSON se valida con `RoutePolicy`.
El hilo remoto no toca objetos SCIP; los callbacks aplican la política en el
hilo del solver. No se ejecuta código generado por el modelo.

## 2. Parada energética en 0,5 %

`SolverConfig.energy_relative_gap` tiene default **`0.005`**, también en
`config/default.json`. Se puede cambiar con `--energy-relative-gap`.
Solo afecta al motor `scip-routes`; `relative_gap` mantiene su uso previo para
entregas y backends heredados.

Con incumbente energético factible `U` y cota inferior global válida `L`,
la parada compara:

```text
abs(U - L) / max(abs(U), 1e-10) <= energy_relative_gap
```

La cota corresponde a las entregas fijadas. Debe proceder de pricing completo
o de una relajación válida; una cota del maestro con pricing interrumpido no
sirve. No se detiene por gap sin una cota finita y coherente.

- `energy_gap_limit` significa tolerancia alcanzada; no significa timeout.
- `proven_optimal` energético y `lexicographic_optimal` permanecen falsos si
  no hay cierre numérico de la cota.
- El objetivo principal sigue siendo maximizar entregas. Si ese máximo no se
  probó, la energía se informa condicionada al cumplimiento alcanzado.
- `--energy-relative-gap 0` desactiva esta parada anticipada y busca cierre
  exacto dentro del presupuesto.
- Un `Gap 0.00 %` de un sub-SCIP no reemplaza el gap global del resultado JSON.

El presupuesto de 120 s es un máximo blando, no un tiempo que haya que consumir.
Las heurísticas iniciales todavía usan una fracción de ese presupuesto antes de
calcular la cota energética. No se promete detenerse en el instante del primer
testigo completo.

## 3. Modelo GPT, autenticación y trazabilidad

La CLI y `scripts/test_clients.sh` usan por defecto **GPT-6 Luna**:
`us.openai.gpt-6-luna`, con esfuerzo de razonamiento **`low`**. El adaptador usa
`boto3` y **Bedrock Converse**, enviando
`additionalModelRequestFields.reasoning.effort`. No usa el campo de esfuerzo
de Anthropic. No requiere una clave de OpenAI ni una sesión del producto ChatGPT.
La elección busca menor latencia; no hay un benchmark que pruebe superioridad
en estas instancias.

Se reutilizan región `us-east-1` y perfil `hackathon`, ambos configurables.
`--bedrock-model` o `BEDROCK_MODEL_ID` reemplazan el modelo predeterminado.
`--bedrock-fast-model` permite otro modelo para eventos posteriores; si se
omite, se mantiene GPT-6 Luna. La API Python exige un `model_id` explícito
en `BedrockConfig` para activar `adaptive`.

**Acceso comprobado el 16 de octubre de 2026:** el perfil de inferencia existe,
pero el rol `WSParticipantRole` del perfil local `hackathon` rechaza su
invocación con `AccessDeniedException`: hay un `explicit deny` en
`ws-bedrock-model-allowlist-policy-1`. No se modificaron permisos.
El administrador debe habilitar el modelo, o el operador debe proporcionar
un perfil autorizado mediante `--aws-profile`. Cambiar un ID o una variable
no concede permisos. Hasta resolverlo, la corrida se registra como fallback;
no debe anunciarse como una decisión aplicada de GPT.

Un intento previo por Responses recibió HTTP 401. La implementación final
reutiliza Converse y deja que el SDK gestione la autenticación. No se añadió
un cliente HTTP, un generador de tokens ni dependencias nuevas.

Los logs conservan solicitudes, respuestas finales, tokens, propuestas, campos
efectivamente cambiados y motivos de rechazo o vencimiento. No contienen
credenciales, cabeceras firmadas ni razonamiento interno del proveedor.
Los `.mps` exportados representan maestros con las columnas conocidas: **no
contienen la física ni todas las rutas futuras**. Solo se envían si existen y
caben en el presupuesto; no se garantiza enviar toda la instancia al modelo.

## 4. Ejecución por terminal

Desde la raíz de esta rama, instalar el entorno del lockfile:

```bash
uv sync --locked --extra dw
```

Para una instancia ya preparada, con salida exacta necesaria para auditar
SCIP y las respuestas del LLM:

```bash
uv run --locked --extra dw ev-routing run \
  --solver scip-routes --search-policy adaptive \
  --instance artifacts/service-instance.json \
  --road-instance artifacts/instance.json \
  --path-archive artifacts/service-paths.json \
  --time-limit-seconds 120 --energy-relative-gap 0.005 \
  --bedrock-model us.openai.gpt-6-luna --llm-reasoning-effort low \
  --aws-profile hackathon --aws-region us-east-1 \
  --llm-timeout-seconds 8 --llm-max-calls 2 --llm-max-output-tokens 2048 \
  --llm-instance-context-bytes 8000 \
  --tee --show-llm-trace \
  --solver-log-directory artifacts/solve-gpt/logs \
  --output artifacts/solve-gpt/result.json
```

Sustituir `hackathon` por un perfil con acceso cuando se disponga de él.
`--search-policy standard` ejecuta el mismo motor sin consultas remotas.
El [README](../README.md#desde-archivos-originales-locales-con-scip-y-llm-en-vivo)
incluye la preparación desde CSV, eVED y GraphML y la simulación a 40 clientes.
No confundir el tiempo de resolución con preparar la red desde cero.

Consultar `logs/decisions/NN/llm-request.json`, `llm-response.json`,
`logs/llm-decision.json`, `result.json.tuning` y `result.json.solve.phases`.
`runtime_seconds.llm` puede solaparse con resolución: no se suma al total.
Una respuesta pendiente o vencida puede no tener todavía consumo conocido.

## 5. Conexión Python para el backend

El ejemplo siguiente usa la API actual. El backend debe decidir las rutas de
archivo y el directorio de cada ejecución:

```python
from ev_routing.contracts import SolverConfig
from ev_routing.inputs import load_instance
from ev_routing.pipeline import run_instance
from ev_routing.resource_graph import prepare_service_graph
from ev_routing.search_policy import (
    DEFAULT_BEDROCK_MODEL, BedrockConfig, SearchConfig,
)


def solve_prepared_road(road_path, log_directory, aws_profile):
    road = load_instance(road_path)
    pricing, archive = prepare_service_graph(road)
    return run_instance(
        pricing,
        SolverConfig(
            solver="scip-routes", time_limit_seconds=120,
            threads=1, seed=0, energy_relative_gap=0.005,
        ),
        road_instance=road,
        path_archive=archive,
        search_config=SearchConfig(
            policy="adaptive",
            bedrock=BedrockConfig(
                model_id=DEFAULT_BEDROCK_MODEL,
                reasoning_effort="low", max_output_tokens=2048,
                profile=aws_profile, region="us-east-1",
            ),
            max_llm_calls=2, instance_context_bytes=8000,
            log_directory=str(log_directory),
        ),
    )
```

Se pueden reutilizar `pricing` y `archive` por hash de entrada/configuración,
manteniendo juntos los tres objetos. El pipeline comprueba su correspondencia.
Cambiar operaciones o energía exige regenerar los perfiles afectados.
El valor retornado es el resultado nativo, todavía sin la proyección de la webapp.

## 6. Qué debe cambiar en `origin/codex/webapp` durante el merge

La API pública auditada es **3.0**. `/solve` recibe una instancia nativa y
`solver.time_limit_seconds`; hoy no acepta configuración AWS ni contexto vial
compactado. `/prepare` genera un grafo sintético de distancias haversine con
confirmación, no una red OSM. No basta cambiar `standard` por `adaptive`.

| Archivo/componente actual | Cambio necesario al integrar |
|---|---|
| `src/ev_routing/`, `pyproject.toml`, `uv.lock` | Integrar el motor y sus dependencias coherentemente; no mezclar un contrato nuevo con un preprocesador antiguo. Ejecutar la suite física y del solver. |
| `backend/service.py::validate_request` | Fijar `energy_relative_gap=0.005` del lado servidor; acordar y versionar el contrato si se exponen nuevas opciones. Mantener los límites de entrada. |
| `backend/service.py::_native_instance` | La API actual rechaza `service_paths_nonnegative` por falta de expansión. Admitir representaciones preprocesadas solo con su red original y `PathArchive` verificados; contemplar `resource_paths` 1.1. |
| `backend/daniel_adapter.py::run` | Pasar `SearchConfig`, `road_instance` y `path_archive` a `run_instance`; crear logs por ejecución. Hoy fuerza `standard`, sin AWS. |
| `backend/daniel_adapter.py::project_result` | Preservar `raw.result`, validaciones, tiempos y certificados. Corregir los textos que actualmente declaran gap cero y política estándar sin AWS. Proyectar la política efectiva, no solo la solicitada. |
| Geometría y distancia en el adaptador | Expandir las rutas de `road_validation` sobre la red vial. Resolver alternativas por `arc_id`; el diccionario actual por `(from_node, to_node)` pierde arcos paralelos. Respetar el cambio `[lat, lon]` → GeoJSON `[lon, lat]`. |
| `webapp/shared/solver-client.js` y UI | Mostrar entregas/cota y energía/cota/gap por separado. `energy_gap_limit` es factible dentro de tolerancia, no óptimo exacto ni timeout. Mostrar modelo, fallbacks y decisiones aplicadas desde la respuesta del backend. |
| `backend/API_CONTRACT.md`, `docs/solver-source.json` | Actualizar contrato, revisión importada y hashes después del merge; retirar afirmaciones de “sin AWS” solo cuando el flujo adaptativo esté conectado y probado. |

El proveedor del adaptador exige importar el `src/ev_routing` del propio
checkout: apuntar `PYTHONPATH` a otro worktree no es una integración soportada.
Conservar la UI y el puente HTTP de webapp y resolver los conflictos explícitos
de contratos, solver y documentación; no sobrescribir toda la rama con una copia.

Para una red grande, mantener la instancia vial, la de pricing y los caminos
en el servidor. Una futura preparación puede devolver un ID opaco que el
backend resuelva en su caché. Es una extensión propuesta, no un endpoint ya
implementado. El navegador no debe enviar rutas locales arbitrarias.
La red auditada de 106.746 nodos excede los límites actuales de `/solve`
(20.000 nodos, 200.000 arcos y 8 MiB de cuerpo); no cabe enviarla tal cual.

Configurar AWS exclusivamente en el servidor, preferentemente con el rol del
despliegue (`profile=None` en Python) o un perfil local autorizado. Mantener
presupuesto de llamadas, tiempo y tokens. El `AbortController` de la webapp
cancela actualmente la espera HTTP, **no la ejecución de SCIP**; no prometer
cancelación del trabajo hasta implementarla en el backend.

## 7. Verificación antes de integrar

En esta rama:

```bash
uv run --locked --extra dw pytest -q 2>&1 | distill "¿Pasaron todas las pruebas? Indica fallos y omitidas."
uv run --locked --extra dw ruff check src tests scripts/test_routing_verbose.py 2>&1 | distill "¿Hay errores de lint?"
```

Después del merge, repetir además las pruebas existentes del puente:
`tests/test_native_output_parity.py`, `tests/test_daniel_pipeline.py`,
`tests/test_web_bridge.py` y `node --test webapp/tests/*.test.mjs`.
Agregar cobertura de gap alcanzado, error AWS, decisión tardía, archivos de
caminos incompatibles, regeneración/arcos paralelos y geometría expandida.
Comparar el resultado nativo CLI/Python con `raw.result` del HTTP sobre la misma
instancia. Una prueba con un doble de LLM no acredita acceso real a AWS.

Validación de este cambio: **665 pruebas aprobadas**; Ruff sin errores en
`src`, `tests` y `scripts/test_routing_verbose.py`. La suite no invoca AWS.

Medición con el código final sobre la instancia preparada de 40 clientes y 60
cargadores, presupuesto 120 s: **15,3570 s** de resolución, **16,2171 s** de
pipeline y **19,0828 s** de proceso; 40/40 entregas, **14,56660712 kWh**, cota
**14,52526525 kWh**, gap **0,2838126 %**, validación vial aprobada.
Terminó por `energy_gap_limit`, sin política GPT aplicada. Este ensayo prueba
la parada anticipada; no prueba rendimiento del LLM ni mide preparación desde
cero. Se comprobó también que omitir `--energy-relative-gap` aplica 0.005.
Evidencia local ignorada por Git: `artifacts/gpt-luna-gap-005-final/`.
El rechazo de acceso se confirmó de forma separada por Converse.

## Referencias

- [Preprocesamiento auditado](resource-paths.md).
- [Motor, callbacks, ALNS y certificados](llm-head-search.md).
- [Contratos del resultado](contracts.md) y [solvers](solvers.md).
- [OpenAI: modelos en Amazon Bedrock](https://developers.openai.com/api/docs/guides/amazon-bedrock).
- [AWS: GPT-6 Luna, APIs, perfiles y esfuerzo](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-openai-gpt-6-luna.html).
- [AWS: Converse](https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html).
