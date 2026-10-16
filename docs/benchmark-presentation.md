# Benchmark para la presentación

`scripts/benchmark_presentation.sh` prepara redes sintéticas, valida un testigo
independiente que no recibe el solver, ejecuta un piloto local y congela su mejor
política. Después compara nuevas semillas con `standard`, `fixed`, `rules` y
`adaptive` (Bedrock). `--ablation` añade AWS sin propuestas de rutas ni cambios al
portafolio nuevo. Todas usan la misma física, presupuesto y gap energético 0,5%.
En macOS el script mantiene el computador despierto con `caffeinate`.
AWS y su ablación parten de `standard`; `fixed` y `rules` conservan la política
seleccionada por el piloto. `--adaptive-start fixed` permite medir la adaptación
sobre esa política ya ajustada. La configuración inicial queda en el manifiesto.

```bash
bash scripts/benchmark_presentation.sh plan
bash scripts/benchmark_presentation.sh run --tee
```

Para una campaña pequeña del flujo completo:

```bash
bash scripts/benchmark_presentation.sh run \
  --customers 16 --families dispatch --test-seeds 1000 \
  --time-limit-seconds 45 --output-dir artifacts/presentation-small --tee
```

Para repetir una campaña interrumpida, añadir `--resume` con el mismo código y
opciones. Los resultados se guardan después de cada corrida; un fallo permanece
en el denominador. El informe se puede recalcular sin llamar AWS:

```bash
bash scripts/benchmark_presentation.sh report \
  --output-dir artifacts/presentation-small --impact config/presentation-impact.json
```

## Qué hace el LLM

Además del tuning y los callbacks existentes, recibe matrices dirigidas de
energía/tiempo mínimo, o un resumen de grupos y vecinos si la instancia es grande.
Esas distancias son orientativas: sus caminos pueden ser distintos y no incorporan
todos los recursos. El contexto no contiene el testigo, la semilla generadora ni
una solución futura.

Puede proponer `route_orders`: clientes ordenados por vehículo. El motor rechaza
IDs desconocidos y duplicados, calcula calles/recargas con recursos continuos y
valida la flota. Solo mejora el incumbente en orden lexicográfico. La propuesta
jamás fija variables, elimina columnas ni acredita una cota.

Puede activar un portafolio de reconstrucción completa: `nearest`, `deadline`,
`energy_blocks` o `window_blocks`. Los dos últimos agrupan clientes con un árbol
de expansión mínima de energía, ensayan órdenes de grupos y particiones de flota;
`window_blocks` ordena plazos e inserta clientes flexibles. `rebuild_seconds`
consume el presupuesto existente. Los límites de candidatos pertenecen a la
heurística; el pricing exacto conserva su espacio.

`electric_local` parte del incumbente factible: invierte segmentos con costes
dirigidos, recoloca clientes e intercambia colas entre vehículos. Cada cambio
se repara y valida; nunca reduce las entregas para aparentar ahorro. El callback
`first_full_service` permite dedicar una consulta reservada a la fase energética.
El contexto conserva el mejor incumbente observado aunque otro arranque sea peor.
El aviso se emite al descubrir cobertura completa. Si la primera consulta
todavía no responde, se guarda el evento para el siguiente callback disponible.
Una mejora eléctrica interrumpida puede continuar en otro tramo; el presupuesto
temporal sigue vigente. `rebuild_seconds` limita trabajo dentro del tramo de
heurística, no añade segundos al presupuesto de resolución.

`window_waves` asigna zonas a vehículos, ordena primero los clientes con ventana
estrecha y luego inserta los flexibles mediante reparación física. Permite
volver a la misma zona. El preset local `waves` ofrece esta construcción sin
LLM y evita gastar tiempo en el arranque genérico. Las reglas locales también
pueden activarla y cambiar a `electric_local` cuando completan las entregas.

Los presets locales `blocks` y `windows` ofrecen las mismas reconstrucciones
sin LLM, y participan en el piloto. Esto permite medir cuánto de la mejora viene
de disponer de la heurística y cuánto de seleccionarla mediante AWS.
El preset `electric` ofrece también la búsqueda local eléctrica sin LLM.
En campañas desatendidas, un preset que falle en cualquier caso queda excluido
de la selección fija. Sus corridas y fallos se conservan; no se eliminan de las
tablas ni del denominador. Si todos fallan, la campaña se detiene.

## Archivos

- `pilot/selected-policy.json`: política fija y semillas de desarrollo.
- `comparison/summary.csv`: KPIs y tiempos individuales.
- `comparison/runs/*/result.json`: solución, validación vial y certificados.
- `comparison/runs/*/process.log`: SCIP y trazas del LLM.
- `comparison/runs/*/logs/decisions/*`: solicitudes y respuestas reales de AWS.
- `presentation/kpis.csv`: energía, kilómetros, CO₂ y facturas estimadas.
- `presentation/paired-impact.csv`: deltas firmados contra cada referencia.
- `presentation/llm-impact.csv`: ganancias, pérdidas, empates e intervalos.
- `presentation/diapositivas.md`: tablas y alcance listos para revisar.

## Interpretación

Se comparan ahorros únicamente para el mismo conjunto de clientes. El tiempo
hasta completar entregas se separa del tiempo para certificar energía. Dos
timeouts no acreditan una aceleración. Los intervalos agrupan repeticiones por
instancia; no transforman una demostración dirigida en evidencia general.

`config/presentation-impact.json` guarda fuentes, fechas y supuestos de Michigan
en USD. El consumo eléctrico repone también la carga inicial. La electrificación
se calcula contra diésel hipotético sobre la misma ruta; no se atribuye al LLM.
El dinero neto resta inferencia estimada con tokens reales y tarifas documentadas
de AWS. Un coste desconocido queda ND, nunca cero. No se cuantifican emisiones
del centro de datos ni ciclo de vida.
El desglose conserva entrada sin caché, escritura, lectura y salida. Las
tarifas de caché del modelo se aplican por separado; no se ignoran prefijos
grandes porque `inputTokens` reporte únicamente la parte no almacenada.

La presentación oficial fija entregas factibles, consumo y tiempo como KPIs
(diapositivas 5–7). El CO₂ y los USD son escenarios adicionales, no reglas del
concurso. Los datos `evaluation` pueden resolverse con código congelado, pero no
se usan para seleccionar heurísticas.

La selección por características y el portafolio se apoyan conceptualmente en
Ropke y Pisinger (2006), DOI `10.1287/trsc.1050.0135`, y Zhang et al. (2025),
arXiv `2506.00490`. La reparación eléctrica conserva el marco de recursos del
proyecto; no ejecuta código generado por el LLM ni reproduce los experimentos de
esos artículos.
