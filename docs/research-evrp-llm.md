# Algoritmos para nuestro EVRP y oportunidades verificables para un LLM en AWS

Revisión dirigida al **15 de octubre de 2026**. Estado del código examinado:
`codex/solver-orchestrator`, commit
`2a89b041db5d28610d5182a6da90ed6137be4051`.

Este documento evalúa alternativas y propone experimentos. No registra la
implementación de los algoritmos propuestos ni nuevos benchmarks. Se da por
correcto el preprocesamiento y se trabaja sobre el grafo de servicios recibido.
La revisión combina artículos, preprints, documentación oficial y una auditoría
del código actual; no es una revisión sistemática exhaustiva.

**Recomendación.** Desarrollar una **búsqueda adaptativa de vecindarios grandes,
con reparación y recombinación mediante SCIP, alimentando un maestro por rutas**.
En paralelo, mejorar el pricing para que busque por coste reducido y produzca
cotas útiles. Utilizar el LLM para analizar estancamientos, proponer vecindarios
y desarrollar políticas reutilizables. Comparar ese sistema con una versión
igual de fuerte que seleccione acciones sin LLM.

La recomendación conserva SCIP por sus funciones de reparación, combinación y
certificación, después de evaluar alternativas. No presupone que SCIP deba
dirigir cada movimiento de la búsqueda ni que todo el esfuerzo deba ir al
branch-price-and-cut.

## 1. Qué problema estamos resolviendo

La formulación vigente está en (25)–(29) de
[`modelamiento.pdf`](../modelamiento.pdf). Su rasgo distintivo no es solamente
la batería:

| Aspecto | Nuestro problema | Consecuencia para transferir literatura |
|---|---|---|
| Clientes | Opcionales; maximizar cantidad atendida | Es cercano a EVRP con beneficios y variantes de orienteering. Un EVRPTW con todos los clientes obligatorios no es el mismo problema. |
| Objetivo | Primero entregas; después energía | No sustituirlo por una suma de beneficios, kilómetros, vehículos y penalizaciones. |
| Flota | Dos vehículos en el escenario oficial; cantidad configurable | Muchos artículos minimizan el número de vehículos. Aquí es un recurso disponible, con vehículos inactivos permitidos. |
| Energía | SoC inicial, capacidad y reserva; recarga parcial y retorno | Una ruta corta puede ser inviable. El evaluador energético pertenece al núcleo del algoritmo. |
| Recarga | Estaciones y calles pueden repetirse; depósito sin recarga | No copiar límites de visitas a estaciones ni asumir reinicio de batería al volver al depósito. |
| Representación | Rutas completas sin H | No reemplazar el problema por una plantilla con un máximo arbitrario de movimientos. |
| Base operacional | Sin capacidad de paquetes, jornada ni ventanas | No importar restricciones de los benchmarks capacitados o con ventanas para hacer más fácil el pricing. |
| Grafo recibido | Dirigido; caminos y costes fijados por el preprocesamiento | La investigación no revisa Dijkstra ni modifica esos caminos. |
| Extensiones | Tiempos, ventanas, reserva final y otras opciones explícitas | Evaluarlas separadamente. No atribuir a la base resultados de una variante distinta. |

La familia **prize-collecting EVRP** es especialmente pertinente para la selección
de clientes. Moradi y Mirzavand Boroujeni estudian una variante con entregas
opcionales y beneficios, y una heurística híbrida de búsqueda de vecindarios y
recocido simulado [1]. Su objetivo económico y sus restricciones adicionales
requieren adaptación; no corresponden directamente a nuestra lexicografía.

No encontré evidencia que permita nombrar un único algoritmo como «el mejor»
para esta combinación exacta de condiciones y presupuestos. La literatura
compara variantes, datos, máquinas, límites y objetivos diferentes. La selección
que sigue es un juicio de ingeniería apoyado en esa evidencia.

## 2. Qué sabemos del motor actual

Los resultados existentes están en
[`performance-orchestrator.md`](performance-orchestrator.md):

| Corrida sobre 40 clientes | Presupuesto de resolución | Resultado final |
|---|---:|---|
| Original | 60 s | 2/40 entregas |
| Mejorado, standard | 60 s | 40/40; 14,566607 kWh |
| Mejorado, prueba corta standard | 15 s | 40/40; 14,566607 kWh |
| Mejorado, Fable 5 / high | 60 s y 120 s | 40/40; misma energía y cota |

**«Prueba corta» significa el mismo motor con menos tiempo disponible.** La
resolución corta duró 15,004 s; el pipeline, 15,713 s. En las corridas standard
de 60 s, el primer testigo que cubría los 40 clientes apareció entre 0,121 y
0,126 s. Ese testigo inicial no debe confundirse con la energía final.

Servir a los 40 clientes prueba el primer objetivo por cardinalidad. La energía
final aún no está certificada óptima: la cota inferior es 14,525265 kWh y el gap,
0,283813 %. Entre cota e incumbente quedan aproximadamente **0,041342 kWh**.
En esta instancia queda poco margen energético absoluto para demostrar una
ventaja del LLM. Hace falta incluir casos difíciles de cobertura y batería.

Las llamadas reales tampoco acreditan una mejora incremental del LLM:
Nova Micro cambió políticas, pero terminó con la misma calidad que standard.
Fable 5 con esfuerzo high consumió 20,058 s de inferencia en la corrida de
60 s y 46,711 s en la de 120 s. La primera solución completa en la corrida
de 60 s llegó a los 20,255 s. Es evidencia de actuación y de latencia, no de
aceleración.

**Hallazgo en el código.** El motor ya tiene componentes útiles, pero el
pricing exacto no implementa varias aceleraciones centrales de la literatura:

| Evidencia local | Implicación |
|---|---|
| `RouteOracle.__init__`, `route_resources.py:165`: no recibe duales | Conserva una exploración física reutilizable, independiente del objetivo dual actual. |
| `RouteOracle.advance`, `route_resources.py:231–255`: cola FIFO/LIFO y mejores rutas por máscara | El orden exacto es anchura/profundidad; no prioriza etiquetas mediante una cota de coste reducido de su continuación. |
| `RoutePricer._price`, `route_solver.py:243–315` | Los duales sí guían el pricing heurístico; en el oráculo exacto evalúan las rutas que este va completando. |
| `route_solver.py:515–522` y `606–615` | El controlador recibe contadores, tiempos, objetivos y cotas; no recibe el detalle de clientes conflictivos, rutas complementarias o recursos críticos. |
| `route_orchestrator.py:71–104` | La llamada remota se hace de forma síncrona y su respuesta controla campos de política y parámetros admitidos. |

En particular, el estado real enviado a Fable después del arranque contiene
40 entregas, energía, tiempo de arranque y 30 columnas heurísticas. No incluye
las secuencias de rutas ni una explicación cuantitativa de dónde se pierde
energía. Un modelo más capaz no puede recuperar información que no recibió.

La combinación de máscaras de clientes y fronteras de recursos también puede
crecer mucho. Cambiar el orden FIFO por LIFO no resuelve por sí solo ese
crecimiento. Esta es una limitación observada en la arquitectura, no un nuevo
perfil de tiempos que permita atribuirle un porcentaje exacto del runtime.

## 3. Algoritmos disponibles y sus diferencias

### 3.1. Branch-price-and-cut con pricing especializado

Desaulniers et al. [2] desarrollan algoritmos exactos para cuatro variantes que
combinan recarga completa/parcial y una/múltiples recargas. Nafstad et al. [3]
extienden esta línea con funciones de recarga no lineales, tecnologías distintas,
etiquetado bidireccional, relajaciones ng y aceleraciones del pricing. Son
referencias directas para mejorar el generador de rutas.

En un maestro por rutas, el pricing busca una ruta con coste reducido negativo:
su coste físico se combina con los duales de cobertura, vehículo y cortes.
Encontrar una ruta factible barata y encontrar una columna útil para ese LP son
tareas relacionadas, pero distintas.

**Aplicación propuesta:**

1. Incorporar duales y restricciones de branching al estado de la búsqueda.
2. Ordenar expansiones por una estimación prometedora y, separadamente,
   descartar continuaciones solo mediante cotas demostradas válidas.
3. Mantener pricing heurístico rápido y pasar a pricing exacto cuando corresponda.
4. Evaluar relajaciones de espacio de estados y refinamiento progresivo.
5. Introducir estabilización dual y cortes de manera gradual, midiendo el coste
   adicional que cada corte impone al pricing.

El etiquetado bidireccional merece un prototipo, pero no una traducción mecánica:
hay que definir cómo se combinan recursos y decisiones de recarga continua.
Una ruta con tránsitos repetidos no es una secuencia elemental de nodos; la
unicidad exigida corresponde a la entrega.

**Advertencia específica de nuestra base.** Muchas aceleraciones de EVRPTW
aprovechan una jornada o una carga que limita la longitud de las etiquetas.
Aquí esos recursos pueden estar desactivados. Si una relajación permite cobrar
repetidamente el dual de un cliente al recorrer un ciclo con recarga, puede
crear ciclos de coste reducido negativo y un problema relajado no acotado.
Esta es una observación matemática sobre la transferencia, no un fallo
documentado de esos artículos.

No se resuelve imponiendo un H nuevo. Hay que justificar la relajación, la
contabilización de entregas, las cotas y la terminación para nuestras hipótesis.
El oráculo físico actual puede servir como referencia de corrección en casos
pequeños mientras se desarrolla el nuevo pricing.

**Ventaja:** calidad de cotas y posibilidad de optimalidad demostrada.
**Coste:** es la opción con mayor trabajo algorítmico delicado. Mejorar la
formulación del maestro sin mejorar el pricing puede dejar intacto el cuello
de botella.

### 3.2. ALNS: destruir y reparar partes de la solución

La búsqueda adaptativa de vecindarios grandes, ALNS, elimina una parte de una
solución, la reconstruye con distintos operadores y adapta su uso según el
resultado. Keskin y Çatay [4] aplican esta familia a EVRPTW con recarga parcial.
Es una base apropiada para obtener buenas soluciones con presupuestos cortos.

Para nuestro problema propondría operadores que actúen sobre:

- Clientes cuya inserción provoca desvíos energéticos grandes.
- Grupos conectados por trayectos de energía baja, respetando la dirección.
- Clientes concentrados en un vehículo y transferibles al otro.
- Tramos que dependen de una estación, incluyendo su reemplazo o reordenamiento.
- Clientes omitidos que necesitan una modificación conjunta, no una inserción
  individual.
- Dos o más rutas del conjunto de columnas que cubren clientes valiosos pero
  se solapan y no pueden seleccionarse juntas.

La reparación puede combinar inserción regret, búsqueda local dirigida,
optimización de recargas para una secuencia y subproblemas resueltos por SCIP.
Los operadores con más libertad física deben conservar visitas repetidas a
estaciones y recargas parciales. «Insertar un solo cargador» puede ser un
operador rápido; no es un reemplazo completo del espacio de soluciones.

**Ventaja:** reutiliza directamente parte del código existente y concentra
trabajo en soluciones enteras. **Límite:** su estancamiento no demuestra
optimalidad. Requiere una fuente de cotas separada.

### 3.3. Búsqueda híbrida genética o memética

Esta familia conserva una población de soluciones y combina diversificación
con búsqueda local. Zheng, Liu y Ong [5] estudian una variante eléctrica con
recarga parcial, recogidas/entregas y ventanas. Su tratamiento de la inserción
de estaciones y la búsqueda entre dominios EV y no EV son ideas pertinentes.

Es una alternativa seria a ALNS cuando la diversidad de soluciones importa.
Podría aportar rutas iniciales y columnas variadas al mismo maestro.

No la elegiría como primera ampliación del proyecto: exige una representación,
recombinación y evaluación energética eficientes, además del control de
diversidad. La recomendación es compararla después de construir un evaluador
común, si ALNS se estanca o el tamaño objetivo crece. Su interés no implica
que esté demostrado que gane en nuestra instancia de 40 clientes.

PyVRP [6] es una referencia de implementación eficiente y un competidor valioso
cuando la variante coincide. Su soporte de premios o recargas de mercancías
no acredita soporte directo de nuestra batería y recarga eléctrica continua.
No propongo presentarlo como sustituto inmediato sin verificar ese contrato.

### 3.4. Matheurísticas: búsqueda de vecindarios más optimización exacta

Una matheurística usa un solver para resolver partes escogidas de una búsqueda.
Aquí caben dos combinaciones distintas:

**Reparación local.** Fijar parte del incumbente y liberar un subconjunto de
clientes, conexiones o decisiones de recarga. El subproblema decide su mejor
reorganización. Una cota de ese subproblema no es una cota del problema completo.

**Recombinación de rutas.** Guardar rutas factibles obtenidas por distintas
búsquedas y resolver un maestro restringido que elija combinaciones compatibles.
Su solución es útil; su cota restringida no certifica columnas todavía ausentes.

Eveborn y Rönnberg [7] proponen *pricing for integrality*: generar columnas
orientadas a completar soluciones enteras, además de mejorar el LP. Reportan
cierre medio del 30–40 % del gap de raíz frente a su heurística de maestro
restringido. El preprint usa GCG/SCIP y **limita cada ruta a dos slots de
recarga**. Esa restricción no se debe importar; tampoco es un resultado de
aceleración transferible a nuestros datos.

Esta línea es especialmente atractiva para el LLM: analizar por qué las buenas
columnas no se combinan, proponer qué cobertura falta y pedir al generador
columnas complementarias. La factibilidad y el coste real siguen comprobándose
con algoritmos.

### 3.5. MIP compacto, descomposición Benders y programación por restricciones

Son alternativas que merecen consideración:

- **MIP compacto:** puede funcionar muy bien cuando existe una formulación
  ajustada para una variante restringida. En nuestro caso hay que representar
  recargas y revisitas sin introducir cotas artificiales. Lo usaría primero
  para reparación o como referencia en instancias pequeñas.
- **Benders o enfoques híbridos con programación por restricciones:** resultan
  atractivos si aparece una separación real entre elegir rutas y programar
  recursos compartidos, por ejemplo puertos de carga y horarios.
- **Modelo de arcos especializado:** puede ser la mejor opción cuando se
  verifica una reducción estructural, como la de un tour factible sin recarga.
  El certificado tiene que comprobarse para cada instancia.

La base actual no modela ocupación de cargadores. Por ello, introducir ahora
una arquitectura de scheduling compartido resolvería un problema que todavía
no tenemos. La evaluación favorable de una futura descomposición no justifica
agregar esas restricciones al problema actual.

### 3.6. Aprendizaje para seleccionar subproblemas y políticas

*Learning to Delegate* [8] aprende a elegir subproblemas y deja su resolución
a un método especializado. Es una referencia más próxima a nuestra propuesta
que pedir a una red que produzca directamente toda la ruta.

Un selector aprendido, un bandit y un LLM son competidores para parte de ese
trabajo. El bandit es especialmente importante como baseline: usa resultados
recientes con coste pequeño. Si la información útil consiste solo en qué
operador ganó las últimas iteraciones, un LLM costoso puede ser innecesario.

Un modelo neural entrenado para construir rutas completas puede ser útil con
muchas instancias repetidas y una distribución estable. Para este proyecto
añade entrenamiento, adaptación a restricciones y evaluación de transferencia.
No lo priorizo sin un conjunto suficiente de entrenamiento. El checker sigue
siendo necesario y la predicción no aporta un certificado.

### 3.7. Comparación para decidir

Las valoraciones siguientes son una recomendación para este código y sus
restricciones, no un ranking experimental universal.

| Alternativa | Papel más útil | Certificación global | Prioridad propuesta |
|---|---|---|---|
| Pricing especializado + branch-price-and-cut | Cotas y cierre de optimalidad | Sí, cuando termina correctamente | Alta; desarrollo gradual |
| ALNS eléctrica | Buen incumbente pronto y mejoras grandes | No por sí sola | Primera ampliación de búsqueda |
| ALNS + reparación SCIP + recombinación | Mejora conjunta de clientes y rutas | Solo mediante componente global válido | Arquitectura principal recomendada |
| Búsqueda memética eléctrica | Diversidad y escalabilidad | No por sí sola | Alternativa a comparar después |
| MIP compacto / CP / Benders | Subproblemas o variantes con estructura apropiada | Depende de formulación y ejecución | Selectiva |
| Selector aprendido / bandit | Decisiones repetidas y baratas | Hereda las garantías del motor | Baseline obligatorio para el LLM |
| LLM construyendo rutas completas | Exploración o baseline | No | Baja prioridad |

## 4. Qué aporta la literatura sobre LLM

Hay que separar **diseñar un algoritmo** de **controlar una ejecución**.

**Diseño fuera de la corrida.** EoH [9] y ReEvo [10] estudian evolución de
heurísticas con LLM, evaluación y realimentación. FunSearch [11] muestra el
valor de combinar propuestas con un evaluador programático. LACE [12],
publicado el 1 de octubre de 2026, propone construcción y selección de
heurísticas complementarias bajo un contrato de ejecución y evaluación.
Estas investigaciones apoyan el diseño de políticas o conjuntos de operadores;
no prueban que una llamada de tuning mejore nuestro EVRP.

G-LNS [18], un preprint de 2026, da una propuesta aún más específica: evolucionar
**pares de operadores de destrucción y reparación**, evaluando su interacción.
Sus experimentos incluyen TSP y CVRP, no nuestro EVRP. Es una referencia concreta
para diseñar operadores que eliminen y reconstruyan conjuntamente clientes y
recargas, en lugar de optimizar cada operador de forma aislada.

Los trabajos que generan y ejecutan código requieren una adaptación importante:
el proyecto prohíbe ejecutar código producido por el LLM. Hay dos vías:

1. El LLM propone una idea; una persona o un proceso de desarrollo autorizado
   la implementa, revisa y prueba antes de incorporarla.
2. El LLM produce una composición declarativa de operadores existentes:
   selección, orden, condiciones, pesos y presupuestos dentro de un contrato.

**Control durante la corrida.** Un estudio de telemetría y ALNS [13] usa nueve
instancias CVRPTW y cuatro semillas. Con 1000 iteraciones, el gap medio pasa de
2,93 % a 0,18 %, pero el tiempo crece de 238 a 979 s. PyVRP obtiene 0,15 % en
0,8 s. Es un gap respecto de la mejor media del conjunto comparado, no respecto
de óptimos probados. **No demuestra ventaja a igual tiempo**; gran parte del
sobrecoste proviene de instrumentación.

**Análisis de MIP.** LLM4MIP [14] explora razonamiento sobre formulación,
estructura, soluciones y cotas con verificación por herramientas. Al corte de
esta revisión, el sitio del proyecto informa un reporte técnico próximo:
su evidencia no debe tratarse como equivalente a un artículo revisado.
La idea transferible es pedir hipótesis verificables y acciones respaldadas
por herramientas, en vez de confiar en afirmaciones del modelo.

## 5. Cómo aprovechar el análisis de un LLM de AWS

### 5.1. Uso fuera de la resolución: diseñar y contrastar hipótesis

Este es el lugar apropiado para el mayor esfuerzo de razonamiento disponible.
El LLM recibe una colección de trazas de entrenamiento, compara fallos y
propone cambios de estrategia:

- «La mejora local cambia el orden, pero nunca transfiere conjuntamente este
  grupo de clientes entre vehículos».
- «Las columnas nuevas tienen buen coste reducido, pero todas compiten por
  los mismos clientes».
- «Las rutas descartadas por batería se concentran alrededor de este conjunto
  de estaciones; conviene cambiar una secuencia completa».
- «La solución apenas cambia mientras la cota sigue mejorando; conviene
  priorizar certificación sobre más destrucciones».

Estas son hipótesis de ejemplo, no diagnósticos ya demostrados en los logs.
Cada una debe venir acompañada de evidencia identificable, una intervención y
una métrica que permita rechazarla.

El ciclo sería: trazas de entrenamiento → análisis LLM → políticas declarativas
o propuesta de desarrollo → evaluación automática → revisión del resultado.
Las políticas seleccionadas se congelan antes del conjunto de prueba.

El resultado puede ser una **cartera pequeña de políticas complementarias**:
una para problemas de cobertura, otra para recarga difícil y otra para cerrar
energía cuando ya se atiende a todos. No hace falta pagar de nuevo por el mismo
razonamiento en cada instancia.

### 5.2. Uso durante la resolución: intervenir en decisiones concretas

El LLM necesita información que permita distinguir causas. Propongo construir
telemetría a partir del grafo y los estados ya disponibles:

| Información resumida | Decisión que habilita |
|---|---|
| Clientes omitidos y causas de fallos de inserción verificadas | Elegir una reparación conjunta |
| Coste marginal, vehículo y reserva mínima de candidatos | Seleccionar transferencias o intercambios |
| Solapamientos entre columnas y cobertura que falta | Pedir columnas complementarias |
| Duales y cambios recientes, resumidos por grupos | Elegir objetivos de pricing heurístico |
| Familias de descartes, tamaños de fronteras y rendimiento por expansión | Distinguir exploración estéril de un cuello de botella de recursos |
| Mejora por operador y por segundo, incluyendo intentos fallidos | Elegir entre intensificación, diversificación y certificación |
| Tiempo restante y latencia observada de AWS | Decidir si todavía compensa consultar |

Las métricas las calcula el programa. El LLM interpreta relaciones entre ellas;
no reconstruye a mano balances de batería ni procesa toda la matriz de calles.
Los grupos de clientes son candidatos de búsqueda, no particiones que recorten
permanentemente el problema.

**Contrato de acción propuesto**, pendiente de implementación:

```json
{
  "state_id": "estado-validado",
  "hypothesis": "las columnas candidatas compiten por los mismos clientes",
  "evidence_refs": ["overlap_group_3", "repair_failure_8"],
  "action": "repair_complementary_routes",
  "candidate_group_id": "group_3",
  "operator_sequence": ["related_removal", "scip_repair", "route_recombine"],
  "requested_budget_ms": 1500,
  "success_metric": "lexicographic_incumbent_improvement"
}
```

El ejecutor comprueba que el estado sigue siendo pertinente, que existen los
IDs y operadores, que el presupuesto cabe y que el resultado pasa validación.
El texto de la hipótesis sirve para auditar; no autoriza operaciones nuevas.
La reparación conserva el objetivo original. Un objetivo auxiliar para generar
columnas no cambia el criterio con que se acepta el incumbente.

### 5.3. Relación con SCIP y las garantías

La propuesta mantiene tres funciones distintas:

1. **Búsqueda de soluciones:** ALNS, heurísticas de rutas y reparación SCIP.
2. **Combinación:** maestro con las rutas conocidas y generadores de columnas
   que buscan complementar una solución.
3. **Certificación:** pricing exacto, branch-and-bound y relajaciones globales
   cuya validez esté demostrada para la variante.

La primera y segunda pueden avanzar aunque la tercera sea lenta. Un timeout
conserva el mejor incumbente validado y la mejor cota global válida disponible.
El LLM no convierte una cota de vecindario o de maestro restringido en una
cota global. Tampoco activa una reducción a tour sin comprobar sus condiciones.

### 5.4. Latencia y ejecución en AWS

Propongo producir primero un incumbente con la política disponible. Cuando
proceda una consulta, la búsqueda debería continuar mientras AWS responde;
la decisión se aplicaría en un punto seguro posterior y se descartaría si el
estado cambió de forma que la vuelve inaplicable.

Eso exige desarrollar concurrencia controlada y medición correcta: es una
recomendación arquitectónica, no una capacidad actual. No recomiendo llamadas
remotas por nodo, etiqueta o callback.

Bedrock ofrece interfaces Converse y herramientas con contratos estructurados
[15]. Su disponibilidad y los controles de razonamiento dependen del modelo.
Hay que mantener el perfil autorizado y comprobar soporte real; no hace falta
cambiar IAM para probar esta arquitectura. Las pruebas existentes con Fable
acreditan acceso bajo las condiciones registradas, no que sea el mejor modelo
para cada decisión ni que esfuerzo máximo sea la mejor política de latencia.

Usaría un modelo de alta capacidad para análisis fuera de la corrida y
compararía, durante ella, la política aprendida, un selector ligero y el mismo
modelo potente. La selección final depende de mejora por tiempo total y coste,
no solo de calidad del razonamiento textual.

## 6. Orden de trabajo recomendado

| Paso | Entregable | Evidencia para continuar |
|---|---|---|
| 1 | Banco de instancias y métricas comunes | Distingue cobertura difícil, recarga y energía; reproduce resultados actuales |
| 2 | ALNS eléctrica con selección adaptativa sin LLM y reparación acotada | Mejora frente al motor actual a igual tiempo |
| 3 | Generación de columnas para completar soluciones y recombinación | Mejora incremental sobre el paso 2, sin atribuirla al LLM |
| 4 | Pricing por coste reducido y cotas de continuación | Coincide con referencia exhaustiva pequeña y mejora cotas o tiempo |
| 5 | Políticas desarrolladas con análisis LLM fuera de la corrida | Ventaja en instancias no usadas para seleccionar políticas |
| 6 | Control LLM durante la corrida con telemetría y respuesta asíncrona | Mejora sobre el mejor selector sin LLM, incluyendo latencia |

Los pasos 2–3 son la primera inversión para calidad de solución. El 4 es la
inversión principal para certificados y puede tener prioridad si la necesidad
dominante es demostrar optimalidad. Las conclusiones del banco de pruebas,
no la novedad de cada técnica, determinan cuánto desarrollar.

No propongo reescribir SCIP, implementar un branch-and-bound propio ni migrar
ahora toda la aplicación a otro paquete. RouteOpt [16] es una referencia útil
para ingeniería modular de pricing y branch-price-and-cut; su disponibilidad
no lo convierte en un backend eléctrico compatible sin adaptación.

## 7. Experimentos que permitirían afirmar una mejora del LLM

**Separación de datos.** Usar entrenamiento para diseñar políticas, desarrollo
para seleccionarlas y prueba congelada para comparar. No usar resultados de
la instancia reservada `evaluation` para ajustar el algoritmo. Separar familias
de instancias, no solamente semillas de una misma geometría.

**Dificultad.** Incluir al menos: cobertura fácil, batería ajustada que exige
recargas, dependencias de estaciones con dirección relevante y casos donde
solo un subconjunto de clientes es factible. Escalar clientes y flota mediante
configuración. Las extensiones temporales forman un bloque de pruebas aparte.

Los benchmarks EVRPTW publicados son útiles, pero solo se comparan sus valores
oficiales si se implementan sus mismas restricciones y objetivos. Eliminar
carga o ventanas produce otra instancia; no permite anunciar un nuevo récord
sobre el benchmark original.

**Comparaciones mínimas propuestas:**

| Variante | Propósito |
|---|---|
| A. Motor actual | Referencia reproducible |
| B. Híbrido ALNS/SCIP/columnas, selector adaptativo sin LLM | Medir la mejora algorítmica |
| C. B ajustado fuera de la corrida con irace | Baseline fuerte de configuración automática |
| D. B con cartera de políticas desarrollada mediante LLM, congelada | Medir el aporte del análisis previo |
| E. C más supervisor LLM durante la corrida | Aislar aporte en ejecución |
| F. D más supervisor LLM durante la corrida | Evaluar combinación de ambos usos |

irace [17] proporciona un baseline consolidado de configuración automática.
Los métodos C y D deben disponer de presupuestos de entrenamiento explícitos
y de opciones comparables. Para E/F también se debe comparar selección aleatoria
o bandit de las mismas acciones: de otro modo no se distingue razonamiento del
beneficio de haber añadido operadores mejores.

**Piloto acotado, propuesto y no ejecutado:** 12 instancias, 3 semillas,
6 variantes y presupuestos de 15 y 60 s: **432 resoluciones**, con 4,5 horas
de presupuesto secuencial agregado, más preparación. La inferencia de ejecución
debe quedar dentro de esos presupuestos. Entrenamiento, configuración y análisis
previo se contabilizan aparte. Este tamaño sirve para depurar y estimar efectos;
no basta por sí solo para una afirmación amplia de superioridad.

Una evaluación posterior debe ampliar instancias independientes y añadir
ablaciones: sin reparación SCIP, sin columnas complementarias, sin nueva
telemetría y sin nuevo pricing. Eso separa qué componente explica la mejora.
La búsqueda memética constituye un competidor adicional cuando exista una
adaptación que respete el mismo contrato físico.

**Métricas:**

- Entregas y cota superior de entregas, antes que energía.
- Energía entre soluciones con igual cobertura; optimalidad energética
  condicionada cuando el máximo de entregas no está probado.
- Tiempo a primera solución y a cobertura completa, cuando existe.
- Evolución del incumbente y de cotas válidas; curvas de cobertura y de energía
  separadas, sin mezclar fases incompatibles en un único gap.
- Tiempo de pared total, tiempo de solver, validación y latencia AWS. Con
  concurrencia, informar intervalos sin sumar dos veces tiempos solapados.
- Llamadas, tokens recibidos, timeouts, propuestas rechazadas y decisiones que
  llegaron a aplicarse. Uso desconocido no equivale a coste cero.
- Rendimiento de operadores y columnas útiles por unidad de tiempo.

La comparación principal debe ser pareada por instancia y presupuesto.
Las semillas miden variabilidad dentro de instancia; no deben contarse como
problemas independientes. Informaría distribución de mejoras y sus intervalos,
incluyendo casos donde el LLM pierde. A igualdad de entregas, una mejora diminuta
de energía con varios segundos extra puede no servir al producto.

**Criterio de decisión.** Mantener el LLM durante la corrida si supera al mejor
baseline sin LLM a igual tiempo total o alcanza antes un objetivo de calidad
predefinido. Si solo mejora la fase de diseño, usarlo allí y desplegar políticas
congeladas. Si la búsqueda memética u otro método gana bajo el mismo contrato,
puede convertirse en generador principal conservando validación y cotas.

## 8. Fuentes y alcance de lectura

Los enlaces siguientes llevan a editoriales, autores, repositorios institucionales
o documentación oficial. «Texto» indica que se consultó contenido más allá del
resumen; no supone reproducción independiente de sus experimentos.

1. **Moradi y Mirzavand Boroujeni (2025).** *Prize-collecting Electric Vehicle
   routing model for parcel delivery problem*. Expert Systems with Applications
   259, 125183. DOI: 10.1016/j.eswa.2024.125183.
   [Registro institucional](https://mdanderson.elsevierpure.com/en/publications/prize-collecting-electric-vehicle-routing-model-for-parcel-delive/).
   **Alcance:** resumen y metadatos; variante con beneficios, no equivalencia
   con nuestro objetivo.
2. **Desaulniers, Errico, Irnich y Schneider (2016).** *Exact Algorithms for
   Electric Vehicle-Routing Problems with Time Windows*. Operations Research
   64(6), 1388–1405. DOI: 10.1287/opre.2016.1535.
   [Informe de autores, GERAD](https://www.gerad.ca/en/papers/G-2014-110).
   **Alcance:** registro y resumen; referencia fundacional de variantes de recarga.
3. **Nafstad, Desaulniers y Stålhane (2025).** *Branch-Price-and-Cut for the
   Electric Vehicle Routing Problem with Heterogeneous Recharging Technologies
   and Nonlinear Recharging Functions*. Transportation Science 59(3), 628–646.
   DOI: 10.1287/trsc.2024.0725.
   [Texto editorial](https://pubsonline.informs.org/doi/full/10.1287/trsc.2024.0725).
   **Alcance:** texto, especialmente pricing y aceleraciones; variante más rica
   en tiempo/recarga.
4. **Keskin y Çatay (2016).** *Partial recharge strategies for the electric
   vehicle routing problem with time windows*. Transportation Research Part C
   65, 111–127. DOI: 10.1016/j.trc.2016.01.013.
   [Repositorio de Sabancı](https://research.sabanciuniv.edu/id/eprint/29170/).
   **Alcance:** resumen y registro; no se reproducen resultados cuantitativos.
5. **Zheng, Liu y Ong.** *Hybrid Memetic Search for Electric Vehicle Routing
   With Time Windows, Simultaneous Pickup-Delivery, and Partial Recharges*.
   [Preprint de autores, arXiv:2410.19580v2](https://arxiv.org/html/2410.19580v2).
   **Alcance:** texto de la versión de autores de 2025; se usa para estructura
   del algoritmo, no para adjudicar superioridad en nuestra variante.
6. **Wouda, Lan y Kool (2024).** *PyVRP: A High-Performance VRP Solver Package*.
   INFORMS Journal on Computing. DOI: 10.1287/ijoc.2023.0055.
   [Código y documentación del proyecto](https://github.com/PyVRP/PyVRP).
   **Alcance:** documentación y capacidades declaradas; no se implementó un
   adaptador eléctrico.
7. **Eveborn y Rönnberg (2026).** *Branch-Price-and-Cut Accelerated with a
   Pricing for Integrality Heuristic for the Electrical Vehicle Routing Problem
   with Time Windows and Charging Time Slots*.
   [Preprint arXiv:2602.08673v2](https://arxiv.org/html/2602.08673v2).
   **Alcance:** texto y comprobación explícita de la restricción (4g), de máximo
   dos slots por ruta. Preprint; resultados propios de esa variante.
8. **Li, Yan y Wu (2021).** *Learning to Delegate for Large-scale Vehicle
   Routing*. NeurIPS 34.
   [Publicación](https://papers.nips.cc/paper/2021/hash/dc9fa5f217a1e57b8a6adeb065560b38-Abstract.html).
   **Alcance:** resumen y descripción del enfoque de selección de subproblemas.
9. **Liu et al. (2024).** *Evolution of Heuristics: Towards Efficient Automatic
   Algorithm Design Using Large Language Model*. ICML, PMLR 235, 32201–32223.
   [Publicación](https://proceedings.mlr.press/v235/liu24bs.html).
   **Alcance:** resumen y método general; no evidencia específica de nuestro EVRP.
10. **Ye et al. (2024).** *ReEvo: Large Language Models as Hyper-Heuristics with
    Reflective Evolution*. NeurIPS 37.
    [Publicación](https://proceedings.neurips.cc/paper_files/paper/2024/hash/4ced59d480e07d290b6f29fc8798f195-Abstract-Conference.html).
    **Alcance:** resumen y diseño de evolución reflexiva.
11. **Romera-Paredes et al. (2024).** *Mathematical discoveries from program
    search with large language models*. Nature 625, 468–475.
    DOI: 10.1038/s41586-023-06924-6.
    [Artículo](https://www.nature.com/articles/s41586-023-06924-6).
    **Alcance:** principios del ciclo de generación/evaluación; problemas
    distintos del ruteo eléctrico.
12. **Gong et al. (2026), LACE.** *Large language models discover complementary
    heuristics for combinatorial optimization*. Nature Machine Intelligence.
    Publicado el 1 de octubre de 2026. DOI: 10.1038/s42256-026-01307-8.
    [Artículo](https://www.nature.com/articles/s42256-026-01307-8).
    **Alcance:** resumen y materiales accesibles; no se presentan como
    resultados EVRP.
13. **Raoofi, Maheut y Tonelli (2026).** *Representing Search State to a Large Language Model:
    A Structured Telemetry Interface for Runtime Control of Adaptive Large
    Neighbourhood Search*. Systems 14(10), 1200.
    DOI: 10.3390/systems14101200.
    [Texto](https://www.mdpi.com/2079-8954/14/10/1200).
    **Alcance:** texto, tablas de resultados, presupuesto por iteraciones y
    comparación con PyVRP.
14. **LLM4MIP (2026).** Proyecto e informe público del 7 de octubre de 2026.
    [Sitio de los autores](https://llm4mip.github.io/).
    **Alcance:** sitio y estado de publicación; reporte técnico anunciado como
    próximo al momento de consulta.
15. **AWS.** Amazon Bedrock, interfaces de inferencia y herramientas.
    [Converse](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html)
    y [tool use](https://docs.aws.amazon.com/bedrock/latest/userguide/tool-use.html).
    **Alcance:** documentación oficial; las capacidades concretas se validan
    por modelo y permisos.
16. **You y Yang.** *RouteOpt: An Open-Source Modular Exact Solver for Vehicle
    Routing Problems*.
    [Repositorio asociado a INFORMS Journal on Computing](https://github.com/INFORMSJoC/2025.1415).
    **Alcance:** documentación del proyecto; fuente de ingeniería, no backend
    EVRP validado para este contrato.
17. **López-Ibáñez et al. (2016).** *The irace package: Iterated racing for
    automatic algorithm configuration*. Operations Research Perspectives 3,
    43–58. DOI: 10.1016/j.orp.2016.09.002.
    [Documentación de autores](https://iridia.ulb.ac.be/irace/).
    **Alcance:** configuración automática como control experimental.
18. **Zhao, Wang y Zeng (2026).** *G-LNS: Generative Large Neighborhood Search
    for LLM-Based Automatic Heuristic Design*.
    [Preprint arXiv:2602.08253v1](https://arxiv.org/html/2602.08253v1).
    **Alcance:** resumen y definición del enfoque; coevolución de operadores,
    sin evidencia específica de restricciones eléctricas.

La recomendación de arquitectura, los operadores propuestos, el riesgo de ciclos
en una relajación sin jornada y el diseño experimental son análisis propios.
Las mejoras publicadas citadas pertenecen a sus respectivos experimentos; las
únicas cifras del proyecto son las mediciones ya registradas en el informe local.
