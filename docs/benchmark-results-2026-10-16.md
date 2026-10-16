# Resultados del benchmark nocturno — 16 de octubre de 2026

La campaña documenta **436 corridas**, incluidos pilotos y **4 fallos**. No son instancias independientes ni pruebas unitarias. Las versiones y presupuestos se analizan por separado. Todo se ejecutó con `caffeinate`, sobre main `94a4e1d` y cambios experimentales en `codex/benchmark-presentation`.

## Instancias oficiales

| Entrada | Entregas | Energía kWh | Desde CSV s | Gap energía % | Ahorro EV % | CO₂ EV kg | USD EV |
| --- | --- | --- | --- | --- | --- | --- | --- |
| competition | 20/20 | 10.55774 | 31.45 | 0.2274 | 24.73 | 1.608 | 0.601 |
| evaluation_access250 | 20/20 | 11.08282 | 31.47 | 0.0000 | 27.55 | 1.953 | 0.730 |

El ahorro compara rutas eléctricas con una inserción greedy que atiende los mismos clientes. El tiempo desde CSV suma etapas medidas y usa GraphML y resumen eVED existentes; excluye su descarga original. Las rutas pasan la validación sobre calles. `evaluation_access250` añade un acceso bidireccional supuesto de 192,9 m para V16, sin verificación de acceso privado en terreno. Se usaron 24 kWh útiles y 2,4 kWh de reserva como supuestos. AWS no aplicó decisiones en estas 18 corridas rápidas.

En ambos casos se verificó la reducción a un tour DFJ por métrica dirigida, energías no negativas, ausencia de plazos y un tour completo dentro de la batería inicial. Las soluciones usan un vehículo y no recargan. Estos tiempos no se extrapolan a instancias con ventanas y recarga.

En la instancia Competition, el preprocesamiento pasó de 106.746 nodos viales a 81 servicios en 1,55 s de caminos mínimos. Carga, construcción desde CSV, serialización, resolución y validación se contabilizan aparte. Las calles originales se conservan para expandir y validar las rutas.

## Aporte de AWS

La comparación principal C tiene 16 instancias, de 40 a 200 clientes, dos familias sintéticas favorables a la elección de heurísticas y cinco políticas: 80 corridas con 45 s cada una. Semillas de prueba 701/702, distintas del piloto. AWS, reglas y política fija completaron las 16; la base completó 13. Ninguna alcanzó el gap energético de 0,5%. Completar las entregas prueba su máximo por cardinalidad, pero no prueba energía óptima.

| AWS frente a | Δ entregas medio | Mismos clientes | Δ kWh medio | Δ USD neto medio |
| --- | --- | --- | --- | --- |
| standard | 8.94 | 13/16 | 3.426 | 0.5710 |
| fixed | 0.00 | 16/16 | 2.369 | 0.3878 |
| rules | 0.00 | 16/16 | -0.247 | -0.0655 |
| best_local_hindsight | 0.00 | 16/16 | -0.619 | -0.1301 |

Positivo favorece AWS. La media energética solo incluye pares con exactamente los mismos clientes. `best_local_hindsight` elige retrospectivamente el mejor control; no representa una política ejecutable ni un tiempo combinado. En esta cohorte, AWS mejora la política fija, pero **no supera en promedio las reglas locales fuertes**.

El modelo fue `us.openai.gpt-5.6-luna` en Bedrock. Eligió reconstrucción por ventanas y mejora local eléctrica, con cambios de presupuesto registrados. El maestro permaneció en raíz y no completó pricing dual exacto; no se atribuye el resultado a branching profundo ni a cortes subset-row que no se ejecutaron.

Demo seleccionada a posteriori en la versión anterior B, con 60 s: `crossed-n80-instance501` ahorró **14.003 kWh (10.83%)**, 6.490 kg CO₂ y **USD 2.407 netos** frente al mejor control observado. B y C no se mezclan para afirmar una mejora general.

## Corrección posterior y flota

| D: candidato / referencia | Δ entregas | Mismos clientes | Δ kWh | Δ USD neto (n) |
| --- | --- | --- | --- | --- |
| adaptive / rules | 0.75 | 3/4 | -1.670 | -0.3123 (3) |
| adaptive_waves / waves | -0.25 | 3/4 | 3.506 | 0.5844 (3) |
| adaptive_waves / rules | 0.50 | 3/4 | -0.016 | -0.0258 (3) |
| adaptive / adaptive_v4 | 0.25 | 3/4 | 0.548 | 0.0908 (3) |
| adaptive_waves / adaptive_waves_v4 | 0.00 | 4/4 | 0.603 | 0.1046 (4) |

Demo de 200 clientes elegida a posteriori: `dispatch-n200-instance1301`. Con el mismo arranque y presupuesto, AWS ahorró **7.533 kWh (11.04%)** y **USD 1.280 netos** frente a la política fija. Ambos cumplieron 200/200. Las reglas locales igualaron la energía de AWS. Las otras tres instancias permanecen en la tabla; una pierde una entrega frente a la fija y no se presenta como ahorro.

En esa demo, AWS redujo épocas de pricing de 12 a 8 y luego 6 s, y pasó de reconstrucción por ventanas a `electric_local`. El motor aceptó 74 mejoras locales. El gap energético final fue 41,32%; no se probó el óptimo ni se alcanzó 0,5%. Se propusieron cortes subset-row, pero se ejecutaron cero.

D usa cuatro instancias nuevas, ocho modos y 30 s por corrida. Compara el aviso temprano de cobertura, la conservación del evento mientras AWS está ocupado y una búsqueda eléctrica reanudable sin límite fijo de 20 mejoras. `adaptive_waves` y `waves` reciben la misma política inicial del piloto. La variante pasó **970 pruebas y 37 subpruebas**; el hash probado coincide con el código congelado de D. El estudio de flota agrega 18 corridas con 200 clientes y 2, 4 u 8 vehículos.

## Factores, archivos y reproducción

Michigan: electricidad comercial USD 0,1646/kWh; diésel Midwest USD 6,259/galón. Escenario optimista: 12 L/100 km y 95% de eficiencia de recarga contable. CO₂: 0,440264 kg/kWh y 2,689271 kg/L diésel. El reporte enlaza EIA, EPA y AWS. Se repone también la batería inicial. No se incluyen CAPEX, fabricación, salarios ni emisiones de cómputo. Electrificación y optimización se contabilizan por separado.

AWS por millón de tokens: USD 0,22 entrada, 1,32 salida, 0,275 escritura de caché y 0,022 lectura. Se usan campos reales del proveedor; consultas sin uso conocido quedan ND. El ahorro neto descuenta el coste incremental de tokens.

- [PDF publicado](benchmarks/2026-10-16/benchmark-hackathon-2026-10-16.pdf).
- [Tablas, gráficos, decisiones y procedencia publicados](benchmarks/2026-10-16/README.md).
- Paquete local: `output/benchmark-hackathon-2026-10-16.zip`.
- Originales completos locales: `artifacts/overnight-20261016/report/`.
- Repetición portable de C con su código histórico: `bash scripts/reproduce_benchmark_20261016.sh plan` y después `run`.
- Runner general para nuevos ensayos: `scripts/benchmark_presentation.sh`.
- Diseño y diagnóstico: [método](overnight-benchmark-method.md).
- Parámetros y ejecución: [benchmark](benchmark-presentation.md).

Los artefactos grandes permanecen locales. Los dos errores de inicialización oficiales se conservaron y se repitieron tras reparar el layout congelado, sin cambiar el solver. No se cuentan como resoluciones. Los fallos del piloto A permanecen en los resultados. Las semillas y copias del código permiten inspeccionar el experimento; nuevas respuestas de AWS pueden variar.
