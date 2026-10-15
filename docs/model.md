# Modelo importado de Daniel Hermosilla

Esta integración usa `modelamiento@624203573bffdeec334a9e07a64b361a515f9725`.
El [PDF](../modelamiento.pdf) y su [fuente LaTeX](../modelamiento.tex) se importan
en esa misma revisión. El registro de archivos está en
[solver-source.json](solver-source.json).

El backend elegido por Daniel es `scip-routes`, implementado en
`route_solver.py` y `route_resources.py` mediante PySCIPOpt. Corresponde al
maestro por rutas de las ecuaciones (25)–(29) del PDF. Primero maximiza entregas,
luego minimiza energía neta efectiva manteniendo el cumplimiento encontrado.
Conserva recarga continua, saturación, reserva, compatibilidad, revisitas,
regreso al depósito y separación entre transitar y atender.

No se fija un máximo artificial de movimientos. `parameters.movement_limit`
sigue en el contrato nativo 1.0 por compatibilidad con los modelos anteriores,
y `formulation.movement_limit_used` es `null` con este backend.
Las ecuaciones (1)–(24) y su implementación Pyomo permanecen como referencia.
El servidor web y la CLI seleccionan explícitamente `scip-routes`; no activan
otros solvers mediante fallback.

El grafo de entrada debe contener arcos elementales y su energía. La factibilidad
y los certificados corresponden a esa representación, sus parámetros y el modelo
energético utilizado. No garantizan consumo real ni opciones viales omitidas.
El comprobador independiente reproduce continuidad, servicios, retorno, batería,
recarga y operaciones. Pricing interrumpido no acredita automáticamente
optimalidad; se conservan las fases nativas y su evidencia.

El PDF upstream describe también una variante con caminos agregados.
**Esa variante no se importa ni se ejecuta aquí**: `service_graph.py` documenta
una adaptación de trabajo de Lucas Zulueta. Se excluye y se rechazan instancias
`service_paths_nonnegative`. Los ejemplos geodésicos del formulario son
explícitamente sintéticos y no usan ese preprocesador.

No se han cambiado ecuaciones, heurísticas, validación ni métricas de Daniel.
La adaptación de `pipeline.py` retira únicamente la dependencia y las ramas de
expansión del preprocesador excluido. Su resultado nativo y sus contratos se
conservan; `road_validation` permanece `null` porque no se ejecuta esa expansión.
