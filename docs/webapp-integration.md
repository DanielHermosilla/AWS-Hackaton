# Webapp, motor eléctrico y GPT en `main`

`main` integra mediante merges con historia las ramas `codex/evrp-llm-search`
(`ab67dc6`) y `codex/webapp` (`a372d03`). Se conserva la interfaz HTML/CSS/JS,
el motor SCIP sin H y el preprocesamiento auditado de
`codex/investigacion-caminos-recursos` (`b14b976`). Las revisiones y huellas
están en [solver-source.json](solver-source.json).

## Arranque local

Desde la raíz del repositorio:

```bash
uv sync --locked --extra dw
AWS_PROFILE=hackathon uv run --locked --extra dw python -m backend.local_server \
  --port 4294 --graphml artifacts/network/competition_delivery.graphml \
  --network-profile delivery --tee
```

Abrir `http://127.0.0.1:4294/`, pulsar **Cargar y calcular → Cargar caso histórico**.
Esto carga el CSV de ubicaciones seleccionado y `data/eVED_EV.csv` del servidor.
**Simular una variante de este caso** permite cambiar clientes y cargadores
conservando el depósito, las calles y el histórico. También se puede cargar un
CSV propio. Seleccionar **Calles del servidor** y la política de búsqueda.
Dos vehículos y 60 % de SoC son los valores oficiales iniciales. La capacidad
útil, reserva y consumo deben ser entradas explícitas: 24 kWh y 2,4 kWh son
supuestos del escenario local, no capacidades medidas ni requisitos oficiales.
El presupuesto predeterminado de la UI es 120 s y el gap energético es 0,5 %.
El margen de consumo de **Flota y supuestos** usa
`operations.energy_margin_fraction`: aumenta las energías positivas, también
las calibradas, y conserva la regeneración. Es un escenario físico editable,
independiente del gap del solver.

El GraphML es un archivo local configurado por el operador. No se descarga
al abrir la webapp ni se aceptan rutas de archivo enviadas por el navegador.
Usar `--network-profile drive` para una caché preparada con ese perfil.
Sin `--graphml`, el comando usa `artifacts/network/competition_delivery.graphml`
si existe. Si tampoco existe esa red local, se pueden resolver instancias JSON elementales y preparar
la alternativa **Distancia geodésica · sintética**. La red sintética se declara
como tal y nunca se sustituye automáticamente por calles ni a la inversa.

`AWS_PROFILE` es opcional: sin él se usa la cadena estándar de credenciales,
por ejemplo el rol del entorno. `AWS_DEFAULT_REGION` tiene default `us-east-1`.
`BEDROCK_MODEL_ID` reemplaza el default **`us.openai.gpt-5.6-luna`**, razonamiento
`low`, mediante Bedrock Converse. No se necesitan claves de OpenAI. La política
web permite dos consultas como máximo, timeout de 8 s, 2.048 tokens de salida
y extracto de instancia de 8.000 bytes. El motor limita además la inferencia
al 25 % del presupuesto. La UI permite **Estándar · sin LLM** para comparar.
Una instancia pequeña puede terminar antes de recibir al LLM: eso queda
registrado y no se presenta como decisión aplicada.

El proceso es local, solo loopback y mismo origen; no tiene autenticación ni
está publicado en Internet. No es un servidor de producción. Detener la espera
en el navegador no cancela SCIP. No se modificaron permisos IAM.

## Flujo compartido

```text
CSV/formato de nodos -> POST /prepare (network_mode: road)
  -> GraphML dirigido + energía por distancia explícita
  -> ProblemInstance vial -> prepare_service_graph
  -> instancia de pricing + PathArchive + ID temporal
POST /solve (instancia + ID + política + presupuesto)
  -> run_instance, el mismo pipeline de la CLI
  -> ALNS / búsqueda memética / maestro SCIP / pricing / cortes
  -> expansión de caminos + validación independiente de calles
  -> resultado nativo íntegro + proyección HTTP para mapa y listas
```

La reducción usa Dijkstra cuando sus hipótesis son válidas. Si hay regeneración
u opciones temporales, conserva perfiles, caminos alternativos e intersecciones
que no convenga eliminar. `arc_id` identifica alternativas paralelas. No se
introducen límites de movimientos, recargas ni etiquetas. El pricing exacto
y las cotas válidas se conservan aunque AWS falle. La regla vigente del modelo
está en el PDF, ecuaciones (25)–(31); Pyomo posicional queda como referencia.

El backend conserva red original, pricing y archivo de caminos juntos. El ID
opaco y la huella de la instancia impiden usar un archivo de caminos con otra
red o escenario. La caché temporal admite dos contextos y 384 MiB de objetos
serializados; no es una garantía de RSS. Repetir la misma preparación reutiliza
su ID. Cambiar nodos, flota, consumo, operaciones, red o perfil genera otro contexto.
Un JSON de preparación puede incluir `operations` (jornada, ventanas, potencia,
velocidad asumida); se valida y aplica antes de comprimir. La UI lo conserva
al reabrir o exportar. El JSON elemental permite importar energías firmadas. Se
pierde al reiniciar o al reemplazar entradas. Los límites son del servicio local,
no reglas del desafío; la CLI sigue disponible para entradas mayores.

La geometría usa las calles expandidas, con conversión de `[lat, lon]` a
GeoJSON `[lon, lat]`; la distancia usa el arco identificado, no un diccionario
que pierda paralelos. Se envían todos los servicios y las intersecciones usadas
por las rutas, no cientos de miles de intersecciones sin visitar. El mapa y la lista muestran paradas de servicio; los pasos por intersecciones
permanecen en el resultado nativo para auditoría. No se inventan
líneas si falta geometría. Los accesos a calles son supuestos explícitos del
preparador nativo; la validación del modelo no demuestra accesos reales o
ausencia de cierres actuales. Cada servicio se conecta a su intersección más
cercana si está dentro de 100 m; si no, al punto más cercano de la calle, que se
subdivide en ambos sentidos sin cambiar su longitud (`access_kind:
street_projection` en `service_access`). Así se prepara V16 de evaluation, junto a
un tramo de 441 m de South Wagner Road sin intersecciones intermedias.

## Qué controla GPT

Recibe características y un extracto declarado de la instancia, recursos,
estado de búsqueda y acciones implementadas. Propone políticas de ALNS,
reparación, búsqueda memética, pricing, branching, selección de nodos, cortes
y parámetros SCIP admitidos. `RoutePolicy` valida cada respuesta JSON. No se
ejecuta código generado ni se modifican datos, física, objetivos, tolerancias
ni certificados por decisión del modelo.

La inferencia ocurre en otro hilo. Los callbacks aplican decisiones válidas en
el hilo de SCIP, sin esperar remotamente por nodo. Los campos de etapas ya
terminadas no se aplican. La UI muestra modelo, latencia, evento, explicación,
propuesta, cambios aceptados, campos inactivos, rechazos y uso de tokens.
**Cambiar una política no demuestra que esa etapa se haya ejecutado ni que
haya mejorado la solución.** Los `.mps` de logs son maestros restringidos;
no contienen todas las rutas futuras ni representan por sí solos la física.

`--tee` muestra SCIP y decisiones LLM en el terminal. En
`artifacts/webapp/<run_id>/` se conservan `result.json` y
`logs/decisions/NN/{llm-request,llm-response}.json`, además de los diagnósticos
nativos. No se registran claves ni razonamiento interno del proveedor.
Un fallo AWS conserva el motor y se muestra como `fallback`; no se oculta.

## Resultados y certificados

Se mantiene la prioridad del PPTX: maximizar entregas factibles con retorno y
batería suficiente; después minimizar energía. El tiempo de cómputo se informa
por separado. No se fuerza a utilizar ambos vehículos si uno basta, pero toda
la flota tiene una ruta válida, incluso si permanece inactiva en el depósito.
El código obtiene los números de clientes y cargadores desde las entradas.

`energy_gap_limit` requiere una cota energética global válida y gap relativo
menor o igual a `0.005`, condicionado a las entregas fijadas. No es timeout ni
óptimo exacto. La UI conserva sentido, incumbente, cota, gap y prueba **por fase**.
Sin prueba del máximo de entregas, la mejora de energía es condicionada.
Una cota del maestro con pricing incompleto o de un sub-SCIP restringido no
certifica el problema completo.

El resultado nativo permanece íntegro en `raw.result`. La proyección no calcula
una segunda versión de los KPIs. Los tiempos de preparación vial, servicio,
resolución, validación y LLM se distinguen: hay inclusiones y solapamientos,
no se suman indiscriminadamente. La preparación reutilizada informa la duración
original, no un coste repetido en cada resolución. Las métricas sin datos
operacionales o referencia, como CO₂ evitado, permanecen desconocidas con motivo.

**Descargar ejecución completa** conserva resultado, instancia de pricing y
entrada original de preparación. Al reabrirla se prepara nuevamente la entrada,
sin depender del ID temporal anterior. Se admiten exportaciones locales de
hasta 64 MB; el cuerpo HTTP sigue limitado a 8 MiB. **Descargar instancia**, para una entrada
vial preparada, entrega `entrada-vial.json` (nodos, flota, coeficiente y modo de
red) para reconstruirla con el GraphML del servidor. No es un archivo vial
portable completo. Para archivar red y caminos reproducibles, usar los snapshots
vial/pricing/PathArchive de la CLI. Los JSON elementales sí se exportan completos.
Cambiar los datos invalida el resultado mostrado; errores y resultados vencidos
no activan silenciosamente los datos de ejemplo.

## Verificación y alcance

```bash
uv run --locked --extra dw pytest -q
node --test webapp/tests/*.test.mjs
uv run --locked --extra dw ruff check backend src tests scripts/test_routing_verbose.py
```

La suite habitual no invoca AWS ni descarga mapas. Comprueba preparación vial
local y HTTP, paridad íntegra de `RunResult`, caminos paralelos, regeneración,
ventanas, expansión, archivos incompatibles/expirados, tolerancia energética,
fallos del LLM y controles de entrada/origen. Las pruebas reales se registran
aparte en `artifacts/merge-validation/`, ignorado por Git. Ver el acta de merge
[main-integration-validation.md](main-integration-validation.md).

La cuenta permitió GPT-5.6 Luna y Terra en la comprobación previa: una consulta
por candidato tomó 4,4351 s y 6,5352 s respectivamente. La corrida previa de
40 clientes recibió Luna en 4,7564 s y aplicó la respuesta a los 5,0581 s.
Esa medición sustentó escoger Luna; no demuestra superioridad estadística ni
mejora del óptimo. GPT-6 Luna fue rechazado por IAM y no se usa como default.

## Referencias del código

- [Contrato HTTP y límites](../backend/API_CONTRACT.md).
- [Preprocesamiento con recursos](resource-paths.md).
- [SCIP, callbacks y heurísticas](llm-head-search.md).
- [Contratos nativos](contracts.md) y [certificados](solvers.md).
- [OpenAI en Bedrock](https://developers.openai.com/api/docs/guides/amazon-bedrock).
