# Medición para la presentación

`scripts/benchmark_evidence.sh` prepara escenarios desde **calles originales** y
ejecuta el mismo pipeline CLI de `main`, con SCIP por rutas sin H. No cambia la
formulación, el solver, el estimador energético ni el validador. `main` al iniciar
este trabajo era `9f03027`; no había una rama `master`.

El PPTX, diapositivas 5–7, pide entregas factibles, consumo, cómputo y
escalabilidad. La rúbrica no convierte CO₂ en objetivo del solver.

## Piloto local

Desde la raíz del checkout con este script:

```bash
bash scripts/benchmark_evidence.sh campaign \
  --road-instance /Users/daniel/AWS-Amazon/artifacts/hackathon/instance.json \
  --routing-csv /Users/daniel/AWS-Amazon/data/competition_routing_nodes.csv \
  --customers 40 --vehicles 2 --seeds 0 1 \
  --budgets 8 --sensitivity --threads 1 \
  --impact config/benchmark-impact.example.json \
  --wall-budget-seconds 600 \
  --output-dir artifacts/evidence-pilot --execute
```

Son **6 escenarios × 2 semillas × 2 políticas = 24 corridas**, hasta 192 s de
presupuesto del solver, más preparación, lectura y auditoría. El límite total
es 600 s para esa invocación; no se inicia otra corrida si falta tiempo para su
presupuesto y margen. La preparación también corre en un proceso con timeout.
La escritura del informe final queda fuera del timeout de los procesos.
No hay llamadas AWS sin `--with-bedrock`.

Sin `--execute`, imprime el plan completo y máximos de trabajo/llamadas, sin
preparar redes ni resolver. Si se interrumpe, repetir el mismo comando con
`--resume`. Conserva los resultados completos y verifica sus hashes. Un timeout
registrado se mantiene como dato; para repetirlo usar otra campaña o repetición.
`--report-only` reconstruye informes sin resolver. Datos, código, versiones y plan
deben coincidir: no mezclar corridas de implementaciones diferentes.

Los scripts de esta guía imprimen logs. En entornos que exijan `distill`, usar
`2>&1 | distill "resume avance, corridas completadas y errores"` al invocarlos.

## Campaña con LLM y escalamiento

Primero revisar el plan sin `--execute`:

```bash
bash scripts/benchmark_evidence.sh campaign \
  --road-instance /Users/daniel/AWS-Amazon/artifacts/hackathon/instance.json \
  --routing-csv /Users/daniel/AWS-Amazon/data/competition_routing_nodes.csv \
  --customers 40 80 160 --vehicles 2 4 8 \
  --scenario-seeds 0 1 2 --seeds 0 1 2 3 4 \
  --budgets 30 120 --sensitivity --threads 1 \
  --with-bedrock --bedrock-model us.openai.gpt-5.6-luna \
  --aws-profile hackathon --aws-region us-east-1 --llm-max-calls 4 \
  --impact config/benchmark-impact.example.json \
  --wall-budget-seconds 3600 \
  --output-dir artifacts/evidence-full
```

Esta matriz tiene **32 escenarios, 960 corridas, 72.000 s de presupuesto del
solver y hasta 1.280 llamadas**. Es una campaña grande: una invocación de 1 h
ejecuta solo una parte y se reanuda. Para un ensayo AWS pequeño, usar
`--customers 40 --vehicles 2 --scenario-seeds 0 --seeds 0 1 2 --budgets 30`
sin `--sensitivity`: 18 corridas y hasta 24 llamadas.
Las cotas son máximos planificados, no un coste monetario ni duración garantizada.
El acceso a AWS no se acredita con el plan ni con las pruebas locales.

La fracción de inferencia es 25%, con máximo de 2.048 tokens de salida por
llamada, contexto de instancia de 8.000 bytes, esfuerzo `low`, timeout configurable
y máximo de llamadas explícito. La entrada completa también incluye estructura,
estado y esquema; 8.000 bytes no limita el total de tokens de entrada.
Se conservan consumo de tokens disponible, errores, respuestas tardías,
fallback y decisiones que efectivamente cambian el algoritmo.

Los pares comparten snapshot, semilla, presupuesto, hilos y gap energético
0,005. El orden de las políticas se mezcla por semilla. Se comparan:

- `standard`: motor sin cabeza LLM.
- `deterministic`: control local implementado.
- `adaptive`: el mismo motor con decisiones Bedrock.
- Inserción simple sin recargas: referencia interna de un inicio, con presupuesto
  blando de 1 s. No es equivalente a la capacidad ni al presupuesto del solver.

Las tres primeras usan exactamente el mismo presupuesto total de búsqueda,
incluido LLM, no tiempo adicional remoto.
La evidencia principal del LLM incluye **todas** las corridas asignadas a
`adaptive`. Separar las efectivas es útil para diagnóstico, pero seleccionar solo
las que funcionaron introduce sesgo. No atribuir una mejora a llamadas que solo
cambian la explicación textual.

## Qué crece y qué se somete a estrés

La red de calles permanece completa. Para añadir demanda se promueven
intersecciones distintas con ida y vuelta al depósito; se conservan clientes
originales, cargadores y arcos. No se duplican coordenadas de clientes para
inflar el tamaño. Las semillas de escenario crean distribuciones diferentes y
las semillas del solver miden variación de búsqueda: son conceptos separados.
La escala reportada es **demanda/flota sobre una geografía fija**. Para medir
crecimiento de red o generalización, ejecutar el mismo script con otros
snapshots viales en directorios separados.

Las cuatro sensibilidades predeterminadas reoptimizan con consumo +25%,
capacidad útil al 80% manteniendo reserva absoluta, SoC inicial 40% o la mitad
de cargadores compatibles deshabilitados (redondeo hacia arriba). Son hipótesis
del experimento; no exigencias oficiales ni pruebas probabilísticas.
No prueban que la ruta original aguante esas perturbaciones sin replanificar.

`--scenarios config/benchmark-scenarios.example.json` agrega jornada de 4 horas
y reserva final 20%. Sus tiempos de servicio, velocidad, potencia y eficiencia
son ilustrativos. Se recalcula la preparación desde calles originales:
una jornada puede exigir perfiles y retener muchas intersecciones. No se
reutiliza silenciosamente un único camino Dijkstra si deja de ser suficiente.

Regeneración, saturación, ventanas y recarga repetida tienen pruebas pequeñas en
el repositorio. No extrapolar su existencia a mediciones de velocidad a gran
escala. Los snapshots actuales de OSM con estimador por distancia no contienen
regeneración observada.

El script no lee los resultados de `evaluation` ni ajusta políticas con ellos.
Solo se usa el CSV suministrado para comprobar la procedencia de la red.

## Cómo leer el informe

- `report.md`: tabla y condiciones para usar cifras en diapositivas.
- `runs.csv` / `runs.json`: todas las corridas, incluso fallos, estados, cotas
  por fase, gap, tiempo total, entregas, energía, distancia, reserva, recargas y LLM.
- `summary.csv`: conteo factible, mediana y máximo de tiempos, rango de
  cumplimiento, energía mediana y número de óptimos exactos. La energía mediana
  no es una comparación válida si cambian las entregas.
- `paired.csv` y `paired-summary.csv`: diferencias, victorias/empates/derrotas,
  rangos y medianas de comparaciones pareadas. Se conservan empeoramientos.
- `cases/*/preparation.json`: configuración física, representación, tamaños,
  tiempo de lectura, construcción de escenario, preprocesamiento y serialización.
- `cases/*/greedy.json`: solución y auditoría de la referencia simple.
- `runs/*/result.json`, `execution.json`, `process.log`, `native/`: evidencia
  íntegra y rutas para verificar los agregados.
- `manifest.json`: commit, hash de fuentes/lockfile/entradas, versiones,
  plataforma, CPU disponible, recursos y plan congelado.

`resolution_seconds` incluye modelo y búsqueda; `pipeline_seconds` añade
validación y comprobaciones internas. `wall_seconds` añade arranque y lectura
del proceso. No sumarlos: son intervalos contenidos. `cold_total_seconds` añade
preparación medida una vez al tiempo de cada ejecución. Es una composición de
mediciones, no múltiples preparaciones independientes en frío.

`certified_speedup` requiere máximo de entregas probado y ambas energías
certificadas dentro del gap objetivo. No se interpreta un timeout que termina
antes como aceleración. Energía se compara solo al mismo número de entregas.
Para comparar rutas parciales por impacto de transporte, además se necesitaría
igual conjunto de demanda, no solo igual cantidad.
Un piloto con pocas semillas es descriptivo; no demuestra significancia,
generalización ni un factor universal de aceleración.

## CO₂ defendible

El ejemplo usa **2,689271493 kg CO₂/L**: EPA informa 10.180 g por galón
estadounidense, dividido por 3,785411784 L. La fuente fue revisada para este
trabajo; la página indica actualización de 3 de junio de 2026:
https://www.epa.gov/greenvehicles/greenhouse-gas-emissions-typical-passenger-vehicle

El ejemplo **supone** 8 L/100 km para un diésel que recorre exactamente los
mismos kilómetros y entregas. No es consumo medido de una flota CASE.

`tailpipe_co2_avoided_kg = distance_km × diesel_litres_per_100km / 100 × diesel_kg_co2_per_litre`

Esto cuantifica un escenario de electrificación y escape, no el beneficio del
algoritmo ni emisiones de ciclo de vida. No titularlo “CO₂e ahorrado medido”.
EPA también distingue emisiones de escape de las asociadas a generar electricidad.

El factor de electricidad y eficiencia quedan vacíos. Si se aportan con
fuente, fecha y geografía, se estima:

`operational_co2_difference_kg = tailpipe_co2_avoided_kg − net_battery_energy_kwh / charging_efficiency × grid_kg_co2_per_kwh`

Incluye la electricidad necesaria para reponer la **carga inicial consumida**,
aunque no haya recarga durante la ruta. Mantiene ahorros negativos. Esta
diferencia tampoco incorpora fabricación ni cadena de suministro del diésel.
Factores CO₂e no deben introducirse en campos CO₂.
La proyección anual requiere `equivalent_route_days_per_year` explícito y
supone repetir íntegramente esa operación; no multiplicar otra vez por los
vehículos que ya están incluidos en el total de la flota.

## Competidores y literatura

Para otro equipo, compartir `cases/<id>/instance.json` y solicitar:

```json
{
  "method": "Nombre y versión del método",
  "instance_sha256": "valor de preparation.json",
  "wall_seconds": 12.34,
  "solution": {"routes": [], "served_visit_ids": [], "unserved_visit_ids": [], "net_energy_kwh": 0}
}
```

El objeto `solution` debe cumplir el contrato `Solution` de Python.
Se puede extraer de `result.json["solve"]["solution"]`. Validar con:

```bash
bash scripts/benchmark_evidence.sh validate-external \
  --case-dir artifacts/evidence-pilot/cases/base \
  --result artifacts/competitor.json \
  --output artifacts/competitor-audit.json
```

Se vuelven a comprobar restricciones físicas y calles, se recalculan KPIs y se
ignora la afirmación de optimalidad del tercero. Su tiempo sigue marcado como
declarado; para una comparación temporal controlada debe ejecutarse en la misma
máquina y registrar proceso, versiones, hilos y presupuesto.

La familia de Schneider, Stenger y Goeke incluye ventanas y capacidad de carga,
ausente en nuestro modelo. No comparar directamente sus mejores valores
publicados con nuestros objetivos de entregas/energía ni afirmar superar a la
competencia. Fuentes primarias revisadas:

- Artículo: https://pubsonline.informs.org/doi/10.1287/trsc.2013.0490
- Instancias publicadas por Goeke: https://data.mendeley.com/datasets/h3mrm5dhxw/1

Un adaptador de esas instancias necesitaría respetar esa semántica y sus
objetivos. La campaña actual mide las políticas internas y permite auditar
soluciones externas del **mismo** problema CASE; no reproduce aquel benchmark.
