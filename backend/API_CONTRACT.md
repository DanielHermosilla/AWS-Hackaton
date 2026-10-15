# Puente local de integración beta

Versión HTTP `2.0-beta.1`, proveedor `evrp` fijado al commit
`f88d0120c0b80087d718224b46b2613735cee69c`, HiGHS `1.11.0` de su `uv.lock`.
Se reutilizan las responsabilidades de `origin/deploy-aws` (`9f1389c`):
`backend/service.py`, `backend/local_server.py` y recursos `/health`, `/solve`.
Los tipos `ev_routing` de esa rama no son compatibles con este proveedor.
La beta mantiene el envoltorio `api_version/result` y cambia explícitamente de versión.

## Transporte

El servidor se ejecuta con el Python del entorno del proveedor fijado, desde este
checkout: `python -m backend.local_server --port 8000`. El frontend y la API se
sirven en `http://127.0.0.1:8000`. Solo admite loopback y el mismo origen; no usa
CORS, autenticación, AWS, mapas descargados, base de datos ni despliegue.
El proveedor permanece instalado por separado mediante su `uv sync --locked --group dev`.
El servidor verifica SHA, cambios en código/lock y versión de HiGHS al cargarlo.

- `GET /health`: `status`, `api_version`, `provider`, `provider_commit`, `provider_available`.
  `status: ok` describe el transporte; `provider_available` indica si el entorno fijado está listo.
- `POST /solve`: JSON UTF-8 de hasta 8 MiB, `Content-Type: application/json` y
  `Content-Length`. Rechaza claves repetidas, `NaN` e infinitos. Un cálculo a la vez.
- `GET /solve?run_id=<UUID>`: recupera la misma respuesta completada. Conserva
  hasta cuatro resultados y 32 MiB en memoria; expiran por reemplazo/reinicio.
  No es almacenamiento permanente, cuenta ni aislamiento entre usuarios.
- Los estáticos se restringen a `webapp/`, extensiones permitidas y archivos
  regulares; no sirven el repositorio, directorios ocultos, tests ni symlinks externos.

Salir de una página o abortar `fetch` deja de esperar; no cancela HiGHS.
La construcción/validación pueden añadir tiempo al presupuesto solicitado al solver.

## Petición

```json
{
  "api_version": "2.0-beta.1",
  "nodes": [
    {"node_id":"B","node_type":"base","latitude":0,"longitude":0},
    {"node_id":"V","node_type":"visit","latitude":0,"longitude":0.001}
  ],
  "network_mode": "haversine",
  "fleet": {
    "num_vehicles": 2,
    "battery_capacity_kwh": 10,
    "reserve_kwh": 1,
    "initial_soc": 0.6,
    "consumption_kwh_km": 1
  },
  "solver": {"time_limit_seconds": 30},
  "exclude_node_ids": []
}
```

Las cifras del ejemplo son sintéticas, no capacidad útil ni consumo confirmados del Leaf.

Se admite exactamente una entrada: `nodes` o `prepared`. `nodes` usa el esquema
CSV del proyecto, con números o texto numérico en campos numéricos de CSV. Son
obligatorios ID, tipo y coordenadas. Los campos opcionales conservan ausencia como
`null` (números) o cadena vacía (texto). `connector_types` es texto separado por `;`.
IDs opacos se preservan, incluidos Unicode, `|` y `#fin`.

`prepared` es un objeto nativo `evrp.instancia_preparada/1`, no un nombre de archivo.
Requiere nodos, todos los pares dirigidos de tramos, red y los cinco campos de
`energia_caminos`; geometrías y origen son opcionales. No accede a rutas de disco
de sus metadatos. La configuración energética se toma de la preparada; si se
indica `consumption_kwh_km`, debe coincidir. La beta admite una flota homogénea;
valida la correspondencia energética de todos los tipos que acepta.
Una preparada no admite `network_mode`. Las claves de pares se resuelven mediante
los IDs completos; una serialización con colisiones se rechaza y debe regenerarse.

Para `nodes`, `network_mode: haversine` debe ser explícito. El proveedor prepara con
geometría, plano y factor de distancia 1. Es una referencia sin red vial. No hay
fallback silencioso a líneas rectas. `consumption_kwh_km`, capacidad útil y reserva
son obligatorios. Para ambas entradas se exige reserva positiva ≤ energía inicial.

Defaults de interfaz: dos vehículos, SoC 0.6, presupuesto 30 s. Límites de esta
beta local: 200 nodos, 20 vehículos, 1–120 s y 200 000 segmentos/puntos guardados.
No son reglas del concurso. Las exclusiones deben existir, no repetirse ni incluir
la base; se retiran de la demanda activa y permanecen en la entrada exportada.
Campos desconocidos se rechazan, incluidos `movement_limit`, `network`, opciones
libres del solver, tipos heterogéneos y configuración AWS.

## Respuesta

`{api_version, result}`. Los campos de `result` son:

| Campo | Significado |
|---|---|
| `run_id`, `status` | UUID; `result_available`, `partial` o `validation_failed`. No es certificado de optimalidad. |
| `nodes` | Nodos activos normalizados al esquema CSV; IDs originales. |
| `fleet` | Lista `{id,type,label,battery_capacity_kwh,reserve_kwh,initial_soc}`. SoC es fracción. |
| `routes` | Lista `{vehicle_id,served_visit_ids,steps,geometry,distance_km,energy_kwh}`. Incluye vehículos inactivos base→base. |
| `steps` | `{position,node_id,arrival_energy_kwh,departure_energy_kwh,charge_kwh,energy_kwh,delivered_visit_ids}`. Posición 0 es el origen, ausente del detalle upstream. Ocurrencias repetidas conservan posiciones. |
| `geometry` | `null` o GeoJSON `LineString` `[lon,lat]`, exclusivamente de secuencias realmente guardadas y continuas. Nunca usa el fallback de `RedPreparada.geometria`. |
| `served_count`, `total_visits`, `unserved_visit_ids` | Contrasta cumplimiento del proveedor con las rutas y demanda activa. |
| `total_energy_kwh`, `routes[].energy_kwh`, `steps[].energy_kwh` | `null`: no se publica consumo efectivo con semántica ambigua. |
| `validation` | `{feasible: boolean\|null,violations: string[],scope: string}`. Se conserva el alcance del validador del proveedor y se comprueba coherencia de presentación. |
| `phases` | `[]`; las trazas heterogéneas originales no se convierten en certificados inventados. |
| `warnings`, `assumptions` | Listas de cadenas en español. |
| `runtime_seconds` | `preparation`, `solver`, `total`. `solver` mide la llamada completa `resolver_preparada`, incluida construcción/validación upstream; no es tiempo puro de HiGHS. `total` es extremo a extremo del servicio. No sumar el total a sus etapas. |
| `network` | `{type,vial,geometry_source,provenance_verified:false}`. `vial` refleja el tipo declarado por la preparada, no una auditoría de su red. |
| `raw` | `input` original, `prepared`, `effective_config`, `result` del proveedor. La configuración se pasa al proveedor; la reducción de presupuesto interna consta en `result.bitacora` (`presupuesto`). |
| `metadata` | Proveedor/SHA, hashes SHA-256 de input/config/red, `id_map` de ID interno→original, `unavailable_statistics`. El hash de red excluye tiempos de preparación y origen de archivo. |

El adapter usa códigos internos únicos antes de preparar/resolver para no activar
las colisiones `|`/`#fin` del proveedor. Los objetos preparados/raw mantienen esos
IDs internos auténticos y `metadata.id_map` permite reconstruirlos; los campos de
presentación y la entrada original mantienen los IDs del usuario.

La configuración del proveedor usa `milp`, formulación `completa`, conectividad
`flujo`, un hilo, sin poda de vecinos ni cargadores. Esta elección evita el segundo
intento automático de `compacta` que reutiliza un presupuesto entero. No cambia
código upstream ni demuestra equivalencia con el PDF base.

### Energía y validación

El validador upstream describe recarga completa, pero `energia_efectiva_kwh` usa otra
simulación con recarga mínima. El caso regenerativo auditado y probado realmente
produce carga 5/final 8 a partir de inicial 6 (balance 3), frente a KPI efectivo −1.
Si el KPI contradice el balance del detalle, `feasible` es `null` y una advertencia
explica la inconsistencia. Las violaciones físicas/estructurales explícitas dejan
`feasible: false`. Un resultado coherente y aprobado por el validador upstream
puede informar `true` dentro del alcance textual, nunca garantía de consumos reales.
La beta no implementa otro estimador energético.

Las cotas/gaps no finitas se exportan como `null` junto a su ruta, motivo y valor
original textual en `unavailable_statistics`. Ningún dato físico no finito se
convierte silenciosamente; invalida la respuesta del proveedor.

## Errores

`{api_version,error:{code,message}}` con mensaje público y sin trazas/rutas del host.
400 entrada; 403 origen; 404 recurso/resultado expirado; 409 cálculo ocupado;
411 longitud; 413 tamaño; 415 tipo; 422 búsqueda sin solución encontrada;
502 contrato/fallo del proveedor; 503 proveedor ausente/no fijado; 500 error interno.
422 no significa infactibilidad probada. La beta no fabrica un resultado de solver
cuando el proveedor lanza una excepción sin incumbente.

## Evidencia reproducible

`python -m unittest discover -s tests -p test_web_bridge.py -v`, ejecutado con el
Python de la instalación fijada, incluye una prueba real HTTP+HiGHS y el caso
regenerativo anterior. Sin `evrp/highspy`, los casos reales se omiten explícitamente;
esa ejecución sola no demuestra integración MILP.

`fixtures/tiny-request.json` es sintética. `fixtures/tiny-response.json` fue obtenida
realmente con la API/HiGHS fijados y contiene entrada, preparada, configuración y
resultado completos. Sus tiempos/run_id son evidencia de esa corrida, no benchmark.
