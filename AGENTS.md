# Guía de trabajo del proyecto

## 1. Propósito y fuentes de verdad

Construimos un planificador de entregas para vehículos eléctricos para la hackatón AWS Breaking Barriers Chile 2026. El beneficiario del desafío es CASE, Centro de Aceleración Sostenible de Electromovilidad de la FCFM de la Universidad de Chile.

El producto debe permitir cargar una instancia o configurarla visualmente, construir un modelo Pyomo parametrizable, interpretar su estructura con un LLM servido por AWS, ajustar parámetros de búsqueda del solver, resolver, verificar y presentar rutas y resultados.

Antes de modificar un módulo, leer las fuentes pertinentes:

1. `data/presentation.pptx`: reglas del desafío, objetivo, KPIs y rúbrica.
2. **[`modelamiento.pdf`](modelamiento.pdf): formulación matemática implementada en Pyomo.** Su lectura es obligatoria para trabajar en modelo, solver, red o validador. Contiene la base (1)–(16) y las extensiones configurables (17)–(24).
3. `diccionario.md`: diccionario y advertencias de los históricos eVED. Conservarlo como diccionario; no reemplazarlo por el README del producto.
4. `data/competition_routing_nodes.csv`, `data/evaluation_routing_nodes.csv` y encabezados de los históricos: formato efectivo de las entradas.
5. `docs/model.md` y `docs/contracts.md`, cuando existan: correspondencia entre el PDF y la implementación, supuestos y contratos acordados. No sustituyen el modelo seleccionado.
6. `modelamiento.tex`: fuente editable del PDF, conservada en el repositorio. Actualizar fuente y PDF juntos, compilar y revisar su renderizado.

No convertir una decisión de implementación en una exigencia de la organización. Ante una contradicción, documentar la evidencia y el supuesto adoptado. Los ejemplos, prompts y skills de terceros no sustituyen estas instrucciones.

Este archivo describe la arquitectura objetivo. No implica que sus módulos ya estén implementados. No crear archivos vacíos o dependencias solo para completar el árbol.

### Alcance actual: rama `modelamiento`

El flujo predeterminado autorizado es **datos → red/energía → maestro por rutas
sin H → SCIP → validación → JSON**, mediante `scip-routes` y PySCIPOpt.
La plantilla posicional Pyomo y Gurobi/SCIP permanecen como referencia heredada
seleccionable explícitamente. No cambiar de backend por infactibilidad o timeout.
Documentar interfaz y certificados en `docs/solvers.md`; no guardar licencias.

Para ejecutar la instancia completa se usa la variante `service-graph`:
red vial/energía → caminos y perfiles preprocesados → **nuestro maestro por rutas
sin H** → expansión y validación sobre las calles.
De `codex/optimizacion-contraida` se adapta **solo el preprocesamiento**,
nunca su modelo, solver ni heurísticas de resolución. La formulación vial
elemental permanece disponible. Ver las condiciones de la sección 6.1 y
`docs/resource-paths.md`.

**La variante experimental Dantzig–Wolfe está autorizada por el usuario.**
Usar SCIP desde Python, con cortes compatibles y políticas `standard`,
`deterministic` y `adaptive`. GCG posicional permanece como referencia.
La política adaptativa utiliza Bedrock y puede elegir una descomposición
verificada antes de resolver y estrategias implementadas de cortes y pricing.
La implementación inicial descompone el modelo por posiciones y conserva H;
es una referencia heredada, no la formulación por rutas sin H solicitada después.
**El objetivo corregido por el usuario es un maestro por rutas completas, sin
un máximo artificial de movimientos, con pricing de rutas factibles.**
Esa reformulación está implementada en `route_solver.py` y `route_resources.py`;
el benchmark usa ahora `scip-routes`. Conservar datos,
restricciones físicas, objetivos y criterios de certificación. No ocultar H
calculándolo automáticamente ni sustituirlo por un límite arbitrario de estaciones
o etiquetas. Convexificar cada vehículo no acredita idealidad del problema conjunto.
Nunca ejecutar código generado por el LLM ni aceptar sus afirmaciones como
certificados. El motor debe conservar pricing exacto o cotas válidas,
también ante fallos de AWS. Las llamadas reales deben estar acotadas y
registradas; una prueba con dobles no acredita acceso a AWS.
La política vigente está en `route_policy.py`: **una llamada Bedrock antes de
resolver, compartida por ambas fases**, ninguna llamada remota por nodo, corte
o ronda de pricing. Consultas excepcionales futuras requieren un evento y
presupuesto explícitos; no están habilitadas. `RoutePolicy` solo admite cortes,
lotes y branching implementados. `dw.py`, `dw_bridge.py`, `dw_callbacks.py`
y su controlador conservan el experimento GCG heredado.
`movement_limit` de snapshots 1.0 es metadato heredado en `scip-routes`, sin
efecto en pricing, arranque ni validación. No construir `model.py` en ese flujo.
Conservar recargas parciales, regeneración, tiempos, revisitas y retornos al
depósito. El pricing mantiene recursos continuos y no impone límites de etiquetas.
El maestro ramifica en asignaciones binarias de clientes; sus pesos de rutas son
continuos. Los cortes subset-row incorporan coeficientes de columnas futuras.
Pricing interrumpido no certifica el LP restringido; usar solo cotas válidas.
La reducción a tour DFJ exige verificar métrica dirigida, costes no negativos,
ausencia de jornada/ventanas/reserva final adicional y un tour completo que cabe
en la batería inicial. Nunca aplicarla por una sugerencia no verificada del LLM.
Región inicial `us-east-1`, perfil AWS inicial `hackathon`, ambos configurables.
El modelo/perfil de inferencia es entrada obligatoria de la política adaptativa.
El benchmark compara las tres políticas del mismo motor y snapshot, registra
llamadas reales y distingue un fallback de una corrida adaptativa efectiva.
El flujo Gurobi/SCIP original continúa disponible como referencia.
La UI queda para una etapa posterior.
Estas decisiones concretan el alcance actual; las secciones de producto y AWS
describen el objetivo posterior. `STRUCTURE.md` explica la implementación presente
y `README.md` contiene comandos ejecutables. Documentar las ecuaciones Pyomo con
sus números del PDF y contrastarlas con pruebas independientes, no solo con
restricciones del mismo modelo.

## 2. Requerimientos oficiales y límites del alcance

- Escenario oficial: **dos Nissan Leaf 2013**, cada uno con **60 % de SoC inicial**.
- Ambos vehículos parten y terminan en el centro de distribución.
- Las rutas deben mantener energía suficiente para continuar la operación. El retorno y la batería son condiciones de factibilidad, no penalizaciones que se puedan compensar con más entregas.
- Se permite usar puntos de recarga cuando sea necesario.
- Objetivo principal: **maximizar entregas cumplidas con rutas factibles**.
- Desempate: **menor consumo energético total y menor tiempo de cómputo**.
- La metodología es libre. Nuestro método principal será un MILP parametrizable construido en Pyomo.
- Un mismo código debe funcionar sobre la instancia reservada reemplazando las entradas. Prohibido depender de nombres de archivo, IDs, coordenadas o soluciones de una instancia concreta.
- Debe ser posible aumentar nodos y vehículos mediante configuración, sin reescribir el modelo.

Discrepancias y omisiones verificadas:

- Algunas diapositivas dicen “20 nodos”, pero la diapositiva 6 y los CSV actuales contienen **1 depósito + 20 locales + 60 cargadores = 81 nodos**. Descubrir cantidades desde la entrada.
- En los dos CSV locales solo cambian las coordenadas de los 20 locales. El PPTX permite que el grafo reservado cambie también depósito y cargadores: el código debe soportarlo.
- Los CSV entregan ubicaciones, no el grafo de calles ni matrices de tiempo, distancia o consumo.
- Tres EV históricos para entrenar no son los dos vehículos operacionales del concurso.
- El PPTX no fija capacidad útil, reserva mínima, jornada máxima, ventanas horarias, tiempos de servicio, capacidad de paquetes, colas ni un límite numérico de cómputo. No inventarlos como reglas oficiales.
- El README menciona `data/processed/`; en este checkout los CSV están en `data/`. No crear una segunda copia de los datos para reproducir esa ruta.

Mantener los supuestos en la configuración y en cada resultado. La capacidad nominal de 24 kWh mencionada por el diccionario no acredita por sí sola una capacidad útil de 24 kWh. Parametrizar capacidad, reserva y compatibilidad. El modelo elegido en `modelamiento.pdf` supone que el depósito no ofrece recarga y permite dejar un vehículo inactivo mediante el arco artificial `(0, 0)`; conservar esos supuestos en la versión base.

## 3. Producto y flujo único de ejecución

Las dos entradas de usuario deben converger al mismo contrato `ProblemInstance`:

1. **Archivo**: cargar un CSV de nodos con el formato existente y completar parámetros que ese archivo no contiene.
2. **Interfaz gráfica**: configurar depósito, destinos, cargadores, direcciones/coordenadas y parámetros de flota. Validar y confirmar resultados ambiguos de geocodificación. Permitir exportar la instancia.

Flujo común:

```text
CSV o formulario
  -> normalización y validación de instancia
  -> red vial y estimaciones de energía
  -> modelo Pyomo
  -> perfil estructural y propuesta de tuning mediante AWS
  -> validación de parámetros del solver
  -> resolución lexicográfica
  -> comprobación independiente de factibilidad
  -> JSON de resultados y visualización
```

CLI e interfaz usan el mismo pipeline. La UI no construye restricciones, modifica parámetros del solver directamente ni calcula una versión alternativa de los KPIs.

El modelo es una plantilla de nuestra familia de problemas. **El LLM no genera un modelo nuevo por consulta ni cambia su significado.**

## 4. Arquitectura simple y modular

Priorizar **código simple, legible y suficiente para el caso real**. Evitar overkill y no recrear la rueda.

- Un solo proyecto Python y un backend organizado por responsabilidades.
- Pyomo para modelar. Usar una integración existente con el solver, no implementar branch-and-bound, presolve o un protocolo propio.
- Para el MVP, usar **Streamlit** como interfaz y un mapa integrado con una biblioteca existente. El backend debe poder ejecutarse sin Streamlit.
- **SCIP/PySCIPOpt es el backend del maestro sin H**. Gurobi y SCIPAMPL conservan la referencia posicional Pyomo. Usar branch-and-bound nativo, no implementarlo de nuevo.
- Usar `boto3` para AWS y estructuras validadas, preferentemente Pydantic, para los contratos. Usar bibliotecas existentes para CSV, grafos y mapas.
- No agregar microservicios, colas, Kubernetes, una base de datos, un framework de agentes, varias capas de repositorios o interfaces genéricas sin una necesidad demostrada.
- Preferir funciones pequeñas y tipos explícitos. Extraer una abstracción cuando exista reutilización real, no por anticipación.
- Mantener dependencias y versiones en `pyproject.toml` y un único lockfile. No mezclar gestores ni replicar entornos.
- Usar nombres en inglés para código y campos de contratos; documentación y UI principal en español. Unidades explícitas en nombres, por ejemplo `energy_kwh` y `runtime_seconds`.

Estructura objetivo:

```text
AGENTS.md
README.md                         # instalación, ejecución y demo del producto
diccionario.md                    # diccionario original de datos
data/presentation.pptx             # enunciado original local
modelamiento.pdf                  # formulación matemática que se implementará
STRUCTURE.md                      # mapa mínimo de archivos y funciones actuales
pyproject.toml
.env.example                      # nombres de variables; nunca secretos
config/
  default.json                    # escenario, presupuestos y opciones documentadas
src/ev_routing/
  contracts.py                    # esquemas compartidos y sus validaciones
  config.py                       # configuración del problema, solver y AWS
  inputs.py                       # CSV/formulario -> ProblemInstance
  network.py                      # geocodificación, red dirigida y caché
  energy.py                       # integración, estimación y perfiles energéticos
  operations.py                   # coeficientes del escenario y calendario de rutas fijas
  service_graph.py                # Dijkstra entre servicios y expansión a calles
  heuristics.py                   # certificado rápido de H e incumbente inicial, sin MILP
  model.py                        # construcción de la plantilla Pyomo
  solve.py                        # adaptador del solver y fases lexicográficas
  validation.py                   # comprobador independiente de la solución
  metrics.py                      # KPIs y comparaciones con referencias
  pipeline.py                     # coordinación de los módulos
  cli.py                          # ejecución reproducible sin interfaz
  llm/
    bedrock.py                    # cliente AWS, límites, errores y uso de tokens
    tuning.py                     # perfil -> propuesta -> opciones validadas
ui/
  app.py                          # formulario, carga, mapa y resultados
tests/
  fixtures/                       # instancias sintéticas pequeñas
docs/
  model.md                        # correspondencia PDF/Pyomo y alcance de certificados
  service-graph.md                # preprocesamiento, supuestos y auditoría vial
  contracts.md                    # contratos y ejemplos mínimos
  llm4mip-adaptation.md            # procedencia y adaptación del upstream
data/                             # datos originales locales, ignorados por Git
artifacts/                        # resultados/cachés locales, ignorados por Git
```

Crear módulos adicionales solo cuando el tamaño o la responsabilidad lo justifiquen. No publicar datos, credenciales, cachés, binarios de solver ni resultados masivos en Git. No modificar ni borrar originales al preprocesar.

## 5. Contratos y datos

El archivo `contracts.py` y su documentación son responsabilidad compartida coordinada. Acordar contratos mínimos antes de que UI, modelo y LLM implementen sus partes en paralelo.

Contratos mínimos:

- `ProblemInstance`: versión, nodos, flota, parámetros, red/perfiles y procedencia.
- `SolverConfig`: backend, presupuesto, recursos, semilla y opciones aprobadas.
- `TuningRequest`: resumen estructural, capacidades del solver, parámetros permitidos y presupuesto.
- `TuningProposal`: opciones propuestas, explicación breve y advertencias; sin código ejecutable.
- `RunResult`: estados, rutas, validación, certificados, KPIs, tiempos y trazabilidad.

Separar `problem_config` de `solver_config`. Capacidad, reserva, objetivos, grafo y límite de movimientos pertenecen al problema. No son parámetros que el LLM pueda modificar para aparentar una mejora.

Formato actual de nodos, CSV UTF-8 con posible BOM:

```text
node_id,node_type,latitude,longitude,address,network,total_ports,dc_fast_ports,level2_ports,connector_types,max_power_kw
```

- `node_id`: string opaco, único y no vacío. No asumir numeración consecutiva.
- `node_type`: `base`, `visit` o `charger`; el MVP requiere exactamente una base.
- Coordenadas finitas y dentro de rangos geográficos válidos.
- Campos de cargadores vacíos en bases/locales son legítimos.
- Puertos: enteros no negativos; informar inconsistencias entre total, DC y nivel 2.
- Conectores: separar por `;` y normalizar espacios.
- `max_power_kw`: máximo reportado para la estación. No equivale a potencia por conector ni potencia aceptada por el vehículo.
- Validar IDs duplicados, referencias inexistentes, parámetros imposibles y problemas de cobertura. Devolver errores accionables, sin correcciones silenciosas.

Construir una red vial dirigida con procedencia y cobertura documentadas. Las coordenadas y las trayectorias históricas no equivalen a conectividad completa. La distancia en línea recta puede ser una referencia exploratoria, pero no debe presentarse como una ruta vial validada.

Reglas para eVED:

- Identificar viajes con `(VehId, Trip)`, ordenar por tiempo y calcular intervalos dentro de cada viaje.
- Integrar energía con tiempo real: `sum(-current_a * voltage_v * delta_t_seconds / 3.6e6)`. La columna `Energy_Consumption` también debe multiplicarse por `delta_t_seconds`.
- No sumar directamente las filas de `Energy_Consumption`.
- Conservar regeneración y limitar lo efectivamente almacenado por la batería. No convertir todos los valores negativos o faltantes a cero.
- Tratar huecos temporales grandes mediante una política explícita y registrada.
- Entrenar energía EV con señales adecuadas de EV; no equiparar consumo ICE/HEV con consumo del Leaf.
- Separar entrenamiento/validación por viajes, vehículos o períodos. No dividir aleatoriamente filas correlacionadas.
- Corriente, voltaje y consumo observado sirven para construir etiquetas; no están disponibles para una ruta futura. Otras variables futuras requieren predicciones o escenarios explícitos.
- No ajustar modelos ni escoger configuraciones mirando desempeño en `evaluation`. El código puede leer la instancia de evaluación para resolverla, pero no aprender de sus resultados de evaluación.
- Cargar solo columnas/datos necesarios. Reutilizar cachés identificadas por contenido y configuración; no reprocesar los históricos completos en cada clic.

## 6. Modelo Pyomo, factibilidad y certificados

La reformulación vigente sin H está en (25)–(29) del PDF y
`docs/dantzig-wolfe.md`. Las reglas posicionales siguientes describen la
referencia Pyomo. Las reglas físicas y de certificación rigen en ambos modelos;
la exigencia de H no rige en `scip-routes`.

**Implementar la formulación de [`modelamiento.pdf`](modelamiento.pdf), manteniendo sus parámetros, variables, dominios y restricciones.** No sustituirla silenciosamente por otra formulación de TSP/VRP ni por una aproximación que cambie las rutas factibles.

Mantener una única plantilla Pyomo parametrizable. Documentar en `docs/model.md` la correspondencia entre las ecuaciones del PDF y los componentes de Pyomo. Toda extensión o reducción del modelo debe explicar su efecto y distinguirse de la versión base.

- El PDF modela un grafo vial dirigido `G = (V, A)` con intersecciones y tramos elementales. Los 81 puntos de los CSV son ubicaciones de servicio, no toda la red vial `V`.
- Las variables `z_ikr` indican ubicación, `x_ijkr` seleccionan calles, `a_ikr` indican entregas y `y_i` contabiliza clientes atendidos. Mantener la separación entre desplazamiento y servicio.
- `H` es el máximo de movimientos por vehículo y corresponde a `movement_limit`. El índice de posición no sincroniza los relojes de los vehículos.
- Prioridad lexicográfica: maximizar entregas; después minimizar energía manteniendo el cumplimiento alcanzado.
- Cada entrega se cuenta como máximo una vez entre todos los vehículos. Pasar físicamente por una ubicación no debe implicar automáticamente atender una entrega.
- Las rutas son continuas y regresan al depósito. Calles y cargadores pueden repetirse cuando la representación lo requiera.
- El PDF permite retornos intermedios al depósito y volver a salir. No añadir una restricción de permanencia obligatoria después del primer retorno.
- Batería inicial `0.6 * B` en el escenario oficial; recarga solo donde esté habilitada y sea compatible.
- Respetar capacidad y reserva durante el recorrido completo. Un balance energético correcto en el destino no prueba factibilidad de los segmentos intermedios.
- Modelar la saturación de regeneración. Si se agregan caminos en arcos, conservar la información necesaria para reproducir su perfil energético y verificarlo. Justificar que la agregación preserva las opciones de recorrido del PDF; fijar caminos entre puntos de servicio puede restringirlas y no es automáticamente una reformulación equivalente.
- Distinguir energía neta efectiva de batería, energía incorporada a batería y electricidad comprada a la red.
- Usar nombres distintos para `movement_limit` y `time_horizon_seconds`. El primero restringe la representación de rutas; no es una jornada oficial.
- Indicar el alcance de la optimalidad: depende de la red, caminos disponibles, modelo energético y límites de representación. No extrapolar un certificado a un problema más amplio.
- La versión base no permite cargar en el depósito y no incorpora tiempos de servicio, ocupación ni jornada. Cualquier variante debe identificarse como extensión y actualizar su documentación.

En la primera fase, registrar mejor solución y cota de entregas. Si se agota el tiempo sin probar el máximo, la segunda fase puede mejorar energía fijando las entregas encontradas, pero debe declararse **mejora condicionada a ese cumplimiento**, no óptimo lexicográfico demostrado.

Guardar por fase: sentido del objetivo, incumbente, cota, gap reportado, estado de terminación y tiempo. No construir un único “gap óptimo” combinando fases incompatibles. No llamar óptima a una solución por haber terminado la ejecución.

Si el solver alcanza su límite con una solución factible, conservarla y validarla. Distinguir: óptimo probado, factible sin prueba de optimalidad, sin solución encontrada, infactibilidad probada y error de ejecución.

`validation.py` debe comprobar el resultado independientemente de las restricciones de Pyomo: continuidad, arcos permitidos, retorno, entregas únicas, SoC inicial, cargadores, capacidad/reserva en segmentos y balance energético. La UI solo presenta una ruta como factible cuando pasa esta comprobación. La factibilidad se refiere al modelo energético utilizado, no a una garantía sobre consumos reales inciertos.

Las metaheurísticas pueden servir después como referencia o para producir incumbentes compatibles, si hay evidencia de necesidad. No reemplazan el flujo principal Pyomo + solver solicitado ni justifican implementar otro solver desde cero.

### 6.1. Preprocesamiento por caminos mínimos de energía

**Alcance actualizado en `codex/investigacion-caminos-recursos`:**
`resource_graph.prepare_service_graph` es la preparación predeterminada sin H.
Usa Dijkstra únicamente con energías no negativas y sin jornada/ventanas.
En los demás escenarios elimina intersecciones componiendo perfiles exactos de
batería y conservando alternativas temporales. Depósito, clientes y cargadores
permanecen. Los límites de trabajo conservan intersecciones, nunca truncan
caminos o etiquetas. Los ciclos regenerativos útiles permanecen disponibles.
El pricing existente consume el multigrafo con `arc_id` y recursos continuos;
el maestro SCIP no cambia. Validar perfiles contra prefijos y expandir calles.
No aplicar dos veces el margen ni reutilizar perfiles de otro escenario.
Los snapshots 1.1 de `resource_paths` requieren `scip-routes`; la referencia
posicional los rechaza. Actualizar fuente y PDF (30)–(31) junto con cambios
físicos. `road_optimum_preserved` no reemplaza la prueba de ambas fases.
La caché y sus límites están en `docs/resource-paths.md`. No añadir llamadas LLM
por preparación o callback sin un ensayo que justifique su costo.

**El resto de esta sección describe la reducción original de Dijkstra y
continúa rigiendo cuando se selecciona esa variante.**

La implementación está en `src/ev_routing/service_graph.py` y su alcance en
`docs/service-graph.md`. Referencia: rama `codex/optimizacion-contraida`,
commit `2bac3ead47576a96de8175f38626ba647232b24c`, en particular `_csr` y
`scipy_multi` de `src/evrp/caminos.py`. Reutilizar únicamente el preprocesamiento.
Mantener el modelo y el adaptador de resolución propios de `modelamiento`;
no incorporar `milp.py`, `milp_compacto.py` ni la lógica de solver de esa rama.

Reglas de la variante:

- Conservar **depósito, todos los clientes y todos los cargadores** como nodos
  del grafo entregado a Pyomo. Descubrir sus cantidades desde la entrada.
- Construir una matriz dispersa CSR y usar `scipy.sparse.csgraph.dijkstra`
  con `directed=True` y peso `energy_kwh`. Ejecutar una búsqueda por servicio,
  procesando un origen por vez para limitar memoria. No construir una matriz
  densa de todas las esquinas ni ejecutar un algoritmo por cada par de servicios.
- Admitir únicamente energías viales **no negativas** y conservar explícitamente
  los arcos de energía cero. Rechazar entradas con regeneración; nunca convertir
  sus valores negativos a cero ni tomar valores absolutos para habilitar Dijkstra.
- Conservar los servicios aislados y omitir los pares ordenados inalcanzables.
  No inventar conexiones ni asumir que un camino puede recorrerse en sentido inverso.
- Guardar la secuencia vial de cada conexión y sumar su energía y distancia.
  Vincular `PathArchive` a los snapshots vial y compacto mediante SHA-256.
  Expandir y validar las calles del arranque y del resultado, además de comprobar
  el grafo compacto. Mantener separados el tiempo de preprocesamiento y el del solver.
- Pasar por un servicio dentro de un camino no implica entregar ni recargar.
  Para realizar esas acciones, el servicio debe aparecer como una parada explícita.
  Conservar recargas parciales, compatibilidad, batería inicial, capacidad,
  reserva, retorno y objetivo lexicográfico.

**Cuándo es válida la reducción.** Con energías fijas y aditivas por calle,
no negativas, independientes del SoC, hora y carga transportada, y sin otras
restricciones u objetivos que dependan del camino, reemplazar el recorrido entre
dos eventos consecutivos de entrega, recarga o depósito por uno de mínima energía
no aumenta el consumo. La batería solo disminuye entre recargas: si alcanza con
reserva al destino, también respeta la reserva en las calles intermedias.
Una llegada con más energía permite reducir la recarga siguiente para respetar
la capacidad, puesto que las cargas son parciales y no tienen un mínimo obligatorio.
Así, con un H de servicios suficiente, esta reducción conserva el valor óptimo
de entregas y energía del problema vial **sin un límite adicional de calles**,
bajo esas hipótesis. No conserva todos sus recorridos posibles.

**Límites que deben declararse.** En esta variante `H` cuenta traslados entre
servicios, no calles. No presentarla como equivalente al modelo del PDF con su
`H` vial original: un camino mínimo energético puede recorrer más calles que
una alternativa. Informar por separado si la expansión satisface aquel límite.
Los certificados emitidos corresponden a la representación y al H resueltos.
La regeneración y su saturación quedan fuera de esta variante, aunque la
formulación vial base las admite; el estimador actual de kWh/km ya utiliza
energías no negativas. Cambiar Dijkstra por otro algoritmo de caminos mínimos
no resuelve por sí solo los déficits intermedios ni la saturación.

Si se incorporan ventanas horarias, jornada, objetivos de tiempo/distancia,
costos dependientes de hora/SoC/carga u otras condiciones del recorrido,
revisar la reducción antes de reutilizar un único camino por par: el de mínima
energía puede dejar de ser suficiente. No afirmar optimalidad para esas extensiones
sin demostrar que se preservan sus decisiones factibles y objetivos.

### 6.2. Elección automática de H y solución inicial (referencia posicional)

`service-graph` prepara por defecto para rutas sin H (`--service-movements none`).
No llamar a `analyze_horizon` ni detener esa preparación por falta de certificado.
Lo siguiente solo rige para `auto` o un entero elegidos explícitamente.

`src/ev_routing/heuristics.py` implementa `analyze_horizon` y
`build_initial_solution`. Usar NetworkX para una construcción greedy desde
distintos nodos; no implementar otra metaheurística, resolver un MILP auxiliar
ni consultar soluciones previas para elegir H. La ejecución tiene un presupuesto
blando predeterminado de 0,5 segundos y como máximo 32 inicios, y termina al
obtener el testigo necesario. Registrar tiempo y cantidad de intentos.

La prueba para reducir H exige comprobar:

1. Variante de servicios, energías no negativas y desigualdad triangular
   dirigida, incluyendo cargadores y pares inalcanzables.
2. Una ruta que atienda **todos** los clientes con energía total
   `U <= initial_energy_kwh - reserve_kwh`.
3. Las hipótesis de la plantilla actual: batería homogénea, sin jornada, ventanas,
   capacidad de paquetes, obligación de utilizar todos los vehículos ni otros
   costos o restricciones que invaliden la eliminación de paradas.

Entonces existe un óptimo lexicográfico con `H = number_of_customers + 1`.
La ruta heurística es un testigo de factibilidad y una cota superior de energía;
**no queda certificada óptima por este argumento**. El certificado de H tampoco
es un certificado del modelo calle por calle.

Distinguir H suficiente de H mínimo. Solo afirmar mínimo si hay además una
prueba: por ejemplo, unir cualesquiera dos rutas con entregas reduce estrictamente
la energía y el consumo total cabe en una batería inicial. Si esa desigualdad
no es estricta, conservar únicamente la afirmación de suficiencia. Con un solo
vehículo o un solo cliente la necesidad de `|C| + 1` es inmediata cuando existe
el testigo completo. Sin clientes basta H=1. Sin cargadores compatibles, `|C|+1`
es suficiente por eliminación de paradas, aunque no puedan atenderse todos.

Si la búsqueda rápida no certifica un H pequeño, **no inventarlo ni lanzar
automáticamente un MILP gigantesco**. Informar el motivo y, cuando se verifican
las hipótesis, la cota conservadora
`(|C|+1) * (1 + max_k |F_k|)`. El modo `auto` se detiene antes de construir el
MILP. Un H numérico explícito permite un ensayo condicionado a ese límite;
registrar si está certificado y no sobrescribirlo silenciosamente.

La preparación escribe el análisis y una solución inicial ligada mediante SHA-256
al snapshot y su H. Verificar unicidad, batería y retorno con `validation.py`;
en la variante, expandir también las calles **antes** de enviar el arranque.
Rechazar un archivo inicial de otro snapshot, parámetros o H.

Gurobi recibe valores iniciales mediante `gurobi_direct` y `warmstart=True`,
sin fijar variables ni alterar restricciones. Registrar `submitted`, no
`accepted`, salvo evidencia de aceptación en el log nativo. La fase energética
reutiliza el mejor incumbente con el número de entregas fijado.
El adaptador actual `SCIPAMPL` no admite ese warm start: registrar `unsupported`
y conservar el incumbente como solución validada fuera del solver. No cambiar
de backend por esa limitación.

Ante timeout, ausencia de incumbente nativo o error, conservar el testigo
validado y declarar su origen. Mantener terminación, cotas, gaps y prueba de
optimalidad por fase; no presentar una ruta heurística como resultado encontrado
por un solver que no llegó a ejecutarse. No atribuir aceleración a este arranque
sin una comparación controlada.

### 6.2. Supuestos operacionales opcionales sobre Dijkstra

`ProblemInstance.operations` y la sección `operations` del JSON de configuración
controlan las extensiones (17)–(24) de `modelamiento.pdf`. Los valores neutros
reproducen la base; no activar supuestos sin declararlos. La configuración está
documentada campo por campo en `docs/operations.md`. El ejemplo
`config/operations.example.json` contiene valores ilustrativos, no mediciones.

- Tiempo de entrega común y excepciones por cliente: `service_seconds` y
  `service_seconds_by_customer`; cero desactiva su efecto.
- Jornada: `max_route_seconds`; `null` desactiva. Sin ventanas basta sumar
  viaje, servicio y recarga por vehículo; no crear relojes innecesarios.
- Tiempo de viaje: conservar tiempos explícitos de las calles y sumarlos en
  los caminos seleccionados. Si faltan, exigir `assumed_speed_kph` explícita.
  No usar automáticamente límites legales ni afirmar tráfico observado.
- Recarga: `include_charging_time`, potencia efectiva común
  `charging_power_kw`, excepciones `charging_power_kw_by_station` y
  `charging_efficiency`. Usar energía incorporada a batería y pérdidas
  coherentes. No equiparar potencia máxima de estación con potencia por
  conector/vehículo. Un escenario temporal con carga habilitada exige su duración.
- Reserva final: `final_reserve_soc`, o `null`; no reemplaza ni eleva
  automáticamente la reserva de posiciones intermedias.
- Margen de consumo: `energy_margin_fraction`, cero desactiva. Conservar
  energías nominales; aplicar el margen una vez a descargas, sin aumentar
  regeneración acreditada. Es un escenario, no una garantía probabilística.
- Estaciones deshabilitadas: `disabled_charger_ids`, lista vacía desactiva.
  Prohibir la recarga, no el tránsito por su ubicación.
- Ventanas: `use_customer_time_windows` y `customer_time_windows`, con
  `open_seconds`/`close_seconds` por cliente. Exigir jornada finita. Permitir
  espera; toda la entrega debe terminar antes del cierre. Condicionar por
  `a_ikr`, nunca por mera presencia `z_ikr`. Clientes sin ventana no reciben una inventada.

Las potencias por estación y jornada son comunes a la flota homogénea actual.
El depósito continúa sin recarga. No se modelan todavía colas, ocupación de
puertos, curvas no lineales, paquetes ni consumo auxiliar durante las paradas.
Compatibilidad física, batería y retorno no son opcionales.

Las opciones se aplican en `prepare` o `service-graph --config`; `run --config`
solo toma recursos del solver. `--reuse-instance` y `--reuse-path-archive`
permiten cambiar de escenario conservando los caminos de Dijkstra, sin
recalcularlos. Con plazos, un camino de energía mínima puede ser lento:
certificar únicamente sobre los caminos fijos disponibles.

Jornada, ventanas o reserva final superior a la reserva base desactivan la
prueba actual de H y su cota estructural. `auto` debe detenerse con diagnóstico;
un H explícito limita el alcance. No asumir que H=21 sigue certificado.
`build_greedy_start` puede construir un incumbente parcial sin recargas, con
presupuesto blando de 0,5 s. No certifica H. Validar calendario, batería y
expansión antes de enviarlo; actualizar todos los valores del warm start.

Persistir opciones, tiempos, energía y hashes de cada escenario. Actualizar
siempre el validador independiente y pruebas al añadir restricciones.
La duración operacional es el máximo de las duraciones de los vehículos,
con salida común; reportar además su suma, sin confundirla con cómputo.
Sin referencias válidas, ahorros y CO2e continúan en `null`.

## 7. LLM obligatorio mediante AWS y adaptación de LLM4MIP

**El LLM del producto debe invocarse mediante la API de los servicios y modelos habilitados para la cuenta, región y plan/créditos AWS de la hackatón.** La integración inicial será **Amazon Bedrock Runtime, API Converse, mediante `boto3`** para un modelo compatible.

- Configurar región e identificador de modelo o perfil de inferencia. No fijar un modelo arbitrario ni asumir que está habilitado, cubierto por créditos o disponible gratuitamente.
- Verificar disponibilidad, permisos, condiciones de acceso, cuotas y presupuesto en el entorno asignado antes de elegir el modelo definitivo.
- La llamada es `boto3.client("bedrock-runtime").converse(...)` y requiere `bedrock:InvokeModel`. Resolver requisitos adicionales del proveedor/cuenta con el responsable del entorno; consultar documentación no demuestra acceso real.
- Usar la cadena estándar de credenciales AWS: rol de ejecución, perfil/SSO local o credenciales temporales del entorno. No incrustar claves ni registrarlas en Git, prompts o logs.
- Convención de configuración: `BEDROCK_MODEL_ID`, `AWS_DEFAULT_REGION` y `AWS_PROFILE` opcional. Mapear explícitamente cualquier variable propia de región a `region_name`. No confundir perfil de credenciales con perfil de inferencia.
- No sustituir esta integración por APIs directas de OpenAI, Anthropic u otros proveedores, ni por un modelo local. Un modelo de esos proveedores servido a través de Bedrock sí puede ser válido si está habilitado para la cuenta.
- Centralizar AWS en `llm/bedrock.py`; el resto del código no maneja credenciales.
- Configurar timeout, límites de entrada/salida, cantidad máxima de llamadas y reintentos acotados. Registrar tokens y costos estimados cuando exista una tarifa verificada.
- Los tests habituales usan dobles del cliente. La aceptación de la integración requiere una prueba real en la cuenta AWS asignada; un mock no demuestra conectividad.

Referencia solicitada: https://llm4mip.github.io/

Repositorio público inspeccionado:
https://github.com/LLM4MIP/llm4mip.github.io

Commit de referencia inspeccionado: `9335a69f446244f28d5b406eb66ddf13afa1d2e9`.

**Reutilizar y adaptar material existente de LLM4MIP. No reconstruir desde cero su trabajo de diagnóstico y diseño de experimentos.** El material público incluye workflows, prompts, referencias y scripts auxiliares; no proporciona una integración lista de Pyomo, Bedrock y autotuning.

Componentes concretos a revisar:

- `data/skill-study/packages/primal-current/`: instrucciones y referencias para analizar estructura y mejorar soluciones.
- `data/skill-study/packages/primal-current/scripts/summarize_runs.py`: resumen de registros; no es un validador de rutas.
- `data/skill-study/packages/dual-current/`: criterios sobre cotas y su validez. No adoptar cortes o transformaciones fuera del alcance sin demostrar que preservan el problema.
- `downloads/milp-structure-research-copt/scripts/profile_mip_structure.py`: perfil estructural basado en COPT. Reutilizar lo pertinente adaptando su dependencia al backend elegido; no añadir COPT solo para obtener estadísticas que Pyomo/nuestro solver ya exponen.
- `downloads/milp-structure-research-copt/references/output-templates.md`: formatos de diagnóstico e hipótesis.

Los materiales usan Gurobi/COPT y el sitio describe un trabajo más amplio que tuning de parámetros. Nuestro MVP adapta su análisis estructural y experimentación al ajuste del solver. **No afirmar una reproducción literal de sus resultados o infraestructura** sin haberla implementado y medido.

Registrar en `docs/llm4mip-adaptation.md`: URL y commit de origen, archivos/prompts reutilizados, cambios, licencia MIT y partes no reproducidas. Conservar avisos de licencia/copyright en material incorporado. No copiar íntegramente el sitio ni asumir acceso a repositorios no públicos referenciados por él.

### Contrato de tuning

El LLM recibe un perfil compacto: número y tipo de variables, restricciones, estructura del ruteo y batería, escalas numéricas, fase de optimización, estadísticas relevantes, solver/versión, opciones admitidas y presupuesto. No necesita los históricos completos, credenciales ni direcciones exactas de clientes.

Debe devolver JSON validable, por ejemplo:

```json
{
  "schema_version": "1.0",
  "solver": "backend_configurado",
  "parameters": {},
  "rationale": "Hipótesis de ajuste basada en la estructura observada",
  "warnings": []
}
```

Reglas obligatorias:

1. Mantener una lista de parámetros permitidos con tipos, rangos y versión del solver. Solo aceptar opciones realmente soportadas.
2. Heurísticas, branching, cortes, presolve u otras estrategias solo pueden proponerse si el backend las expone y están aprobadas. No inventar equivalencias entre opciones de COPT, Gurobi y HiGHS.
3. El LLM no modifica datos, restricciones, dominios, objetivos, capacidad, reserva, límite de movimientos, tolerancias de factibilidad/integralidad ni criterios de certificación.
4. Presupuestos, recursos y metas de gap los fija el protocolo/configuración del usuario. No dejarlos variar para aparentar aceleración.
5. No usar `eval`, `exec`, shell o archivos Python generados por el LLM para aplicar tuning.
6. Ante respuesta inválida, parámetros desconocidos, fallo de AWS o presupuesto agotado, usar la configuración estándar y marcar `fallback`. No ocultar que el LLM no se utilizó.
7. Comparar baseline y configuración propuesta con la misma instancia, formulación, fase, recursos y presupuesto. Registrar propuestas aceptadas/rechazadas y resultados. No prometer una mejora antes de medirla.
8. Empezar con una propuesta y un experimento acotado; no crear un bucle autónomo indefinido. Separar presupuesto de tuning del de resolución.
9. Medir tiempo de solver y tiempo total, incluyendo llamadas al LLM y experimentos. El costo del tuning forma parte del costo de uso del producto.

## 8. JSON de salida, KPIs y experiencia de usuario

`RunResult` se serializa como JSON versionado, incluso cuando no hay solución. Usar `null` más un motivo para datos no disponibles; no `NaN`, infinitos ni ceros ficticios.

Campos mínimos:

- Identidad: `schema_version`, `run_id`, hashes de entradas/configuración/red, versión del código y del modelo energético.
- Escenario: flota, capacidad, reserva, SoC inicial, límites y supuestos.
- Ejecución: solver/versión, semilla, presupuesto, parámetros solicitados/efectivos y estado.
- `phases`: objetivo, incumbente, cota, gap, terminación y tiempo de cada fase.
- `tuning`: estado, modelo/región AWS, propuesta, validación, fallback, tokens y costo cuando estén disponibles.
- `routes`: vehículo, pasos en orden, clientes atendidos, geometría/arcos, batería de llegada/salida, recarga y energía por tramo.
- `unserved_visit_ids`, validación independiente y sus violaciones.
- `kpis`: valores, unidades, definición y calidad de la información.
- `runtime_seconds`: carga/preparación, modelo, LLM, experimentos, solver, validación y total. Definir intervalos para no sumar dos veces etapas incluidas en otras.
- Advertencias y procedencia de los datos usados para impactos estimados.

No guardar “todas las estadísticas posibles” como un volcado indiscriminado. Conservar las estadísticas útiles y soportadas para diagnosticar, comparar y reproducir, con logs detallados en artefactos separados.

KPIs oficiales:

| Prioridad | Métrica | Tratamiento |
|---|---|---|
| Factibilidad | Retorno al depósito y batería suficiente de ambos vehículos | Condición obligatoria, mostrar validación |
| Principal | Entregas cumplidas | Maximizar; mostrar cumplidas/total |
| Desempate | Consumo energético total, kWh | Minimizar, indicando la definición energética |
| Desempate | Tiempo de cómputo, segundos | Medir solver y ejecución total |
| Escalabilidad | Mismo código con más nodos/vehículos | Evaluar calidad, factibilidad y tiempo |

La rúbrica del jurado es distinta: innovación técnica 25 %, impacto social 25 %, factibilidad y sustentabilidad 20 %, escalabilidad 15 %, presentación 15 %. **No convertir esos porcentajes en pesos de la función objetivo.**

Mostrar además, cuando se puedan calcular: kilómetros, tiempo operacional, paradas de carga, energía recargada, mínima reserva, clientes pendientes y estado/gap por fase.

Para ahorro de tiempo y emisiones:

- Indicar qué se compara: tiempo de cómputo contra baseline, duración operacional contra una ruta de referencia o emisiones contra una alternativa de transporte.
- Usar la misma demanda/alcance para comparar, o advertir diferencias de entregas. Conservar resultados negativos si la propuesta empeora la referencia.
- No inferir tiempo operacional a partir de tiempo de cómputo.
- CO2e evitado requiere referencia, consumo, factores de emisión, unidades, fuente/fecha y alcance de la estimación. No presentar emisiones de escape como emisiones de ciclo de vida.
- No equiparar consumo neto de batería con electricidad comprada sin modelar pérdidas y condiciones de comparación.
- Sin referencia o factores válidos, devolver `null` y explicar qué falta. No inventar ahorros ni presentar estimaciones como mediciones.

UI pensada para un operador de CASE/FCFM:

- Carga de archivo y edición gráfica/formulario con errores claros.
- Mapa vial con depósito, entregas, cargadores y colores por vehículo.
- Primero factibilidad y entregas; después energía, tiempos y estado de optimalidad.
- Detalle por ruta con secuencia, batería y recargas; supuestos visibles cuando afectan decisiones.
- Comparación estándar/tuning, cuando exista una comparación medida.
- Descarga del JSON y de la instancia normalizada.
- Estados comprensibles: validando, preparando, ajustando, resolviendo, comprobando, completado/error. No mostrar resultados antiguos como si correspondieran a parámetros recién editados.

## 9. Trabajo paralelo, branches y worktrees

La rama de integración objetivo es **`master`**. Al redactar esta guía, el checkout estaba en `main`. Durante el bootstrap del repositorio, el integrador debe establecer `master` desde la base verificada y conservar la historia existente; no asumir que ya existe ni borrar/reescribir `main` automáticamente.

- Una tarea/agente por rama `codex/<area>-<tarea>` y worktree o workspace designado.
- Antes de editar: identificar rama, directorio, estado de Git, alcance y propietario de los archivos.
- No trabajar varios agentes en el mismo checkout mutable ni cambiar la rama bajo otro agente.
- No usar `reset --hard`, limpieza masiva, force push o descarte de cambios ajenos para resolver conflictos.
- No integrar directamente trabajo incompleto en `master`. Usar commits/PRs pequeños y revisables.
- El integrador coordina cambios transversales, revisa merges y resuelve conflictos preservando los contratos y objetivos.
- No automatizar el stage de todo el repositorio. Incluir solo cambios correspondientes a la tarea.

Reparto inicial:

| Área | Responsabilidad principal | Coordinación necesaria |
|---|---|---|
| Integración | contratos, configuración, pipeline, dependencias y merges | acuerda contratos antes de trabajo paralelo |
| Datos/energía | inputs, red, perfiles y estimador | entrega instancias normalizadas al modelo |
| Optimización | Pyomo, solver, fases y certificados | consume contratos; no depende de UI/AWS |
| LLM/AWS | Bedrock, adaptación LLM4MIP y tuning | usa capacidades reales del adaptador |
| UI/UX | formulario, mapa y resultados | consume pipeline/RunResult, sin duplicar lógica |
| Validación/métricas | comprobador, KPIs y comparaciones | independiente de construcción Pyomo |

Una persona puede cubrir varias áreas. La tabla asigna responsabilidades, no exige crear más equipos o capas. Coordinar antes de editar simultáneamente `contracts.py`, `config.py`, `pyproject.toml`, el lockfile o este archivo.

## 10. Entregas y verificaciones necesarias

Construir incrementos ejecutables:

1. Contratos, configuración y un ejemplo sintético pequeño.
2. Flujo CLI con Pyomo, solver estándar, validador y JSON.
3. Datos/red/energía reales con sus supuestos y cachés.
4. Bedrock y tuning validado con material reutilizado de LLM4MIP.
5. Interfaz conectada al mismo pipeline.
6. Comparación reproducible, prueba con entradas reemplazables y demo para el jurado.

UI y AWS pueden avanzar en paralelo usando fixtures acordadas, sin presentar fixtures como resultados reales.

Pruebas mínimas con valor:

- Lectura CSV con BOM, campos opcionales y errores de esquema.
- Integración energética en tiempos irregulares y separación entre viajes.
- Instancia pequeña con óptimo conocido; caso donde solo parte de las entregas es factible.
- Recarga repetida y regeneración con saturación y déficit intermedio.
- Retorno, reserva y unicidad de entregas comprobados independientemente.
- Timeout con/sin incumbente y reportes correctos de las fases lexicográficas.
- Respuestas LLM inválidas, opciones no permitidas y fallback.
- CLI y UI consumen el mismo contrato y toleran reemplazar la instancia.

No escribir tests que solo repitan la implementación ni benchmarks costosos para cambios documentales. Las pruebas unitarias no llaman a AWS ni descargan mapas. Separar explícitamente pruebas de integración con red y su presupuesto.

Cada entrega debe informar qué cambió, validación ejecutada, limitaciones y cómo reproducirla. No afirmar mejoras de tiempo, energía, gap o emisiones sin comparación verificable.

Fuentes técnicas de la integración AWS:

- https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html
- https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html
