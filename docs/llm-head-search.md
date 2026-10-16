# Branch-price-and-cut eléctrico con cabeza LLM

Implementación en `codex/evrp-llm-search`, basada en el preprocesamiento
`b14b97655ab30ce9232422fe426fb8e0dfdc9d17` y el motor anterior
`2a89b041db5d28610d5182a6da90ed6137be4051`. El checkout original y sus otros
worktrees no se modifican. Esta rama conserva (25)–(31) de `modelamiento.pdf`.

Actualización: el objetivo de gap energético es **0,5 %**, configurable mediante
`--energy-relative-gap`; cero vuelve a buscar cierre exacto. No se relaja el
objetivo principal de entregas. La CLI usa **GPT-6 Luna con esfuerzo `low`**
por Converse. La prueba real encontró un deny explícito de AWS para el perfil
`hackathon`; hace falta acceso autorizado antes de atribuir decisiones a GPT.
La [guía de integración](webapp-integration.md) reúne comandos, estado del acceso,
semántica del gap y conexión futura con `origin/codex/webapp`.

## Conexión con el preprocesamiento auditado

Se revisaron `resource_graph.py`, `service_graph.py`, el informe
`resource-paths.md` y la propagación de perfiles de `route_resources.py`.
El preprocesamiento permanece separado y reutilizable:

- Dijkstra solo en el caso no negativo sin jornada o ventanas.
- Eliminación de intersecciones mediante perfiles de batería y tiempo en los
  demás casos. Cada alternativa conserva `arc_id` y testigo vial.
- Una intersección costosa o numéricamente ambigua permanece en el grafo;
  el límite de trabajo de compresión no limita rutas ni etiquetas.
- `PricingNetwork` indexa el multigrafo una vez y guarda potenciales optimistas.
  No sustituye alternativas físicas por el arco de menor energía o tiempo.
- El pricing y la reparación recorren las intersecciones retenidas y los
  arcos paralelos; propagan saturación, déficits intermedios, recargas parciales,
  ventanas y retornos.

Se corrigió una incompatibilidad al integrar la relajación energética antigua:
una CSR con entradas repetidas sumaba arcos paralelos. Ahora la relajación
escoge su coste mínimo; sumar alternativas habría invalidado la cota.
Esta simplificación solo pertenece a la relajación, nunca a la física.

## Motor implementado

1. **Construcción y reparación física.** La inserción directa rápida permanece
   para el caso simple. Con recursos, `SequenceOracle` fija el orden de entregas,
   pero elige caminos y recargas sobre el multigrafo. Su presupuesto es heurístico;
   un timeout nunca se memoriza como infactibilidad.
2. **ALNS.** Destrucción aleatoria, relacionada, por desvío o por ruta; reparación
   greedy/regret, selección adaptativa de operadores y aceptación diversificada.
3. **Búsqueda memética eléctrica.** Población de soluciones factibles, cruce de
   órdenes de entrega sin duplicados, reparación física, elitismo y diversidad
   de aristas. Su tamaño es un parámetro heurístico.
4. **Matheurísticas.** SCIP recompone rutas del pool tanto entre etapas como
   dentro de `Heur`. Solo produce incumbentes; su cota restringida se descarta.
   La relajación independiente de tour puede cerrar energía si se obtiene un
   testigo físico que coincide con su cota, sin convertirla en el modelo físico.
5. **Pricing.** Primero construcción dual y columnas complementarias para buscar
   soluciones enteras; después `ReducedCostOracle` exacto. Cada consulta dual
   tiene estado propio, recursos continuos y cotas conservadoras de completación.
   No hay H, discretización de batería ni límite de etiquetas.
6. **Cortes y árbol.** Triples subset-row separados dinámicamente con coeficientes
   de columnas futuras, branching en asignaciones de clientes y selección de
   nodos controlable. SCIP sigue gestionando su árbol.

La cota del pricing usa `b_inicial + min(Q-b) + distancia_al_deposito` con
energías no negativas, y `b_inicial + min(Q) - capacidad` con regeneración.
Resta una sobreestimación de los premios duales pendientes y un margen numérico
conservador. Los duales de subset-row se acotan según su signo. No encontrar
columnas heurísticas no prueba nada; agotar la consulta exacta sí tiene alcance
de pricing completo para ese dual. Al interrumpirla se descarta la cota nativa
del maestro restringido.

No se implementa todavía pricing bidireccional ni ng-routes. No se reemplaza el
oráculo de poliedros continuos por una aproximación de recargas. El LLM no
ejecuta código generado, no altera las restricciones y no emite certificados.

## Exploración y uso efectivo de SCIP

Se inspeccionaron la API instalada, sus firmas y sus parámetros: PySCIPOpt 6.0.0,
SCIP 10.0.0, 409 entradas públicas de `Model`, 3.082 parámetros nativos y 1.242
parámetros admitidos en el catálogo del maestro general. Son conteos de esta
instalación, no una promesa para otras versiones. El catálogo completo se
exporta; el prompt incluye una selección de LP, frecuencias y prioridades.

| Familia | API usada | Acción ejecutable |
|---|---|---|
| `Pricer` | `includePricer`, `addVar`, `addConsCoeff`, `getDualsolLinear`, `getDualfarkasLinear` | Lotes, búsqueda por dual, heurísticas y completitud exacta |
| `Branchrule` | `getLPBranchCands`, `branchVar` | Fraccionalidad, escasez de conexiones o prioridad de clientes |
| `Nodesel` | `getPrioChild`, `getBestboundNode`, comparador | Profundidad, mejor cota o combinación |
| `Sepa` | `addCons(modifiable=True)`, `getSolVal` | Subset-row con soporte de columnas futuras |
| `Heur` | `createSol`, `setSolVal`, `trySol(completely=True)` | Sub-SCIP de recombinación con verificación nativa |
| `Eventhdlr` | `catchEvent`, `dropEvent` | Incumbentes, nodos y LP resueltos |
| Configuración y contexto | `getParams`, `setParam`, `writeProblem`, estadísticas LP/árbol | Parámetros validados, MPS real y telemetría |

También se inspeccionaron `Prop`, `Cutsel`, `Conshdlr`, `Presol`, `Relax`, bases LP
y pseudocostes. No se agregaron adaptadores vacíos ni se afirma control ejecutable
sobre esas familias. No fue necesario modificar código C de SCIP.
Presolve y separación genéricos permanecen bloqueados en el maestro con
columnas futuras; pueden utilizarse en problemas finitos auxiliares.
Las tolerancias, recursos globales, datos y criterios de prueba permanecen fuera
del espacio de acciones del LLM. Los parámetros nativos que no pueden aplicarse
durante `optimize()` se difieren al siguiente maestro.

## Cabeza LLM y contexto

`LLMHead` inicia análisis antes de la búsqueda y recibe eventos de heurísticas,
pricing, nodos, LP, separación e incumbentes. Envía mediciones, rutas incumbentes,
duales de clientes, presupuesto, esquema de acciones y contexto físico.
El modelo principal se configura con `--bedrock-model`; `--bedrock-fast-model`
permite usar otro de menor latencia en eventos durante la búsqueda.

La inferencia usa un hilo que recibe únicamente JSON. Los callbacks continúan
ejecutando la política validada; ninguna llamada de SCIP ocurre en el hilo remoto.
La llamada nativa es `optimizeNogil()`, también en los sub-SCIP: `optimize()`
retiene el GIL de Python y, en el ensayo inicial, una respuesta que AWS generó
en 3,295 s se procesó localmente después de 36,39 s. Los callbacks Python de la
versión instalada recuperan el GIL al entrar; SCIP y su árbol siguen en el hilo
principal. Las pruebas de integración se repitieron con esta API.
La respuesta se valida y aplica en el hilo del solver. Cambiar `RoutePolicy`
afecta directamente los adaptadores; se registran revisiones observadas,
cambios efectivos, campos de etapas terminadas y cambios nativos ejecutados.
Una propuesta recibida pero sin campos efectivos no demuestra mejora.
`decisions_changing_algorithm` excluye respuestas que solo cambian `rationale`.

Los límites incluyen llamadas, tokens de salida, bytes de entrada, intervalo,
timeout y fracción del presupuesto global. El vencimiento de una decisión se
comprueba en puntos de observación; no interrumpe una operación C indivisible.
Una solicitud vencida deja de bloquear la siguiente decisión y su respuesta
tardía no se aplica. Esto **no cancela una solicitud ya enviada a AWS**:
su coste/uso puede permanecer desconocido al finalizar el solver.
La última política válida sigue activa ante respuestas inválidas o fallos.
Si el tiempo restante no alcanza la latencia de una respuesta válida anterior
del mismo modelo, con un margen del 25 %, no se lanza otra consulta.

Con `--solver-log-directory` se exportan:

- `pricing-instance.json`: grafo físico, perfiles, vehículos y operaciones completos.
- `scip-api-catalog.json` y `scip-parameter-catalog.json`: capacidades instaladas.
- `*.mps`: maestros nativos con las columnas conocidas en su construcción.
- `decisions/*/llm-request.json` y `llm-response.json`: payloads y respuestas
  efectivamente recibidas, sin credenciales ni cabeceras HTTP.
- `llm-decision.json`: aplicación, rechazo, vencimiento y uso conocido.

Un MPS restringido **no contiene la familia implícita de rutas futuras ni la
física del pricing**. Se envía su texto si cabe en el presupuesto y existe al
momento de consultar; la primera consulta previa al maestro aún no lo tiene.
Si no cabe se registra exportación local y omisión. Del mismo modo, el grafo
puede enviarse completo o como extracto explícito; nunca se presenta el extracto
como instancia completa. No se envían históricos de entrenamiento, coordenadas,
direcciones ni credenciales.

## Validación y mediciones locales

Las pruebas habituales no llaman a AWS. Incluyen comparación de pricing con
enumeración exhaustiva para duales positivos/negativos y Farkas, perfiles paralelos,
regeneración, recarga repetida, ventanas, recombinación, callbacks SCIP reales
con LLM doble y respuestas inválidas, vencidas y tardías.

Mediciones iniciales del 15 de octubre de 2026, anteriores a la parada en 0,5 %
y sin atribución causal de aceleración:

| Instancia/política | Entregas | Energía kWh | Resolución | Certificado |
|---|---:|---:|---:|---|
| 40 clientes, estándar, límite 15 s | 40/40 | 14,56660712 | 15,0021 s | Entregas óptimas; cota energética 14,52526525; gap 0,2838 % |
| Temporal auditada, estándar, límite 30 s | 20/20 | 10,55774084 | 5,7330 s | Ambas fases probadas dentro de tolerancias |

La instancia temporal se preparó de nuevo con el mismo escenario ilustrativo
del informe: jornada y ventanas amplias de 28.800 s, velocidad supuesta 30 km/h,
potencia supuesta 3 kW. **No son reglas oficiales ni mediciones operacionales.**
Preparación: 106.746 → 607 nodos, 6.333 arcos, 4,4590 s; 526 intersecciones
retenidas. La solución utiliza 1.999 calles, consume 10,55774084 kWh y no recarga.
Su duración es 8.081,39 s. Validación incluida la expansión: 0,6502 s; pipeline
de resolución 6,9140 s, excluyendo la preparación separada.
La prueba energética combina testigo factible con cota 10,55774081 de la
relajación sin recursos. **Este caso termina antes de necesitar branch-and-price**;
no demuestra rendimiento de sus callbacks en una instancia temporal difícil.

En 40 clientes se mantiene la calidad del motor anterior. El ensayo estándar
ejecutó 20 llamadas de pricing, cuatro sub-MIP dentro del callback, incorporó
cuatro columnas complementarias y podó 6.442 etiquetas por cota; terminó
sin completar el pricing. No hay prueba de aceleración ni de mejora de energía
frente a aquel motor. Los presupuestos heurísticos se eligen para probar una
configuración operativa; requieren A/B repetidos antes de atribuir mejoras.

Los resultados completos y las solicitudes reales se conservan, ignorados por Git,
en `artifacts/llm-head/`. Las primeras corridas son ensayos de desarrollo sobre
distintos estados del código, no un A/B controlado ni un benchmark de versiones
idénticas. El manifiesto local identifica ese alcance.

### Llamadas reales y fallos detectados

1. Con `optimize()` y contexto de 45.000 bytes, Fable seguía pendiente al finalizar
   60 s. El solver mantuvo la solución; no hubo política adaptativa aplicada.
2. Tras introducir vencimientos de decisiones, una respuesta Nova de 3,295 s
   según AWS tardó 36,39 s de extremo a extremo. Se identificó el GIL retenido por
   la llamada nativa y se pasó a `optimizeNogil()` en maestro y subproblemas.
3. Con `optimizeNogil()`, Nova produjo una respuesta aplicable en 4,345 s, aunque
   solo cambió la explicación. No se contó como mejora algorítmica.
4. Un ensayo de 90 s, contexto de 8.000 bytes y tres llamadas aplicó durante
   `route_recombination` una propuesta Nova en 2,951 s. Cambió pricing, ALNS,
   recombinación y selección de nodos; los callbacks observaron la revisión
   posterior. Fable sí produjo una recomendación estructurada, pero llegó
   después del límite de 30 s y se descartó. Se conservaron 40/40 entregas,
   14,56660712 kWh y la cota anterior, en 90,0131 s, sin errores de callbacks.

Estas llamadas prueban integración real y trazabilidad, **no que el LLM mejore
el resultado ni el tiempo**. Los fallos, respuestas tardías y consumo recibido
permanecen en los logs. Un presupuesto corto puede terminar antes de que un
modelo de mayor latencia tenga oportunidad de intervenir.

### Verificación histórica anterior al gap de 0,5 %

Suite completa: **644 pruebas aprobadas en 7,69 s**; `ruff check src tests` sin
errores. PDF compilado, nueve páginas; revisión visual de las páginas modificadas
7–9. Los casos de física del preprocesamiento original siguen incluidos.

| Corrida final | Entregas | Energía kWh | Resolución | Pipeline con validación |
|---|---:|---:|---:|---:|
| 40 clientes, estándar, 15 s | 40/40 | 14,56660712 | 15,0036 s | 15,8638 s |
| 20 clientes, escenario temporal, 30 s | 20/20 | 10,55774084 | 5,7593 s | 6,9513 s |
| 40 clientes, Fable + Nova, 120 s | 40/40 | 14,56660712 | 120,0082 s | 120,8910 s |

Todas pasan la validación de calles. El escenario temporal vuelve a probar ambos
objetivos. En 40 clientes la primera solución completa aparece a los **0,1585 s**
en estándar y **0,1674 s** en adaptativo. El resto del presupuesto busca mejorar
energía y cerrar el gap; permanece la cota 14,52526525 kWh y el gap 0,2838 %.
Estos presupuestos distintos no forman un A/B que permita atribuir aceleración.

La corrida adaptativa final utilizó contexto de 8.000 bytes, máximo dos llamadas,
timeout de 45 s para Fable y 8 s para Nova. **Fable 5, esfuerzo `high`, respondió
en 38,4560 s y su política cambió 22 campos del algoritmo**. Se observaron después
callbacks con esa revisión y cambios reales en maestros posteriores, por ejemplo
`lp/pricing: l → s`. `lp/solutionpolishing=3` coincidía con el valor vigente:
se distingue propuesta de cambio efectivo. Los campos de etapas cerradas
quedaron inactivos. Nova respondió en 6,6586 s y conservó la política.
El estado final es `adaptive`, sin errores de callbacks, dos respuestas válidas,
una decisión que cambia algoritmo, 31.382 tokens reportados por AWS.
Los 45,1146 s acumulados de inferencia se solapan con la resolución.

No se mejoró la energía frente al control estándar ni se cerró su gap.
Se verifica la integración solicitada, no una ventaja de rendimiento general.
Resultados: `40-standard-final/result.json`, `temporal/standard-final-result.json`
y `40-fable-validated/result.json`, relativos a `artifacts/llm-head/`.
`validation-manifest.json` liga resultados, entradas, código y verificaciones.

## Fuentes primarias y antecedentes

- [SCIP: variable pricers y contratos de completitud](https://www.scipopt.org/scip/doc/html/PRICER.php).
- [SCIP: familias de plugins](https://www.scipopt.org/doc/html/HOWTOADD.php).
- [PySCIPOpt: API Model](https://pyscipopt.readthedocs.io/en/stable/api/model.html).
- [PySCIPOpt: heurísticas](https://pyscipopt.readthedocs.io/en/stable/tutorials/heuristic.html).
- [PySCIPOpt: selección de nodos](https://pyscipopt.readthedocs.io/en/latest/tutorials/nodeselector.html).
- [PySCIPOpt: eventos](https://pyscipopt.readthedocs.io/en/latest/tutorials/eventhandler.html).
- [AWS: API Converse](https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html).

El informe `research-evrp-llm.md` conserva la investigación previa y sus referencias;
es un mapa de antecedentes, no evidencia de que todas sus técnicas estén
implementadas. `resource-paths.md` contiene la demostración y auditoría del
preprocesamiento integrado.
