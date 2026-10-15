# Caminos con regeneración y ventanas de tiempo

Investigación del 15 de octubre de 2026. Rama:
`codex/investigacion-caminos-recursos`. Base:
`56cb75c711dbf118cecfc2b584cf7e36f00941a2`, de `modelamiento`.

**Recomendación revisada tras ampliar la comparación bibliográfica:** para
nuestra red con pocos servicios, empezar por un **multigrafo de servicios
precalculado con alternativas no dominadas y perfiles exactos de batería**.
Reutilizar `RouteOracle` y mantener nuestro maestro por rutas sin H en SCIP.
La generación de conexiones durante el pricing queda como alternativa a evaluar
si el preprocesamiento resulta demasiado costoso. Conservar Dijkstra para el
escenario que satisface sus hipótesis.

Esta prioridad es una hipótesis de ingeniería que aún debe medirse. La literatura
respalda tanto el multigrafo como el pricing vial; no acredita que nuestro diseño
con búsquedas de conexiones anidadas en el pricing sea superior. Un catálogo
limitado de candidatos es heurístico; solo una representación completa o una
prueba adicional permite certificar el problema vial.

**Implementación posterior en esta rama:** la preparación separada usa
contracción de intersecciones con perfiles y alternativas, conservando nodos
cuando la eliminación sea costosa. Así no necesita enumerar toda la frontera
entre todos los pares antes de empezar el pricing. La vía Dijkstra segura sigue
disponible. Ver [diseño, garantías y comprobaciones](resource-paths.md).
Los cambios locales que estaban pendientes en `modelamiento` no se incorporaron
a esta rama. Los diagnósticos y experimentos de las secciones siguientes
describen el código anterior al cambio.

## 1. Diagnóstico del código y del modelo

Se leyó `modelamiento.pdf`, incluidas las ecuaciones (11)–(16), (20)–(24) y
(25)–(29), y se revisaron las páginas renderizadas de batería, ventanas y maestro.
La revisión distingue tres problemas:

| Componente actual | Comportamiento comprobado | Consecuencia |
|---|---|---|
| `service_graph.build_service_graph` | Rechaza cualquier `energy_kwh < 0` y usa Dijkstra con peso energético | La regeneración está excluida explícitamente; no se está ejecutando Dijkstra silenciosamente con pesos negativos |
| Mismo preprocesador | Conserva un solo camino por par y suma sus tiempos después de elegirlo | Puede perder un camino más rápido indispensable para una ventana o jornada |
| `route_resources.RouteOracle` | Propaga batería, tiempo y carga acumulada; separa saturación y espera; comprueba ventanas | El modelo de rutas sí contempla esas condiciones, pero no puede recuperar calles que el preprocesamiento descartó |

Fuentes locales: [preprocesador](../src/ev_routing/service_graph.py),
[oráculo](../src/ev_routing/route_resources.py),
[operaciones](../src/ev_routing/operations.py),
[validador](../src/ev_routing/validation.py),
[formulación](../modelamiento.pdf) y [alcance de la reducción](service-graph.md).

Además, `network.py` asigna a las calles distancia multiplicada por una tasa
descriptiva de kWh/km. Ese procedimiento no reconstruye descargas y regeneración
de cada calle. Cambiar el buscador de caminos no producirá por sí solo un modelo
energético vial con regeneración. Los intervalos históricos negativos deben
traducirse a coeficientes de segmentos futuros mediante un estimador justificado;
no copiar mediciones de un viaje a calles arbitrarias.

La formulación exige reserva en **cada segmento**, almacenamiento limitado por
capacidad y ventanas de **fin del servicio**, no solo de llegada. No hay consumo
auxiliar por esperar en las extensiones actuales. Los caminos que atraviesan un
cliente o cargador no activan automáticamente entrega o recarga.

## 2. Contraejemplos ejecutados

[Script reproducible](../scripts/research_service_paths.py):

```bash
uv run --locked python scripts/research_service_paths.py 2>&1 \
  | distill "Resume los contraejemplos, las aserciones y cualquier error."
```

### Una ventana hace perder una entrega

Instancia sintética con una base, una intersección, un cliente y un vehículo:
batería de 10 kWh, salida al 60 %, reserva de 1 kWh y jornada de 3.600 s.
La entrega dura 60 s y debe terminar antes de 900 s.

| Camino desde la base al cliente | Energía | Viaje | Fin de servicio | Admisible |
|---|---:|---:|---:|---|
| Por la intersección | 1 kWh | 1.200 s | 1.260 s | No |
| Directo | 2 kWh | 600 s | 660 s | Sí |

El regreso consume 1 kWh y tarda 300 s. Se agotó el mismo `RouteOracle` en
las dos representaciones, sin límite de movimientos:

| Representación | Entregas máximas encontradas al agotar el oráculo | Energía | Duración |
|---|---:|---:|---:|
| Red vial original | 1 | 3 kWh | 960 s |
| Red reducida con Dijkstra energético | 0 | 0 kWh | 0 s, vehículo inactivo |

Ambas soluciones pasaron el validador independiente. El resultado de cero
entregas es correcto para la red reducida: el error sería extrapolarlo a la red
vial original. No se ejecutó SCIP para este experimento.

### La suma oculta un déficit

Con salida de 6 kWh, capacidad de 10 y reserva de 1, el perfil de consumos
`[+6, -5]` suma solo 1 kWh. Restar esa suma predice una llegada con 5 kWh.
Sin embargo, la secuencia real es `6 → 0 → 5`: el primer segmento viola la
reserva. Bellman–Ford sobre la suma de energías tampoco descubre esta
infactibilidad física.

### La saturación vuelve insuficiente el coste escalar

Con la misma batería:

| Perfil | Suma nominal | Estados de batería | Consumo efectivo |
|---|---:|---|---:|
| `[-6, +4]` | −2 kWh | `6 → 10 → 6` | 0 kWh |
| `[+4, -6]` | −2 kWh | `6 → 2 → 8` | −2 kWh |

Ambos son factibles. En el primero se pierde regeneración por saturación.
La energía efectiva de un camino depende de la batería con que se inicia.

### Combinar tiempo y energía con pesos no recupera toda la frontera

Considérese el catálogo `(tiempo, energía)`:
`A=(5,9)`, `B=(10,6)`, `C=(15,1)`.
Con plazo 10, B es el camino factible de menor energía.
Pero minimizar `energía + α tiempo`, para `α ≥ 0`, nunca elige B:
ganarle a A exige `α ≤ 0,6` y ganarle a C exige `α ≥ 1`.
Por ello, incluso recorrer todos los pesos no garantiza conservar todos los
caminos útiles. Guardar solo el más rápido y el más económico también pierde B.
Este es un ejemplo algebraico independiente, no una instancia del concurso.

## 3. Qué aporta la literatura

Se priorizaron artículos originales, páginas editoriales y documentación oficial.
Los siguientes resultados tienen alcances distintos; no se trasladan sus tiempos
experimentales a este proyecto.

| Fuente | Aporte pertinente | Límite al adaptarla |
|---|---|---|
| SciPy, documentación de [Dijkstra][scipy-dijkstra] y [Johnson][scipy-johnson] | Dijkstra no admite pesos negativos; Johnson maneja arcos negativos y detecta ciclos negativos | Cambiar de rutina resuelve el problema aditivo, no las restricciones internas de batería ni las ventanas |
| Dorfman, Kaplan, Tarjan y Zwick, 2023, [Optimal energetic paths for electric cars][dorfman] | Adapta Bellman–Ford y Dijkstra/A* a la transición de batería saturada, sin ciclos negativos | Caso energético con estado inicial dado; no resuelve por sí solo la flota con ventanas y recargas |
| Baum, Sauer, Wagner y Zündorf, SEA 2017, [Consumption Profiles…][profiles] | Representa el consumo como función del SoC inicial y estudia perfiles y recargas parciales | El resultado energético no vuelve polinomial el problema con tiempo; su variante práctica acelerada renuncia formalmente a corrección |
| Letchford, Nasiri y Oukil, 2014, [Pricing routines…][road-pricing] | Estudia precisamente la pérdida de alternativas coste-tiempo al reducir una red vial y propone pricing en la red original | Su modelo no incorpora nuestra saturación; la frontera completa puede exigir espacio exponencial |
| Ben Ticha et al., 2019, [A branch-and-price algorithm…][road-comparison] | Compara los dos enfoques completos y encuentra ventaja del multigrafo, especialmente en redes reales con pocos clientes | No estudia nuestra batería; los tiempos publicados excluyen construir el multigrafo |
| Yamín, Desaulniers y Mendoza, publicación online 2024 y volumen 2025, [The Electric Vehicle Routing and Overnight Charging Scheduling Problem on a Multigraph][ev-multigraph] | Emplea alternativas de tiempo y energía con branch-price-and-cut y ventanas en un problema de vehículos eléctricos | Incluye carga nocturna en depósito; su evidencia no demuestra compatibilidad automática con nuestra regeneración y recarga en ruta |
| Desaulniers, Errico, Irnich y Schneider, 2016, [Exact Algorithms…][evrptw] | Branch-price-and-cut con etiquetas y funciones de extensión para ventanas y múltiples recargas parciales | Hay que derivar las extensiones para nuestra energía regenerativa, objetivo y convenciones temporales |
| Baum et al., 2019, [Shortest Feasible Paths with Charging Stops…][charge] | CHArge integra tiempo de recorrido, factibilidad energética y paradas de carga | Minimiza tiempo de un viaje; aquí se mantiene la prioridad entregas y después energía |
| Baum et al., 2020, [Modeling and Engineering Constrained Shortest Path Algorithms…][constrained] | Trata el compromiso tiempo-consumo con física de batería y métodos exactos y heurísticos | Su variante incluye elección de velocidad y excluye recargas; no copiar esas decisiones al problema actual |
| Ahmadi, Raith y Jalili, ESA 2025, [A Fast and Simple Algorithm…][nwrca] | NWRCA* combina etiquetas, cotas consistentes y evaluación diferida de dominancia, incluso con pesos negativos | Usa recursos aditivos y supone ausencia de ciclos negativos; no es un reemplazo directo para saturación y recargas continuas |

La conclusión para este repositorio es una **inferencia de diseño** apoyada en
estos trabajos y en los contraejemplos anteriores: usar perfiles y etiquetas,
integrados con el pricing existente, en lugar de sustituir únicamente la llamada
a Dijkstra.

La comparación de [Ben Ticha et al.][road-comparison], especialmente secciones
4.3.3–4.4, obliga a matizar la preferencia inicial por el pricing vial.
Los autores señalan que el estudio de 2014 examinaba un pricing con menos
recursos y altas densidades de clientes. Su comparación posterior favorece al
multigrafo, aunque advierte que futuras implementaciones podrían cambiar el
resultado. Es evidencia para priorizar un ensayo, no una garantía de velocidad.

## 4. Diseño recomendado

### Mantener un modo rápido con hipótesis comprobadas

Conservar el preprocesamiento actual cuando las energías sean no negativas y no
existan restricciones u objetivos dependientes del camino que invaliden la
sustitución por mínima energía. Ventanas, jornada y duración de carga requieren
revisar esas condiciones. Si se usa igualmente un catálogo fijo, declarar que el
certificado corresponde a él.

Dijkstra sigue siendo útil para **cotas inferiores de tiempo**, calculadas con
tiempos no negativos e ignorando batería y servicios. Por ejemplo,
`t + lower_bound_return_time > max_route_seconds` permite descartar un estado
que ya no puede regresar a tiempo. No emplear cero como supuesta cota inferior
de energía cuando existe regeneración.

### Extender el oráculo de recursos que ya existe

La etiqueta conceptual de una ruta conserva:

```text
(nodo vial, clientes atendidos, región factible de batería/tiempo/carga total,
 testigos de calles, servicios y recargas)
```

`RouteOracle` ya tiene esta estructura. Primero lo usaría como referencia exacta
en redes pequeñas con ambas dificultades, y después mediría sus costes sobre
subredes crecientes. No asumiría que explorar toda la red grande con la
implementación Python actual será rápido.

Las transiciones conservan:

- Calle: `b' = min(B, b - e)` y reserva en cada segmento.
- Servicio: `inicio = max(llegada, apertura)` y
  `inicio + duración <= cierre`, solo si se decide entregar.
- Cargador compatible: `0 <= q <= B-b`, con duración
  `3600*q/(eficiencia*potencia)` cuando está habilitada.
- Coste: `E = b_inicial + Q_total - b_final`, como en (25)–(28).

Al comparar estados del mismo nodo y conjunto atendido, mayor batería,
menor tiempo y menor carga acumulada permiten una dominancia segura bajo los
supuestos actuales. Para regiones continuas hay que comprobar un testigo
factible: no basta comparar extremos independientes. Tampoco se debe
convexificar arbitrariamente recursos de caminos diferentes y fabricar un
estado sin recorrido físico.

Las ventanas se evalúan al decidir una entrega y según la hora real de llegada.
No se puede eliminar universalmente una conexión porque falle a una hora
particular. Llegar temprano permite esperar bajo la física actual.
Ventanas fijas no equivalen a tráfico dependiente de la hora: incorporar este
último exigiría funciones de viaje y nuevas pruebas de dominancia.

### Acelerar mediante perfiles y caché, sin fijar un único camino

Para una pareja de servicios interesa una frontera de alternativas de
**duración y transformación de batería**, no solamente `(tiempo, suma de kWh)`.
Probaría primero su precomputación en un módulo independiente, con caché por
red y configuración y testigos viales. El pricing consumiría ese multigrafo,
sin repetir una búsqueda vial por cada etiqueta. Se conservan el maestro SCIP,
los clientes, cargadores, recargas parciales y revisitas.

La comparación entre conexiones debe cubrir los SoC iniciales relevantes, no
solo el 60 % de la salida del depósito. La batería cambia durante la ruta y con
las recargas. Comprobar la dominancia por perfiles es una exigencia adicional
respecto de un multigrafo ordinario de costes y tiempos aditivos.

Si la frontera o su tiempo de construcción crecen demasiado, evaluaría generar
conexiones bajo demanda o explorar la red vial en un único pricing de recursos.
Son dos implementaciones distintas: la evidencia sobre pricing vial no demuestra
que anidar una búsqueda independiente por pareja dentro del pricing sea mejor.
Antes de elegir mediría preparación, resolución y memoria conjuntamente.

Entre dos eventos consecutivos no hay recarga ni servicio intermedio. Para
tiempos constantes se puede resumir cada camino fijo mediante un perfil exacto
de batería y su duración, como se demuestra en la sección siguiente. Una
alternativa domina universalmente a otra solo si tarda menos o igual, admite
todos sus SoC iniciales factibles y deja al menos tanta batería para cada uno.
Los servicios atravesados siguen siendo tránsito hasta elegir una parada.

Las cotas de A* deben corresponder al objetivo y a los duales del pricing.
Una prioridad heurística puede ordenar la búsqueda; no permite podar ni
declarar agotado el pricing sin una cota válida. Comenzaría por cotas temporales
y dominancia comprobada; estudiaría búsqueda bidireccional después, porque
invertir saturación, espera y recarga exige funciones específicas.
No marcar un nodo vial como resuelto después de su primera extracción:
pueden llegar etiquetas distintas que aún sean necesarias. Usar una exploración
que permita corregir etiquetas hasta demostrar las condiciones que justifican
un orden definitivo de procesamiento.

### Heurística inicial concreta

Si hace falta entregar una mejora acotada antes del motor general:

1. Crear candidatos rápidos y energéticamente factibles para distintos
   presupuestos temporales mediante búsquedas con recursos.
2. Guardar varios caminos no dominados y sus perfiles; reutilizar sus calles
   para construir incumbentes y columnas factibles.
3. Validar cada ruta completa y cada expansión.
4. Continuar con el oráculo exacto para detectar alternativas omitidas y
   completar la prueba; si no termina, conservar solo cotas justificadas.

Limitar candidatos o usar dominancia aproximada pertenece únicamente a esa
heurística. Nunca convertir el límite en una definición de factibilidad.
Un timeout sin encontrar camino significa **búsqueda inconclusa**, no
inaccesibilidad demostrada. No recomiendo empezar por una metaheurística de
flota: el problema comprobado está en la representación de los caminos.

## 5. Un perfil exacto pequeño para cada camino fijo

Esta derivación aplica directamente las ecuaciones (11)–(14) del modelo local.
Supone energías fijas por segmento, capacidad B, reserva R y ninguna recarga
intermedia. Primero se aplica el margen configurado a cada descarga; no al total
neto de un camino con signos mezclados.

Sean `e_1,...,e_n` esos consumos y:

```text
S_0 = 0
S_j = e_1 + ... + e_j
E = S_n
m = min_j S_j
M = max_j S_j
D = max_{0 <= k <= j <= n}(S_j - S_k)
```

Para una batería inicial `b` en `[R,B]`, el camino completo es factible si y
solo si:

```text
b >= R + M
D <= B - R
```

Cuando es factible, su batería final es:

```text
F_P(b) = min(b - E, B - E + m)
```

La energía efectiva es `b-F_P(b)`. Por tanto basta almacenar, para B y R fijos,
el umbral de entrada `R+M`, E y el techo de llegada `B-E+m`, después de comprobar
D. La secuencia vial se conserva para auditar y reconstruir la solución.

**Justificación.** Por inducción en la recurrencia saturada, tras el prefijo j:
`b_j = min(b-S_j, B-S_j+min_{0<=k<=j} S_k)`.
Exigir `b_j >= R` para todos los prefijos da exactamente las dos condiciones
anteriores. La capacidad superior ya está incorporada en la recurrencia.
La fórmula final resulta al tomar `j=n`.

El script contrastó esta expresión y su dominio contra una reproducción por
segmentos en **74.195 estados**: todas las secuencias de 1 a 5 arcos con energías
en `{-6,-2,0,2,6}`, y 19 estados iniciales entre 1 y 10 kWh.
Todos coincidieron. Esa enumeración es una comprobación de implementación de la
fórmula; la demostración cubre las energías reales bajo las hipótesis señaladas.
No demuestra escalabilidad ni que un catálogo de varios caminos esté completo.

## 6. Cambios necesarios y certificados

La adaptación no es simplemente devolver más elementos desde Dijkstra:

| Pieza | Cambio que habría que diseñar e implementar |
|---|---|
| `contracts.py` | Identificador de alternativa/perfil: hoy rechaza arcos paralelos por pareja |
| `service_graph.py` y `PathArchive` | Varios caminos identificables por par, perfiles, duración, testigos y hashes; distinguir catálogo completo e incompleto |
| `route_resources.py` | Aplicar perfiles exactos y/o explorar calles a demanda conservando estados continuos y testigos |
| `operations.py`, `validation.py` y expansión | Elegir por identificador del camino; reproducir saturación, margen por segmento, tiempos y servicio |
| `route_solver.py` y resultados | Registrar alcance del pricing y de las cotas; preservar el maestro sin H y las fases lexicográficas |

Actualmente varias tablas de consulta usan `(from_node_id, to_node_id)` como
clave. Permitir duplicados solo en el contrato sobrescribiría alternativas en
esas tablas. Una primera referencia sobre calles originales evita esa migración;
la compresión con perfiles exige hacerla explícitamente.

**Ciclos:** los arcos negativos no implican por sí solos ciclos negativos.
Johnson y varios algoritmos estudiados requieren excluir estos últimos.
Detectarlos debe producir un diagnóstico del modelo energético, no borrar los
arcos, limitar visitas o declarar automáticamente infactible el problema físico.
La saturación cambia el problema respecto de sumar costes indefinidamente.
También deben distinguirse ciclos de energía física y costes reducidos negativos
creados por los duales.

**Certificación:** un catálogo incompleto puede proporcionar una solución vial
factible y una cota primal. Su óptimo o su LP restringido no certifican el problema
vial completo. La prueba exige pricing completo sobre las alternativas relevantes
o cotas válidas del problema original, y conservar la información por fase.
Validación física y optimalidad son comprobaciones diferentes.

## 7. Verificación realizada y siguiente experimento

Ejecutado en esta rama:

- Script de contraejemplos: aserciones completadas y 74.195 comprobaciones de
  perfiles; agotamiento del oráculo en las dos instancias temporales.
- `ruff check scripts/research_service_paths.py`: aprobado.
- `pytest -q tests/test_service_graph.py tests/test_operations.py`:
  **66 pruebas aprobadas**, 18,25 s.

No se ejecutó la suite completa ni un benchmark de la instancia vial grande.
Estos resultados no acreditan rendimiento de un algoritmo aún no implementado.

El siguiente experimento debería comparar sobre los mismos snapshots:

1. Dijkstra actual, como control dentro de su dominio y como catálogo restringido
   en los ejemplos temporales.
2. Multigrafo precalculado de alternativas con perfiles, registrando si se
   completó la búsqueda o si quedó un catálogo heurístico.
3. Pricing completo sobre calles/perfiles, con referencia exhaustiva pequeña.
4. Generación bajo demanda, solo después de tener las dos referencias anteriores.

Separar casos sin regeneración, solo regeneración, solo ventanas y ambos;
incluir saturación, déficit antes de una bajada, recarga parcial, espera,
final de servicio exactamente en el cierre, pasos por servicios sin acción y
revisitas necesarias. Mantener semillas, presupuestos, hardware y objetivos.
Medir entregas, energía efectiva, violaciones, tiempo de preparación y pricing,
etiquetas, memoria, caminos añadidos y alcance real del certificado.
Reutilizar datos preparados y reservar `evaluation` para resolver, sin elegir
configuraciones a partir de su desempeño.

La decisión pendiente es el diseño de la interfaz de perfiles y su caché.
La dirección prioritaria es **preprocesamiento modular de un multigrafo con
perfiles y pricing con recursos sobre él**. El resultado del ensayo, incluyendo
el coste de preprocesar, decidirá si conviene introducir generación bajo demanda.

[scipy-dijkstra]: https://docs.scipy.org/doc/scipy/reference/generated/scipy.sparse.csgraph.dijkstra.html
[scipy-johnson]: https://docs.scipy.org/doc/scipy/reference/generated/scipy.sparse.csgraph.johnson.html
[dorfman]: https://arxiv.org/abs/2305.19015
[profiles]: https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.SEA.2017.19
[road-pricing]: https://www.lancaster.ac.uk/staff/letchfoa/articles/2014-pricing-time-windows.pdf
[road-comparison]: https://pure.tue.nl/ws/files/126068122/Ticha_et_al_2019_Networks.pdf
[ev-multigraph]: https://pubsonline.informs.org/doi/abs/10.1287/ijoc.2023.0404
[evrptw]: https://pubsonline.informs.org/doi/10.1287/opre.2016.1535
[charge]: https://arxiv.org/abs/1910.09812
[constrained]: https://arxiv.org/abs/2011.10400
[nwrca]: https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.ESA.2025.97
