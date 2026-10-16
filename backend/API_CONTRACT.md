# API local 3.0 — motor integrado en main

El proveedor es el núcleo local `ev_routing`, integrado desde
`codex/evrp-llm-search@ab67dc6` con la webapp `a372d03`. Las revisiones base y
adaptaciones están en `docs/solver-source.json`. HTTP 2.x no está soportado.

La resolución usa `scip-routes`, todos los CPU disponibles para el proceso hasta
el máximo de 64 admitido por SCIP, semilla 0, gap de entregas 0 y tolerancia
energética **0.005** por defecto. `solver.random_seed` admite enteros de 0 a
2.000.000.000 y `solver.energy_relative_gap` admite fracciones de 0 a 1. Este
último solo afecta al desempate energético: no permite sacrificar entregas.
`solver.search_policy` admite `standard`, `deterministic` y
`adaptive`; omitirlo conserva `standard` por compatibilidad. La UI envía
`adaptive` por defecto. El núcleo conserva física y certificados; el puente
no importa proveedores de otro checkout ni acepta rutas locales, credenciales,
modelos o parámetros libres dentro de una petición de resolución. La conexión
AWS tiene un endpoint local independiente y no forma parte de la instancia.

El número de hilos efectivos se registra en `raw.effective_config.solver.threads`.
Configurar `parallel/maxnthreads` y `lp/threads` permite recursos al motor; no
garantiza que cada etapa use todos los núcleos. Se conserva el algoritmo con
callbacks del núcleo, sin sustituirlo por la modalidad concurrente de SCIP.

La política adaptativa usa GPT-5.6 Luna `low` por Bedrock, configurable mediante
`AWS_PROFILE` opcional, `AWS_DEFAULT_REGION` y `BEDROCK_MODEL_ID` del servidor.
Dos consultas máximas, timeout de 8 s, 2.048 tokens y contexto físico de 8.000 bytes.
El controlador limita la inferencia al 25 % del presupuesto. Respuestas tardías,
inválidas o fallos se informan sin atribuirles decisiones aplicadas. El mismo
pipeline mantiene pricing exacto o cotas válidas y nunca cambia de backend por
esos fallos. El resultado nativo completo permanece en `raw.result`.

## Históricos y conexión AWS

Los históricos son una entrada separada de los destinos. Un eVED válido se
procesa sin IA. Los CSV/JSON de otro formato necesitan columnas y unidades
documentadas o una interpretación validada mediante Bedrock. Para esa
interpretación se exige **HIGH** en un modelo compatible; no se sustituye
silenciosamente por un nivel inferior. El historial y el solver comparten la
misma sesión AWS. La configuración de búsqueda conserva su presupuesto acotado.

| Endpoint | Entrada / salida |
|---|---|
| `POST /history/upload` | Bytes, `application/octet-stream`, `X-History-Filename` codificado con URL. CSV hasta 4 GiB; JSON hasta 256 MiB con `records` y metadatos opcionales. Máximo veinte millones de filas, sin truncamiento silencioso. |
| `GET /history?profile_id=…` | `{api_version, profile}`: estado `ready`, `needs_mapping` o `error`, resumen, supuestos, advertencias y análisis IA. |
| `POST /history/analyze` | `{profile_id}`. Una interpretación y, al normalizar un formato nuevo, una explicación adicional de estadísticas; máximo dos llamadas por acción. |
| `POST /history/remove` | `{profile_id}`. Elimina el archivo temporal y su perfil. |
| `GET /bedrock/session` | Estado saneado: `state`, `connected`, región, modelo, perfil local opcional y segundos restantes. No comprueba la red. |
| `POST /bedrock/session` | `mode: configured` con perfil local opcional, o `mode: temporary` con `access_key_id`, `secret_access_key` y `session_token`; región/modelo opcionales. Comprueba acceso mediante Converse. |
| `POST /bedrock/disconnect` | `{}`. Invalida la sesión para nuevas consultas; no deshace una petición ya enviada a AWS. |

Las peticiones de conexión tienen un límite de 16 KiB. Sus secretos permanecen
solo en la sesión SDK en memoria. La conexión deja de admitir consultas al
cumplir una hora o vencer las credenciales. No se escriben en configuración, logs, resultados ni
almacenamiento del navegador. La API sigue limitada a loopback y al mismo origen.

`POST /prepare` admite `energy_profile_id`. Devuelve el resumen de calibración
en `preparation.energy_profile`: cobertura, evaluación por viajes reservados,
supuestos y motivos de respaldo. Se aplican costes al grafo elemental antes
de preparar caminos y perfiles de batería; las huellas cambian con el histórico.
Una red sintética conserva su consumo supuesto porque no identifica calles.
Los JSON nativos ya contienen sus energías y no se sobrescriben implícitamente.

Hasta dos históricos permanecen temporalmente en el servidor; reiniciarlo,
retirarlos o cargar otros puede hacerlos caducar. Una preparación que referencia
un histórico inexistente devuelve `history_expired`: adjuntarlo de nuevo o
retirarlo es una decisión visible. Los originales no se modifican. Bedrock
recibe solo una muestra y estadísticas limitadas; las integrales se calculan
localmente sobre el archivo admitido. Una unidad o signo ambiguos no se inventan.

Los CSV se transfieren a disco en bloques de 1 MiB y se leen únicamente las
columnas de mediciones, clasificación y contexto necesarias. La normalización
ordena el conjunto completo admitido por vehículo, viaje y tiempo antes de
integrar; el límite de bytes no garantiza RAM para cualquier número de muestras.
La memoria depende de las columnas normalizadas. Un JSON se materializa para
validarlo y conserva el límite menor. Los históricos de combustión e híbridos
se rechazan por esquema antes de leer todas sus filas.

### Caso histórico y variantes de la hackatón

`GET /scenarios/hackathon?dataset=competition|evaluation` devuelve
`{api_version, scenario: {name, source_file, nodes, network_mode: "road", scenario}}`.
Lee exclusivamente los dos CSV conocidos en `data/`; no admite rutas arbitrarias
ni publica el directorio. La ausencia del original devuelve 404
`scenario_unavailable`, sin inventar ubicaciones. Los nodos se validan con el
lector compartido y preservan coordenadas, IDs, conectores y puertos.

`POST /scenarios/hackathon` recibe `{dataset: "competition"|"evaluation"}` y
devuelve `{api_version, scenario, profile}`. Carga también el archivo local fijo
`data/eVED_EV.csv` en el mismo almacén temporal de históricos; reutiliza un perfil
con igual SHA-256. No acepta rutas arbitrarias. Si falta el histórico devuelve
404 `example_history_unavailable`.

Opcionalmente recibe `simulation: {customers, chargers, seed?}`: clientes ≥ 1,
cargadores ≥ 0, hasta 200 servicios incluido el depósito; semilla entera entre
0 y 2.000.000.000, predeterminada 0. Reducir cantidades selecciona ubicaciones
fuente con esa semilla. Las adicionales se muestrean sin reemplazo entre
intersecciones de la red local dentro del rectángulo de clientes originales
y en el componente fuertemente conexo del depósito, mediante el muestreador
compartido `simulate_customers`. Los originales no se modifican. No se inventan
arcos ni se descarga una red. Si faltan calles o candidatos, la acción falla
con un error explícito. Los cargadores añadidos declaran conectores J1772/CHAdeMO,
un puerto DC y uno L2, máximo nominal 50 kW; no se infiere potencia efectiva.
La respuesta incluye `scenario.simulation` con cantidades, semilla y supuestos.

`energy_profile_id` opcional reutiliza el histórico seleccionado en lugar de
cargar el local, sin aceptar perfiles caducados o no preparados. La interfaz
lo envía al crear una variante sobre el histórico actual.

`POST /prepare` admite el metadato aditivo
`scenario: {kind: "hackathon"|"hackathon_simulation", dataset, seed?}`. Se conserva
en la procedencia y en la entrada exportada; declara origen, no certifica
factibilidad ni autenticidad de ubicaciones editadas. El margen del formulario
se convierte a `operations.energy_margin_fraction` y utiliza la física vigente.

La interfaz obtiene las ubicaciones de `competition` automáticamente al abrir una
pestaña sin borrador ni ejecución; solo hace el GET, sin procesar históricos,
preparar la red o resolver. Al calcular ese caso carga eVED mediante el POST si
todavía no existe una elección explícita de histórico. Conserva las ubicaciones
editadas: cargar el histórico no reemplaza el borrador. El mapa inicial y el
formulario de cálculo comparten esa misma entrada. Las variantes se previsualizan
en el mapa antes de enviarse a `/prepare`; los errores no sustituyen sus puntos
por ejemplos.

La interfaz permite cargar cualquiera de los casos explícitamente. Si se adjunta
un histórico válido sin ubicaciones, carga el caso seleccionado automáticamente
y conserva la flota y los supuestos editados. Después utiliza los endpoints
existentes `/prepare` y `/solve`, con `energy_profile_id`. No interpreta los
trayectos del histórico como demanda ni inventa un depósito. Sin histórico,
el mismo caso puede calcularse con el consumo supuesto. Los controles de capacidad
24 kWh, reserva 2,4 kWh y respaldo 0,2 kWh/km se completan únicamente si están vacíos
y se identifican como supuestos ajustables.

## Preparación explícita de CSV

`POST /prepare`, mismo origen, `Content-Type: application/json`:

```json
{
  "api_version": "3.0",
  "nodes": [
    {"node_id":"BASE","node_type":"base","latitude":0,"longitude":0},
    {"node_id":"V1","node_type":"visit","latitude":0,"longitude":0.001}
  ],
  "fleet": {
    "num_vehicles": 2,
    "battery_capacity_kwh": 10,
    "reserve_kwh": 1,
    "initial_soc": 0.6,
    "consumption_kwh_km": 1
  },
  "network_mode": "haversine"
}
```

Estas cifras son sintéticas. Capacidad útil, reserva y consumo son obligatorios.
Defaults: dos vehículos, SoC 0.6 y conectores nativos `J1772`/`CHAdeMO`; puede
especificarse `vehicle_connector_types` como lista. La coincidencia de conectores
es textual, conforme al núcleo; no se inventan equivalencias de conectores.

`nodes` usa los campos CSV conocidos, con valores numéricos ya normalizados por
el lector de CSV y `connector_types` como texto separado por `;`. No admite
intersecciones en este modo ni coordenadas ausentes. IDs opacos se conservan sin
recodificar. Duplicados, números no finitos, puertos incompatibles y campos
extraños producen errores accionables.

La respuesta es `{api_version: "3.0", instance: ProblemInstance}`. Es una instancia
nativa 1.0 con red dirigida completa **sintética**: distancia haversine por el
consumo indicado y sin pendiente. Los arcos de esta preparación incluyen líneas
entre sus extremos para mostrar el ejemplo. Su procedencia incluye
`kind: "synthetic"`, `network.kind: "haversine"`,
`network.geometry_source: "synthetic_haversine"` y los supuestos. No representa
calles, accesos, permisos, sentidos viales ni consumos observados. La interfaz debe
mostrar ese alcance junto al selector de red; no requiere una casilla adicional.

El límite local de este modo es 200 nodos y 20 vehículos; no son reglas del concurso.
No se añade una matriz distinta en JavaScript.

### Preparación vial

El mismo cuerpo admite `network_mode: "road"` y `operations` opcional,
validado con el contrato nativo. Ventanas/jornada exigen tiempos explícitos
o `assumed_speed_kph`; no se inventan velocidades. Las opciones se aplican
antes del preprocesamiento y forman parte de la huella de caché. El comando local
usa `artifacts/network/competition_delivery.graphml` si existe, o la ruta explícita
`--graphml <archivo_local>`, `--network-profile drive|delivery` y opcionalmente
`--max-snap-distance-m`. Son parámetros del operador; no se descargan mapas.
Se usa el preparador nativo: calles dirigidas, accesos con alcance explícito,
energía por el coeficiente recibido y preprocesamiento con archivos de caminos.

Devuelve `instance` de pricing (1.0 o 1.1), `prepared_instance_id` opaco y
`preparation: {runtime_seconds, reused}`. La red original y `PathArchive` quedan
en el servidor. `/solve` exige la instancia canónica devuelta y ese ID; comprueba
su huella y el pipeline verifica la correspondencia de los tres objetos.
Un contexto alterado o vencido produce HTTP 400 y exige preparar nuevamente.
La caché guarda como máximo dos contextos y 384 MiB de objetos serializados;
no es una garantía de memoria RSS. Se pierde al reiniciar o reemplazar entradas.
El límite HTTP es 64 MiB; solo viaja la instancia de pricing. Si ella
excede ese tamaño, usar la CLI, sin reducir la red silenciosamente.


## Resolución nativa

```json
{
  "api_version": "3.0",
  "instance": {"schema_version":"1.0", "nodes":[], "arcs":[], "parameters":{}, "provenance":{}},
  "solver": {"time_limit_seconds": 120, "search_policy": "adaptive", "energy_relative_gap": 0.005, "random_seed": 0}
}
```

El objeto mostrado es solo una estructura: la instancia debe contener exactamente
una base y un grafo válido. El ejemplo completo ejecutable está en
`backend/fixtures/native-request.json`.

`POST /solve` admite `api_version`, `instance`, `solver` y, para caminos preparados,
`prepared_instance_id`. El presupuesto
obligatorio está entre 1 y 120 segundos. Política, tolerancia energética y semilla
son las únicas opciones adicionales aceptadas. La instancia se valida con Pydantic nativo en modo
estricto, sin cambiar nodos, arcos, parámetros, compatibilidad, opciones operacionales
ni IDs. Su serialización canónica añade únicamente los defaults del contrato nativo.

Se rechazan `service_paths_nonnegative` y `resource_paths` sin un contexto vial
del servidor: los caminos requieren red original y archivo de expansión. La
forma textual de `representation` es inválida. Se admiten instancias nativas
1.0 y 1.1; los perfiles y arcos paralelos conservan sus `arc_id`. No hay campos HTTP antiguos `nodes`, `prepared`, `fleet`, `network` o
`movement_limit` en `/solve`. El `movement_limit` **nativo** sí se conserva en los
datos; el proveedor `scip-routes` informa que resuelve sin H en su formulación.
El límite del JSON elemental subido es 20 000 nodos, 200 000 arcos y 64 MiB por
petición. Las redes grandes preparadas permanecen en el servidor.

## Respuesta y conservación del resultado

`{api_version: "3.0", result: {...}}` conserva la proyección de presentación:

| Campo | Semántica |
|---|---|
| `run_id` | UUID del resultado HTTP. El identificador nativo permanece en `metadata.native_run_id` y `raw.result.run_id`. |
| `status` | Con solución: `result_available`, `partial` o `validation_failed`. Sin solución: `no_solution`, `unavailable` o `error`. |
| `has_solution` | Existencia de incumbente nativo; es independiente de su factibilidad. |
| `nodes` | Nodos nativos; en preparación vial, todos los servicios y las intersecciones usadas por las rutas expandidas. Coordenadas emparejadas pueden ser `null`; `connector_types` es una lista. |
| `fleet` | IDs nativos `vehicle_1`, etc.; capacidad, reserva y SoC de `parameters`. |
| `routes` | Vehículo, entregas **explícitas**, pasos ordenados, geometría, kilómetros, energía neta y `duration_seconds` nativa, incluido `null`. Transitar por un cliente no implica atenderlo. |
| `steps` | `position`, `node_id`, energía de llegada/salida, recarga y entregas explícitas. `energy_kwh` corresponde a `effective_arc_energy_kwh` del arco **saliente**; es `null` en el paso terminal. Los campos nativos de energía, destino y tiempo se conservan también con sus nombres originales, detallados abajo. |
| `total_energy_kwh` | Energía neta efectiva de batería de los KPIs nativos cuando la solución pasa el validador; incluye regeneración saturada correctamente. No es electricidad comprada. |
| `kpis` | Copia completa de los KPIs nativos y sus `unavailable_reasons`, sin recomputar, rellenar ausencias ni borrar métricas futuras. |
| `operations` | Copia completa de las opciones operacionales nativas efectivamente utilizadas, incluidos sus defaults. |
| `tuning` | Informe nativo completo: modelo, política solicitada/efectiva, propuestas, cambios, campos inactivos, latencias, fallbacks y tokens. |
| `validation` | Resultado del validador independiente nativo, violaciones, `checks` y alcance. Sin incumbente: `feasible: null`, `checks: {}`. |
| `phases` | Copia completa de las fases nativas: sentido, estado, terminación, incumbente, cota, gaps, prueba, tiempo y mensajes. No se combinan certificados. |
| `metadata` | Proveedor/SHA, esquema nativo, hashes, estado nativo, `lexicographic_optimal`, alcance/formulación, indicador de límite de tiempo y resumen `native_solver`. |
| `raw` | `input` exacto, `instance` canónica, `effective_config` y `result` nativo completo. |
| `runtime_seconds` | `preparation` valida la petición; `solver` toma resolución incluyendo modelo del núcleo; `total` mide el servicio completo. Añade los tiempos nativos detallados abajo sin sumarlos. |

La ampliación de presentación es aditiva y conserva API 3.0. Cada paso añade,
sin conversión ni estimación, `arc_id`, `next_node_id`, `predicted_arc_energy_kwh`,
`effective_arc_energy_kwh`, `arrival_seconds`, `service_start_seconds`,
`departure_seconds`, `service_duration_seconds`, `charging_duration_seconds` y
`travel_time_seconds`. Los `null` originales permanecen `null`. La energía
predicha expresa el potencial del arco; la efectiva puede diferir por saturación
de regeneración. Son datos nativos, no certificados nuevos. El alias existente
`energy_kwh` sigue omitiéndose cuando la solución no pasa el validador.

`metadata.native_solver` contiene los campos nativos `requested_solver`,
`used_solver`, `solver_version`, `fallback_reason`, `solution_source` y `message`.
Los diagnósticos completos de búsqueda permanecen en `raw.result.solve.search`.
No se infiere optimalidad de un mensaje, una duración o la existencia de una ruta.

Los tiempos adicionales son `validation`, `initial_solution_validation`, `llm`,
`native_resolution_including_model` y `native_total`, copiados del resultado
nativo. `solver` y `native_resolution_including_model` describen el mismo
intervalo. El tiempo LLM puede estar incluido en resolución; `native_total`
abarca el pipeline y `total` el servicio HTTP, incluida la preparación y
proyección. Estos intervalos se solapan y **no deben sumarse**.

Las métricas disponibles dependen de la instancia: con opciones temporales el
núcleo añade duración por vehículo, tiempo hasta el último retorno y suma de
tiempos de vehículos. Con carga temporizada añade electricidad de red usando la
eficiencia configurada. Sin esos supuestos conserva `null` y sus motivos.
La interfaz debe consumir `kpis.charging_stops` para el contador global: no
recontar paradas con otro umbral. No se inventa un contador por ruta, que el
resultado nativo no proporciona.

Cuando no hay incumbente se devuelve un JSON completo con HTTP 200, `routes: []`,
`served_count: null`, `total_energy_kwh: null`, `unserved_visit_ids: []` y
`validation.feasible: null`. Esa lista vacía significa que no hay datos de pendientes,
no que todas las entregas se completaron. El total de demanda sí es conocido. Las
fases y el estado nativo permanecen disponibles; una ausencia de solución no se
traduce en infactibilidad probada.

`metadata.time_limit_reached` es `true` únicamente ante una terminación nativa
explícita `timelimit`, `budget_exhausted`, `maxTimeLimit` o `time_limit`; en los otros
casos es `null`. `pricing_incomplete` por sí solo no prueba un timeout. Una solución
conservada tras un timeout mantiene sus rutas y validación.

Si una solución nativa es inválida, los KPIs energéticos se mantienen no disponibles.
Una lectura de batería fuera de `[0, capacidad]` se omite de la presentación con
advertencia, conservando el original; nunca se recorta para aparentar factibilidad.

La preparación vial añade `raw.prepare_request`, suficiente para reconstruir
la entrada usando el GraphML del operador. `raw.instance` es la instancia de
pricing; no basta por sí sola sin red original y `PathArchive`. Los archivos
completos se conservan mediante la CLI. La UI admite importar archivos locales
de hasta 256 MiB, incluidos resultados completos que repiten la instancia original
y la canónica. La instancia extraída para resolver mantiene el límite HTTP de
64 MiB: importar una envoltura no garantiza que todo su contenido sea resoluble.
El almacén temporal conserva hasta cuatro resultados dentro de 256 MiB en total.
Estos son límites de archivos serializados, no garantías de memoria RAM. Los
históricos eVED son mediciones para entrenamiento, no instancias de ruteo, y se
rechazan con una indicación del formato correcto. La UI reabre la entrada de preparación
para no depender del ID temporal. El resultado nativo preserva `road_validation`
con rutas expandidas y la comprobación de segmentos. Solo se muestra geometría
vial si esa comprobación pasa.

`runtime_seconds.road_preprocessing` es la duración de la preparación original,
reutilizable; no forma parte de `total` de `/solve`. El `total` de `/prepare`
se mide aparte. `energy_gap_limit` significa tolerancia energética alcanzada,
no timeout ni óptimo exacto; se preservan cotas y pruebas por fase.

## Geometría

`Arc.geometry` nativa usa `[latitud, longitud]`, confirmado en `network.py`; el
puente convierte exclusivamente a GeoJSON `[longitud, latitud]`. No usa líneas
rectas para rellenar arcos ausentes. La preparación explícita haversine es la
única que crea líneas aproximadas entre nodos; se identifican como sintéticas.
Las secuencias guardadas deben ser continuas y sus extremos deben corresponder a
las coordenadas de sus nodos, con tolerancia conservadora de `1e-6` grados por
componente. Si faltan coordenadas, geometrías o esa correspondencia, la geometría
de la ruta es `null`; las paradas siguen disponibles. Esto comprueba asociación y
continuidad gráfica, no acredita conectividad vial real.

`provenance.network.source: "directed_road_graph"`, producido por el preparador
nativo de Daniel, se presenta como `network.type: "directed_road_graph"` y
`vial: true`: identifica una procedencia declarada. `provenance_verified` sigue
siendo `false`; no verifica datos externos, accesos, cierres ni circulación real.
Un `network.kind` explícito prevalece y las instancias sintéticas/haversine
mantienen `vial: false`, aunque incluyan además aquella cadena de procedencia.

## Transporte, errores y ejecución

Desde el checkout integrado y su entorno sincronizado:

```sh
uv sync --locked --group dev --extra dw
AWS_PROFILE=hackathon uv run --extra dw python -m backend.local_server --port 8000
```

El servidor sirve `webapp/` y la API en `http://127.0.0.1:8000`, solo loopback y el
mismo origen, sin CORS ni autenticación. Rechaza JSON no finito, claves duplicadas,
rutas aproximadas y archivos fuera del directorio estático permitido.

`GET /health` informa versión 3.0, revisión base del proveedor, `provider_available`
y capacidades: preparación vial configurada, políticas y tolerancia energética.
En `capabilities`, el campo existente `historical_upload_max_bytes` indica el
máximo global de históricos: 4.294.967.296 bytes (4 GiB), admisible para CSV,
no para todos los formatos. La extensión aditiva
`historical_upload_max_bytes_by_format` informa
`{"csv": 4294967296, "json": 268435456}`; los clientes deben usar el límite del
formato elegido, incluido el máximo JSON de 256 MiB.

`GET /solve?run_id=<UUID>` recupera resultados temporales (máximo cuatro y 256 MiB),
que expiran por reemplazo o reinicio. No son almacenamiento persistente ni cuentas.
Abandonar la página no cancela SCIP. Los límites del solver son blandos y los
sobrecostos pueden exceder el tiempo solicitado.

Errores: `{api_version,error:{code,message}}`. 400 entrada; 403 origen;
404 recurso/resultado expirado; 409 cálculo ocupado; 411 longitud; 413 tamaño;
415 contenido; 503 dependencia/núcleo local no disponible; 502 fallo inesperado.
Los estados nativos sin solución no son errores de transporte.

Pruebas: `uv run python -m unittest discover -s tests -p test_web_bridge.py -v`.
Incluyen SCIP real, preparación→resolución HTTP, ejemplos nativos de recarga y
regeneración, estados sin incumbente, timeout simulado sobre una solución real,
paridad de fases/energía, coordenadas ausentes y controles HTTP. Las fixtures son
sintéticas; sus tiempos/run IDs prueban una ejecución, no rendimiento comparativo.

`uv run python -m unittest discover -s tests -p test_native_output_parity.py -v`
captura el JSON nativo antes del adaptador y exige igualdad completa tras POST,
serialización y recuperación GET. Incluye recarga con operación, regeneración
con tres vehículos, demanda parcial con IDs opacos, defaults, ausencia/error
simulados y extensiones futuras del resultado, métricas y diagnósticos.

Las fixtures `native-operations-request.json` y `native-operations-response.json`
proceden del ejemplo sintético de recarga de Daniel con opciones temporales
explícitas: dos entregas, 14 kWh netos, 9 kWh incorporados a batería, 10 kWh de red
y 3.580 segundos hasta el último retorno. La respuesta procede de SCIP real a
través del servidor local; las cifras no representan una operación real.

Las pruebas del merge en `tests/test_integrated_webapp.py` añaden preparación
vial→SCIP→expansión→GET, reutilización/alteración/expiración de contexto,
paralelos con ventanas, fallo AWS explícito y gap sin falsa optimalidad.
Las pruebas JS cubren reabrir la preparación, políticas y decisiones visibles.
La aceptación real con datos públicos y AWS se documenta por separado en
`docs/main-integration-validation.md`; no ocurre en la suite habitual.
