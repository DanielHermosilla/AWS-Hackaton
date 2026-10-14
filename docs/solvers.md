# Resolución y certificados

`solve_instance(instance, config)` construye la formulación de `modelamiento.pdf`
y resuelve sus dos fases. No utiliza un LLM y no modifica el problema físico.
El resultado extraído requiere posteriormente la comprobación independiente de
`validation.py`.

## Backends y fallback

`solver="auto"` intenta Gurobi mediante `gurobi_direct` de Pyomo y, solo ante
falta de interfaz, ejecutable o licencia válida, intenta SCIP mediante el plugin
`scip`. Una licencia Gurobi que acepta un ejemplo pequeño pero rechaza la
instancia por tamaño también activa este fallback. La comprobación decisiva es
resolver el modelo real: tener `gurobipy` instalado no demuestra disponibilidad.

`solver="gurobi"` y `solver="scip"` fijan el backend para comparaciones
reproducibles. Una infactibilidad, un timeout, una cota débil o un error numérico
no provocan un cambio de solver. Se registran el backend utilizado, su versión
y el motivo de fallback sin copiar detalles privados de las licencias. Cada
fase registra también su backend; si la licencia falla al añadir la segunda
fase, puede existir un certificado de entregas de Gurobi y uno de energía de
SCIP. `used_solver` identifica el último backend utilizado.

Las únicas opciones configurables son presupuesto, gap solicitado, hilos,
semilla y salida del solver. El adaptador traduce explícitamente:

| Configuración | Gurobi | SCIP |
|---|---|---|
| Tiempo restante | `TimeLimit` | `limits/time` |
| Gap solicitado | `MIPGap` | `limits/gap` |
| Hilos | `Threads` | `parallel/maxnthreads` |
| Semilla | `Seed` | `randomization/randomseedshift` |

Las semillas y parámetros pertenecen a implementaciones distintas: no implican
trayectorias idénticas. Los denominadores del gap nativo tampoco son idénticos.
No se alteran tolerancias de factibilidad ni integralidad.

## Presupuesto compartido

El reloj comienza antes de construir Pyomo. El 70 % del presupuesto restante
tras la construcción se reserva como máximo para maximizar entregas. El otro
30 % y cualquier tiempo no utilizado pasan a la fase energética. Los intentos
fallidos, la selección del backend, la carga de resultados y la extracción
consumen el mismo presupuesto. Nunca se reinicia el presupuesto al cambiar de
backend o de objetivo. Si ya se agotó, no comienza otra llamada al solver.

Los límites de Gurobi/SCIP son **blandos**. La escritura/traducción del modelo,
el arranque y el retorno del solver pueden exceder el tiempo restante. Esta
versión no mata procesos mediante un supervisor externo ni promete un límite
duro de pared. `runtime_seconds` informa el tiempo real, incluido cualquier
exceso, en vez de truncarlo al presupuesto.

## Lectura de resultados

Los resultados se cargan explícitamente, solo cuando existe un vector de
incumbente. Un registro `solution` vacío no cuenta como solución, y los valores
dejados por la primera fase no acreditan que la segunda encontró una nueva.

La primera fase conserva una **cota superior** al máximo de entregas; la
segunda, una **cota inferior** al mínimo de energía condicionado al número de
entregas fijado. SCIP puede informar la cota global en `solver.dual_bound` aunque
no llene las cotas de `problem` al detenerse por tiempo. Se utiliza esa evidencia.
Sentinelas infinitos o datos ausentes se serializan como `null`.

Por fase se informa `absolute_gap = |incumbent - best_bound|` y un gap normalizado
común `absolute_gap / max(1, |incumbent|, |best_bound|)`. Este campo descriptivo
no es una copia del gap nativo del solver ni sustituye el criterio de parada
configurado. No se mezclan cotas o gaps de ambas fases.

Un estado `OPTIMAL` con gap permitido positivo no basta para declarar
optimalidad lexicográfica. Para las entregas, la integralidad permite certificar
el máximo cuando la cota global excluye el siguiente entero. Para energía se
requiere terminación óptima y cierre numérico de la cota; si falta la cota, solo
se acepta el estado óptimo con gap solicitado cero. Estos son certificados
numéricos del solver, sujetos a sus tolerancias, no pruebas racionales exactas.

Si la primera fase no prueba el máximo, la energía se mejora con las entregas
encontradas, y `lexicographic_optimal` permanece falso. Si la segunda no produce
solución, falla o entrega un incumbente peor, se conserva la solución de la
primera. Una solución retenida todavía debe pasar el validador independiente.
La optimalidad se refiere únicamente a la instancia, red, modelo energético y
`movement_limit` configurados.
