# Rendimiento del maestro por rutas y su orquestador

Mediciones locales del 15 de octubre de 2026. El trabajo se realizó en
`codex/solver-orchestrator`, en un worktree aislado del checkout `modelamiento`
donde continúa otro agente.

## Resultado principal

Sobre el mismo snapshot de **40 clientes, 60 cargadores y dos vehículos**,
el código original encontró **2 entregas en 60 segundos**. El motor mejorado
sirve **40/40**, prueba ese objetivo de entregas y obtiene **14,566607 kWh**.
La cota inferior energética es **14,525265 kWh**, con **0,283813 %** de gap
respecto del incumbente. Todavía no hay prueba de optimalidad energética.

La misma calidad se alcanzó también en un ensayo de **15 segundos**, sin AWS.
Esto acredita una mejora fuerte del motor en esta instancia; no demuestra
una aceleración universal ni una contribución causal del LLM.

| Versión y política | Semillas | Límite de resolución | Entregas | Energía kWh | Cota energética kWh | Gap energético |
|---|---:|---:|---:|---:|---:|---:|
| Original `56cb75c`, standard | 0 | 60 s | 2/40 | 2,209426* | 0 | 100 %* |
| Mejorado `9c6fb3a`, standard | 0, 1, 2 | 60 s | 40/40 | 14,566607 | 14,525265 | 0,283813 % |
| Mejorado `9c6fb3a`, deterministic | 0, 1, 2 | 60 s | 40/40 | 14,566607 | 14,525265 | 0,283813 % |
| Mejorado `9c6fb3a`, adaptive / Nova Micro | 0, 1, 2 | 60 s | 40/40 | 14,566607 | 14,525265 | 0,283813 % |
| Mejorado `49cd5b1`, adaptive / Fable 5, high | 0 | 60 s | 40/40 | 14,566607 | 14,525265 | 0,283813 % |
| Mejorado `9c6fb3a`, standard, ensayo corto | 0 | 15 s | 40/40 | 14,566607 | 14,525265 | 0,283813 % |

\* La energía del original corresponde a solo dos entregas y **no es comparable**
con la energía de servir cuarenta. Su gap de entregas fue 1900 % usando
`(40 - 2) / 2`.

Las nueve corridas de 60 segundos del motor mejorado pasaron validación física
y expansión vial. El primer testigo completo de las tres corridas `standard`
estuvo disponible entre **0,121 y 0,126 segundos** desde el inicio de resolución.
El ensayo corto terminó la resolución en 15,004 s y el pipeline en 15,713 s.
El límite corresponde a resolución e incluye las llamadas del orquestador;
lectura, validación y arranque del proceso se informan aparte.

## Qué fallaba y qué cambió

El original consumió 42,10 s en entregas y 17,91 s en energía, ambas fases con
`pricing_incomplete`. El problema no era falta de una solución física de
40 clientes: la construcción nueva encuentra y valida una casi inmediatamente.
La búsqueda original dependía demasiado de que la enumeración física produjera
rutas útiles antes de agotar el presupuesto.

El cambio actúa en varios puntos:

1. Inserción con múltiples inicios, mejora local y reparación de rutas producen
   incumbentes completos antes de enumerar exhaustivamente.
2. Servir todos los clientes prueba directamente el primer objetivo por la
   cota de cardinalidad. El tiempo restante se dedica a energía.
3. El pricing heurístico usa los duales y luego conserva el oráculo exacto.
   Se reutiliza exploración física entre vehículos compatibles.
4. Un maestro temporal con columnas conocidas mejora soluciones, pero su cota
   no se usa como certificado global.
5. La relajación energética independiente ofrece una cota válida aun cuando
   el pricing completo no termina. El gap dejó de depender de una cota cero.

El detalle y la justificación de las cotas están en
[orchestration.md](orchestration.md) y en la sección 7 de
[`modelamiento.pdf`](../modelamiento.pdf).

## Evidencia del LLM

En el benchmark de Nova Micro hubo **12 llamadas reales**, con **11 decisiones
aplicadas**. Dos semillas aplicaron las cuatro; la tercera rechazó su primera
propuesta y aplicó las tres posteriores. Esa corrida declara `partial_fallback`.
Los tiempos acumulados de inferencia fueron 6,566 s, 6,371 s y 7,813 s.

Se registran cambios reales en arranque, mejora local, pricing, cortes, reparto
del tiempo y parámetros nativos. Aun así, los tres modos terminaron con la misma
energía y cota: **este ensayo no demuestra que Nova Micro mejore al modo fijo**.
Las propuestas, estados y efectos están preservados por evento.

### Modelo de mayor capacidad

Se inspeccionaron el catálogo y la política IAM efectiva del perfil `hackathon`.
Opus 5.5 apareció disponible en el catálogo, pero su invocación real fue
rechazada con `AccessDeniedException` por la lista de modelos permitidos.
Fable 5 sí figura en esa lista y respondió a una invocación real. Se eligió
`us.anthropic.claude-fable-5`, manteniendo `us-east-1` y el mismo perfil.
No se modificaron permisos.

Las tres corridas iniciales con Fable 5, esfuerzo `max` y timeout de 12 s
terminaron con dos timeouts cada una. Conservaron 40/40 y la misma energía,
pero **ninguna fue adaptativa efectiva**: las seis llamadas fueron rechazadas
por timeout. Una prueba separada de la solicitud completa con timeout de 55 s
también expiró. En esos casos no se recibió el uso de tokens; no se le asigna
un coste cero ni se infiere consumo a partir de una respuesta inexistente.

Con esfuerzo `high`, la solicitud completa de diagnóstico respondió en
20,956 s y produjo una política válida. En la corrida de 60 s:

- Una llamada aplicada, sin fallback, con **17 campos de política modificados**.
- Inferencia: **20,058 s**; 5769 tokens de entrada y 1405 de salida.
- Primera solución completa disponible a los **20,255 s**.
- Resolución: **60,009 s**; pipeline: **60,708 s**.
- Resultado: 40/40, 14,566607 kWh, gap 0,283813 %, validación vial correcta.
- Se modificaron inicios, mejora local, lotes, orden de pricing, heurísticas
  nativas y selección de nodos, entre otras opciones.

El límite de llamadas fue tres, pero la asignación de inferencia de 30 s
ya no permitía otra llamada de 25 s después de la primera. Esto es una decisión
del control de presupuesto, no una llamada omitida en el registro.
La mayor capacidad del modelo **no produjo una mejora adicional de energía**
en este ensayo y retrasó la primera solución respecto de `standard`.

En una corrida adicional de **120 segundos**, Fable 5 aplicó dos decisiones:
`before_search` y `after_seed`, con 16 y 18 campos modificados. Consumió
46,711 s de inferencia y 15 382 tokens informados. No hubo fallback.
El presupuesto restante impidió una tercera llamada. Terminó en 120,009 s
de resolución con 40/40, la misma energía/cota y validación vial correcta.
Este ensayo acredita actuación en dos etapas; no se compara como aceleración
contra los ensayos de 60 s ni acredita una decisión Fable ante estancamiento.

Las especificaciones consultadas fueron la
[ficha AWS de Fable 5](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-fable-5.html)
y la documentación de
[razonamiento adaptativo](https://docs.aws.amazon.com/bedrock/latest/userguide/claude-messages-adaptive-thinking.html).
Se expone `--llm-reasoning-effort` explícitamente; no se fuerza temperatura cero
en ese modo. El soporte conserva el comportamiento anterior cuando no se usa.

## Protocolo y trazabilidad

- Origen: `56cb75c711dbf118cecfc2b584cf7e36f00941a2`.
- Copia de cambios locales existentes: `c5952420bf1eaaaf91c4a26ab0f71898bd13a85c`.
- Motor del benchmark de nueve corridas:
  `9c6fb3a016414dab3f36bb2f8f23ee6822e81140`.
- Soporte posterior de esfuerzo de razonamiento:
  `5cf163585217b1455be48e74bb726d0ef7a07a8f`.
- Corrección de contabilidad de decisiones:
  `49cd5b1692b1d2b4ca250d3354b0465f6324e217`.
- Python 3.12.11, SCIP 10.0.0, PySCIPOpt 6.0.0, un thread.
- Semillas del solver 0, 1 y 2; mismo snapshot y archivo de caminos.
- Orden de políticas pareado y permutado por semilla; procesos secuenciales.
- SHA-256 del archivo de servicios:
  `c8a49c608ae21a4f51978d8691714166b8ffbc2019170f7766b57b3a626a0edd`.
- SHA-256 del código del benchmark de nueve corridas:
  `bbd3444312c994942b21df3ec4e0251ec86034e9023e9f4892f321151b5030d4`.

Los resultados masivos permanecen locales e ignorados por Git:

| Evidencia | Directorio relativo al worktree |
|---|---|
| Referencia original reproducida | `artifacts/orchestrator/baseline-standard-s0/` |
| Nueve corridas comparables | `artifacts/orchestrator/benchmark-40c-final/` |
| Ensayo corto | `artifacts/orchestrator/regression-40c-15s/` |
| Regresión de 20 clientes | `artifacts/orchestrator/regression-20c/` |
| Modelos y acceso real AWS | `artifacts/orchestrator/model-discovery/` |
| Fable 5 max, timeout y fallback | `artifacts/orchestrator/benchmark-40c-fable5-max/` |
| Fable 5 high, 60 segundos | `artifacts/orchestrator/benchmark-40c-fable5-high-60s/` |
| Fable 5 high, 120 segundos | `artifacts/orchestrator/benchmark-40c-fable5-high-120s/` |
| Auditoría de los 14 resultados y hashes | `artifacts/orchestrator/final-audit.json` |
| Suite final | `artifacts/orchestrator/full-tests-final.log` |

Cada benchmark guarda `manifest.json`, `summary.json`, `execution.json`,
resultados, logs nativos y solicitudes/respuestas reales. Los hashes se
registraron antes de resolver y el código se mantuvo fijo durante cada lote.
Los cambios posteriores a `9c6fb3a` incorporan esfuerzo de razonamiento y
contabilidad del benchmark; no cambian la lógica física, heurísticas o pricing.
El campo histórico `llm_updates_during_solve` de los primeros resúmenes contaba
también decisiones de planificación. Desde `49cd5b1` excluye `before_search`,
`after_seed` y `before_decomposition`. Los registros por evento originales
se conservan sin reescribir.

## Validación y límites

La suite completa pasó **581 pruebas** tras incorporar el modo de razonamiento
y corregir la contabilidad de decisiones,
y Ruff pasó sin diagnósticos. La regresión de 20 clientes conservó el óptimo
lexicográfico de **10,5577408405 kWh**, comprobado con el certificado de reducción
aplicable a esa instancia y validado sobre las calles.

Las 40 ubicaciones incluyen demanda sintética; no representan una muestra
independiente de desempeño real. No se reentrenó energía ni se ajustó el método
sobre `evaluation`. Hay una sola instancia de 40 clientes y una sola repetición
por semilla. Las semillas no convierten esa instancia en tres problemas distintos.

La solución de 40 clientes utiliza una recarga parcial, con 2,566607 kWh
incorporados a batería, y mantiene la reserva del modelo. Las cantidades se
refieren al modelo energético fijado. La validación vial no supone una garantía
sobre el consumo real.

El motor mantiene rutas sin H. La expansión puede exceder el antiguo límite de
calles guardado como metadato; no es un certificado del modelo posicional con
ese límite. No se limita el número de etiquetas del pricing exacto ni se
convierte una interrupción en prueba de ausencia de columnas.
