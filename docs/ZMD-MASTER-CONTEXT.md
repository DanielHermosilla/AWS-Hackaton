# ZMD · contexto maestro

Sesión madre `01a1415b-d61e-7a51-b306-2ef1441f7bf0`. Actualizado el 16-10-2026.
Este registro describe el estado vigente; contratos y formulación siguen en sus fuentes.

## Encargo vigente

El usuario pidió integrar el solver terminado publicado en `main` con las features
F02 (cargadores), F03 (resumen imprimible) y F05 (editor), y resolver el feedback
completo de carga, parámetros, persistencia, resultados, mapa y diseño del panel.
[Backlog y aceptación](implementation/ZMD-FULL-INTEGRATION.md).

Aclaración posterior del usuario: aceptar archivos con datos de la instancia y
sus parámetros; **no aceptar históricos eVED como instancias de ruteo**.
La nueva petición de recordar el modo oscuro reemplaza iniciar siempre en claro.
Se autorizaron agentes, worktrees aislados, correcciones y pruebas. No se autorizó
publicación automática; la entrega se integra localmente con revisión independiente.

## Base y ramas

- Checkout principal del usuario: `codex/webapp@a372d03`, se mantiene sin modificar.
- Madre: `codex/features-implementation`, worktree `features-review`.
- Antes de esta ola: `d3e045a`, recuperable desde `codex/pre-main-refinement`.
- `git fetch origin` recuperó `origin/main@9f03027`.
- Merge real con historia: `f5b4ea8`. Conserva las features y el motor completo.
- Los agentes trabajan sobre esa misma base en worktrees separados. La madre
  incorpora y verifica sus commits; trabajar en una rama no equivale a entregar.

## Arquitectura actual

```text
CSV / formulario → /prepare (calles del servidor o aproximación explícita)
JSON nativo ──────────────────────────┐
                                     ↓
                   ProblemInstance 1.0 / 1.1 → /solve
                                     ↓
               SCIP sin H + política local o Bedrock acotado
                                     ↓
          validación independiente → JSON nativo + proyección API 3.0
                                     ↓
                   Inicio / Plan / resumen / descargas
```

La interfaz sigue en HTML/CSS/JS. El servidor local comparte pipeline con la CLI.
`backend/runtime.py` conserva la red vial y sus caminos; el navegador recibe un
identificador de preparación, no rutas de archivos del servidor. Las ubicaciones
editadas requieren preparación nueva. Un JSON con grafo conserva su física.

Main incluye el preprocesamiento auditado y la búsqueda especializada. La
solicitud actual reemplaza la exclusión histórica de `service_graph.py`.
[Procedencia](solver-source.json), [contrato HTTP](../backend/API_CONTRACT.md),
[guía de integración](webapp-integration.md), [modelo](model.md) y
[PDF vigente](../modelamiento.pdf) definen las fronteras. No sustituir el motor.

## Condiciones que deben conservarse

- Prioridad: entregas factibles; luego energía. Retorno, batería, reserva y
  validación independiente no se relajan para hacer funcionar una pantalla.
- El gap energético predeterminado es 0,5 %. Cumplirlo no demuestra óptimo exacto;
  la fase de entregas conserva su propio certificado.
- IDs opacos internos; nombres legibles en la presentación. Cero y ausencia son distintos.
- `raw.result` conserva íntegro el resultado nativo; no recalcular KPIs en JS.
- Una geometría sintética se identifica como aproximada; no acredita calles.
- Configuración editable invalida la ejecución vigente. Respuestas tardías no
  reemplazan borradores nuevos. Los resultados anteriores se pueden consultar.
- Credenciales AWS solo en servidor. Mock no demuestra acceso real ni mejora del LLM.
- Resultados y contextos locales son temporales; reiniciar el servidor puede
  expirarlos. Se conservan exportaciones para reutilizar las entradas.

## Features previas conservadas

| Feature | Integración previa | Estado previo verificado |
|---|---|---|
| F02 · cargadores | `450fc0f` | Lista completa, metadatos, uso por vehículo, coordenadas opcionales |
| F03 · resumen | `78be661` | Ficha imprimible, fases, validación y aviso de resultado anterior |
| F05 · editor | `d9684b3` | Formulario/mapa, confirmar/cancelar, borradores, grafo nativo protegido |

[Entrega previa](implementation/ENTREGA-FEATURES.md) y sus explicaciones breves
siguen disponibles. Autocompletado externo de direcciones fue investigado, no
implementado: depende de proveedor/cobertura/acceso; la búsqueda actual usa puntos cargados.
Las pruebas históricas están identificadas como tales en
[orquestación](ZMD-ORCHESTRATION.md), no acreditan los cambios de esta nueva ola.

## Investigación confirmada de esta ola

El error de 8516 km surge al intentar ajustar los puntos sintéticos de Santiago
a una red vial de Ann Arbor. No se resuelve elevando el umbral de acceso de 100 m.
El ejemplo debe conservar una red sintética explícita y los CSV reales deben
validarse contra una red que cubra sus ubicaciones.

La carga antigua permitía importar 64 MiB, pero enviar al motor solo 8 MiB.
Los CSV de nodos locales tienen 81 ubicaciones y pesan aproximadamente 6 KiB;
los históricos eVED pesan entre 100 MiB y varios GiB y no son archivos de instancia.
La alineación de límites y mensajes se prueba con entradas válidas completas.

La suite inicial del merge pasó 137 pruebas JS y 13 pruebas de puente + 10 subtests.
La suite Python completa tuvo una aserción de óptimo exacto que pasó al repetirse
sola; se revisará de nuevo al cerrar y no se atribuye aún a un defecto del motor.

## Fuentes y límites

Solicitud actual y aclaraciones de este chat; directiva adjunta
`741c5e5c-169c-4e3e-8a80-d0bf387ed513/Pasted text.txt`; commits locales/remotos;
contratos y formulación versionados. El contexto de las olas previas se conserva
en la historia Git y en el registro de orquestación.
No se ha desplegado un producto público con autenticación, telemetría ni cuentas empresariales.
