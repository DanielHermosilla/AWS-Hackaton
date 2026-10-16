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
