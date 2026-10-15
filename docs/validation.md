# Verificación de la rama `modelamiento`

## Ensayo visible 20/60: 15 de octubre de 2026

`scripts/test_20_clients.sh` se ejecutó con los snapshots preparados de
`artifacts/hackathon/`, 60 segundos, un hilo y semilla 0.
Los artefactos están en `artifacts/test-20c-60s/validation-verbose/`.
Obtuvo **20/20 entregas, 10,557740840522953 kWh y óptimo lexicográfico** sobre
los caminos disponibles, con expansión y validación vial satisfactoria.

Una llamada real a Bedrock (`us.amazon.nova-micro-v1:0`, `us-east-1`,
perfil `hackathon`) consumió 924 tokens y cambió `subtour_batch_size` de
100 a 150 y `branching` de `relpscost` a `mostinf`. Se verificó que el prompt
guardado corresponde al cuerpo de Converse, la decisión coincide con el
resultado y `run.log` contiene tanto los prompts como el log nativo de SCIP.
Este ensayo verifica funcionamiento y trazabilidad; no mide aceleración.

La suite final pasó **560 pruebas**; Ruff, sintaxis Bash y `git diff --check`
también pasaron. Los ocho casos nuevos cubren prompts, respuestas inválidas,
cambios efectivos, ausencia de llamada, salida íntegra, códigos de error,
recuento de nodos y conservación de logs. La corrección posterior del directorio
de logs en el manifiesto quedó cubierta por la suite; no requirió otra llamada AWS.

## Reformulación sin H: 15 de octubre de 2026

La suite completa pasó **552 pruebas** y Ruff no encontró errores. Los nuevos
casos verifican independencia respecto de H=1/3/10000, recargas parciales,
eficiencia y jornada, ventanas, tránsito sin entrega, estaciones repetidas,
retornos intermedios, regeneración/saturación, déficit intermedio, Farkas,
integralidad del maestro y pérdida de certificación ante pricing interrumpido.
Además, 12 instancias aleatorias pequeñas coincidieron con el oráculo independiente
de estados energéticos enteros, incluyendo regeneración y uno/dos vehículos.
No se discretiza el modelo real: ese oráculo solo contrasta fixtures enteras.

Benchmark real: `artifacts/benchmark-routes-validated/`, nueve procesos,
tres políticas × semillas 0/1/2, un hilo y presupuesto blando de 60 segundos.
Todos obtuvieron **20 entregas, 10,557740840522953 kWh y óptimo lexicográfico**,
con validación de las 1.999 calles recorridas y del vehículo inactivo.
La reducción a tour fue certificada en los datos; no aplica por defecto a
escenarios con jornada/ventanas o sin un testigo que quepa en la batería inicial.

| Mediana (s) | Standard | Deterministic | Adaptive |
|---|---:|---:|---:|
| Resolución, incluida construcción y LLM | 0,0333 | 0,0336 | 1,1270 |
| Llamadas nativas a optimize | 0,0205 | 0,0205 | 0,0296 |
| Pipeline, incluida validación | 1,0214 | 1,0187 | 2,1310 |
| Proceso completo, incluida carga | 3,6921 | 3,7080 | 4,9534 |

Las tres corridas adaptativas aplicaron una llamada real a Bedrock por corrida,
modelo `us.amazon.nova-micro-v1:0`, región `us-east-1`, perfil `hackathon`.
Total: 2.749 tokens, sin fallback ni llamadas desde callbacks. No se observa
ventaja temporal del LLM en esta instancia pequeña: su coste domina la resolución.
No extrapolar estos tiempos a los casos generales de pricing.

El ensayo previo `artifacts/benchmark-routes/` conserva dos fallbacks por JSON
inválido y un campo de tiempo nativo ausente. No usar ese campo como medición.
Se corrigió el registro y la invocación estratégica usa temperatura 0 y formato
JSON explícito antes de repetir el benchmark. Después se corrigieron textos de
metadatos en `benchmark.py`/`cli.py` y se hizo cumplir estrictamente el tamaño
de lote en el pricing general, con regresión de lotes unitarios. La reducción
DFJ medida no cambió. Las copias previas de los textos están en
`source-before-metadata-cleanup/`; el manifiesto conserva el hash real ejecutado.

`modelamiento.pdf` fue recompilado a siete páginas, con ecuaciones (25)–(29);
se comprobaron texto y renderizados de la reformulación.

## Referencia posicional anterior

Ejecución local del 15 de octubre de 2026 (UTC), Python 3.12, Pyomo 6.10.1,
Gurobi 13.0.3 y SCIP 9.2.4. Los resultados describen esta implementación y
estos ensayos; no acreditan rendimiento en la instancia completa del concurso.

## Actualización: Dantzig–Wolfe y Bedrock

El 15 de octubre de 2026 se ejecutó la suite ampliada con el extra `dw`:
**522 pruebas aprobadas, sin fallos ni omisiones**, en 6.17 segundos.
También pasaron Ruff, la sintaxis Bash del benchmark y `git diff --check`.
Este ensayo no volvió a medir cobertura; el porcentaje de la sección siguiente
corresponde a la suite inicial.

Las pruebas nuevas contrastan ambas descomposiciones con óptimos manuales y
enumeración independiente, incluyendo carga continua, regeneración, ventanas,
jornada, reservas, H, tránsito, retornos intermedios, infactibilidad y timeout.
Se ejercitan pricing, cortes y cambios de política desde callbacks reales,
con proveedores dobles en los tests ordinarios. Un caso de tres clientes
requiere ramificación por debajo de la raíz y prueba energía 9 kWh, frente
a la combinación fraccional de rutas de 7.5 kWh.
También se prueba el benchmark como procesos independientes, la expansión vial,
la reanudación y el rechazo de resultados modificados.

Separadamente se invocó **Bedrock real**, región `us-east-1`, perfil `hackathon`,
modelo de prueba `us.amazon.nova-micro-v1:0`, sobre `toy_recharge.json`:

| Política GCG | Entregas | Energía | Ambas fases probadas | Tiempo de proceso |
|---|---:|---:|---|---:|
| Estándar | 2 | 14 kWh | Sí | 0.882 s |
| Determinista | 2 | 14 kWh | Sí | 0.890 s |
| Adaptativa | 2 | 14 kWh | Sí | 3.349 s |

La adaptativa aplicó dos decisiones reales antes de descomponer, con **2691
tokens** informados por AWS. La instancia termina demasiado rápido para exigir
una decisión remota durante la búsqueda; ese mecanismo se verifica mediante
callbacks y un proveedor doble. Un ensayo previo devolvió respuestas inválidas
y quedó registrado como fallback, sin atribuirle uso efectivo de una política LLM.

Los artefactos están en `artifacts/dw-development/benchmark-aws-validated/`,
con manifiesto y hash del código de esa corrida. Ajustes posteriores de
telemetría y supervisión están cubiertos por la suite local final; los tiempos
anteriores no se reasignan a otro hash.
El log de la suite final está en `artifacts/dw-development/full-tests.log`.
Son artefactos locales ignorados por Git.

Este ejemplo prueba integración y corrección, **no aceleración**: aquí el costo
de inferencia domina. No se midió todavía rendimiento DW en los 81 servicios
ni costo monetario con una tarifa verificada.
Ver [protocolo y comando de benchmark](dantzig-wolfe.md).

## Suite automatizada inicial

**349 pruebas aprobadas, 0 fallos, 0 errores y 0 omitidas.**
Cobertura de líneas: **96.1 %** (1049 de 1092 sentencias).
Los informes locales están en `artifacts/tests/final.xml` y
`artifacts/tests/coverage.json`, fuera de Git.

| Área | Casos |
|---|---:|
| Configuración y contratos | 103 |
| Lectura de datos, energía y red | 54 |
| Modelo Pyomo y oráculos independientes | 50 |
| Adaptador Gurobi/SCIP y certificados | 32 |
| Validador independiente y métricas | 65 |
| CLI y pipeline | 37 |
| Esqueleto de tuning desactivado | 8 |

Se comprueban recarga repetida, regeneración saturada, déficit antes de
regeneración, vuelta intermedia al depósito, entregas únicas, clientes
inaccesibles, flotas parametrizadas y límites de movimientos. Los oráculos
enumeran caminatas diminutas con hipótesis de exactitud documentadas en
`docs/model.md`, sin reutilizar las restricciones Pyomo.

Las pruebas de fallos del solver simulan licencia ausente/insuficiente,
timeouts con y sin incumbente, errores de segunda fase y cotas incompletas.
Además hay ejecuciones reales con Gurobi y SCIP. La cobertura mide líneas
ejecutadas: no demuestra corrección para todas las instancias posibles.

Reproducir:

```bash
uv sync --locked
uv run pytest --cov=ev_routing --cov-report=term-missing \
  --cov-report=json:artifacts/tests/coverage.json \
  --junitxml=artifacts/tests/final.xml
uv run ruff check src tests
```

## CLI con ejemplos sintéticos

Se ejecutó cada ejemplo con ambos backends, con igual óptimo y validación
independiente satisfactoria:

| Ejemplo | Entregas | Energía neta | Recarga a batería |
|---|---:|---:|---:|
| `examples/toy_recharge.json` | 2/2 | 14 kWh | 9 kWh |
| `examples/toy_regeneration.json` | 1/1 | 2 kWh | 0 kWh |

En el segundo caso, sumar los consumos nominales de arcos daría −1 kWh:
sería incorrecto porque 3 kWh regenerados se descartan por saturación.
Los dos solvers producen el consumo efectivo correcto.

```bash
uv run ev-routing run --instance examples/toy_recharge.json \
  --solver gurobi --output artifacts/examples/toy_recharge-gurobi.json
uv run ev-routing run --instance examples/toy_recharge.json \
  --solver scip --output artifacts/examples/toy_recharge-scip.json
uv run ev-routing run --instance examples/toy_regeneration.json \
  --solver gurobi --output artifacts/examples/toy_regeneration-gurobi.json
uv run ev-routing run --instance examples/toy_regeneration.json \
  --solver scip --output artifacts/examples/toy_regeneration-scip.json
```

## Ensayo con datos locales y calles de Ann Arbor

Se integró `data/eVED_EV.csv` usando intervalos reales y excluyendo huecos
mayores a 10 segundos: 476308 filas, 504 viajes, 475223 intervalos válidos y
581 huecos excluidos. La razón descriptiva fue
366.975683 kWh / 2340.835385 km = **0.1567712473 kWh/km**.
No se utilizó la instancia `evaluation` para escoger ese coeficiente.
No es una evaluación predictiva fuera de muestra.

Se preparó una red vial OSM dirigida sin simplificar para el depósito y el
cliente V13 de `competition_routing_nodes.csv`, sin cargadores:
935 nodos y 1921 arcos, incluyendo accesos supuestos de 15.09 m y 7.93 m.
El snapshot local es
`artifacts/instances/ann-arbor-one-customer.json`.
El viaje requiere al menos 41 movimientos de ida y 41 de vuelta; por ello
`H=30` no permite esa entrega, aunque haya energía suficiente.

Para resolver un juguete acotado se conservó el subgrafo inducido por la unión
de los caminos de mínimo número de movimientos de ida y vuelta, y se fijó
`H=82`, con los dos vehículos. **Esta restricción es exclusiva del ensayo;
el pipeline de producción no recorta automáticamente la red.**
La selección y su alcance constan en `provenance.toy_scope`.

Gurobi probó ambas fases: **1/1 entrega**, **0.6008965368 kWh**,
**3.832951176 km**, sin recargas, con batería mínima de **13.79910346 kWh**.
El comprobador independiente aceptó el resultado. El tiempo medido de
resolución, incluida construcción, fue 1.254 s en esta ejecución;
no se presenta como benchmark ni ahorro frente a otro método.

Los artefactos locales permiten repetir exactamente el problema ya preparado:

```bash
uv run ev-routing run \
  --instance artifacts/instances/ann-arbor-restricted-toy.json \
  --time-limit-seconds 30 \
  --output artifacts/results/ann-arbor-restricted-toy.json
```

La optimalidad corresponde solo al subgrafo, `H` y estimador usados.
No se ha resuelto ni evaluado el rendimiento de la instancia completa de
81 ubicaciones de servicio. Los datos originales, GraphML y resultados
grandes permanecen locales; los ejemplos sintéticos sí viajan con el repo.
