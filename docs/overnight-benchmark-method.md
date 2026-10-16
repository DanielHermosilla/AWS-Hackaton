# Campaña nocturna del 16 de octubre de 2026

Base: `origin/main` en `94a4e1d9fbaab94756b731661a30afb588a03061`.
Los cambios experimentales están en `codex/benchmark-presentation`. Los artefactos
locales se guardan en `artifacts/overnight-20261016/`; contienen snapshots del
código, entradas, manifiestos, salidas, logs nativos y consultas de Bedrock.

## Desarrollo y diagnóstico

La fase A probó 48 combinaciones locales: 40, 80, 120 y 200 clientes, dos
familias sintéticas y seis políticas, con 15 segundos por resolución. Es
desarrollo, no una evaluación del LLM. Cuatro corridas de 200 clientes fueron
interrumpidas por el supervisor; permanecen en los datos.

Una repetición con `faulthandler` y el muestreador nativo de macOS encontró el
tiempo dentro de `SCIPflattenVarAggregationGraph`, durante el presolve del
subproblema de recombinación de rutas. La corrección desactiva presolve y
multiagregación únicamente en ese subproblema primal de presupuesto corto.
La repetición terminó en 15,32 s, con 108/200 entregas y validación física.
No cambia las rutas admisibles, las cotas ni el pricing exacto del maestro.

Las reconstrucciones completas por zonas produjeron cero candidatos factibles
en varios casos con ventanas cruzadas. Se añadió `electric_local`, que modifica
rutas ya factibles. En tres incumbentes de desarrollo mantuvo todas las entregas:

| Clientes | Antes, kWh | Después, kWh | Tiempo local, s |
|---:|---:|---:|---:|
| 40 | 43,02573 | 42,89794 | 0,018 |
| 80 | 49,44153 | 48,70886 | 0,577 |
| 120 | 53,73607 | 51,82443 | 0,638 |

Estos ensayos justifican ofrecer la heurística al controlador. No acreditan
por sí solos una mejora del LLM: el piloto también puede elegirla sin AWS.
Se corrigió además el contexto para que un arranque parcial posterior no
reemplace las rutas del mejor incumbente conocido.

Un segundo ensayo de desarrollo encontró que la inserción física de todos los
clientes flexibles en todas las posiciones consumía su presupuesto sin cerrar
rutas completas. `window_waves` prioriza hasta 16 posiciones prometedoras por
cliente y conserva el pricing exacto sin ese límite. En la semilla de desarrollo
0 de la familia `crossed`, produjo rutas completas para 40, 80, 120 y 200 clientes
en 0,046; 0,393; 0,403 y 1,296 s de trabajo heurístico respectivamente. No son
tiempos del pipeline completo ni pruebas de optimalidad. Los ensayos fallidos
anteriores están en `diagnostics/waves`; los nuevos, en `diagnostics/waves-v2`.

## Comparación posterior

Cada fase nueva congela código y semillas antes de ejecutar. Las semillas de
desarrollo y evaluación sintética son disjuntas; no se proporciona el testigo
generador al motor ni al LLM. Son demostraciones sintéticas dirigidas, no una
muestra representativa del ruteo real.

Se conserva `standard`, una política fija elegida en el piloto, reglas locales,
AWS y una ablación de AWS sin propuestas de rutas ni selección del nuevo
portafolio. Todas conservan la física, el presupuesto y el objetivo
lexicográfico. Se informan fallos, pérdidas, costes desconocidos y timeouts.

La instancia `evaluation` oficial se resuelve únicamente con código congelado;
sus resultados no seleccionan heurísticas. La preparación desde CSV utiliza
GraphML y un resumen eVED existentes: su tiempo no incluye la descarga original
de OSM ni la adquisición de históricos.

Las estimaciones optimistas de CO₂ y USD se distinguen del efecto causal del
LLM. El ahorro energético entre políticas requiere los mismos clientes
atendidos; las entregas adicionales se presentan como cobertura, sin convertir
un recorrido más corto por atender menos clientes en ahorro.

## Estudio posterior de callbacks

En un diagnóstico de desarrollo con 200 clientes, el constructor completó
las entregas a los 8,42 s. El aviso `first_full_service` llegó al controlador
a los 18,69 s: el motor esperaba a que terminara la mejora inicial.
La variante posterior emite el aviso durante la construcción. Si la primera
consulta AWS sigue en vuelo, conserva ese evento y lo envía desde un callback
posterior cuando el trabajador queda libre. Respeta el mismo límite de dos
llamadas y el presupuesto temporal; no consulta por cada nodo del árbol.

Otro caso pidió `electric_local` durante 25 s, pero ejecutó 20 mejoras y
consumió aproximadamente 5 s entre las reconstrucciones. Había dos límites
adicionales: el tramo de heurística disponible y un máximo de 20 mejoras en
el código. La variante posterior elimina ese máximo de mejoras, conserva el
plazo temporal y permite reanudar una pasada interrumpida. Una pasada sin
mejora solo agota el vecindario heurístico explorado: no prueba optimalidad.
El prompt explica que `rebuild_seconds` no amplía el tramo padre ni recupera
tiempo que ya gastó la época de pricing.

El estudio D compara ambas versiones en instancias nuevas, con las mismas
rutas factibles y 30 s por corrida. Incluye reglas locales en ambas versiones
y AWS en ambas versiones. Sus resultados se presentan aparte de la cohorte C
de 45 s; no se mezclan presupuestos ni versiones para calcular una mejora.
Antes de ejecutar la semilla 1301 se registraron doce ensayos adicionales:
la política fija `waves`, AWS partiendo de esa misma política y la misma
configuración AWS con los callbacks anteriores. La política inicial procede
del piloto C, no de resultados de esa semilla. El plan completo contiene
32 corridas y queda en `phase-d/plan.json`; su registro previo está en
`phase-d/prospective-extension.json`.

## Recuperación de las campañas oficiales

Los dos primeros lanzamientos oficiales sobre la copia congelada C fallaron
antes de resolver: el registrador de procedencia buscaba `uv.lock` junto al
árbol `src`, mientras que el código se había congelado bajo `source`.
Se copió el mismo lockfile y se creó `src -> source`, sin modificar Python
del solver. La repetición se programó después del estudio de flota, en serie.
Los intentos iniciales permanecen en `remaining-sequence.json` y la repetición
en `official-recovery.json`; no se cuentan los errores de inicialización como
benchmarks resueltos.
