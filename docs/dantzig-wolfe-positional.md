# Referencia heredada: GCG posicional con H

Este documento conserva el experimento `--solver gcg`, que usa H.
El motor vigente sin H y el benchmark actual están en
[dantzig-wolfe.md](dantzig-wolfe.md). Los comandos y resultados siguientes
son históricos y no describen el motor actual del script de benchmark.

La opción experimental `--solver gcg` resuelve el **mismo MILP Pyomo** mediante
GCG, con PyGCGOpt y PySCIPOpt. Añade generación de columnas, branching y cortes
compatibles nativos. No implementamos otro branch-and-bound ni un pricing que
declare optimalidad sin prueba. El backend `auto` conserva Gurobi/SCIP.

## Formulación y alcance

`dw_bridge.py` traduce las filas activas, constantes, cotas, dominios y objetivo
del modelo construido en `model.py`. Registra una huella de la matriz por fase.
No reemplaza las ecuaciones del PDF ni sus extensiones operacionales.

Para cada vehículo \(k\), sea \(X_k\) su conjunto factible local, con las
variables binarias y continuas originales. La descomposición representa un
punto del bloque mediante combinaciones convexas de puntos de
\(\operatorname{conv}(X_k)\). El maestro conserva las restricciones acoplantes
y GCG mantiene la integralidad original mediante su búsqueda:

\[
 v_k=\sum_{p\in P_k}v_{kp}\lambda_{kp},\qquad
 \sum_{p\in P_k}\lambda_{kp}=1,\qquad \lambda_{kp}\geq0.
\]

El pricing busca puntos con costo reducido mejorante dentro del bloque.
Los multiplicadores de las filas del maestro, sus cortes y las restricciones
de branching deben incorporarse correctamente; esa responsabilidad permanece
en GCG. Un maestro restringido sin columnas mejorantes **certificadas** no da
por sí solo una cota válida del problema completo.

Se desactiva la discretización de bloques mixtos de GCG
(`relaxing/gcg/discretization=False`, `mipdiscretization=False`): carga, batería
y relojes son continuos. Se utiliza convexificación, sin agregar rutas
mediante supuestos de integralidad de las cantidades continuas.

| Descomposición | Bloques | Maestro |
|---|---|---|
| `vehicle` | Todas las filas locales de cada vehículo, incluidas batería, recarga y tiempos | Entregas únicas, energía total y acoplamientos |
| `vehicle_routing` | Ubicación, continuidad y vínculo de servicio, ecuaciones (1)–(5) | También batería, energía y tiempos |

La segunda opción tiene una relajación distinta y puede hacer más barato el
pricing; sus columnas parciales no son necesariamente rutas factibles en
batería. Todas las filas y dominios siguen presentes. No se promete que una
opción sea siempre superior. GCG desactiva el presolve original al recibir
esta descomposición explícita; continúa usando sus procedimientos internos.

**H permanece en el modelo.** Esta implementación descompone nuestra formulación
por posiciones; no implementa una formulación de rutas sin H. Tampoco recupera
caminos eliminados por el preprocesamiento Dijkstra. En la variante de servicios,
el certificado sigue condicionado a los caminos fijos y al H de traslados.
Se conservan regeneración, tránsito sin entrega, visitas repetidas, retornos
intermedios y todas las opciones de `operations`.

## Tres políticas sobre el mismo motor

| Política | Decisiones |
|---|---|
| `standard` | Bloques `vehicle`, estrategias nativas de GCG, sin AWS |
| `deterministic` | Bloques `vehicle`, separación original, ranking por eficacia dividida por raíz de densidad, hasta 20 cortes opcionales, pricing heurístico seguido del exacto, lotes de 50 columnas, límite heurístico inicial de 500 nodos |
| `adaptive` | Bedrock elige acciones del contrato validado a partir de estructura y progreso |

Las tres usan la misma convexificación, presupuesto, hilos, semillas, tolerancias
y criterios de certificación. `standard` significa GCG con nuestra descomposición
fijada; no significa Gurobi ni detección automática de descomposiciones.

El LLM puede seleccionar:

- Descomposición `vehicle` o `vehicle_routing` **antes de cada fase**.
- Familia `native`, `original` u `original_basis`, mediante los separadores
  propios de GCG. No se admiten desigualdades redactadas por el LLM.
- Ranking nativo, eficacia o eficacia ajustada por densidad; entre 1 y 200
  cortes opcionales. Los cortes forzosos permanecen bajo control del solver.
- Pricing nativo, heurístico seguido del exacto o exacto; entre 1 y 500 columnas
  por ronda, presupuesto heurístico inicial de 10 a 10000 nodos y estabilización.

El límite heurístico es el parámetro nativo `startnodelimit`: GCG puede adaptarlo
internamente, no es un presupuesto total adicional. Los lotes de columnas no
eliminan columnas admisibles del problema.

No ofrecemos subset-row: el separador nativo requiere un maestro puramente
entero y no se aplica a esta convexificación con variables continuas. Habilitar
un separador tampoco asegura que encuentre cortes violados.

`dw_callbacks.py` registra un observador de pricing, un selector de cortes y
eventos de LP. El observador devuelve `NOTAPPLICABLE` y cota menos infinito;
GCG sigue ejecutando su solver de pricing. El pricing exacto permanece
habilitado, incluido el tratamiento nativo de Farkas. Un contador cero de
callbacks exactos no prueba que faltó certificación: el pricing heurístico
nativo también puede resolver un subproblema a optimalidad.

Durante una fase, el trabajador de Bedrock recibe solamente una copia JSON.
No toca objetos SCIP. Los callbacks del hilo del solver validan y aplican las
respuestas. La descomposición queda bloqueada durante `optimize()`.
Las respuestas tardías se registran sin aplicarlas a otra fase. Se conserva
la última política válida entre fases; un fallo inicial usa la política estándar.

## AWS y presupuestos

Instalación opcional, con versiones binarias compatibles fijadas en el lockfile:

```bash
uv sync --locked --extra dw
```

`--bedrock-model` acepta un ID de modelo o perfil de inferencia; alternativamente
se lee `BEDROCK_MODEL_ID`. No hay modelo predeterminado.
Definir la variable en la misma terminal antes de usar los ejemplos:

```bash
# Modelo utilizado en nuestra prueba real; se puede reemplazar por otro habilitado.
export BEDROCK_MODEL_ID='us.amazon.nova-micro-v1:0'
```

Si se omite ese paso, `"$BEDROCK_MODEL_ID"` puede expandirse a una cadena vacía.
El programa lo detecta antes de ejecutar las corridas. Alternativamente, pasar
el ID directamente en `--bedrock-model`.

`--aws-region` usa `AWS_DEFAULT_REGION` o `us-east-1`.
`--aws-profile` usa `AWS_PROFILE` o `hackathon`; pasar `--aws-profile ''` habilita
la cadena estándar sin un perfil nombrado. El programa no carga archivos `.env`
automáticamente ni guarda claves.

La invocación real usa `bedrock-runtime.converse`. Tener un perfil en el catálogo
no demuestra permiso para invocarlo: revisar `tuning.decisions`.
El perfil transmitido contiene conteos, H, opciones operacionales resumidas,
estado de búsqueda y acciones admitidas; no contiene direcciones ni históricos.

Valores iniciales: máximo 3 llamadas por corrida, separación de 15 segundos
entre solicitudes durante búsqueda, al menos 10 callbacks de pricing y timeout
de lectura de 8 segundos. La conexión tiene su propio límite de hasta 3 segundos;
no hay reintentos de inferencia. El máximo de salida es 700 tokens.
El tiempo de autenticación y los límites nativos no constituyen un límite duro
de pared. Las llamadas iniciales y tardías también se contabilizan.

Las llamadas iniciales consumen el presupuesto compartido. Las llamadas durante
el solve pueden solaparse con el solver. `runtime_seconds.llm` es trabajo remoto
incluido en resolución/total: **no sumarlo otra vez**. Los tokens provienen de
Bedrock; el costo monetario queda en `null` sin una tarifa verificada.
Un JSON inválido, una acción desconocida o un error de AWS no alteran el modelo.

## Ejecución y benchmark

Ejemplo sintético:

```bash
uv run --locked --extra dw ev-routing run \
  --instance examples/toy_recharge.json \
  --solver gcg --search-policy adaptive \
  --bedrock-model "$BEDROCK_MODEL_ID" \
  --aws-region us-east-1 --aws-profile hackathon \
  --time-limit-seconds 60 --threads 1 \
  --output artifacts/dw-adaptive.json
```

Benchmark de las tres políticas sobre los caminos ya preparados:

```bash
bash scripts/benchmark_dw.sh \
  --instance artifacts/hackathon/service-instance.json \
  --road-instance artifacts/hackathon/instance.json \
  --path-archive artifacts/hackathon/service-paths.json \
  --initial-solution artifacts/hackathon/service-instance.start.json \
  --bedrock-model "$BEDROCK_MODEL_ID" \
  --aws-region us-east-1 --aws-profile hackathon \
  --time-limit-seconds 60 --threads 1 --seeds 0 1 2 \
  --output-dir artifacts/benchmark-dw
```

Son **9 corridas** en procesos separados, 3 por política; como máximo 9 llamadas
a Bedrock con el límite inicial de 3 por corrida adaptativa. `--seeds 0` reduce
el ensayo a 3 corridas. `--policies standard deterministic` permite validar sin
AWS. Para los JSON viales/sintéticos, omitir los dos argumentos del contexto de
servicios. El arranque es opcional; si se proporciona, es el mismo para todos.

El script no vuelve a preparar la red ni cambia H. Comprueba hashes de entradas,
código y versiones; mantiene recursos y presupuesto; intercala las políticas
con un orden aleatorio reproducible por semilla y repetición. Cada corrida
guarda resultado, log del proceso, logs nativos y registro de ejecución.
`summary.csv` y `summary.json` incluyen entregas, energía, factibilidad,
cotas/gaps por fase, tiempo nativo, tiempo total, llamadas, tokens y decisiones.

El supervisor corta un proceso que exceda presupuesto más
`--process-grace-seconds` (60 por defecto), registrando código 124. No inventa
un resultado factible cuando el proceso muere antes de guardar JSON.
`--resume` reutiliza registros solo con el mismo manifiesto y hashes de resultado.
No mezcla corridas de versiones distintas ni vuelve a llamar a AWS por registros
ya terminados.

Si no se aplicó ninguna propuesta real, la corrida adaptativa queda
`llm_comparison_eligible=false` y el benchmark devuelve código 2; un fallback
no se presenta como evidencia a favor del LLM. Los errores de ejecución también
producen código 2. Una corrida sin solución o con infactibilidad probada conserva
su estado para el análisis.

Comparar primero factibilidad y entregas. Comparar energía directamente solo
al mismo cumplimiento. Luego comparar cotas por fase y tiempo total, incluido
AWS. El script entrega observaciones; no concluye aceleración ni significancia
estadística. Las pruebas pequeñas validan semántica y conexión de callbacks,
no escalabilidad en los 81 servicios.

## Certificación y trazabilidad

Las cotas se leen de `GCG.getDualbound()` del problema original; nunca de la
función objetivo del maestro restringido. Se conservan los criterios existentes
de `solve.py`: prueba entera para entregas, cierre numérico para energía y
optimalidad lexicográfica solo si ambas fases están probadas.

Un error en callbacks interrumpe la búsqueda, anula el certificado de esa fase
y conserva cualquier incumbente validado. La recuperación carga variables
originales en Pyomo y pasa por `validation.py`. La variante de servicios se
expande y valida también sobre las calles antes de presentarse como factible.

`solve.search` registra versiones, matriz, partición de filas, parámetros
efectivos, callbacks, decisiones aceptadas/rechazadas, errores y tiempos.
`native_cuts_applied` cuenta los cortes aplicados por el maestro; el contador
`policy_selected_cuts` solo mide selecciones del callback propio, no las que
realiza el selector nativo al delegarle la decisión.
`initial_solution_stored` es la respuesta a almacenar el arranque; no demuestra
que haya acelerado la resolución.

Referencias primarias:

- [GCG](https://github.com/scipopt/gcg), motor de branch-price-and-cut.
- [PyGCGOpt: instalación y ABI](https://github.com/scipopt/PyGCGOpt/blob/master/INSTALL.md).
- [PyGCGOpt: modelos y cotas](https://scipopt.github.io/PyGCGOpt/api/model.html).
- [SCIP: responsabilidades del pricing](https://www.scipopt.org/scip/doc/html/PRICER.php).
- [PySCIPOpt: selección de cortes](https://pyscipopt.readthedocs.io/en/latest/tutorials/cutselector.html).
- [Bedrock Converse](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html).

