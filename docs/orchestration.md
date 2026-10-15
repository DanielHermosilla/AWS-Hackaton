# Orquestación de la búsqueda de rutas

**Referencia del motor anterior `codex/solver-orchestrator`.** Su contrato por
etapas y sus mediciones se conservan para comparación. La implementación actual
con callbacks asíncronos, perfiles de batería, ALNS y población memética está
documentada en [llm-head-search.md](llm-head-search.md); reemplaza las limitaciones
de eventos y reparación descritas aquí.

La rama anterior se creó en un worktree separado desde `56cb75c`, incluyendo una
copia de los cambios sin commit que existían en el checkout de origen.
`c595242` conserva esa copia. No se modifica el workspace donde trabaja el
otro agente. Las instancias y los caminos usados en los ensayos se copiaron;
no se reentrena energía ni se usa la instancia reservada para elegir opciones.

## Flujo ejecutado

1. Verificar el certificado existente de reducción a un tour. Sigue requiriendo
   todas sus hipótesis; ninguna sugerencia del LLM lo habilita por sí sola.
2. `before_search`: elegir la estrategia sobre el perfil de la instancia.
3. Construir rutas por inserción y múltiples inicios. Una vecindad adicional
   intenta tours con una recarga parcial. Solo son generadores de incumbentes:
   no excluyen del pricing recorridos con varias recargas o revisitas.
4. `after_seed`: observar entregas, energía, coste del arranque y columnas
   disponibles. Revisar las decisiones que aún pueden ejecutarse.
5. Mejorar incumbentes con inversión de segmentos, reubicación, intercambio y
   destrucción/reinserción. Se comprueba el coste dirigido y la factibilidad.
6. Si un testigo sirve todos los clientes, la cota de cardinalidad prueba el
   objetivo de entregas y se pasa inmediatamente a energía. En caso contrario,
   el LLM puede asignar entre 10 % y 95 % del tiempo restante a esa primera fase.
7. Con todos los clientes atendidos y energías no negativas, calcular una cota
   de asignación o una relajación de tour sin recursos. Intentar reparar el
   orden de ese tour mediante partición de flota o una recarga parcial.
8. Resolver etapas de SCIP con el maestro por rutas. Un solve breve del conjunto
   de columnas conocidas puede mejorar el incumbente; después vuelve el pricing
   completo. La búsqueda heurística usa los duales actuales para insertar
   clientes; si no encuentra columnas, continúa el oráculo físico exacto.
9. `search_stagnation`: después de una etapa sin mejora, y si quedan tiempo y
   llamadas, el LLM revisa pricing, cortes, mejoras primales y tuning de SCIP.
10. Validar el resultado compacto y su expansión vial, conservando cotas y
    estados separados para entregas y energía.

Los modos `standard` y `deterministic` ejecutan el mismo motor sin AWS.
`deterministic` usa más inicios de inserción y pricing. `adaptive` parte de
valores operativos y permite modificar las acciones implementadas.

## Poder del LLM y límites

`RoutePolicy` es el esquema ejecutable de opciones. El LLM recibe únicamente
el perfil, las mediciones de progreso y las acciones que aún tienen efecto.
Una respuesta parcial conserva los valores anteriores. Una respuesta inválida
conserva la última política válida; se registra fallback, no éxito adaptativo.
Los campos de una etapa terminada aparecen como inactivos si el modelo insiste
en modificarlos. No se ejecuta código generado.

| Área | Opciones |
|---|---|
| Arranque | Estrategia de inserción, cantidad de inicios, recarga heurística y fracción de tiempo |
| Mejora primal | Operadores, pasadas, fracción destruida, rondas y tiempo |
| Tiempo | Fracción para entregas, duración de etapas y tiempo para el maestro restringido |
| Cotas | Ninguna, asignación o tour relajado; presupuesto y lotes de subtours |
| Pricing | Heurístico seguido de exacto o solo exacto, inicios, segundos, lotes y pool opcional |
| Oráculo físico | Compartir vehículos compatibles, orden de exploración y dominancia |
| Cortes | Ninguno o subset-row triples; todos reciben coeficientes de columnas futuras |
| SCIP | Presets, branching y parámetros instalados de LP, heurísticas y selección de nodos |

`scip_tuning.py` valida nombres, tipos y dominios contra SCIP instalado.
Los límites globales, threads, semilla, gap y tolerancias no son decisiones
del LLM. Presolve y separación genéricos permanecen desactivados en el maestro
con columnas futuras; sus presets sí actúan en las relajaciones finitas de arcos.
Cada etapa registra los cambios nativos reales, incluidos los efectos de presets.

La selección de campos permitidos se reduce a medida que termina cada etapa.
Los parámetros de creación de oráculos no se cambian después de crearlos.
Los operadores rápidos se aplican solo en el caso no negativo sin condiciones
temporales que soportan. Las demás extensiones continúan en el oráculo físico.

## Recursos y llamadas

- Máximo predeterminado: cuatro llamadas, configurable con `--llm-max-calls`.
- Asignación de inferencia: 25 % del tiempo global, configurable con
  `--llm-time-fraction` y limitada a 50 %.
- Timeout predeterminado por llamada: ocho segundos. Para ensayos de 60 segundos,
  se utilizó `--llm-timeout-seconds 4`.
- Salida predeterminada: hasta 2048 tokens, configurable con
  `--llm-max-output-tokens`.
- `--llm-reasoning-effort` envía `output_config.effort` para modelos Anthropic
  compatibles. Al usarlo se omite `temperature`: Fable no admite el valor cero.
  El identificador de modelo sigue siendo obligatorio y explícito.
- No se lanza una llamada si no queda su timeout más un segundo de margen en
  la asignación de inferencia y en el presupuesto global.
- Una respuesta que llega después del deadline se registra pero no se aplica.
- El timeout de red limita conexión y lectura, no constituye una preempción
  exacta de toda llamada. Los presupuestos son blandos y se registra el tiempo real.
- Todos estos tiempos están incluidos en la resolución, no se suman nuevamente
  al tiempo total. Preprocesamiento y validación permanecen identificados aparte.

Las llamadas ocurren en el hilo de coordinación, fuera de callbacks SCIP.
Un fallo de AWS no elimina ni desactiva el pricing exacto.

## Cotas y certificados

El maestro restringido, resuelto solo con columnas conocidas, es una heurística
primal. **Su cota nativa no es una cota del problema completo.** Se descarta para
certificación. Un timeout del oráculo tampoco acredita ausencia de columnas.

La relajación energética de `route_relaxation.py` requiere servicio completo
y arcos de energía no negativa. Calcula distancias mínimas dirigidas en el
grafo de entrada, incluyendo cargadores. Esto no requiere que los costes de
sus arcos directos ya satisfagan exactamente la desigualdad triangular.

Para cualquier solución de flota que sirve todos los clientes:

1. Concatenar sus recorridos en el depósito conserva la suma de energías.
2. Ordenar los eventos de entrega únicos y conservar un evento de depósito.
3. Reemplazar los recorridos entre esos eventos por distancias mínimas no puede
   aumentar la energía. Eliminar las visitas adicionales al depósito tampoco.

Así se obtiene un tour en la clausura cuyo coste no supera el de la flota.
Un cycle cover de asignación relaja a su vez ese tour. Por tanto la asignación
y las cotas duales de SCIP al añadir subtours son cotas inferiores válidas.
Se resta un margen conservador para acumulación numérica de caminos y sumas.
No se usa esta cota cuando quedan clientes sin atender o existe regeneración.
Las restricciones temporales y de batería se eliminan solo en la relajación.

Un tour de esa relajación **no es automáticamente factible** para la flota:
su reparación se valida antes de entrar como incumbente. La formulación
principal y sus certificados siguen correspondiendo al maestro por rutas
sin H y a la instancia física original.

El oráculo conserva recargas continuas, ventanas, saturación, revisitas y retornos.
La mejora del caso de dos vértices resuelve analíticamente el intervalo de
combinaciones convexas y comprueba el testigo sin relajar dominancia.
`vertices_only` es conservador: puede retener estados adicionales.
Vehículos con las mismas estaciones compatibles comparten la exploración
física cuando la política lo elige; cada uno conserva sus propios duales y columnas.
No hay cota de movimientos, estaciones o etiquetas. El límite del pool afecta
solo columnas heurísticas opcionales.

## Ejecución y evidencia

```bash
uv sync --frozen --extra dw
uv run ev-routing run \
  --solver scip-routes \
  --instance artifacts/test-40c-60s/validation-seed0/service-instance.json \
  --road-instance artifacts/test-40c-60s/validation-seed0/instance.json \
  --path-archive artifacts/test-40c-60s/validation-seed0/service-paths.json \
  --search-policy adaptive \
  --bedrock-model us.anthropic.claude-fable-5 \
  --aws-region us-east-1 --aws-profile hackathon \
  --llm-reasoning-effort high --llm-max-output-tokens 4096 \
  --llm-max-calls 3 --llm-timeout-seconds 25 --llm-time-fraction .5 \
  --time-limit-seconds 120 --threads 1 --seed 0 \
  --solver-log-directory artifacts/orchestrator/example/logs \
  --output artifacts/orchestrator/example/result.json \
  --show-llm-trace
```

`logs/decisions/NN-evento/` conserva la solicitud, respuesta y estado de cada
decisión. `llm-decision.json` contiene el informe consolidado.
`solve.search.phases` distingue etapas del maestro restringido y del exacto,
tiempos del pricing heurístico y físico, columnas, etiquetas, parámetros nativos
y aceptación del arranque. `first_full_delivery_seconds` indica cuándo quedó
disponible un testigo completo. `energy_relaxation` documenta la cota independiente.
Estos campos no prueban por sí solos que la política adaptativa acelere una instancia.

El perfil `hackathon` permitió invocar Claude Fable 5. La política IAM de la
cuenta rechazó Opus 5.5, aunque el catálogo lo mostraba disponible. No se
modificaron permisos ni se cambió de región para eludir ese límite.
El esfuerzo máximo de Fable superó el timeout de 12 segundos en las solicitudes
completas y una prueba de latencia de 55 segundos. El esfuerzo alto respondió
en unos 21 segundos; por eso el ejemplo reserva tiempo para decisiones útiles.
Un modelo más capaz también puede retrasar la primera solución.

La comparación inicial con Nova Micro se conserva en
`artifacts/orchestrator/benchmark-40c-final/`,
con hashes de código y entradas, orden pareado por semilla, recursos idénticos,
uso real de Bedrock y validación vial. El coste energético solo se compara
directamente entre resultados con el mismo número de entregas.
Los resultados y las limitaciones están en
[performance-orchestrator.md](performance-orchestrator.md).

Fuentes de integración: [pricers de SCIP](https://www.scipopt.org/doc/html/PRICER.php),
[API PySCIPOpt](https://pyscipopt.readthedocs.io/en/stable/api/model.html) y
[heurísticas nativas](https://pyscipopt.readthedocs.io/en/stable/tutorials/heuristic.html).
Modelo y API:
[Fable 5 en Bedrock](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-fable-5.html)
y [razonamiento adaptativo](https://docs.aws.amazon.com/bedrock/latest/userguide/claude-messages-adaptive-thinking.html).
