# Benchmark sintético del control con LLM

El script `scripts/benchmark_llm.sh` genera redes eléctricas, prepara el grafo de
pricing y compara políticas del mismo motor `scip-routes`. El objetivo es medir
si el LLM mejora la búsqueda contando su costo de ejecución. Generar casos
difíciles no garantiza que el LLM gane.

## Instancias

Cada instancia tiene dos vehículos, cuatro zonas de clientes y ocho cargadores.
Los consumos, tiempos y potencias son sintéticos. No son datos del concurso ni
estimaciones obtenidas de `evaluation`.

- Batería de 24 kWh, SoC inicial de 60 % y reserva de 2,4 kWh.
- Consumo positivo distinto por arco, recarga parcial y tiempos de recarga.
- Dos alternativas entre zonas: una rápida que consume más y otra lenta que
  consume menos. El preprocesamiento conserva las alternativas necesarias.
- Ventanas de servicio y jornada finita. El depósito no permite cargar.
- Sin regeneración, colas, capacidad de paquetes ni ocupación compartida de
  cargadores en esta primera familia de pruebas.

El generador admite entre 4 y 200 clientes y tres familias:

| Familia | Construcción |
|---|---|
| `loose` | Ventanas amplias, como referencia menos restrictiva. |
| `clustered` | Clientes agrupados; aproximadamente 30 % con ventanas estrechas. |
| `crossed` | Las ventanas se construyen desde recorridos que alternan zonas; aproximadamente 50 % son estrechas. |

Se construye y valida independientemente un recorrido que atiende a todos los
clientes. Las ventanas dejan margen alrededor de su calendario. Esto acredita
que la instancia tiene solución completa; no acredita energía óptima ni obliga
al solver a seguir ese recorrido. Se guarda en `witness-audit.json`, separado:
**el solver y el LLM reciben solamente la instancia, su red original y el
archivo de caminos, sin un arranque derivado del testigo**.

## Piloto y comparación

El piloto no llama a AWS. Compara tres configuraciones declaradas en
`synthetic_benchmark.py::PRESETS`: estándar, mayor esfuerzo en construcción de
soluciones (`primal`) y mayor esfuerzo en pricing (`pricing`).

Congela una configuración con este criterio lexicográfico:

1. Mayor proporción de corridas que completan las entregas dentro del presupuesto.
2. Menor fracción promedio de clientes sin atender.
3. Menor tiempo promedio hasta completar las entregas, asignando dos veces el
   presupuesto a cada fracaso —criterio PAR2—.

Un empate favorece la configuración estándar. Si ninguna corrida termina todas
las entregas, el script lo advierte; la selección no demuestra que el caso sea
adecuado para evaluar tiempo hasta cumplimiento completo. Revise el piloto antes
de lanzar una comparación grande. Un error de ejecución impide congelar una
política.

La evaluación usa nuevas semillas y rechaza instancias usadas en el piloto.
Compara:

| Modo | Política |
|---|---|
| `standard` | Configuración actual del motor, sin control remoto. |
| `fixed` | Configuración congelada por el piloto. |
| `rules` | Parte de `fixed`; reglas locales priorizan clientes urgentes y caminos rápidos mientras faltan entregas, y energía después de completarlas. |
| `adaptive` | Parte de `fixed`; el LLM puede revisar la política mediante los eventos y callbacks ya implementados. |

Todos conservan ALNS, búsqueda memética, pricing exacto y validación del motor.
`fixed` fija los parámetros del controlador; no desactiva la adaptación interna
propia de ALNS. Las reglas locales no simulan respuestas de un LLM ni inicializan
Bedrock. Sus cambios se registran aparte en `tuning.local_decisions`.

Se ejecutan procesos separados, con el mismo número de hilos, presupuesto,
semilla del solver, objetivo, batería y gap energético de **0,5 %**. El orden de
los modos se baraja de forma reproducible. La referencia principal de la
comparación es `fixed`, para distinguir el efecto del LLM del de ajustar
parámetros una sola vez.

## Ejecución corta

Desde la raíz del repositorio, este piloto tiene tres corridas de hasta 60 s:

```bash
bash scripts/benchmark_llm.sh pilot \
  --customers 16 --families clustered \
  --instance-seeds 0 --solver-seeds 0 \
  --time-limit-seconds 60 \
  --output-dir artifacts/llm-pilot \
  2>&1 | distill "Resume las tres corridas, sus entregas y la política elegida."
```

La evaluación siguiente tiene cuatro corridas de hasta 120 s y **como máximo
dos llamadas reales a Bedrock**, solamente en `adaptive`:

```bash
bash scripts/benchmark_llm.sh compare \
  --fixed-policy artifacts/llm-pilot/selected-policy.json \
  --customers 16 --families clustered \
  --instance-seeds 100 --solver-seeds 0 \
  --time-limit-seconds 120 \
  --aws-profile hackathon --aws-region us-east-1 \
  --bedrock-model us.openai.gpt-5.6-luna \
  --llm-max-calls 2 --llm-timeout-seconds 8 \
  --tee --output-dir artifacts/llm-comparison \
  2>&1 | distill "Compara entregas, energía, gap y tiempo; indica decisiones LLM aplicadas y fallbacks."
```

El script resuelve las rutas relativas desde la raíz de **su propio checkout**.
También puede invocarse con su ruta absoluta desde cualquier directorio.
`uv run --locked --extra dw` prepara el entorno desde el lockfile.
Las credenciales AWS deben estar configuradas externamente; no se guardan.

El modelo predeterminado es el de la configuración del proyecto,
`us.openai.gpt-5.6-luna`, con esfuerzo `low`. `BEDROCK_MODEL_ID` o
`--bedrock-model` permiten cambiarlo. La validación local del benchmark no
acredita disponibilidad ni acceso actual al modelo.

Una instancia y una semilla sirven para comprobar el flujo, no para afirmar una
mejora significativa. Para ampliar el ensayo, aumente `--customers`, familias,
semillas de instancia y semillas del solver. Use semillas de desarrollo, por
ejemplo `0 1`, y semillas de prueba distintas, por ejemplo `100 101 102`.
Seleccione tamaños y presupuesto mirando **solamente el piloto**; no descarte
instancias de prueba porque el LLM pierde.

## Presupuestos y reanudación

- `--time-limit-seconds`: presupuesto común del solver, incluyendo la
  coordinación con el LLM. Es un límite blando en operaciones indivisibles.
- `--energy-relative-gap`: criterio energético; predeterminado `0.005`.
- `--threads`: hilos del solver y bibliotecas numéricas; predeterminado 1.
- `--llm-max-calls`: máximo de solicitudes por corrida adaptativa; predeterminado 2.
- `--llm-timeout-seconds`: plazo de cada decisión remota; predeterminado 8.
- `--llm-time-fraction`: fracción reservada a inferencia; predeterminado 0.25.
- `--process-grace-seconds`: margen del supervisor, adicional al presupuesto;
  predeterminado 20. Al agotarse termina el proceso y registra el fallo.
- `--preprocessing-seconds`: presupuesto de compresión de la red; predeterminado
  5. Conservar una intersección evita recortar caminos por agotar ese presupuesto.

`--dry-run` genera y valida las instancias e imprime número de corridas,
presupuesto agregado y máximo de llamadas. No resuelve ni consulta al LLM.
Para ejecutar después, repita el comando quitando `--dry-run` y agregando
`--resume`.

`--resume` conserva las corridas terminadas y verifica hashes de entradas,
resultados, configuración y código. También conserva los fallos: no repite
selectivamente resultados malos. Una interrupción sin registro de finalización
puede repetir esa corrida y sus llamadas. Use una salida nueva si cambia código
u opciones. Un cambio de código exige repetir el piloto.

Se puede usar `generate` para preparar sin resolver y
`compare --policies standard fixed rules` para evaluar sin AWS.

## Resultados, tiempos y respuestas del LLM

La carpeta de salida contiene:

| Archivo | Contenido |
|---|---|
| `manifest.json`, `plan.json`, `cases.json` | Código, versiones, opciones, orden de ejecución y hashes. |
| `selected-policy.json` | Selección congelada; solamente en el piloto. |
| `summary.csv`, `summary.json` | Una fila por corrida, incluidos fallos y fallbacks. |
| `comparisons.json`, `report.md` | Comparación pareada, tasas de éxito, PAR2 y diferencias de energía con iguales entregas. |
| `runs/*/process.log` | Log completo del proceso, incluido SCIP y las trazas LLM. |
| `runs/*/result.json` | Rutas, certificados por fase, validación y decisiones del controlador. |
| `runs/*/logs/llm-decision.json` | Decisiones solicitadas, aplicadas, rechazadas y cambios efectivos. |
| `runs/*/logs/decisions/` | Solicitudes y respuestas remotas registradas por el cliente Bedrock. |
| `runs/*/logs/*.mps` | Maestros restringidos; no contienen todas las rutas futuras. |

`--tee` también muestra los logs en vivo. `distill` resume la salida visible;
los archivos conservan el texto completo. El LLM recibe el contexto físico y
el catálogo de acciones implementadas. Si la instancia excede
`--instance-context-bytes` —24 000 por defecto— se declara el recorte y se guarda
el grafo completo localmente.

`first_full_delivery_solver_seconds` es la primera observación del motor de una
solución completa. No reconstruye eventos dentro de una operación indivisible.
Se informa por separado si ocurrió dentro del presupuesto.

`process_wall_seconds` incluye arranque del proceso, lectura, solver,
coordinación/inferencia, validación y escritura. La inferencia puede solaparse
con la búsqueda: **no se suma otra vez** al tiempo total. La preparación se mide
una vez por instancia y se comparte entre modos. `cold_pipeline_estimate_seconds`
es su suma con el tiempo del proceso: una estimación comparable del flujo desde
la red sintética sin preparar, no una repetición real en frío de cada modo.
Generar el dataset y validar su testigo se mide aparte.

El objetivo energético se considera alcanzado solo con todas las entregas,
validación sobre la red original y una cota global finita que satisface el gap.
El tiempo asociado es la finalización con ese gap, no su primer instante exacto.
Nunca se toma la cota de un maestro restringido como cota del problema completo.

Los speedups del gap se calculan solo en éxitos conjuntos, con intervalos
bootstrap por instancia cuando hay al menos dos. Deben leerse junto a las tasas
de éxito y PAR2, que conservan los timeouts. Un fallback sigue en el grupo
`adaptive`; `llm_algorithm_changes` permite saber si realmente cambió la búsqueda.
Sin varias instancias de prueba ni una comparación favorable, no hay evidencia
de una aceleración general.
