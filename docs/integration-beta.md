# Integración local con el solver de Daniel

El frontend de `codex/webapp` se conecta al solver de Daniel Hermosilla importado
desde `origin/modelamiento`, commit
`624203573bffdeec334a9e07a64b361a515f9725` del 15 de octubre de 2026.
Se usa **SCIP/PySCIPOpt, `scip-routes`**, con su comprobador independiente.

Se excluye `service_graph.py`, cuyo origen documentado adapta trabajo de Lucas
Zulueta, y los módulos que dependen de ese preprocesador. El antiguo puente
`evrp` se retira. [solver-source.json](solver-source.json) registra el commit,
los archivos, sus huellas y las adaptaciones locales. Es una importación acotada
de código; no fusiona las ramas ni reescribe su historia.

## Ejecutar

Desde la raíz de esta rama, con Python 3.12 o 3.13 y `uv`:

```sh
uv sync --locked
uv run --locked python -m backend.local_server --port 4294
```

Abrir `http://127.0.0.1:4294/` y pulsar **Cargar y calcular**. El servidor sirve
la interfaz y la API en el mismo origen. El entorno y el único lockfile están
en este repositorio; no se necesita otro checkout del proveedor.
La cartografía de fondo necesita internet; resolver un JSON completo no descarga
mapas ni llama a AWS.

La CLI consume el mismo contrato y llama al mismo pipeline:

```sh
uv run --locked ev-routing run \
  --instance examples/toy_recharge.json \
  --time-limit-seconds 30 \
  --output artifacts/toy-result.json
```

## Comunicación estable

La frontera pública está en [backend/API_CONTRACT.md](../backend/API_CONTRACT.md).
La instancia nativa se define una sola vez en
[`ProblemInstance`](../src/ev_routing/contracts.py), con `schema_version: "1.0"`.
El transporte web tiene `api_version: "3.0"`:

```text
CSV/formulario → POST /prepare → ProblemInstance
JSON nativo ──────────────────→ ProblemInstance
ProblemInstance → POST /solve → pipeline de Daniel → resultado y validación
                                         ↓
                             proyección de presentación → Inicio y Plan
```

`/solve` recibe `instance` y el presupuesto `solver.time_limit_seconds`.
La web no construye restricciones ni estima resultados. Conserva los IDs opacos.
La instancia exportada sirve directamente para otra ejecución o para la CLI.

El resultado conserva el JSON nativo completo en `raw.result`, la instancia
normalizada en `raw.instance`, la petición en `raw.input` y la configuración
efectiva. La proyección web mantiene sus campos aunque cambie el algoritmo.
Estados, cotas, gaps, mensajes y tiempos por fase proceden del motor.
`metadata.provider_commit` identifica el código importado.

Antes de actualizar el solver, comparar el commit con `docs/solver-source.json`,
comprobar cambios en contratos y ejecutar las pruebas con los ejemplos compartidos.
No copiar de nuevo los módulos excluidos. Los campos nuevos opcionales pueden
evolucionar sin cambiar significado; cambiar unidades, campos obligatorios o
semántica requiere una versión nueva y una adaptación explícita. Compartir un
número de versión no demuestra compatibilidad.

## Entradas y alcance

- **JSON nativo**: conserva nodos, arcos dirigidos, flota, compatibilidad,
  operaciones y procedencia. No se completan calles ausentes ni se recalcula
  energía desde coordenadas. El formulario no sobrescribe los parámetros físicos
  del archivo; permite cambiar el presupuesto de resolución.
- **CSV/formulario**: requiere confirmar una red geodésica **sintética**, con
  consumo por kilómetro explícito. `/prepare` construye la instancia en Python.
  Los puntos no acreditan conectividad vial. No se usa el preprocesador excluido.
- Los formatos `evrp.instancia_preparada/1` y API `2.0-beta.1` se rechazan.
  Tampoco se admite `service_paths_nonnegative`, que necesita una expansión vial
  excluida de esta integración.
- Las coordenadas pueden faltar en el contrato nativo. Las rutas y baterías
  siguen disponibles; no se inventan ubicaciones ni trazados para el mapa.
  `Arc.geometry` nativa usa `[latitud, longitud]`; el puente convierte a GeoJSON
  `[longitud, latitud]` solo al presentar una geometría completa y anclada.

La referencia oficial sigue siendo dos vehículos al 60 % inicial. Capacidad
útil, reserva, consumo, jornada y extensiones son entradas o supuestos.
`scip-routes` implementa la formulación sin H de Daniel: `movement_limit`
se conserva por compatibilidad, pero no limita esta resolución.
Ver [model.md](model.md) y el PDF importado junto al motor.

## Estados y datos disponibles

La factibilidad requiere el comprobador independiente favorable. Sin incumbente,
la respuesta conserva estados y fases, con rutas vacías y métricas desconocidas
como `null`. Un límite de tiempo no demuestra infactibilidad. Una solución parcial
o factible al agotar presupuesto se conserva y se valida. Solo las pruebas de
ambas fases permiten afirmar optimalidad lexicográfica para el grafo y modelo
energético recibidos.

La energía mostrada es **energía neta efectiva de batería** del motor. Puede
ser negativa con regeneración. Se distingue de energía recargada y de energía
comprada. Ahorros y emisiones permanecen sin dato cuando faltan referencias.
El tiempo de resolución incluye el modelo y la búsqueda; la validación se
conserva separada. Los intervalos contenidos no se suman dos veces.

Editar marca el resultado anterior como pendiente de recalcular. Las respuestas
tardías no reemplazan una revisión nueva. Inicio y Plan comparten `run_id`;
el navegador guarda solo una referencia y estado mínimo. **Dejar de esperar**
no cancela la búsqueda del servidor. Un error no activa datos de ejemplo.

El servidor conserva hasta cuatro resultados y 32 MiB en memoria; expiran
al reiniciarlo o reemplazarse. Es una ejecución local sin autenticación,
base de datos, despliegue ni tuning AWS. La política es `standard`, sin llamadas
a Bedrock. No acredita acceso AWS ni rendimiento del concurso.
Los límites de la API se detallan en su contrato; no son reglas oficiales.

## Verificar antes del merge

```sh
uv run --locked pytest -q
node --test webapp/tests/*.test.mjs
git diff --check
```

Los ejemplos `toy_recharge.json` y `toy_regeneration.json` provienen de Daniel.
Sus cuentas manuales esperan 2 entregas/14 kWh/9 kWh de recarga y 1 entrega/2 kWh.
Se comprueban con SCIP real, JSON finito y sin importar `evrp` ni el preprocesador
excluido. Los tests del puente cubren HTTP, conversión a presentación, rechazo de
entradas y preservación del contrato. Estados forzados mediante dobles se
distinguen de ejecuciones reales.

La evidencia de la antigua beta con HiGHS es histórica y no valida esta entrega.
Los cambios se mantienen en commits locales para revisión y merge posterior.
No se hace push ni despliegue automáticamente.
