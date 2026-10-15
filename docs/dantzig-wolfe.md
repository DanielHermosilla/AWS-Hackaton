# Maestro por rutas sin H

`--solver scip-routes` es el backend predeterminado. Utiliza PySCIPOpt, sin
construir el modelo posicional, elegir H ni limitar visitas a estaciones.
Pyomo y [GCG posicional](dantzig-wolfe-positional.md) permanecen como referencias.

## Formulación

Sea \(\mathcal R_k\) el conjunto de recorridos finitos físicamente factibles de
\(k\), sin límite artificial de longitud. Incluye recargas continuas, saturación,
calles repetidas, retornos intermedios, tránsito sin entrega y todas las opciones
operacionales. La ruta inactiva se incluye solo si satisface la reserva final.
Para cada ruta, \(a_{ir}\) indica servicio y
\(c_r=b^{ini}+Q_r-b^{final}_r\) es energía neta efectiva.

\[
\sum_{r\in\mathcal R_k}\lambda_{kr}=1,\qquad
\sum_{r\in\mathcal R_k}a_{ir}\lambda_{kr}=z_{ki},\qquad
\sum_k z_{ki}\le1,\qquad z_{ki}\in\{0,1\},\quad\lambda_{kr}\ge0.
\]

Primero maximizar \(\sum_{ki}z_{ki}\); después fijar el cumplimiento encontrado
y minimizar \(\sum_{kr}c_r\lambda_{kr}\).

**Equivalencia entera:** una combinación convexa de vectores binarios cuyo
resultado es entero solo mezcla vectores idénticos. Con \(z_k\) entero, todas
las columnas positivas de \(k\) atienden el mismo subconjunto. Seleccionar la
de menor energía recupera una ruta factible sin empeorar el objetivo.
SCIP ramifica en asignaciones \(z\); los enlaces afectan también columnas futuras.

El maestro completo convexifica la proyección local de cada vehículo sobre
entregas y coste. **No es ideal globalmente:** el acoplamiento de vehículos
puede producir soluciones fraccionarias. Ni DFJ ni una familia limitada de
cortes describen todas las facetas de la envolvente convexa de la flota.

## Pricing y certificados

`route_resources.py` explora etiquetas por nodo y conjunto atendido. Cada
etiqueta conserva un poliedro de batería \(b\), tiempo \(t\) cuando hay jornada,
y carga acumulada \(Q\). La operación de carga representa todo
\(0\le q\le B-b\); no discretiza SoC ni obliga a cargar completamente.
Saturación y ventanas se dividen en regiones afines antes de convexificar.
Los vértices conservan testigos de cargas para reconstruir recorridos.

La dominancia exige mismo nodo/conjunto atendido y acredita, para cada estado
descartado, otro con más batería, no más tiempo y no más \(Q\). Comparar solo
energía consumida sería incorrecto con saturación. Se usan pequeños LP de
`scipy.optimize.linprog` para comprobar combinaciones convexas dominantes.
Antes del LP se comprueban cotas por coordenada; para dos vértices se resuelve
la intersección de intervalos del peso convexo y se verifica el testigo sin
relajar tolerancias. `vertices_only` admite una dominancia más conservadora:
puede retener etiquetas redundantes, pero no elimina rutas adicionales.
El checker reproduce por separado la física de las rutas reconstruidas.

La política puede recorrer la cola en anchura o profundidad. Se reutilizan
etiquetas entre duales y fases. No hay máximo de movimientos,
estaciones ni etiquetas. La exploración puede crecer exponencialmente y no
se garantiza resolución rápida para toda red. Un presupuesto temporal blando
puede interrumpir el pricing, especialmente con ciclos regenerativos sin jornada.
Eso **no** prueba ausencia de columnas ni infactibilidad.

`pricerredcost` y `pricerfarkas` añaden variables a todas sus filas modificables.
Si se interrumpe el pricing, no se usa el LP restringido como cota global.
Permanecen cotas analíticas: entregas \(\le |C|\), energía \(\ge0\) con arcos
no negativos, o \(\ge|K|(b^{ini}-B)\) en general. Los ciclos regenerativos no
vuelven ilimitadamente negativo este objetivo, pues \(Q\ge0\) y \(b^{final}\le B\).

Se pueden incorporar al inicio cortes subset-row para ternas \(S\):

\[
\sum_{kr}\left\lfloor\frac{\sum_{i\in S}a_{ir}}2\right\rfloor\lambda_{kr}\le1.
\]

Toda columna futura recibe ese coeficiente y su contribución al coste reducido.
Son válidos por unicidad de servicio y recuperación entera de rutas. Se desactivan
cortes genéricos del maestro que no implementen coeficientes de columnas futuras.
No se usa el separador de GCG que exigía un maestro de otro tipo.

`route_heuristics.py` añade dos aceleraciones para casos no negativos y sin
restricciones temporales. Una inserción por coste o regret construye rutas
completas de flota sin recargar, validadas sin H; no altera la disponibilidad
de recargas del modelo. Si atiende todos los clientes, la primera fase queda
probada por el testigo y la cota cardinal. Su energía no queda probada óptima.
Los inicios tienen un presupuesto fijo de 0,5 segundos dentro del tiempo total.
Se conserva primero un arranque por inserción barata y se informa al LLM junto
con el presupuesto restante. La estrategia elegida puede añadir candidatos,
pero solo reemplaza al incumbente si mejora entregas o, a igual cumplimiento,
energía. El presupuesto de 0,5 segundos es compartido, no se duplica.

El pricing opcional `heuristic_then_exact` busca primero columnas por inserción
guiada por duales de clientes y ternas, con hasta 0,25 segundos por llamada
dentro del tiempo restante. Si no añade columnas, vuelve al oráculo exacto.
No se emite un certificado por agotar inicios o no encontrar una mejora heurística.
Regeneración, recargas continuas, ventanas y revisitas siguen en el oráculo.
Las otras instancias omiten estas inserciones y mantienen el pricing general.

## Reducción certificada rápida

Se verifica métrica dirigida no negativa, incluyendo cargadores y pares
inalcanzables, ausencia de jornada/ventanas/reserva final adicional, y un tour
completo de coste \(U\le b^{ini}-\underline b\).

Un óptimo de flota cuesta como máximo \(U\). Concatenar rutas y quitar paradas
sin entrega no aumenta consumo por la desigualdad triangular. El tour obtenido
cabe en la batería inicial. Existe entonces un óptimo con un vehículo activo
sin recargar y los demás inactivos. El testigo heurístico no queda probado óptimo.

En este caso se resuelve DFJ dirigido: variables de arco, grados y cortes de
subtours. Se añaden componentes desconectadas y se resuelve hasta obtener un
tour o agotar tiempo. Cada problema intermedio es una relajación con cota válida.
No usa MTZ, posiciones ni Big-M de batería.

En la instancia local de 20 clientes: testigo de 11,67963408 kWh, óptimo de
10,55774084 kWh, 420 binarias, 3 rondas y 9 cortes en el primer ensayo.
El certificado es sobre caminos fijos disponibles; no recupera opciones
eliminadas por Dijkstra.

## Una decisión estratégica de Bedrock

Las políticas comparten formulación, reducción certificada, recursos y pruebas:

| Política | Acción |
|---|---|
| `standard` | Valores explícitos de `RoutePolicy`, sin AWS |
| `deterministic` | Lotes de 20 columnas y hasta 50 ternas, sin AWS |
| `adaptive` | Una llamada previa, compartida por ambas fases |

El LLM recibe el catálogo de parámetros de la biblioteca SCIP instalada.
`scip_parameters` permite más de 1.200 controles en el maestro general:
branching, heurísticas, selección de nodos y opciones de LP. DFJ expone además
presolve, separación, propagación y conflictos: más de 2.000 controles.
Los nombres disponibles dependen de la versión; sus tipos y rangos se validan
con SCIP antes de aplicarlos. Presets de heurísticas/presolve/separación también
pueden modificar numerosos parámetros nativos; se registran sus efectos reales.

Además elige arranque por inserción, número de inicios, pricing heurístico seguido
de exacto, orden de exploración, dominancia, ternas y lotes. El perfil identifica
qué aplica. Parámetros globales de recursos, semillas, tolerancias, comprobaciones
físicas y certificados permanecen fijados por el usuario y el motor. En el maestro
general siguen bloqueadas las reducciones/cortes nativos sin compatibilidad
implementada con columnas futuras. Una propuesta inválida completa produce
fallback, sin aplicar parcialmente parámetros. Solo los campos adicionales
con valor `null` se omiten como anotaciones sin acción, registrándolos en
`ignored_null_fields`; un campo desconocido con valor o un parámetro nativo
inválido rechaza la propuesta completa. El JSON original se conserva.

Los callbacks de pricing son locales. No hay AWS por nodo, corte o ronda.
Consultas excepcionales durante la búsqueda quedan fuera de esta implementación:
requerirían un evento de utilidad medible, acciones seguras y presupuesto.
`--llm-max-calls` se conserva por compatibilidad; `scip-routes` hace como máximo
una llamada incluso si se configura un valor superior.

Región inicial `us-east-1`, perfil `hackathon`; modelo/perfil de inferencia
parametrizable y obligatorio para `adaptive`. Se registran uso y tiempo;
coste monetario desconocido sin tarifa verificada. No se guardan claves.
El script de ensayo propone Claude Opus 5 por solicitud del usuario, conservando
la selección por argumento/entorno. Para Claude se omite temperatura;
`--llm-effort medium`, `--llm-max-output-tokens 4096` y
`--llm-timeout-seconds 30` permiten una propuesta más amplia. La llamada y la
preparación de arranques consumen parte del mismo presupuesto de resolución.
El catálogo tiene un límite de entrada de 160.000 bytes para esta política.
Se agrupan prefijos repetidos sin eliminar parámetros; la respuesta debe usar
nombres completos con `/`. `*.parameters.json` registra los cambios nativos
efectivos, incluidos los presets, y `llm-decision.json` registra las decisiones
del controlador. Ambos complementan los prompts y las respuestas originales.

## Ejecución

```bash
uv sync --locked --extra dw
export BEDROCK_MODEL_ID='us.anthropic.claude-opus-5'
bash scripts/benchmark_dw.sh \
  --instance artifacts/hackathon/service-instance.json \
  --road-instance artifacts/hackathon/instance.json \
  --path-archive artifacts/hackathon/service-paths.json \
  --initial-solution artifacts/hackathon/service-instance.start.json \
  --bedrock-model "$BEDROCK_MODEL_ID" \
  --llm-timeout-seconds 30 --llm-effort medium \
  --time-limit-seconds 60 --threads 1 --seeds 0 1 2 \
  --output-dir artifacts/benchmark-routes
```

El benchmark usa `scip-routes`, procesos separados, orden pareado aleatorizado,
hashes, logs y resúmenes. No mezclar resultados GCG anteriores al reanudar.
`service-graph` prepara por defecto con `--service-movements none`; no elige H.

Los snapshots 1.0 retienen `movement_limit` por compatibilidad.
`formulation.movement_limit_used` y `solve.search.movement_limit_used` son `null`;
el valor heredado no restringe optimización ni validación. Las rutas y su
expansión vial tienen longitud variable y no se rellenan para igualarlas.

## Referencias

- SCIP: [pricers, Farkas, filas modificables y pricing interrumpido](https://www.scipopt.org/doc/html/PRICER.php).
- Jepsen et al.: [Subset-Row Inequalities Applied to the VRPTW](https://pubsonline.informs.org/doi/10.1287/opre.1070.0449).
- Desaulniers et al.: [Exact Algorithms for Electric Vehicle-Routing Problems with Time Windows](https://pubsonline.informs.org/doi/10.1287/opre.2016.1535).

El diagnóstico del LLM adapta LLM4MIP; ver [procedencia](llm4mip-adaptation.md).
El oráculo poliedral es implementación del proyecto: no se afirma reproducir
literalmente algoritmos o resultados computacionales de esos artículos.
