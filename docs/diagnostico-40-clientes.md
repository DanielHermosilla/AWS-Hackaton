# Diagnóstico del ensayo con 40 clientes y 60 cargadores

Fecha: 15 de octubre de 2026. Los 40 clientes incluyen los 20 originales y
20 ubicaciones sintéticas de la red vial, con semilla 0. Se conservan los
60 cargadores, dos vehículos, batería, reserva y caminos de la instancia.
No se utilizaron resultados de `evaluation` para desarrollar estos cambios.

## Por qué se obtuvieron solo dos entregas

El resultado original está en
`artifacts/test-40c-60s/validation-seed0/result.json`:
2/40 entregas, 2,2094256171 kWh, rutas factibles, sin prueba de optimalidad.
Con 60 segundos y un hilo, la primera fase solo construyó seis columnas,
ejecutó cinco llamadas de pricing, dos de ellas Farkas, y expandió
740 etiquetas por vehículo. SCIP permaneció en un único nodo del árbol.
La fase energética terminó con 12 columnas y 1.034 etiquetas por vehículo.

La limitación dominante era la generación de rutas:

1. El oráculo recorría primero rutas cortas, en anchura. Con 101 servicios,
   las combinaciones de desplazamiento, servicio y carga crecen rápidamente.
   El coste reducido se comprobaba sobre las rutas encontradas; la exploración
   no se orientaba con los duales del maestro hacia rutas prometedoras.
2. Faltaba un arranque factible de toda la flota cuando no se certificaba la
   reducción a un único tour. El maestro debía descubrir esas rutas dentro
   del presupuesto. Una búsqueda que encuentra dos entregas no demuestra
   que solo dos entregas sean físicamente posibles.
3. La dominancia de recursos resolvía miles de LP diminutos mediante SciPy/HiGHS.
   Un perfil instrumental de ocho segundos registró 12.332 llamadas a `linprog`.
   Los parámetros de SCIP no controlan esos LP externos.
4. Nova Micro produjo una propuesta aceptada que no cambió ninguna de las
   opciones efectivas. El controlador exponía muy pocas decisiones.
   Cambiar branching o separación tampoco elimina por sí solo un atasco
   dentro del pricing de la raíz.

La reducción DFJ no se aplicó: la comprobación estricta de métrica detectó
diferencias de redondeo de hasta 4,44e-16 kWh. Además, el tour greedy completo
encontrado consumía 15,450716 kWh frente a 12 kWh utilizables sin cargar.
Este último dato es una cota superior de una heurística, **no una prueba**
de que sea imposible encontrar otro tour que quepa. No se relajó el
certificado ni se impuso un H para evitar el caso general.

## Cambios de implementación

- Arranques por inserción para toda la flota, comprobados por el validador
  independiente. Encontrar los 40 clientes prueba el máximo de entregas
  mediante la cota trivial 40; no prueba energía óptima.
- Pricing heurístico guiado por duales, seguido del oráculo exacto cuando
  no encuentra columnas. También se puede cambiar anchura por profundidad
  y elegir dominancia convexa o una prueba conservadora por vértices.
- Para una combinación de dos vértices, dominancia por intersección de
  intervalos y verificación del testigo, evitando un LP cuando puede
  comprobarse directamente. No se amplían tolerancias de factibilidad.
- Catálogo descubierto en SCIP 10.0.0: 3.082 parámetros nativos, de los cuales
  1.240 están disponibles para el maestro con pricing y 2.042 para DFJ.
  El LLM puede combinar parámetros concretos con presets nativos.
- Claude Opus 5 mediante Bedrock, con una única llamada estratégica y
  trazabilidad de prompt, respuesta, validación y parámetros aplicados.

Los arranques y el pricing por inserción aceleran exclusivamente el caso
no negativo y sin restricciones temporales; el oráculo general conserva
recargas parciales, regeneración, ventanas, estaciones repetidas y retornos.
Las heurísticas no restringen el conjunto de rutas del modelo ni certifican
la ausencia de una columna de coste reducido negativo.

Los límites globales, semillas, threads, tolerancias y criterios de prueba
no son ajustables por el LLM. En el maestro con pricing también permanecen
desactivadas las reducciones y la separación nativa cuya compatibilidad con
columnas futuras no está implementada. DFJ sí expone esas familias.
Modificar todos los parámetros indiscriminadamente no es una estrategia de
optimización ni una condición para considerar sustancial una decisión.

## Protocolo de comparación

Se reutiliza exactamente el snapshot de la corrida original. La huella
`instance_sha256` del JSON de resultados es:

```text
e2287297ccd049cff9a21f07ff2f2ca78413b9e8313e8709c046047043d37e20
```

Las políticas estándar y adaptativa comparten implementación, instancia,
un hilo, semilla 0 y presupuesto de 60 segundos. La llamada al LLM consume
ese presupuesto. Carga, validación y terminación del callback pueden hacer
que el tiempo de proceso supere ligeramente el límite blando.
La comparación con el motor anterior diagnostica el cambio de implementación;
la comparación estándar/adaptativa mide el efecto conjunto de la política
elegida y su coste de inferencia, no el efecto aislado de cada knob.

Los intentos previos se conservaron como fallbacks: Sonnet 5.5 fue denegado
por la política IAM de la cuenta; dos respuestas reales de Opus 5 fueron
rechazadas por formato, una explicación demasiado larga y un campo adicional
nulo. No se cambiaron permisos AWS. Esos ensayos no acreditan tuning efectivo.
La validación admite ahora explicaciones de hasta 6.000 caracteres y registra
anotaciones nulas sin acción, manteniendo el rechazo de acciones o parámetros
inválidos. No hay reintentos remotos automáticos.

El primer ensayo con una propuesta aplicada está en
`artifacts/tuning-diagnostics/comparison-opus5-applied/`. Opus 5 propuso
20 parámetros nativos y el preset `fast`: el estado efectivo de SCIP difirió
en 34 parámetros respecto del estándar. El pricing pasó de 8 a 1.040 columnas,
incluyendo 1.038 columnas heurísticas, pero la energía empeoró:
17,871695 kWh frente a 17,202666 kWh. La nueva estrategia de arranque fue peor
y el maestro no mejoró ese incumbente. Esto demuestra que más columnas y más
knobs modificados no garantizan un resultado mejor.

Se corrigió esa pérdida evitable: todas las políticas conservan el arranque
barato antes de inferencia. El LLM recibe su número de entregas y energía,
además del presupuesto restante; sus arranques adicionales solo reemplazan
una solución si la mejoran lexicográficamente. El presupuesto total de arranque
sigue siendo 0,5 segundos. La comparación final usa esta protección en ambas
políticas y conserva el ensayo anterior como evidencia.

## Resultado final verificado

Artefactos: `artifacts/tuning-diagnostics/comparison-opus5-final/`.
Código Python ejecutado, según el manifiesto:
`233a4c54e640c2fcade8d4cecb9a0e073d563e1ff6884b8198753f7a7130c019`.

| Medición | Estándar corregido | Opus 5 aplicado |
|---|---:|---:|
| Entregas | 40/40 | 40/40 |
| Energía, kWh | 17,2026658055 | 17,2026658055 |
| Validación sobre calles | Factible | Factible |
| Máximo de entregas probado | Sí | Sí |
| Mínimo energético probado | No | No |
| Columnas del maestro energético | 8 | 849 |
| Columnas de pricing heurístico | 0 | 847 |
| Llamadas de pricing | 4 | 87 |
| Tiempo nativo de optimización, s | 59,979 | 36,184 |
| Tiempo de LLM, s | 0 | 23,743 |
| Tiempo de proceso, s | 64,035 | 63,866 |

La propuesta eligió 14 parámetros nativos explícitos, un preset `fast`,
branching `mostinf`, selección de nodos, simplex dual, 24 ternas en vez de 100,
lotes de 150 columnas, inserción regret con ocho inicios, pricing heurístico
con 12 inicios y recorrido en profundidad. Comparando los valores efectivos
de **ambas** configuraciones, incluidos presets y la prioridad de branching
que vuelve al valor nativo, hay **33 parámetros SCIP distintos**.

Una llamada real a `us.anthropic.claude-opus-5`, región `us-east-1`, perfil
`hackathon`, consumió 17.105 tokens de entrada y 1.653 de salida: 18.758 en total.
La decisión se aplicó sin fallback ni llamadas remotas desde callbacks.
El arranque regret de 17,871695 kWh se conservó como candidato descartado;
el incumbente de 17,202666 kWh permaneció disponible.

**No se observó mejora de energía por el LLM en este ensayo.** El salto de
2 a 40 entregas corresponde a la corrección del arranque del motor.
El LLM sí cambió sustancialmente la búsqueda, pero el pricing siguió ocupando
casi todo el tiempo nativo y ambos maestros permanecieron en la raíz.
La cota energética sigue siendo 0, pues el pricing exacto quedó incompleto.
No se presenta el LP restringido como cota del problema completo.

Es una observación de una semilla en una máquina sin aislamiento de otros
procesos; no demuestra aceleración general ni una diferencia significativa
de tiempo de proceso. Harían falta réplicas controladas para esa afirmación.
Cambiar más knobs o usar un modelo mayor no resuelve automáticamente la
dificultad combinatoria del pricing exacto.

Consultar en ese directorio:

- `diagnostic-summary.json` y `summary.csv`: comparación compacta.
- `adaptive-seed0-rep0/native/llm-request.json`: prompts exactos enviados.
- `adaptive-seed0-rep0/native/llm-response.json`: respuesta original y tokens.
- `adaptive-seed0-rep0/native/llm-decision.json`: propuesta validada y acciones.
- `adaptive-seed0-rep0/native/energy.parameters.json`: efectos nativos del tuning.
- `adaptive-seed0-rep0/native/energy.scip.log`: progreso de SCIP.

El resumen distingue la huella del snapshot del manifiesto de la del resultado:
las funciones existentes usan distintas serializaciones JSON. Ambas políticas
leen los mismos archivos y comparten cada huella correspondiente.
