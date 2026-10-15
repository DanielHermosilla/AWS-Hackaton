# API local 3.0 — núcleo de Daniel

El proveedor es el núcleo local `ev_routing` importado de la rama `modelamiento`,
commit `624203573bffdeec334a9e07a64b361a515f9725`. La procedencia y los archivos
seleccionados constan en `docs/solver-source.json`. El adaptador anterior y sus
fixtures se retiraron. Esta versión no es compatible con solicitudes HTTP 2.x.

La resolución utiliza `scip-routes`, un hilo, semilla 0, gap relativo 0 y política
`standard`, sin llamadas a AWS. El núcleo conserva la formulación, contratos,
validador, energía y certificados nativos. El puente no importa proveedores desde
otro checkout ni acepta rutas de archivos en una petición.

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
consumo indicado, sin pendiente y sin geometrías fabricadas. Su procedencia incluye
`kind: "synthetic"`, `network.kind: "haversine"` y los supuestos. No representa
calles, accesos, permisos, sentidos viales ni consumos observados. La interfaz debe
obtener la confirmación explícita del usuario antes de solicitar esta preparación.

El límite local de este modo es 200 nodos y 20 vehículos; no son reglas del concurso.
No se añade una matriz distinta en JavaScript ni se rellena una instancia nativa
con esta preparación sin una petición explícita.

## Resolución nativa

```json
{
  "api_version": "3.0",
  "instance": {"schema_version":"1.0", "nodes":[], "arcs":[], "parameters":{}, "provenance":{}},
  "solver": {"time_limit_seconds": 30}
}
```

El objeto mostrado es solo una estructura: la instancia debe contener exactamente
una base y un grafo válido. El ejemplo completo ejecutable está en
`backend/fixtures/native-request.json`.

`POST /solve` admite únicamente `api_version`, `instance` y `solver`. El presupuesto
obligatorio está entre 1 y 120 segundos. El resto de la configuración de resolución
queda fijado por el puente. La instancia se valida con Pydantic nativo en modo
estricto, sin cambiar nodos, arcos, parámetros, compatibilidad, opciones operacionales
ni IDs. Su serialización canónica añade únicamente los defaults del contrato nativo.

Se rechaza `provenance.representation.kind: "service_paths_nonnegative"`, también
su forma textual, porque esta integración no incluye esa transformación ni su
expansión. No hay campos HTTP antiguos `nodes`, `prepared`, `fleet`, `network` o
`movement_limit` en `/solve`. El `movement_limit` **nativo** sí se conserva en los
datos; el proveedor `scip-routes` informa que resuelve sin H en su formulación.
El límite local de entrada es 20 000 nodos, 200 000 arcos y 8 MiB por petición.

## Respuesta y conservación del resultado

`{api_version: "3.0", result: {...}}` conserva la proyección de presentación:

| Campo | Semántica |
|---|---|
| `run_id` | UUID del resultado HTTP. El identificador nativo permanece en `metadata.native_run_id` y `raw.result.run_id`. |
| `status` | Con solución: `result_available`, `partial` o `validation_failed`. Sin solución: `no_solution`, `unavailable` o `error`. |
| `has_solution` | Existencia de incumbente nativo; es independiente de su factibilidad. |
| `nodes` | Nodos nativos, incluidos `junction`. Coordenadas emparejadas pueden ser `null`; `connector_types` es una lista. |
| `fleet` | IDs nativos `vehicle_1`, etc.; capacidad, reserva y SoC de `parameters`. |
| `routes` | Vehículo, entregas **explícitas**, pasos ordenados, geometría, kilómetros y energía neta nativa. Transitar por un cliente no implica atenderlo. |
| `steps` | `position`, `node_id`, energía de llegada/salida, recarga y entregas explícitas. `energy_kwh` corresponde a `effective_arc_energy_kwh` del arco **saliente**; es `null` en el paso terminal. |
| `total_energy_kwh` | Energía neta efectiva de batería de los KPIs nativos cuando la solución pasa el validador; incluye regeneración saturada correctamente. No es electricidad comprada. |
| `validation` | Resultado del validador independiente nativo, violaciones y alcance. Sin incumbente: `feasible: null`. |
| `phases` | Copia completa de las fases nativas: sentido, estado, terminación, incumbente, cota, gaps, prueba, tiempo y mensajes. No se combinan certificados. |
| `metadata` | Proveedor/SHA, esquema nativo, hashes, estado nativo, `lexicographic_optimal`, alcance/formulación e indicador de límite de tiempo. |
| `raw` | `input` exacto, `instance` canónica, `effective_config` y `result` nativo completo. |
| `runtime_seconds` | `preparation` valida la petición; `solver` toma resolución incluyendo modelo del núcleo; `total` mide el servicio completo. Los tiempos del validador y desglose original están en `raw.result`. |

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

## Geometría

`Arc.geometry` nativa usa `[latitud, longitud]`, confirmado en `network.py`; el
puente convierte exclusivamente a GeoJSON `[longitud, latitud]`. No construye
geometrías a partir de los nodos ni usa líneas rectas para rellenar arcos ausentes.
Las secuencias guardadas deben ser continuas y sus extremos deben corresponder a
las coordenadas de sus nodos, con tolerancia conservadora de `1e-6` grados por
componente. Si faltan coordenadas, geometrías o esa correspondencia, la geometría
de la ruta es `null`; las paradas siguen disponibles. Esto comprueba asociación y
continuidad gráfica, no acredita conectividad vial real.

## Transporte, errores y ejecución

Desde el checkout integrado y su entorno sincronizado:

```sh
uv sync --locked --group dev
uv run python -m backend.local_server --port 8000
```

El servidor sirve `webapp/` y la API en `http://127.0.0.1:8000`, solo loopback y el
mismo origen, sin CORS ni autenticación. Rechaza JSON no finito, claves duplicadas,
rutas aproximadas y archivos fuera del directorio estático permitido.

`GET /health` informa versión 3.0, proveedor/SHA y `provider_available`.
`GET /solve?run_id=<UUID>` recupera resultados temporales (máximo cuatro y 32 MiB),
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
