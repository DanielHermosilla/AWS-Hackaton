# Resultados para la presentación — 16 de octubre de 2026

Resultados de la campaña nocturna. Se conservaron las pérdidas, los empates y los fallos.

## Instancias del desafío

La diapositiva 7 del PPTX prioriza entregas factibles con retorno y batería suficiente; después, energía y tiempo. Ambas entradas tienen 20 clientes y 60 cargadores. Dos Leaf disponibles, SoC inicial 60%, capacidad útil supuesta de 24 kWh y reserva de 2,4 kWh.

| Entrada | Entregas | kWh | km | Batería mínima, kWh | Solver med., s | Desde CSV estimado, s | Gap energético |
|---|---|---|---|---|---|---|---|
| competition | 20/20 | 10,5577 | 67,34 | 3,842 | 0,054 | 31,4 | 0,227% |
| evaluation_access250 | 20/20 | 11,0828 | 70,69 | 3,317 | 0,049 | 31,5 | 0,000% |

Los tiempos desde CSV suman etapas medidas por separado. Se reconstruye la instancia y el grafo de servicios, usando un GraphML y un resumen de integración eVED existentes. Se excluyen su descarga/adquisición originales. Los tiempos de solver no son los del pipeline completo.

El estimador usa 0,156771 kWh/km: cada calle consume según su longitud; no predice pendiente, aceleración, tráfico, clima ni auxiliares por segmento. Los ahorros son del modelo.

La red pasa de 106.746 nodos viales a 81 servicios; los caminos mínimos de Competition tardaron 1,55 s. En ambas entradas se verificó la reducción a un tour DFJ dentro de la batería inicial, bajo las hipótesis de métrica y ausencia de plazos. La solución usa un vehículo y no recarga. Esto explica la rapidez; no es un benchmark de recarga y ventanas difíciles.

| Entrada / ahorro por recorrido | kWh EV | kg CO₂ por optimizar EV | USD por optimizar EV | kg CO₂ diésel→EV | USD diésel→EV |
|---|---|---|---|---|---|
| competition | 3,469 | 1,608 | 0,601 | 23,98 | 15,92 |
| evaluation_access250 | 4,213 | 1,953 | 0,730 | 26,35 | 17,44 |

### competition

- **vehicle_1:** depósito → V12 → V3 → V6 → V19 → V7 → V16 → V15 → V14 → V1 → V18 → V8 → V17 → V4 → V20 → V10 → V2 → V9 → V5 → V11 → V13 → depósito.
- **vehicle_2:** inactivo en el depósito.

Referencia greedy: 20 entregas, 14,0265 kWh, 89,47 km. Reducción de energía: 24,73%. Clientes idénticos: True.
Solución nativa: [result.json](artifacts/overnight-20261016/official-final/competition/runs/base-standard-b30-s0-r0/result.json).

### evaluation_access250

- **vehicle_1:** depósito → V10 → V3 → V17 → V6 → V16 → V2 → V20 → V19 → V9 → V13 → V5 → V15 → V7 → V11 → V4 → V18 → V8 → V14 → V1 → V12 → depósito.
- **vehicle_2:** inactivo en el depósito.

Referencia greedy: 20 entregas, 15,2962 kWh, 97,57 km. Reducción de energía: 27,55%. Clientes idénticos: True.
Solución nativa: [result.json](artifacts/overnight-20261016/official-final/evaluation_access250/runs/base-standard-b30-s0-r0/result.json).

Evaluation requirió declarar un acceso bidireccional supuesto de 192,9 m para V16. El escenario original con máximo de 100 m falló y permanece registrado. La variante de 250 m no acredita acceso privado real. No se ajustaron heurísticas usando sus resultados.

Decisiones AWS aplicadas en los ensayos oficiales: competition: 0; evaluation_access250: 0. Una llamada iniciada cuya respuesta llega después del cierre no demuestra ayuda del LLM; su coste queda desconocido si no se recibió uso confirmado.

## Aporte del LLM

GPT-5.6 Luna en AWS Bedrock (`us.openai.gpt-5.6-luna`), región `us-east-1`, con hasta dos consultas asíncronas. El LLM recibe estructura, ventanas, distancias resumidas, capacidades de SCIP y estado de búsqueda. Selecciona estrategias implementadas; el reparador y el validador verifican rutas, recargas y batería. El LLM no cambia el problema ni certifica optimalidad.

La cohorte principal C contiene 16 instancias nuevas (40/80/120/200 clientes, dos familias y dos semillas) y cinco políticas: base, fija ajustada mediante piloto, reglas locales, AWS con portafolio y AWS solo tuning. Presupuesto blando idéntico: 45 s. Las familias se diseñaron expresamente para favorecer selección de heurísticas; no son una muestra representativa de todas las rutas reales.

Corridas AWS con cambios aceptados en la política: 16/16. Fallback parcial o completo: 0/16. Los fallbacks permanecen en los promedios.

| AWS contra | Pares | Δ entregas medio | Mismos clientes | Gana energía | Pierde energía | Δ kWh medio comparable | Δ USD neto medio conocido (n) |
|---|---|---|---|---|---|---|---|
| adaptive / standard | 16 | 8,9 | 13 | 10 | 2 | 3,426 | 0,5710 (13) |
| adaptive / fixed | 16 | 0,0 | 16 | 11 | 4 | 2,369 | 0,3878 (16) |
| adaptive / rules | 16 | 0,0 | 16 | 5 | 4 | -0,247 | -0,0655 (16) |
| adaptive / adaptive_knobs | 16 | 10,5 | 11 | 9 | 2 | 5,343 | 0,9255 (11) |
| adaptive / best_local_hindsight | 16 | 0,0 | 16 | 3 | 6 | -0,619 | -0,1301 (16) |
| adaptive_knobs / best_local_hindsight | 16 | -10,5 | 11 | 1 | 8 | -5,752 | -1,0195 (11) |

Positivo favorece AWS. Los ahorros energéticos exigen los mismos IDs de clientes atendidos. Los casos con distinta cobertura conservan su Δ de entregas y sus consumos brutos, pero no se convierten en ahorros comparables. Los USD netos descuentan tokens incrementales. El n de la última columna cuenta pares con coste conocido: esa media puede cubrir menos casos que la media energética y no debe presentarse como una media de toda la campaña.
`best_local_hindsight` elige después de correr el mejor resultado de base, fija y reglas para cada instancia. Es una referencia exigente construida a posteriori, no una política que conozca de antemano cuál método ganará.

### Caso destacado, seleccionado después de observar la campaña

**dispatch-n120-instance702, adaptive frente a best_local_hindsight:** 0,661 kWh (1,28%) menos, 0,306 kg CO₂ menos, USD 0,0933 netos por recorrido.

| Política | Entregas | kWh | Gap energía, % | Proceso, s | Primera cobertura total, s | Tokens, USD |
|---|---|---|---|---|---|---|
| adaptive | 120/120 | 50,9444 | 30,27 | 46,36 | 6,38 | 0,02121 |
| adaptive_knobs | 120/120 | 51,4263 | 30,92 | 46,53 | 6,04 | 0,02107 |
| fixed | 120/120 | 54,1597 | 34,41 | 46,27 | 0,27 | 0,00000 |
| rules | 120/120 | 53,3697 | 33,44 | 46,06 | 0,26 | 0,00000 |
| standard | 120/120 | 51,6052 | 31,16 | 46,28 | 5,73 | 0,00000 |

Con estas tarifas, bastaba ahorrar 0,122 kWh para pagar los tokens (USD 0,02121). En este caso seleccionado, el ahorro bruto en electricidad equivale a 5,4 veces el coste de tokens.

- Evento `before_search`: **applied**, 4,07 s de inferencia.
  - `rebuild_strategy`: `none` → `window_waves`.
  - `rebuild_seconds`: `4` → `20.0`.
  - Explicación del modelo: The 120-customer instance has four geographically separated energy groups but tightly staggered, overlapping windows and two vehicles, so whole-zone completion is risky. Use window_waves to assign areas while allowing revisits and globally anchor tight deadlines; spend the limited budget on diversified charging-aware seeds and validated repair. Retain reduced-cost exact pricing after primal construction.
- Evento `first_full_service`: **applied**, 6,26 s de inferencia.
  - `rebuild_strategy`: `window_waves` → `electric_local`.
  - Explicación del modelo: All 120 customers are already served and delivery optimality is proven. The prior window_waves portfolio produced no improving reward, while repair has many time rejections but few infeasible sequences; use the remaining budget for incumbent-preserving energy local search with slightly deeper continuous-resource repair and diversification. Keep reduced-cost exact pricing afterward for certification.

Acciones observadas: 20 mejoras locales eléctricas, 0 mejoras por reconstrucción, 0 cortes subset-row y un máximo de 1 nodos B&B por época. Consultas exactas de pricing completadas: 0/2. Un parámetro solicitado no implica que su callback haya producido una acción.

Este caso ilustra una ventaja observada, no una ganancia típica garantizada.

### Comparación anterior B: versión 70f9daf, 60 segundos

24 instancias nuevas y cinco políticas: 120 corridas. Los controles todavía no tenían el constructor `window_waves` añadido después. Estos resultados permanecen separados de C; no representan una repetición de la misma versión.

| Candidato / mejor local observado | Pares | Δ entregas medio | Mismos clientes | Gana kWh | Pierde kWh | Δ kWh medio | Δ USD neto conocido (n) |
|---|---|---|---|---|---|---|---|
| adaptive | 24 | -4,25 | 18 | 11 | 5 | 0,490 | 0,2127 (17) |
| adaptive_knobs | 24 | -3,46 | 18 | 7 | 9 | 0,240 | 0,0193 (18) |

Caso seleccionado a posteriori en B: **crossed-n80-instance501, adaptive**, frente al mejor control observado (`rules`), con idénticos clientes. Ahorró 14,003 kWh (10,83%), 6,490 kg CO₂ modelados y USD 2,4066 después de los tokens. Las pérdidas de cobertura de otras instancias permanecen en la tabla anterior.

## Escalabilidad

| Familia | Clientes | Política | Entregas, % | Cobertura total ≤45 s | PAR2, s |
|---|---|---|---|---|---|
| crossed | 40 | adaptive | 100,0 | 2/2 | 5,89 |
| crossed | 40 | adaptive_knobs | 100,0 | 2/2 | 5,68 |
| crossed | 40 | fixed | 100,0 | 2/2 | 0,05 |
| crossed | 40 | rules | 100,0 | 2/2 | 0,05 |
| crossed | 40 | standard | 100,0 | 2/2 | 5,50 |
| crossed | 80 | adaptive | 100,0 | 2/2 | 17,57 |
| crossed | 80 | adaptive_knobs | 95,0 | 0/2 | 90,00 |
| crossed | 80 | fixed | 100,0 | 2/2 | 0,17 |
| crossed | 80 | rules | 100,0 | 2/2 | 0,21 |
| crossed | 80 | standard | 100,0 | 2/2 | 28,77 |
| crossed | 120 | adaptive | 100,0 | 2/2 | 7,34 |
| crossed | 120 | adaptive_knobs | 89,6 | 1/2 | 63,11 |
| crossed | 120 | fixed | 100,0 | 2/2 | 0,39 |
| crossed | 120 | rules | 100,0 | 2/2 | 0,39 |
| crossed | 120 | standard | 91,7 | 1/2 | 59,24 |
| crossed | 200 | adaptive | 100,0 | 2/2 | 8,30 |
| crossed | 200 | adaptive_knobs | 66,2 | 0/2 | 90,00 |
| crossed | 200 | fixed | 100,0 | 2/2 | 1,33 |
| crossed | 200 | rules | 100,0 | 2/2 | 1,28 |
| crossed | 200 | standard | 69,2 | 0/2 | 90,00 |
| dispatch | 40 | adaptive | 100,0 | 2/2 | 0,82 |
| dispatch | 40 | adaptive_knobs | 100,0 | 2/2 | 0,81 |
| dispatch | 40 | fixed | 100,0 | 2/2 | 0,03 |
| dispatch | 40 | rules | 100,0 | 2/2 | 0,03 |
| dispatch | 40 | standard | 100,0 | 2/2 | 0,69 |
| dispatch | 80 | adaptive | 100,0 | 2/2 | 1,67 |
| dispatch | 80 | adaptive_knobs | 100,0 | 2/2 | 1,65 |
| dispatch | 80 | fixed | 100,0 | 2/2 | 0,11 |
| dispatch | 80 | rules | 100,0 | 2/2 | 0,11 |
| dispatch | 80 | standard | 100,0 | 2/2 | 1,50 |
| dispatch | 120 | adaptive | 100,0 | 2/2 | 6,80 |
| dispatch | 120 | adaptive_knobs | 100,0 | 2/2 | 6,45 |
| dispatch | 120 | fixed | 100,0 | 2/2 | 0,28 |
| dispatch | 120 | rules | 100,0 | 2/2 | 0,28 |
| dispatch | 120 | standard | 100,0 | 2/2 | 6,16 |
| dispatch | 200 | adaptive | 100,0 | 2/2 | 7,91 |
| dispatch | 200 | adaptive_knobs | 100,0 | 2/2 | 18,63 |
| dispatch | 200 | fixed | 100,0 | 2/2 | 0,90 |
| dispatch | 200 | rules | 100,0 | 2/2 | 0,84 |
| dispatch | 200 | standard | 100,0 | 2/2 | 14,95 |

PAR2 usa el tiempo hasta atender a todos los clientes y asigna 90 s a los intentos que no lo consiguieron dentro de 45 s. No elimina los casos difíciles al calcular rendimiento.

### Flota: 2, 4 y 8 vehículos

Cohorte separada; no se mezcla con la comparación principal C.

| Caso | Política | Entregas | kWh | Proceso, s | Tokens, USD |
|---|---|---|---|---|---|
| crossed-n200-v4-instance902 | adaptive | 199/200 | 86,4893 | 31,55 | 0,01207 |
| crossed-n200-v8-instance901 | rules | 200/200 | 80,9754 | 31,37 | 0,00000 |
| crossed-n200-v2-instance902 | adaptive | 200/200 | 115,9032 | 31,59 | 0,02507 |
| crossed-n200-v2-instance901 | adaptive | 200/200 | 110,8191 | 31,44 | 0,02518 |
| crossed-n200-v8-instance901 | adaptive | 200/200 | 80,9754 | 31,47 | 0,02483 |
| crossed-n200-v2-instance901 | standard | 126/200 | 103,4713 | 31,31 | 0,00000 |
| crossed-n200-v8-instance902 | adaptive | 117/200 | 102,8692 | 41,59 | 0,02450 |
| crossed-n200-v8-instance901 | standard | 119/200 | 102,9272 | 39,68 | 0,00000 |
| crossed-n200-v8-instance902 | standard | 118/200 | 102,9886 | 37,29 | 0,00000 |
| crossed-n200-v4-instance902 | rules | 200/200 | 89,8412 | 31,30 | 0,00000 |
| crossed-n200-v4-instance901 | standard | 119/200 | 114,8098 | 31,35 | 0,00000 |
| crossed-n200-v4-instance901 | rules | 200/200 | 80,9754 | 31,30 | 0,00000 |
| crossed-n200-v8-instance902 | rules | 200/200 | 89,8412 | 31,63 | 0,00000 |
| crossed-n200-v2-instance902 | rules | 200/200 | 115,9032 | 31,60 | 0,00000 |
| crossed-n200-v4-instance901 | adaptive | 200/200 | 85,1114 | 31,47 | ND |
| crossed-n200-v2-instance902 | standard | 125/200 | 103,5937 | 31,40 | 0,00000 |
| crossed-n200-v4-instance902 | standard | 122/200 | 103,3035 | 31,60 | 0,00000 |
| crossed-n200-v2-instance901 | rules | 200/200 | 110,8191 | 31,46 | 0,00000 |

| Caso | Candidato / referencia | Δ entregas | Δ kWh | Δ USD neto |
|---|---|---|---|---|
| crossed-n200-v4-instance902 | adaptive / standard | 77 | ND | ND |
| crossed-n200-v4-instance902 | adaptive / rules | -1 | ND | ND |
| crossed-n200-v8-instance901 | adaptive / standard | 81 | ND | ND |
| crossed-n200-v8-instance901 | adaptive / rules | 0 | 0,000 | -0,0248 |
| crossed-n200-v2-instance902 | adaptive / standard | 75 | ND | ND |
| crossed-n200-v2-instance902 | adaptive / rules | 0 | 0,000 | -0,0251 |
| crossed-n200-v2-instance901 | adaptive / standard | 74 | ND | ND |
| crossed-n200-v2-instance901 | adaptive / rules | 0 | 0,000 | -0,0252 |
| crossed-n200-v8-instance902 | adaptive / standard | -1 | ND | ND |
| crossed-n200-v8-instance902 | adaptive / rules | -83 | ND | ND |
| crossed-n200-v4-instance901 | adaptive / standard | 81 | ND | ND |
| crossed-n200-v4-instance901 | adaptive / rules | 0 | -4,136 | ND |

### Variante posterior: aviso inmediato y búsqueda local con presupuesto

Cohorte separada; no se mezcla con la comparación principal C.

`adaptive_waves` y `waves` parten de la misma política fija elegida en el piloto C; solo la primera consulta AWS. `adaptive_waves_v4` permite contrastar el mismo arranque con la versión anterior de callbacks. La extensión se registró antes de ejecutar la semilla nueva 1301; no se eligió mirando sus resultados.

| Caso | Política | Entregas | kWh | Proceso, s | Tokens, USD |
|---|---|---|---|---|---|
| dispatch-n200-instance1301 | standard | 190/200 | 74,1056 | 31,44 | 0,00000 |
| dispatch-n80-instance1301 | waves | 80/80 | 48,8014 | 31,18 | 0,00000 |
| crossed-n80-instance1301 | adaptive_v4 | 77/80 | 92,8318 | 30,80 | ND |
| dispatch-n80-instance1301 | adaptive_waves_v4 | 80/80 | 47,6543 | 31,20 | 0,01913 |
| crossed-n80-instance1301 | waves | 78/80 | 103,9054 | 30,80 | 0,00000 |
| crossed-n200-instance1301 | adaptive_v4 | 200/200 | 121,8091 | 31,34 | 0,01214 |
| crossed-n200-instance1301 | waves | 200/200 | 117,3242 | 31,49 | 0,00000 |
| dispatch-n80-instance1301 | standard | 80/80 | 48,7221 | 31,07 | 0,00000 |
| crossed-n200-instance1301 | rules | 200/200 | 115,4872 | 31,23 | 0,00000 |
| dispatch-n200-instance1301 | rules_v4 | 200/200 | 62,4627 | 31,30 | 0,00000 |
| dispatch-n80-instance1301 | rules_v4 | 80/80 | 49,5639 | 31,01 | 0,00000 |
| crossed-n200-instance1301 | adaptive_waves | 200/200 | 115,4872 | 31,82 | 0,02480 |
| crossed-n200-instance1301 | rules_v4 | 200/200 | 116,1042 | 31,21 | 0,00000 |
| dispatch-n80-instance1301 | adaptive_waves | 80/80 | 47,6543 | 31,15 | 0,01912 |
| crossed-n200-instance1301 | adaptive_waves_v4 | 200/200 | 116,1042 | 31,26 | 0,02512 |
| crossed-n200-instance1301 | adaptive | 200/200 | 121,8091 | 31,35 | 0,02471 |
| dispatch-n200-instance1301 | adaptive_waves | 200/200 | 60,6674 | 31,44 | 0,02511 |
| crossed-n80-instance1301 | adaptive_waves | 77/80 | 87,7386 | 30,84 | 0,00958 |
| dispatch-n200-instance1301 | adaptive | 200/200 | 60,8195 | 31,51 | 0,02507 |
| crossed-n80-instance1301 | standard | 76/80 | 128,5742 | 30,87 | 0,00000 |
| dispatch-n200-instance1301 | rules | 200/200 | 60,6674 | 31,33 | 0,00000 |
| dispatch-n200-instance1301 | adaptive_v4 | 200/200 | 62,4627 | 31,62 | 0,02494 |
| crossed-n200-instance1301 | standard | 133/200 | 114,0943 | 31,33 | 0,00000 |
| dispatch-n80-instance1301 | adaptive | 80/80 | 46,1417 | 31,32 | 0,01921 |
| crossed-n80-instance1301 | rules_v4 | 76/80 | 83,0732 | 30,76 | 0,00000 |
| crossed-n80-instance1301 | adaptive | 78/80 | 103,9054 | 30,88 | 0,01906 |
| dispatch-n80-instance1301 | rules | 80/80 | 47,6058 | 30,94 | 0,00000 |
| dispatch-n80-instance1301 | adaptive_v4 | 80/80 | 46,1417 | 31,31 | 0,01954 |
| crossed-n80-instance1301 | adaptive_waves_v4 | 77/80 | 87,7386 | 30,93 | 0,00938 |
| dispatch-n200-instance1301 | waves | 200/200 | 68,2001 | 31,41 | 0,00000 |
| dispatch-n200-instance1301 | adaptive_waves_v4 | 200/200 | 62,4627 | 31,48 | 0,02527 |
| crossed-n80-instance1301 | rules | 75/80 | 82,9552 | 30,77 | 0,00000 |

| Caso | Candidato / referencia | Δ entregas | Δ kWh | Δ USD neto |
|---|---|---|---|---|
| dispatch-n200-instance1301 | adaptive / standard | 10 | ND | ND |
| dispatch-n200-instance1301 | adaptive / rules | 0 | -0,152 | -0,0514 |
| dispatch-n200-instance1301 | adaptive / adaptive_v4 | 0 | 1,643 | 0,2846 |
| dispatch-n200-instance1301 | rules / rules_v4 | 0 | 1,795 | 0,3110 |
| dispatch-n200-instance1301 | adaptive_waves / waves | 0 | 7,533 | 1,2800 |
| dispatch-n200-instance1301 | adaptive_waves / rules | 0 | 0,000 | -0,0251 |
| dispatch-n200-instance1301 | adaptive_waves / adaptive_waves_v4 | 0 | 1,795 | 0,3112 |
| dispatch-n80-instance1301 | adaptive / standard | 0 | 2,580 | 0,4279 |
| dispatch-n80-instance1301 | adaptive / rules | 0 | 1,464 | 0,2345 |
| dispatch-n80-instance1301 | adaptive / adaptive_v4 | 0 | 0,000 | 0,0003 |
| dispatch-n80-instance1301 | rules / rules_v4 | 0 | 1,958 | 0,3393 |
| dispatch-n80-instance1301 | adaptive_waves / waves | 0 | 1,147 | 0,1796 |
| dispatch-n80-instance1301 | adaptive_waves / rules | 0 | -0,048 | -0,0275 |
| dispatch-n80-instance1301 | adaptive_waves / adaptive_waves_v4 | 0 | 0,000 | 0,0000 |
| crossed-n80-instance1301 | adaptive / standard | 2 | ND | ND |
| crossed-n80-instance1301 | adaptive / rules | 3 | ND | ND |
| crossed-n80-instance1301 | adaptive / adaptive_v4 | 1 | ND | ND |
| crossed-n80-instance1301 | rules / rules_v4 | -1 | ND | ND |
| crossed-n80-instance1301 | adaptive_waves / waves | -1 | ND | ND |
| crossed-n80-instance1301 | adaptive_waves / rules | 2 | ND | ND |
| crossed-n80-instance1301 | adaptive_waves / adaptive_waves_v4 | 0 | 0,000 | -0,0002 |
| crossed-n200-instance1301 | adaptive / standard | 67 | ND | ND |
| crossed-n200-instance1301 | adaptive / rules | 0 | -6,322 | -1,1201 |
| crossed-n200-instance1301 | adaptive / adaptive_v4 | 0 | 0,000 | -0,0126 |
| crossed-n200-instance1301 | rules / rules_v4 | 0 | 0,617 | 0,1069 |
| crossed-n200-instance1301 | adaptive_waves / waves | 0 | 1,837 | 0,2935 |
| crossed-n200-instance1301 | adaptive_waves / rules | 0 | 0,000 | -0,0248 |
| crossed-n200-instance1301 | adaptive_waves / adaptive_waves_v4 | 0 | 0,617 | 0,1072 |

Demo seleccionada a posteriori: **dispatch-n200-instance1301**. AWS y la política fija cumplen 200/200. Ahorro frente a la fija: **7,533 kWh (11,04%)**, 3,491 kg CO₂ y USD 1,2800 netos; los tokens costaron USD 0,02511. Las reglas locales consiguieron 60,667 kWh y AWS 60,667 kWh. El ejemplo acredita una mejora frente a la fija, no frente a esas reglas.

AWS redujo las épocas de pricing de 12 a 8 y luego 6 segundos y cambió `window_waves` por `electric_local` al completar las entregas. El motor aceptó 74 mejoras locales. Gap final: 41,32%. La propuesta de cortes subset-row no produjo cortes ejecutados. Las dos consultas tardaron aproximadamente 4,60 y 3,96 s, solapadas con la búsqueda.

## Supuestos optimistas y coste

- Electricidad comercial Michigan: USD 0,1646/kWh (EIA, julio 2026).
- Diésel Midwest: USD 6,259/galón estadounidense (EIA, 12 de octubre de 2026).
- Furgón diésel hipotético: 12 L/100 km; eficiencia de recarga: 95%.
- Electricidad RFCM: 0,440264 kg CO₂/kWh generado (EPA eGRID2023 Rev2). Diésel: 2,689271 kg CO₂/L (EPA).
- La batería inicial también debe reponerse. No se trata como electricidad gratuita.
- El 95% es un factor contable para estimar electricidad comprada. No recalcula los tiempos ni la factibilidad temporal de los snapshots sintéticos ya resueltos.
- Se excluyen emisiones del cómputo, fabricación, inversión, mantenimiento, salarios, colas y sobreprecio de recarga rápida. No se acreditó equivalencia de capacidad entre furgón y Leaf.
- Las proyecciones anuales suponen 300 recorridos equivalentes. No son actividad medida.

```text
Ahorro de electricidad = (kWh referencia − kWh AWS) / 0,95
Ahorro neto USD = ahorro de electricidad × 0,1646 − coste incremental de tokens
Ahorro de CO₂ = ahorro de electricidad × 0,440264
```

Tarifas AWS por millón de tokens: USD 0,22 entrada, 1,32 salida, 0,275 escritura de caché y 0,022 lectura. Se contabilizan los prefijos de caché reportados por el proveedor. Inferencias sin uso confirmado quedan ND.

Coste conocido de las consultas de las comparaciones sintéticas: **USD 2,1897**. Corridas sintéticas con coste desconocido: **3**. No incluye diagnósticos de desarrollo ni pretende ser una factura de AWS.

## Diagnóstico y reproducción

Se corrigió un atasco de presolve en el sub-MIP de recombinación; se añadieron reconstrucción por ventanas y mejora local eléctrica. La cohorte C da esas herramientas tanto a AWS como a controles locales fuertes. La cohorte D, si está completa, evalúa por separado el aviso inmediato de cobertura total y la eliminación del corte heurístico de 20 mejoras locales.

Base de trabajo: main `94a4e1d`. Cohorte C: `a04a884`. Cada cohorte conserva copia del código, hashes, semillas, planificación, fallos, stdout de SCIP y consultas/respuestas de Bedrock. El testigo del generador sirve para auditoría; no se entrega al solver ni al LLM.

En las 80 comparaciones C, el maestro por rutas no pasó del nodo raíz, no añadió cortes subset-row y no completó consultas de pricing dual exacto. La relajación energética auxiliar sí puede separar sus propios cortes. El aporte observado de AWS viene de seleccionar y presupuestar heurísticas; no se acredita una mejora por branching profundo. Ninguna de las 80 corridas C alcanzó el gap energético solicitado de 0,5%. Esto no invalida sus rutas factibles.

La mediana hasta completar todas las entregas fue 7,14 s con AWS, frente a 0,26 s con reglas locales y 0,22 s con la política fija. Esos tres métodos completaron las 16 instancias. Las consultas AWS duraron 4,94 s de media y se solaparon con trabajo local; no deben sumarse otra vez al tiempo total.

Los dos primeros intentos de las campañas oficiales terminaron antes de resolver porque faltaba `uv.lock` en la copia congelada. Se reparó la disposición de archivos, sin modificar el solver, y se repitieron en serie. Los errores originales y la recuperación están en los manifiestos de procedencia; no se cuentan como resoluciones del benchmark.

| Cohorte | Corridas | Fallos | Consultas AWS | Uso |
|---|---|---|---|---|
| a-pilot | 48 | 4 | 0 | development |
| b-pilot | 56 | 0 | 0 | development |
| b-comparison | 120 | 0 | 96 | paired_synthetic |
| c-pilot | 64 | 0 | 0 | development |
| c-comparison | 80 | 0 | 64 | paired_synthetic |
| fleet | 18 | 0 | 11 | supplemental_separate |
| callbacks | 32 | 0 | 29 | supplemental_separate |

Los conteos anteriores son benchmarks, no pruebas unitarias. Las instancias oficiales y los ensayos de diagnóstico están separados. Alcanzar 0,5% de gap no significa óptimo energético exacto; completar todas las entregas sí prueba el máximo de entregas por cardinalidad.

### Archivos

- `official-kpis.csv`: instancias oficiales, referencias y ahorros.
- `phase-c/kpis.csv`, `phase-c/all-reference-pairs.csv`: todos los resultados de la comparación principal.
- `llm-decisions.csv`: eventos, decisiones aplicadas y uso del proveedor.
- `scalability.csv`: escalabilidad por tamaño, familia y política.
- `fleet-kpis.csv`, `fleet-pairs.csv`: estudio de flota, cuando termina.
- `callbacks-kpis.csv`, `callbacks-pairs.csv`: estudio de callbacks, cuando termina.
- `figures/`: gráficos PNG y SVG para usar directamente en diapositivas.

### Fuentes

- [EIA, electricidad comercial por estado](https://www.eia.gov/electricity/monthly/epm_table_grapher.php?t=table_5_06_a).
- [EIA, precios semanales de diésel](https://www.eia.gov/petroleum/gasdiesel/).
- [EPA eGRID, datos regionales](https://www.epa.gov/egrid/summary-data).
- [EPA, CO₂ por combustible](https://www.epa.gov/greenvehicles/greenhouse-gas-emissions-typical-passenger-vehicle).
- [AWS, GPT-5.6 Luna](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-openai-gpt-56-luna.html).
- [AWS, campos de uso de tokens](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_TokenUsage.html).
