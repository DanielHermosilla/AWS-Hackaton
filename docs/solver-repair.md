# Reparación del solver: cobertura, energía y control LLM

Auditoría del 16 de octubre de 2026, en `codex/benchmark-llm`.
La referencia anterior es el commit `758e016`. Las mediciones siguientes usan
instancias sintéticas con dos vehículos y ocho cargadores, no la red del concurso.
No se cambia la formulación física, el preprocesamiento ni el objetivo
lexicográfico del PDF.

## Por qué faltaban entregas

En la corrida original `clustered`, 16 clientes, semilla 100, había una solución
independientemente validada de **16 entregas y 54,227844 kWh**. El solver estándar
terminó con 13 entregas después de 120 s; las políticas fija, local y adaptativa
terminaron con 12. El testigo confirma factibilidad, no energía óptima, y nunca
se entregó como arranque al solver ni al LLM.

Los problemas encontrados fueron concretos:

1. **Construcción sin prioridad temporal.** La extensión por vecinos cercanos
   llenaba rutas con clientes flexibles y dejaba para después ventanas que ya
   habían cerrado. Esto no demostraba que los clientes fueran incompatibles.
2. **Reparación demasiado cara por intento.** Cada inserción podía explorar
   etiquetas con recursos continuos, aunque un calendario optimista bastara
   para rechazarla o un pequeño LP bastara para construirla.
3. **Destrucción antes de completar.** ALNS podía gastar su etapa desarmando una
   buena solución parcial sin intentar primero insertar los clientes pendientes.
4. **Pérdida de entregas en la fase energética.** La reparación de un tour
   relajado podía devolver una solución parcial y aceptarse solamente por
   consumir menos. Se observó una ejecución que pasó de 24 a 17 entregas, con
   una cota energética mayor que el incumbente final. Era un error, no un
   intercambio admisible entre objetivos.
5. **Telemetría y decisiones tardías.** Algunas salidas anticipadas de SCIP no
   registraban el tiempo hasta servicio completo. Además, una respuesta LLM
   podía figurar como cambio de arranque cuando ese arranque ya había terminado.
   Con dos consultas, ambas se gastaban antes de observar el pricing nativo.

El log también mostraba pricing incompleto en la raíz. Cambiar la selección de
nodos de un árbol que todavía no se desarrolla no resuelve ese cuello de botella.
Más columnas o un incumbente mejor tampoco prueban optimalidad energética.

## Cambios

### Construcción de rutas

- Con ventanas, insertar primero cierres próximos, examinando posiciones en
  todos los vehículos. Alternar con arranques por proximidad.
- Antes de reparar, calcular un calendario optimista con tiempos mínimos,
  espera y servicio. Rechazar únicamente órdenes temporalmente imposibles.
- Probar caminos candidatos de energía y tiempo con `FixedPathRepair`.
  El LP ajusta recargas parciales y horarios. Toda propuesta se reconstruye y
  valida físicamente antes de entrar al pool.
- Si esa reparación falla, conservar `SequenceOracle`, que busca caminos,
  cargadores y recargas en el multigrafo completo. Un fallo del LP o timeout
  heurístico no elimina una ruta del pricing exacto.
- Intentar completar el incumbente antes de destruirlo. Mantener ALNS,
  población memética y recombinación con SCIP.
- Subir los presupuestos iniciales predeterminados de 6 % a **15 %** para
  construcción y de 12 % a **20 %** para mejora. Son asignaciones del mismo
  presupuesto global; las opciones explícitas siguen prevaleciendo.

En un camino fijo, si \(E_i\) es el consumo acumulado hasta la posición \(i\),
el LP usa

\[
b_i^{\mathrm{salida}}
 = b_{\mathrm{inicial}}-E_i+\sum_{j\le i}q_j,
\qquad q_j\ge0.
\]

Solo hay \(q_j\) en paradas de carga compatibles. Se imponen capacidad, reserva,
requisitos intermedios de cada perfil de batería, tiempos, ventanas y reserva
final. Para un perfil agregado
\(b'=\min(b-e,\overline b)\), este LP prueba la rama sin saturación, mediante
\(b\le\overline b+e\). Las demás posibilidades permanecen en el oráculo general.
El LP no se usa con energías netas negativas ni produce certificados globales.

### Conservación de objetivos y cotas

La reparación energética solo sustituye al incumbente si conserva su número
de entregas y reduce energía. La partición del tour ahora distribuye segmentos
entre vehículos; no intenta obligatoriamente atender todo con uno solo.
Una llamada que recibe un tour concreto no lo reemplaza por un arranque parcial
sin relación.

Si una heurística posterior encuentra más entregas, se actualiza también el
resultado de la fase de cobertura y se descarta la cota energética condicionada
al cumplimiento anterior. El informe rechaza una cota inferior mayor que el
incumbente energético o una cota superior menor que las entregas validadas.
Conserva la solución, pero no emite un certificado con esa cota.

El pricing exacto añade dos descartes necesarios:

- Llegar demasiado tarde para completar un orden o alcanzar un cliente antes
  de su cierre, usando tiempos mínimos sin recarga.
- No tener energía suficiente para llegar a ninguna estación compatible ni
  al depósito, solo con costes no negativos.

La cota de costo reducido omite los premios duales positivos que ya no pueden
obtenerse por tiempo. Sigue siendo optimista e incluye los cortes según el
signo de su dual. No hay H, discretización de batería, límite de etiquetas ni
certificado basado en una consulta interrumpida.

### LLM

Los parámetros consumidos se registran en `locked_policy_fields`; las etapas
terminadas, en `finished_stages`. Una sugerencia tardía queda en
`inactive_settings` y no cuenta como modificación efectiva.
`unsupported_policy_fields` también excluye controles de adaptadores que la
instancia no utiliza: los de búsqueda local heredada no gobiernan el ALNS con
recursos.

Con dos llamadas y una primera respuesta aplicada, la última se reserva para
`search_stagnation`. Recibe etiquetas del pricing por dual, consultas exactas
completadas, descartes, reparaciones, cota, incumbente y tiempo hasta cubrir
todos los clientes. El prompt explica las nuevas heurísticas y pide cambios
concretos según ese diagnóstico. Se mantienen límites de tiempo, llamadas,
tokens y validación; el LLM no modifica la física ni certifica soluciones.

## Comparación entre versiones

Misma semilla de instancia **101**, semilla del solver **0**, un hilo,
presupuesto **20 s por caso**, política `standard`, sin LLM. La semilla 101 se
usó durante el desarrollo; esta tabla es una regresión comparada, no una prueba
estadística sobre instancias no vistas.

| Familia | Clientes | Antes: entregas finales | Ahora: entregas finales | Primera cobertura completa | Gap energético final |
|---|---:|---:|---:|---:|---:|
| `clustered` | 16 | 15 | 16 | 2,493 s | 15,04 % |
| `clustered` | 24 | 21 | 24 | 4,217 s | 15,53 % |
| `clustered` | 40 | 12 | 40 | 4,110 s | 14,93 % |
| `crossed` | 16 | 11 | 16 | 1,210 s | 49,97 % |
| `crossed` | 24 | 17 | 24 | 2,199 s | 38,74 % |
| `crossed` | 40 | 12 | 40 | 5,443 s | 53,78 % |

Cobertura acumulada: **88/160 → 160/160**; casos completos: **0/6 → 6/6**.
Todas las soluciones pasan la expansión y validación sobre la red sintética
original. Alcanzar todos los clientes prueba el máximo de entregas por la cota
cardinal. **Ninguno de estos seis casos alcanza el gap energético de 0,5 %.**
Los tiempos de la tabla no son tiempos hasta optimalidad energética; el solver
continúa usando el presupuesto para mejorarla.

Los artefactos locales, ignorados por Git, conservan resultados, logs, versiones
y hashes:

- `artifacts/solver-repair-final-before/`: referencia `758e016`, seis corridas.
- `artifacts/solver-repair-verified-after/`: código corregido, seis corridas.
- `artifacts/solver-repair-sources/v7/`: copia exacta del código medido.
- `artifacts/solver-repair-sources/v8/`: versión final; añade el filtro de
  controles LLM heredados no disponibles, sin modificar los algoritmos numéricos.
- `artifacts/solver-repair-final-after/`: ejecución intermedia que permitió
  detectar la pérdida de entregas; se conserva como diagnóstico.

No se compara energía entre versiones que atienden distinto número de clientes.
Tampoco se atribuye esta mejora al LLM: las doce corridas de la tabla no lo usan.
Se comprobó igualdad de nodos, arcos, perfiles, flota y operaciones entre cada
par. Los hashes de snapshot compacto difieren por la procedencia, que incluye
el tiempo de preparación; el contenido del modelo es idéntico.

### Instancia original y semilla nueva

Con el código final, la instancia original de 16 clientes, semilla 100, alcanza
**16/16 a los 1,151 s**, sin LLM. Termina el presupuesto de 20 s con 62,751289 kWh,
cota 43,225293 kWh y gap 31,12 %. Su validación vial pasa. La corrida antigua
había terminado en 13/16 después de 120 s; estos dos tiempos son presupuestos
distintos y no constituyen una razón de aceleración pareada.

Después de congelar el código se probaron dos casos de 40 clientes, semilla
**202**, sin usar sus resultados para ajustar el método:

| Familia | Entregas finales en 20 s | Primera cobertura completa | Gap energético |
|---|---:|---:|---:|
| `clustered` | 39/40 | No alcanzada | 100 %, condicionado a 39 entregas |
| `crossed` | 40/40 | 4,572 s | 52,02 % |

Ambos pasan validación vial. El caso 39/40 sigue siendo una limitación de la
búsqueda bajo ese presupuesto, pues el testigo separado del generador atiende
40/40. No se descarta este caso ni se afirma éxito universal.
Resultados: `artifacts/solver-repair-original/` y
`artifacts/solver-repair-holdout/`.

### Comparación final con LLM real

Código final `v8`, misma instancia original, un hilo, semilla 0, **60 s en ambos
modos**, sin arranque externo. Ejecuciones secuenciales, estándar y después
adaptativa. Es un solo par, no una evaluación estadística.

| Modo | Entregas | Primera cobertura completa | Energía | Gap | Tiempo del solver |
|---|---:|---:|---:|---:|---:|
| Sin LLM | 16/16 | 1,194 s | 62,678266 kWh | 31,036 % | 60,009 s |
| Con LLM | 16/16 | 1,315 s | 62,735580 kWh | 31,099 % | 60,008 s |

Ambos usan la cota global 43,225293 kWh y pasan validación vial.
**En este par, el LLM no mejora la solución:** consume 0,057314 kWh más
para las mismas entregas, aproximadamente 0,09 %. La diferencia de una sola
ejecución no demuestra una desventaja general.

Se usó `us.openai.gpt-5.6-luna`, esfuerzo `low`, por Bedrock en
`hackathon`/`us-east-1`. Hubo dos consultas reales, ambas aplicadas, sin errores
de callbacks. La inferencia acumuló **9,145 s**, solapados con la búsqueda;
no se suman al tiempo del solver. El tiempo completo del proceso fue
60,962 s sin LLM y 61,041 s con LLM.

1. **Primera respuesta, aplicada a los 5,555 s del controlador.** Subió columnas
   por ronda de 50 a 100, esfuerzo de reparación de 0,04 a 0,08 s, heurísticas
   de pricing de 0,15 a 0,30 s; priorizó caminos por tiempo y acortó épocas
   de 12 a 8 s. Los cambios sugeridos para el arranque ya terminado se
   registraron como inactivos.
2. **Segunda respuesta, `search_stagnation`, aplicada a los 26,871 s.**
   Al observar tres consultas exactas sin completar y 275 reparaciones
   agotadas por tiempo, desactivó la fase heurística previa al pricing exacto,
   alargó épocas de 8 a 15 s, subió columnas de 100 a 150 y redujo la
   recombinación restringida de 0,5 a 0,1 s. Los callbacks registraron la
   revisión 2 durante la búsqueda.

La cobertura completa apareció **antes de la primera respuesta**. En este caso
la mejora de entregas procede del solver corregido, no del LLM.
Su explicación textual también confundió una diferencia de unos 19,6 kWh con
un porcentaje; los gaps de la tabla los calcula el solver, no esa explicación.
Se conservan las respuestas originales para auditar tanto aciertos como errores.

Artefactos: `artifacts/solver-repair-final-pair/manifest.json`,
`standard/result.json`, `adaptive/result.json` y
`adaptive/logs/decisions/`. El manifiesto guarda comandos, hashes de entradas,
hash de código, tiempos y retornos de ambos procesos.

## Reproducir

Desde este checkout:

```bash
bash scripts/benchmark_llm.sh pilot \
  --customers 16 24 40 --families clustered crossed \
  --instance-seeds 101 --solver-seeds 0 --policies standard \
  --time-limit-seconds 20 --tee \
  --output-dir artifacts/solver-repair-check \
  2>&1 | distill "Resume entregas, primer servicio completo, energía, gap y errores."
```

Ese comando tiene seis corridas, ninguna llamada AWS. Para comparar las cuatro
políticas, repetir primero el piloto completo en una carpeta nueva y seguir
[la guía del benchmark](benchmark-llm.md). Un piloto anterior a estos cambios
no se reutiliza: su hash de código ya no coincide.

## Alcance de la validación

Las regresiones contrastan pricing con enumeración exhaustiva en casos pequeños,
incluyendo regeneración y duales de ambos signos. Cubren recargas parciales
repetidas, ventanas, fallback a desvíos que el LP no considera, reparto entre
vehículos, conservación de entregas, rechazo de cotas incompatibles, respuestas
LLM tardías y tiempos de servicio completo obtenidos por SCIP.
La suite completa pasó **759 pruebas y 37 subtests**, con
`uv run --locked --extra dw pytest -q`; Ruff y `git diff --check` también pasaron.

La construcción ahora encuentra rápido las soluciones completas de los casos
comparados. Cerrar el gap energético sigue requiriendo mejor búsqueda primal y
cotas: el pricing con recursos continuos puede agotar el presupuesto en la raíz.
Estos resultados no acreditan una aceleración general, un óptimo energético ni
una ventaja causal del LLM.
