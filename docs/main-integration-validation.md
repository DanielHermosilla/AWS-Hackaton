# Verificación de la integración en main — 16 de octubre de 2026

## Revisiones y resolución de conflictos

- Base de `main`: `4750ac8`.
- Motor: `codex/evrp-llm-search@ab67dc6b88a720f274789bb0dace8e47a68a7460`.
- Webapp: `codex/webapp@a372d03efc270b0ac23769e5d4334c2d3f4144ff`.
- Preprocesamiento auditado incluido en el motor: `b14b97655ab30ce9232422fe426fb8e0dfdc9d17`.

Se fusionaron las historias, sin squash ni rebase. Los conflictos de núcleo,
contratos, modelo matemático y dependencias conservan el motor actualizado;
la webapp tenía una copia anterior con funciones de preparación excluidas.
Se conservaron la UI, el transporte HTTP, el resultado nativo completo, los
controles de origen/tamaño y la validación estricta de JSON. Esta última se
adaptó también a la CLI completa: claves duplicadas, no finitos y booleanos
no se convierten silenciosamente en energía. El PDF y su fuente permanecen
idénticos a los del motor importado; no se cambió la formulación.

Se añadió preparación vial con contexto acotado en servidor, política GPT,
expansión para geometrías, selección de arcos por identidad, presentación de
decisiones y distinción entre gap energético y óptimo exacto. Las instrucciones
históricas que excluían el preprocesador fueron reemplazadas por la autorización
actual del usuario. `docs/solver-source.json` identifica modificaciones locales.

## Requisitos contrastados con el PPTX local

| Regla del desafío | Integración y evidencia |
|---|---|
| Dos Leaf 2013 con 60 % inicial | Valores iniciales de UI y escenario; flota configurable. Capacidad útil/reserva siguen siendo supuestos explícitos. |
| Inicio y retorno al centro; batería suficiente | Validación independiente del núcleo y nueva expansión calle por calle antes de presentar geometría vial. |
| Maximizar entregas, después minimizar energía | Maestro sin H y fases conservados; gap 0,5 % solo energético. No se combinan cotas de fases. |
| Recarga permitida | Recarga parcial y compatibilidad conservadas; caso real de 40 clientes con una parada de recarga, validada. |
| CSV público de 20 clientes y 60 cargadores | Se preparó y resolvió completo por HTTP; no se confunde con el texto de “20 nodos” de otra diapositiva. |
| Cambiar archivos sin reescribir el método | IDs y cantidades se descubren; GraphML/configuración del operador y CSV/JSON son entradas. Se prueba también demanda sintética de 40. |
| Escalabilidad | Misma implementación y API; caché separada del solver. Los límites del servidor local están documentados y no son reglas oficiales. |
| KPIs entregas/energía/cómputo | Se copian del resultado nativo, con nulos y motivos cuando faltan datos. No se inventan CO₂ evitado ni ahorro frente a referencias inexistentes. |
| Calidad de presentación y genAI | Mapa de calles y servicios, estado de ambas fases y decisiones reales de GPT; interfaz revisada en escritorio y móvil. |

No se ajustaron modelos usando la instancia reservada de evaluación. El grafo
se leyó de la caché GraphML local. Los accesos a calles, el coeficiente energético,
la capacidad de 24 kWh y reserva de 2,4 kWh son supuestos declarados del escenario.
La factibilidad validada corresponde a esa red y modelo energético.

## Pruebas automáticas

- `uv run --locked --extra dw pytest -q`: **715 aprobadas**, más 37 subcasos.
- `node --test webapp/tests/*.test.mjs`: **105 aprobadas**.
- Ruff: sin errores en `backend`, `src`, `tests` y el runner de terminal.

La suite no consulta AWS ni descarga mapas. Incluye restricciones físicas,
preprocesamiento, multigrafos con ventanas, fallos AWS con doble, estado de gap,
JSON nativo íntegro, contexto alterado/vencido, preparación HTTP y recuperación.
Las pruebas heredadas que exigían excluir `service_graph` fueron actualizadas
al nuevo alcance autorizado; se mantuvieron sus verificaciones físicas.

## Pruebas reales mediante HTTP

Misma configuración: dos vehículos, 24 kWh útiles supuestos, reserva 2,4 kWh,
SoC 0,6, consumo explícito de 0,15677124732025158 kWh/km, SCIP con 120 s máximos,
un hilo, semilla 0 y gap energético 0,005. No hay jornada ni ventanas activas.
El coeficiente coincide con la calibración descriptiva previa; en esta prueba
web se suministró como entrada, no se entrenó de nuevo eVED.

| Instancia/política | Preparación CSV + GraphML local | Resolución nativa | Petición /solve completa | Entregas | Energía | Gap energía |
|---|---:|---:|---:|---:|---:|---:|
| 20 públicos, standard | 11.9206 s | 0.0464 s | 1.7241 s | 20 | 10.55774084 kWh | 0.227424 % |
| 20 públicos, adaptive | 11.9206 s | 0.1842 s | 1.4067 s | 20 | 10.55774084 kWh | 0.227424 % |
| 40: 20 públicos + 20 sintéticos, standard | 13.8721 s | 15.4966 s | 16.8659 s | 40 | 14.56660712 kWh | 0.283813 % |
| 40: 20 públicos + 20 sintéticos, adaptive | 13.8721 s | 14.9502 s | 16.2934 s | 40 | 14.56660712 kWh | 0.283813 % |

La preparación se comparte entre las dos políticas; no se volvió a ejecutar
para cada resolución. Las cifras no incluyen descarga de OSM ni entrenamiento
del estimador. El tiempo de inferencia se solapa con la búsqueda y no se suma
al tiempo nativo. Son ensayos de aceptación, una corrida por combinación, no un
benchmark estadístico ni evidencia de una aceleración general del LLM.

Las cuatro corridas conservaron las entregas, validaron compactación y calles,
y terminaron por `energy_gap_limit`; la fase de entregas probó su máximo, la
energética no certificó óptimo exacto. Una ruta activa y otra inactiva son
compatibles con el modelo: ambos vehículos conservan retorno al depósito.

En 20 clientes, el solver terminó antes de recibir GPT: `fallback`, ninguna
decisión aplicada. En 40, **GPT-5.6 Luna low** respondió en **6,6852 s** y se
aplicó a los **6,7914 s**: `adaptive`, una llamada, una decisión aplicada.
Modificó presupuestos y operadores de reparación, ALNS, población, pricing y
cortes. El cierre por gap evitó fases posteriores; no se atribuyen efectos a
etapas no ejecutadas. La energía fue la misma que sin LLM.

## Navegador y archivos

Se comprobó con Chrome headless real: Inicio, Plan, mapa vial, contadores,
selección de política, decisiones GPT, gap, invalidez del resultado al editar,
descarga nativa íntegra y vistas de escritorio/móvil. Se mostraron 44 paradas
de servicio en la ruta/flota, conservando 3.446 pasos físicos en los datos.
No se crean miles de marcadores de intersecciones; la geometría sigue completa.
No hubo errores JavaScript de página.

Se cargó el CSV público desde el navegador y se completó preparación vial,
resolución y validación de 20 entregas/10,55774084 kWh. Se comprobó también
que la huella del contexto tolera la serialización JSON 24.0→24 de JavaScript,
sin tolerar cambios numéricos, booleanos o texto.
Se envió desde el formulario un caso sintético por `/prepare`→`/solve` y un
JSON elemental con regeneración directamente por `/solve`. La exportación
completa de 14 MB se reabrió conservando 40 clientes, modo vial y política GPT.
Se amplió la importación local a 64 MB para admitir las exportaciones propias;
el cuerpo HTTP sigue limitado a 8 MiB. Un JSON nativo demasiado grande debe
prepararse por servidor/CLI; no se reduce silenciosamente.

Evidencia local, excluida de Git: `artifacts/merge-validation/`, con mediciones,
resultados, captura de descarga y PNG de Inicio/Plan/móvil. Las llamadas y sus
respuestas están en `artifacts/webapp/<run_id>/logs/decisions/`. El repositorio
publica código, pruebas y este informe, sin CSV originales, redes ni credenciales.

## Límites operacionales actuales

Servidor local, mismo origen, sin autenticación ni despliegue público. Los
contextos y resultados temporales expiran; salir de la página no cancela SCIP.
El CSV aporta ubicaciones: fuera de la cobertura del GraphML se devuelve un
error, no se inventan calles. Las instancias grandes o con recursos difíciles
pueden agotar el presupuesto y deben mantener su estado/cota real. No se promete
optimalidad exacta, latencia constante ni mejora de calidad gracias a GPT.

## Consolidación de `master` y del solver en `main` — 16-10-2026

Se esperó a que terminara el chat que editaba `master` y se comprobó que no
quedaban otros agentes activos en el repositorio. Su trabajo local terminado
se guardó en `6da80e9`, conservando históricos, carga directa del caso y variantes
de simulación. Se integró con `7076e6b` (reparación del solver) y `297cdf1`
(campaña de evidencias que ya estaba en `main`), manteniendo los tres historiales.

El único conflicto manual estuvo en `tests/test_route_orchestration.py`:
se conservó la ejecución determinista de `master` y el presupuesto de tres
consultas del test, que permite dos decisiones de preparación y reserva la
última para estancamiento. Los módulos del solver reparado se conservaron
idénticos a `7076e6b`.

Validación sobre el árbol combinado:

- `uv run --locked --extra dw pytest -q`: **948 pruebas y 37 subtests aprobados**.
- `node --test webapp/tests/*.test.mjs`: **160 pruebas aprobadas**, ninguna fallida.
- `git diff --check`: sin errores de espacios.

Estas pruebas no hicieron nuevas consultas AWS. Los ensayos reales y límites
del solver están en [solver-repair.md](solver-repair.md); los de históricos y
simulación, en [historical-web-validation.md](historical-web-validation.md).
Se publica código y documentación, sin los datos locales ni las carpetas ajenas
`luna/`, `output/` y `tmp/`. La rama de integración y publicación es `main`;
el remoto configurado en este repositorio se llama `origin`.
