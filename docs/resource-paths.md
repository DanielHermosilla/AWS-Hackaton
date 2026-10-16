# Preprocesamiento de caminos con recursos

La preparación sigue separada del solver. El comando `service-graph`, con su
valor predeterminado `--service-movements none`, llama a
`resource_graph.prepare_service_graph`. El pricing de SCIP consume sus
conexiones, elige alternativas por `arc_id` y aplica sus perfiles a los recursos
continuos existentes. El maestro por rutas, su objetivo y sus certificados no
cambian.

Esta implementación concreta la investigación de
[caminos con regeneración y ventanas](investigacion-caminos-recursos.md).
Empieza por un multigrafo disperso y puede conservar intersecciones. No exige
calcular antes todas las alternativas entre todos los pares de servicios.
No se afirma que sea el preprocesador más rápido posible.

## Selección de la preparación

1. **Energías no negativas y ninguna jornada/ventana activa:** Dijkstra dirigido
   sobre CSR, como antes. El camino de mínima energía domina para el objetivo
   actual. Los tiempos se conservan para informar el calendario, pero no son
   una restricción ni un objetivo de este caso. También se preservan la reserva
   final configurable y el margen uniforme sobre las descargas.
2. **Regeneración o jornada/ventanas:** eliminación de intersecciones con perfiles
   exactos de batería, tiempo de viaje y alternativas no dominadas. Nunca se
   agregan energías firmadas ignorando su orden.
3. **Intersección costosa o presupuesto agotado:** se conserva en el grafo.
   El pricing sigue explorándola normalmente. No se truncan etiquetas, no se
   eligen solo k caminos y no se añade H.

La preparación posicional seleccionada mediante `auto` o un H entero conserva
el comportamiento heredado de Dijkstra y sus límites declarados. Los nuevos
perfiles requieren `scip-routes`: los backends posicionales los rechazan
explícitamente para impedir que interpreten una conexión como una calle simple.

## Perfil de una conexión

Con capacidad B, reserva R y energía efectiva por calle e, la transición es
`b' = min(B, b-e)`, válida si no viola R. El margen de consumo se aplica primero
a **cada descarga**: `e = nominal + margin*max(nominal,0)`.

Sin actividades dentro del camino, el perfil se representa con tres números:

- `minimum_departure_kwh = L`: menor batería de salida permitida.
- `consumption_kwh = E`: suma de consumos después del margen, antes de limitar
  regeneración por capacidad.
- `maximum_arrival_kwh = U`: techo de batería al llegar.

Su dominio es `[L,B]` y su función de llegada es `F(b)=min(b-E,U)`.
El consumo efectivo que entra al objetivo es **b − F(b)**, no E.
Para una calle: `L=max(R,R+e)`, `E=e`, `U=min(B,B-e)`.

Al concatenar P y Q:

```text
E(PQ) = E(P) + E(Q)
L(PQ) = max(L(P), L(Q) + E(P))
U(PQ) = min(U(P) - E(Q), U(Q))
```

La concatenación es inviable si `U(P)<L(Q)` o `L(PQ)>B`.
Así se conserva tanto un déficit intermedio como la saturación. No se
discretiza la batería.

Ejemplo con B=10, R=1 y salida=6: `[-6,+4]` termina en 6, mientras
`[+4,-6]` termina en 8. Aunque ambos suman −2, sus perfiles son distintos.
`[+6,-5]` exige al menos 7 al salir; su suma 1 no basta para declararlo factible.

## Eliminación y dominancia

Se priorizan intersecciones por `número_de_entradas × número_de_salidas`.
Para eliminar v, se componen todas sus entradas con todas sus salidas.
Depósito, clientes y cargadores nunca se eliminan. Tampoco se elimina una
intersección que tenga un ciclo regenerativo útil representado como autoarco.

Entre conexiones con los mismos extremos, P domina Q si:

- Su dominio contiene el de Q.
- Llega al menos con la misma batería para **todo** `b∈[L(Q),B]`.
- Si hay jornada, no tarda más que Q.

La diferencia de dos funciones `min(b-E,U)` es monótona; basta comparar en
`L(Q)` y B. Las comparaciones de dominancia no relajan tolerancias. Un ciclo
dominado por permanecer en su nodo puede eliminarse; un ciclo que permite
recuperar batería se conserva. No se requiere suponer que no hay ciclos
energéticos negativos.

Si una prueba de factibilidad al componer cae a unas pocas unidades de
redondeo de la frontera, se conserva la intersección y su propagación original.
`roundoff_retained_junctions` registra esos casos. Esa precaución no relaja
dominios ni dominancia y evita perder rutas que pasan exactamente por la
reserva, como una descarga de 21,6 kWh desde 24 kWh con reserva de 2,4 kWh.

Cada eliminación reemplaza un paso entrada-salida sin actividad en v por su
composición exacta. Cada conexión resultante se expande a esas mismas calles.
La sustitución por una conexión dominante no empeora el objetivo ni la
factibilidad: puede esperarse para respetar aperturas y reducir una carga
parcial posterior para evitar sobrecargar. La identidad
`consumo = batería_inicial + carga_acumulada − batería_final` conserva el
sentido de la dominancia incluso con regeneración.

Por inducción sobre las eliminaciones, detenerse en cualquier punto conserva
el óptimo vial **sin H**, para el escenario configurado. Se pueden descartar
recorridos dominados, por lo que no se conserva literalmente cada recorrido.
`provenance.representation.road_optimum_preserved` describe esta suficiencia;
**no significa que SCIP haya probado optimalidad**. Las dos fases y la
completitud del pricing siguen requiriendo sus propias pruebas.

Los supuestos son los del modelo actual: tiempos constantes y no negativos,
espera sin consumo, recarga parcial, actividades solo en servicios y objetivos
de entregas/energía. Esta prueba no cubre tráfico dependiente de hora, carga
transportada, peajes, objetivos de distancia ni consumo auxiliar al esperar.

## Presupuestos, caché y auditoría

```bash
uv run --locked ev-routing service-graph \
  --road-instance artifacts/hackathon/instance.json \
  --config config/operations.example.json \
  --output artifacts/resources/instance.json \
  --path-archive artifacts/resources/paths.json \
  --cache-directory artifacts/resources/cache \
  --max-pair-expansions 64 \
  --preprocessing-seconds 10 \
  2>&1 | distill "Resume reducción, caché, tiempo y alcance."

uv run --locked ev-routing run \
  --instance artifacts/resources/instance.json \
  --road-instance artifacts/hackathon/instance.json \
  --path-archive artifacts/resources/paths.json \
  --solver scip-routes --time-limit-seconds 60 \
  --output artifacts/resources/result.json \
  2>&1 | distill "Resume entregas, energía, auditoría vial y certificados."
```

Los valores operacionales del archivo de ejemplo son supuestos ilustrativos.
Se aplican **antes** de decidir el preprocesador; `run` no cambia el escenario.

`max_pair_expansions` limita el trabajo por eliminación, conservando las
intersecciones que lo exceden. `preprocessing_seconds` es un presupuesto
blando; construir índices, terminar una eliminación y serializar tienen
sobrecostos. Cero permite usar la representación perfilada sin comprimir.
Una reducción mayor no garantiza un pricing más rápido: puede crear muchas
alternativas paralelas.

La caché depende del contenido de la red, operaciones, parámetros físicos,
versión del algoritmo y opciones de preparación. Se guarda atómicamente la
instancia junto a su archivo de caminos. Los hashes se comprueban al leer.
Cambiar el escenario invalida la caché; no se reutiliza un perfil de otro margen
o capacidad. `--reuse-instance` solo admite el mismo escenario para perfiles.

Los snapshots `resource_paths` son versión 1.1. Los arcos tienen `arc_id` único
y `battery_profile`; los pasos de solución y el archivo de caminos guardan
ese mismo ID. Esto distingue caminos paralelos y ciclos del arco ficticio de
inactividad. La versión 1.0 y sus hashes anteriores siguen siendo legibles.

Antes de resolver se auditan los perfiles contra los prefijos de sus calles,
con una derivación independiente de la composición. Tras resolver, se expanden
los recorridos y se reproducen todas las transiciones, servicios y recargas.
Los KPIs, incluida la batería mínima, se calculan sobre las calles expandidas,
para no ocultar mínimos interiores.

## AWS y límites de rendimiento

El preprocesamiento no añade llamadas remotas. La política Bedrock previa
existente sigue siendo opcional para el solver. En esta implementación se
intentó una sola consulta de diseño a `us.anthropic.claude-fable-5`: AWS confirmó
acceso y ejecutó inferencia, pero respondió `max_tokens` sin texto utilizable
(610 tokens de entrada, 2.000 de salida; 31,35 s). No se aplicó ninguna propuesta.
Los logs se conservaron localmente, sin datos de clientes ni credenciales.

Los perfiles y los límites que preservan la red son decisiones verificables
localmente; una llamada LLM por preparación o por etiqueta añadiría latencia
sin una mejora demostrada. Un ensayo futuro puede comparar configuraciones
seguras con el mismo presupuesto y medir también ese costo.

La cantidad de alternativas y el propio pricing pueden crecer mucho.
Conservar intersecciones acota el trabajo de compresión, no la complejidad del
problema de ruteo. No se presenta un benchmark sintético como prueba de rapidez
para regeneración y ventanas sobre toda la red de competición.

## Comprobaciones y medidas locales

Ensayos del 15 de octubre de 2026 en esta rama. La suite completa pasó:
**607 pruebas**, incluidas 36 de perfiles y su integración; Ruff sin errores.
Se contrastaron 14.820 estados de batería con reproducción independiente
por segmentos, doce redes pequeñas generadas con semillas fijas, ciclos
regenerativos, reserva decimal, recargas parciales, ventanas, caché alterada,
interrupción de la compresión y expansión completa con SCIP.

Comparación de tres repeticiones por caso sintético. La columna de perfiles
incluye **preparación, pricing exhaustivo y auditoría vial**:

| Caso | Nodos originales → reducidos | Etiquetas expandidas | Pricing vial | Total con perfiles |
|---|---:|---:|---:|---:|
| Contraejemplo de ventana | 3 → 2 | 8 → 6 | 0,305 ms | 0,459 ms |
| Corredores de 8 segmentos | 16 → 2 | 43 → 7 | 1,212 ms | 0,727 ms |
| Corredores de 80 segmentos | 160 → 2 | 105 → 3 | 2,656 ms | 2,384 ms |

Son medianas locales y tiempos pequeños: no acreditan una aceleración general.
El caso mínimo es más lento al incluir preparación. Los mejores objetivos
coincidieron con el oráculo sobre las calles originales; las pruebas de
equivalencia comparan además todos los subconjuntos factibles y sus energías.
El Dijkstra anterior perdía la única entrega del contraejemplo de ventana;
el nuevo preprocesador conserva la alternativa rápida y obtiene 3 kWh.

Red local leída desde `artifacts/hackathon/instance.json`, SHA-256 normalizado:
`b277009514c10a394131d3a052f122b25db664f41f225ab707e6db8ebe4e35cb`.
Tiene 106.746 nodos y 211.725 calles, sin energías negativas ni tiempos explícitos.
En el escenario base, las 6.006 conexiones conservaron **exactamente** sus
energías respecto de Dijkstra. Medianas de tres repeticiones:

| Preparación del escenario base | Tiempo |
|---|---:|
| Dijkstra existente | 1,282 s |
| Selección automática nueva, sin caché | 1,310 s |
| Reutilización de caché, tres aciertos | 0,715 s |

Una ejecución SCIP con presupuesto de 10 s probó **20 entregas y
10,5577408405 kWh**, con expansión vial factible. El pipeline tardó 1,100 s,
excluyendo preparación y lectura del archivo. No es una comparación A/B de
tiempo de solver.

En la misma topología, un escenario **supuesto** de ocho horas, ventanas
`[0,28800]`, velocidad de 30 km/h y potencia efectiva configurada hasta 3 kW
activó la preparación general. Conservó 607 nodos (81 servicios y
526 intersecciones) y 6.333 conexiones, eliminando 106.139 intersecciones.
Una medición dio **4,374 s** de preparación y **0,440 s** de auditoría completa
de perfiles. El presupuesto de compresión fue 10 s y no se agotó. **No se
resolvió el problema temporal completo**; este ensayo verifica la preparación,
no su tiempo de pricing ni un óptimo con ventanas.

Los JSON locales `artifacts/resource-graph/benchmark-final.json` y
`large-temporal.json` contienen mediciones y supuestos completos. Ambos ensayos
registran el hash del código Python de producción:
`da194c0d8cbd5f1cde95e04c6d35851e31bf08d500734c6bb9c395884e8373cf`.
Los archivos originales permanecen intactos; no se usó `evaluation` para elegir
parámetros.

Pruebas y ensayo reproducible:

```bash
uv run --locked pytest -q tests/test_resource_graph.py \
  2>&1 | distill "Indica conteos y cualquier fallo de equivalencia."
uv run --locked python scripts/benchmark_resource_paths.py \
  --road-instance artifacts/hackathon/instance.json --repeats 3 \
  --solver-seconds 10 --output artifacts/resource-graph/benchmark.json \
  2>&1 | distill "Compara tiempo total, objetivos y validación; separa red local y casos sintéticos."
```
