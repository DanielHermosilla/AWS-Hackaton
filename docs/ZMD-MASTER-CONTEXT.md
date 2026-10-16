# ZMD · contexto maestro

Documento mantenido por **ZMD Features Implementation**, sesión madre
`01a1415b-d61e-7a51-b306-2ef1441f7bf0`. Registro iniciado el **16-10-2026**.

Este documento consolida decisiones y evidencia; no reemplaza los contratos ni
la formulación de Daniel. El seguimiento de implementación está en
[ZMD-ORCHESTRATION.md](ZMD-ORCHESTRATION.md).

## 1. Autoridad, alcance y acceso real

- **Confirmado:** Diego convirtió este chat, antes «ZMD Features review», en
  sesión madre y autorizó implementar los puntos **2, 3 y 5 de la última tabla**:
  información de cargadores, resumen imprimible y edición de ubicaciones.
  El punto 5 incluye analizar autocompletado de direcciones. [H0, H3]
- Se consultaron directamente los turnos disponibles de **ZMD Integracion Beta**
  y **ZMD UI 2** con `read_thread`. Para recuperar mensajes de usuario y respuestas
  finales que la salida extensa truncaba, se leyeron esos registros locales.
  No se atribuye lectura de chats anteriores no solicitados ni de salidas omitidas.
  La arquitectura y los resultados se contrastan además con archivos y commits. [H1, H2]
- La numeración corresponde a la tabla más reciente de nueve features, no a la
  lista histórica de cinco propuestas de UI 2 ni a los números de los archivos
  explicativos. La indicación de autocomplete en el punto 5 respalda esta lectura. [H0, H3]
- El encargo anterior de investigación sin implementación queda sustituido por
  la autorización actual. Se permite preparar e integrar localmente incrementos
  revisados; esta ola no publica ni despliega automáticamente.
- Daniel conserva la responsabilidad del solver y su integración matemática.
  Los agentes de esta ola no editan `src/ev_routing/`, formulación, dependencias
  del solver, PDF ni manifiesto de procedencia. [H0, H1, S1]

## 2. Base actual y evolución verificada

Base fijada tras `git fetch origin`: **`a372d03efc270b0ac23769e5d4334c2d3f4144ff`**
en `origin/codex/webapp`. La rama madre `codex/features-implementation` parte de
esa revisión. El checkout de trabajo sigue en
`/Users/caballero/.codex/worktrees/features-review/AWS-Hackaton`;
se conserva la ruta para no romper los archivos enlazados al usuario.

| Etapa | Evidencia | Decisión o resultado |
|---|---|---|
| UI consolidada | `bb08a4a`; UI 2 | HTML/CSS/JS, Inicio Consola y Plan Cristal/Esencial; ejemplos sin solver. |
| Primera Beta | `97e4cef`; entrega histórica | Puente `evrp` + HiGHS; sus pruebas no validan el motor actual. |
| Cambio solicitado por Diego | H1, 15-10 22:28 UTC | Usar Daniel y excluir trabajo de Lucas Zulueta; priorizar estabilidad de entradas/salidas. |
| Integración Daniel | `0d12d5a`, `8d02d83`, `677a30e`, `45eec08` | API 3.0, instancia nativa 1.0, SCIP, validación y presupuestos coherentes. |
| Tema y resultados completos | `711e79a`, `cde85dd`, `8e1a8d8` | Inicio siempre claro; conservación íntegra del resultado nativo y exposición ampliada. |
| Rama compartida actual | `9b093ef`, `a372d03` | Guía de adopción y rechazo de claves JSON duplicadas; publicado en `codex/webapp`, no evidencia de despliegue. |

**Corrección de contexto:** la tabla de features de las 19:35 y sus archivos
explicativos son un snapshot anterior. Sus afirmaciones de «Beta no publicada»,
proveedor `evrp` y discrepancias energéticas no deben trasladarse al código
actual como defectos reproducidos. El ranking se conserva como decisión editorial,
no como auditoría actualizada. [H3, S1, S2]

## 3. Arquitectura actual

```text
CSV / formulario ── POST /prepare ── instancia nativa ProblemInstance 1.0
JSON nativo ──────────────────────── instancia nativa ProblemInstance 1.0
                                         │
                                    POST /solve
                                         │
                         backend → pipeline de Daniel → SCIP
                                         │
                           comprobador independiente + RunResult
                                         │
                    proyección API 3.0 → Inicio / Plan / descargas
```

- Frontend sin build ni framework: `webapp/`. `boot.js` monta shell y panel de
  ejecución; Inicio y Plan usan `shared/data.js` y el mismo `run_id`. [S2]
- `backend/local_server.py` sirve UI y API local en el mismo origen.
  `backend/service.py` valida/prepara entradas; `backend/daniel_adapter.py`
  proyecta resultados sin sustituir energía ni certificados. [S3]
- Núcleo importado de Daniel: `modelamiento@624203573bffdeec334a9e07a64b361a515f9725`.
  Backend expuesto: `scip-routes`, SCIP/PySCIPOpt, política `standard`.
  La formulación vigente resuelve sin H; `movement_limit` no limita esa búsqueda.
  El PDF actual pertenece a esta revisión, distinto del PDF posicional histórico. [S1, S4]
- `service_graph.py` y dependientes identificados en `solver-source.json`
  permanecen excluidos. No reintroducirlos para resolver una necesidad del mapa. [H1, S4]
- Un proyecto Python, `pyproject.toml` y `uv.lock`. No agregar otro gestor,
  infraestructura o dependencias para estas tres features sin necesidad concreta.

## 4. Contrato que deben conservar las features

- `ProblemInstance` nativa conserva nodos, arcos, parámetros, operaciones,
  compatibilidad y procedencia. Su definición autoritativa está en
  `src/ev_routing/contracts.py`; el frontend hace comprobaciones de entrada,
  no una segunda implementación del modelo. [S3, S5]
- CSV y formulario solo disponen hoy de preparación **geodésica sintética**
  explícitamente confirmada: no crea calles ni demuestra cobertura vial.
  Un JSON nativo conserva su grafo; no se sustituye por haversine silenciosamente.
- `raw.result` conserva el `RunResult` nativo completo; `raw.instance`,
  `raw.input` y configuración efectiva conservan el contexto de ejecución.
  Resultado nativo e instancia son descargas distintas. [S3]
- IDs opacos; servicio explícito separado de transitar por un nodo; visitas
  repetidas conservadas por posición/ocurrencia. Cero es un dato, `null` es ausencia.
- Batería de contrato en kWh o SoC fraccional según campo; la UI convierte a %
  para presentar. Geometría de arcos nativos `[lat, lon]`; GeoJSON `[lon, lat]`.
- KPIs, recargas globales, fases y tiempos provienen del backend. No deducir
  causas de pendientes, sumar intervalos de tiempo solapados ni llamar «óptima»
  a una solución porque haya terminado.
- Sin incumbente: métricas desconocidas, sin rutas; no equivale a cero entregas
  ni infactibilidad probada. Validación fallida no se presenta como plan factible.
- Ediciones invalidan el resultado vigente; respuestas tardías no pueden
  reemplazar el nuevo borrador. Ningún error reactiva el ejemplo como fallback.
- El servidor conserva hasta cuatro corridas/32 MiB en memoria. Reiniciar puede
  expirar el resultado: no hay persistencia empresarial. [S1, S3]

## 5. Funciones existentes y pendientes

| Área | Confirmado en la base actual | Pendiente de esta ola o ajeno a ella |
|---|---|---|
| Entrada y ejecución | CSV, JSON nativo, revisión, `/prepare`, `/solve`, validación y descargas | Edición visual de ubicaciones: F05. |
| Cargadores | Metadatos nativos disponibles; detalle básico y mapa | Conservar puertos en la proyección JS y presentar ficha completa: F02. |
| Resultados | Inicio/Plan, batería por parada, pendientes, métricas y detalle nativo | Resumen único legible e imprimible: F03. |
| Mapa | MapLibre, OpenFreeMap, selección por ocurrencia, ausencia de geometría honesta | Editor confirmado con teclado y mapa; autocomplete sujeto a investigación: F05. |
| Diseño | Batería en marcha, Inicio Consola + Plan Cristal/Esencial, preferencias | Conservar identidad; no reabrir exploraciones archivadas. |
| Tema | Cada documento comienza claro; cambio oscuro solo durante esa página | No persistir oscuro accidentalmente. |
| Cuenta | Nombre de organización local y perfil ilustrativo | Login, aislamiento y persistencia no implementados en esta base. |
| AWS | Cliente upstream incluido; política web estándar sin invocaciones | Aceptación AWS/tuning no forma parte de estas tres features; requisito global pendiente. |
| Telemetría | Históricos y metadatos estáticos | Sin proveedor vivo; fuera de alcance. |

La Beta reportó 347 pruebas Python y 96 JS al cerrar su revisión de outputs.
Son resultados históricos atribuidos a esa sesión. La sesión madre ejecuta un
baseline nuevo y registra su evidencia en ORCHESTRATION; no reutiliza esos
conteos como comprobación de modificaciones posteriores. [H1]

### Incremento F02/F03/F05 integrado localmente

Sobre la base anterior, la madre incorporó tres commits revisados:
`450fc0f` (cargadores), `78be661` (resumen) y `d9684b3` (editor).
El estado entregado y sus límites están en
[ENTREGA-FEATURES.md](implementation/ENTREGA-FEATURES.md).

- F02 conserva los puertos, lista todas las estaciones y separa los metadatos
  de cada ocurrencia de recarga; Inicio permite continuar en esa pestaña.
- F03 presenta una ficha operativa con impresión, nombre/ID de ejecución,
  comprobación y fases; marca la corrida anterior al editar o imprimir.
- F05 permite editar CSV/caso sintético con formulario y mapa. Los cambios
  confirmados se conservan en la pestaña, incluidos parámetros y presupuesto;
  confirmar exige preparar de nuevo. JSON nativo con grafo permanece protegido.
- Autocomplete externo: [análisis terminado](implementation/F05-address-autocomplete.md);
  Amazon Location es candidato sujeto a acceso/cobertura/presupuesto. La función
  actual busca entre puntos cargados y no geocodifica direcciones.
- Validación final propia: **133 JS**, **347 Python + 37 subtests**, una omisión
  del plugin alternativo Pyomo/SCIP; once comprobaciones combinadas en navegador
  con cálculo real. Revisión independiente sin hallazgos pendientes. [I1]

Esta integración está en `codex/features-implementation`, local y revisable.
No modifica el motor de Daniel ni acredita un despliegue.

## 6. Decisiones de producto, diseño y descartes

- Usuario objetivo: una persona que planifica reparto eléctrico. ZMD es
  producto/consultora; CASE es beneficiario. Carla es un caso ilustrativo;
  Ann Arbor es geografía de datos, no una empresa cliente comprobada. [H2]
- Flujo simple: cargar → revisar → confirmar → calcular → comprender/exportar.
  Mantener controles existentes, español claro, teclado, foco y móvil. [H2, S2]
- Estación registrada no implica compatible, disponible o en funcionamiento.
  `network` indica la red declarada, no acredita operador legal. La potencia
  reportada no es potencia aceptada por el Leaf ni tiempo de carga.
- Planificar entregas no confirma entregas realizadas en terreno.
- UI 2 investigó OptimoRoute, SimpliRoute, Geotab, Monta y Onfleet: se retomaron
  patrones de revisión, vigencia, permisos y procedencia, no promesas comerciales
  de ahorro ni arquitectura interna. [H2, R1]
- Se descartaron para este incremento cuentas empresariales, CRM, app de
  conductor, pagos/reservas, telemetría, mantenimiento predictivo y CO2 automático.
  Faltan fuentes o amplían sustancialmente el alcance. [R1, H3]
- Las preferencias antiguas por Opus/Kiro fueron sustituidas para estos
  encargos por Astra Ultra. No atribuir autoría o revisiones a modelos no usados. [H2]

## 7. Evaluación y prioridades

El objetivo oficial es maximizar entregas **con rutas factibles**; retorno y
batería son condiciones, energía y cómputo son desempates. El mismo código debe
aceptar entradas y flotas diferentes. Escenario: dos Leaf 2013 al 60 % inicial;
no hardcodear la cantidad de nodos del archivo. [S0]

La rúbrica es innovación 25 %, impacto social 25 %, factibilidad/sustentabilidad
20 %, escalabilidad 15 %, presentación 15 %. No son pesos del solver.
F02 mejora comprensión de recargas; F03 lectura/presentación y trazabilidad;
F05 preparación de entradas. Ninguna garantiza mejorar energía o entregas.

La última tabla ordenó demo, cargadores, resumen, duplicación, editor, batería,
comparación IA, empresas y datos vivos. Diego seleccionó F02/F03/F05; la selección
actual prevalece sobre la recomendación anterior de postergar el editor.
Corte del equipo heredado: **16-10-2026 10:00 America/Santiago**; reservar
integración y ensayo. No es una regla oficial del concurso. [H0, H3]

## 8. Dependencias de Daniel, riesgos e hipótesis

| Tema | Estado y tratamiento |
|---|---|
| Evolución del solver | Confirmado que puede cambiar; fijar SHA/contrato y adaptar explícitamente una futura actualización. No editar su matemática. |
| Edición de una red nativa | Cambiar coordenadas puede invalidar arcos, energía y geometría. No resolver el grafo anterior como si estuviera actualizado. F05 debe conservar esa frontera. |
| Preparación vial real | No está expuesta en la API local actual. El editor debe declarar el alcance sintético o pedir una instancia nuevamente preparada; no inventar cobertura. |
| Metadatos de estaciones | F02 conserva los puertos en la proyección JS; no se modificó el contrato del solver. |
| Autocomplete | Análisis terminado; cuenta, cobertura y presupuesto no confirmados. No confundir geocodificación con conexión vial. |
| Estado viejo del research | Confirmado desfasado por el cambio de motor. Conservar como historia y no usarlo como prueba de defectos actuales. |
| Revisión de energía | El defecto reproducido en `evrp` no se atribuye a Daniel. Respetar el validador y los KPIs nativos actuales. |
| Capacidad de producción | Sin autenticación/despliegue/aislamiento: esta ola mejora el producto local, no lo certifica para empresas reales. |
| Pruebas externas | Documentación pública o un mock no prueba cuenta AWS, cobertura ni servicio operativo. |
| Texto nativo pendiente de Daniel | En una ejecución sin operaciones, el motivo de duración desconocida aún dice «H cuenta movimientos; no modela tiempo», aunque el backend actual resuelve sin H. Se conserva como mensaje recibido; se requiere corregir esa explicación upstream, no inferir una duración. Observado en I1, sin cambios a cifras ni solver. |

## 9. Fuentes

- **H0:** petición adjunta de esta sesión,
  `/Users/caballero/.codex/attachments/b0095f82-e739-46ce-a203-4f82757d3c55/Pasted text.txt`.
- **H1:** «ZMD Integracion Beta», chat `01a1415d-6568-7800-ac64-b9b4cac025f6`;
  mensajes de Diego de 15-10-2026 22:28 y 22:54 UTC; cierre 23:09 UTC.
- **H2:** «ZMD UI 2», chat `01a140ed-b60d-7612-9020-f278a0e0307f`;
  investigación y encargo de 15-10-2026 20:40 UTC, cierre 21:00 UTC.
- **H3:** esta sesión; tabla y explicaciones en
  `.local/features-review-2026-10-15/tabla-impacto-factibilidad.md` y
  `features-explicadas/`. Mensajes accesibles también mediante `read_thread`.
- **S0:** [AGENTS.md](../AGENTS.md), instrucciones del usuario y presentación
  original; extracción previa verificada en
  `.local/features-review-2026-10-15/challenge-original-extraction.txt`.
- **S1:** [integración vigente](integration-beta.md).
- **S2:** [webapp](../webapp/README.md), código `webapp/` en `a372d03`.
- **S3:** [API 3.0](../backend/API_CONTRACT.md).
- **S4:** [procedencia](solver-source.json), [modelo](model.md),
  [PDF vigente](../modelamiento.pdf).
- **S5:** [contratos](contracts.md) y `src/ev_routing/contracts.py`.
- **R1:** investigación y auditoría UI 2, conservadas en
  `/Users/caballero/.codex/worktrees/68f3/AWS-Hackaton/.local/research-mejoras-2026-10-15/`.
- **I1:** [registro de integración](ZMD-ORCHESTRATION.md), commits del incremento
  y pruebas de la madre en `.local/features-implementation-2026-10-15/`:
  `final-node.log`, `final-python.log` y `qa/combined-report.json`.

Los documentos versionados anteriores contienen lo necesario para implementar.
Las rutas locales son evidencia adicional: no exigir que existan en otro clon.
