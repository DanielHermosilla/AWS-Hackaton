# ZMD · orquestación

Sesión madre: **ZMD Features Implementation**,
`01a1415b-d61e-7a51-b306-2ef1441f7bf0`.
Contexto: [ZMD-MASTER-CONTEXT.md](ZMD-MASTER-CONTEXT.md).
Base de producto: `a372d03efc270b0ac23769e5d4334c2d3f4144ff`.

## Objetivo y mecanismo

Goal persistente para consolidar contexto, implementar F02/F03/F05,
revisar, probar y preparar integración local. No se asignó presupuesto de tokens.
Objetivo técnico cumplido en la rama local; entrega verificada y documentada.
Se mantiene el modo de ejecución actual; no se afirma haber activado `/plan`.

La sesión madre es el único integrador y editor de estos registros. Tres agentes
Astra Ultra reciben especificaciones acotadas y worktrees gestionados propios.
No reciben tareas de solver. Se usan subagentes del chat, no tres chats huérfanos
que el usuario deba dirigir. Cada rama es un fork de la misma base consolidada.

Las conversaciones y los cambios futuros **no se sincronizan automáticamente**:
los agentes reportan por las herramientas de colaboración; entregan commits,
diff, comandos, resultados, capturas y riesgos. El integrador revisa e incorpora
los commits explícitamente y actualiza este registro. No compartir una carpeta
mutable ni escribir desde un agente en el checkout de otro.

## Registro de trabajo

| Trabajo | Responsable | Rama / worktree | Estado | Dependencia |
|---|---|---|---|---|
| Contexto, contratos de integración y coordinación | Madre | `codex/features-implementation`; worktree `features-review` | Contexto, integración y entrega verificados | Base fijada tras fetch |
| F02 · información de cargadores | `/root/implement_chargers` | `codex/feature-chargers`; `zmd-feature-chargers` | `e604f45` → `450fc0f`, incorporado y revisado | QA combinado aprobado |
| F03 · resumen imprimible | `/root/implement_summary` | `codex/feature-summary`; `zmd-feature-summary` | `260e01a` → `78be661`, incorporado y revisado | PDF de fixture pequeño: 2 páginas A4 |
| F05 · editor de ubicaciones | `/root/implement_editor` | `codex/feature-editor`; `zmd-feature-editor` | `d7dca48` → `d9684b3`, incorporado y revisado | CSV/sintético editable; grafo nativo protegido |
| Autocomplete de direcciones | Madre; conclusión transferida a F05 | Rama madre, [decisión documentada](implementation/F05-address-autocomplete.md) | Análisis terminado; servicio externo no implementado | Acceso, cobertura y presupuesto AWS pendientes |
| Revisión e integración | Madre + `/root/review_features` (solo lectura) | Rama madre | Cerrada sin hallazgos pendientes; regresión y once comprobaciones combinadas aprobadas | Sin push ni despliegue |

Los tres worktrees parten de `04e7f313e49279ac671f17f5bceaa7f7c197918c`,
que incorpora el contexto y los prompts a la base de producto. Sus rutas son
`/Users/caballero/.codex/worktrees/<worktree>/AWS-Hackaton`. Los puertos de QA
son 4312 (F02), 4313 (F03), 4315 (F05) y 4310 (integración de la madre).
Al cerrar la entrega se detuvieron los servidores auxiliares. La vista integrada
queda disponible en 4310. Se conservan las ramas/worktrees y su evidencia para revisión.

## Propiedad de archivos

| Responsable | Archivos autorizados |
|---|---|
| F02 | `webapp/plan.js`, `webapp/shared/solver-adapter.js`, nuevo `webapp/shared/charger-details.js`, nuevo `webapp/charger-details.css`, pruebas de cargadores |
| F03 | `webapp/boot.js`, nuevos módulos/estilos de resumen imprimible y sus pruebas |
| F05 | `webapp/run-panel.js`, `webapp/run-panel.css`, `webapp/map.js` solo si es necesario, nuevos módulos/estilos de edición y sus pruebas |
| Madre | `docs/ZMD-*.md`, `docs/implementation/`, documentación global, investigación de autocomplete y ajustes de unión revisados |

No editar `webapp/shared/data.js`, `solver-input.js`, `solver-client.js`,
`backend/`, dependencias o contratos compartidos sin presentar primero el cambio
al integrador. Si se necesita un ajuste común, lo implementa la madre o asigna
un único propietario. `src/ev_routing/` y `docs/solver-source.json` quedan fuera.

## Flujo de cada hito

1. Leer contexto, especificación y skills pertinentes; confirmar rama/directorio.
2. Escribir pruebas útiles para el comportamiento afectado e implementar.
3. Ejecutar pruebas del área y Node completo; probar el flujo visible con fixtures
   sintéticas y ejecución real cuando corresponda. Distinguir mocks de datos reales.
4. Revisar diff y alcance, resolver fallos y crear commit solo con archivos propios.
5. Reportar: objetivo, SHA base/final, archivos, comportamiento, comandos/resultados,
   pruebas omitidas, capturas y limitaciones.
6. Madre revisa compatibilidad, solicita correcciones e incorpora el commit.
7. Tras integrar las tres: regresión Python/JS, flujos combinados, impresión,
   escritorio/móvil, teclado, mapa ausente, estado viejo y exportaciones.

No hacer merge a ramas compartidas, push, despliegue ni llamadas AWS pagas.
La entrega es una rama local revisable. El permiso histórico de publicación de
la Beta no se usa como publicación automática de esta nueva ola.

## Evidencia y problemas

| Comprobación | Estado |
|---|---|
| Lectura directa de los tres chats y recuperación de decisiones | Confirmada; fuentes en MASTER-CONTEXT |
| Fetch y base de implementación | `origin/codex/webapp=a372d03`; limpio antes de documentación |
| Baseline JavaScript | **101/101** aprobadas, sin omisiones |
| Baseline Python | **347 aprobadas, 1 omitida, 37 subtests aprobados**; `python -m pytest -q`, 49,92 s |
| Entorno | `uv` no estaba en PATH; se localizó la herramienta existente y se usa su ruta explícita, sin otro gestor |
| Invocación de pytest | `uv run --locked pytest -q` falló al importar `backend` durante colección; `uv run --locked python -m pytest -q` resuelve la ruta del proyecto. Se corrige el comando documentado. |
| Omisión de baseline | `tests/test_solve.py:421`: ejecutable SCIP del plugin alternativo Pyomo no disponible. PySCIPOpt, usado por el servidor actual, sí está instalado. |
| F02, pruebas del agente | **111/111 Node**, cinco escenarios Chromium: escritorio/móvil, sin WebGL, sin coordenadas, sin solución. API y mapa base sintéticos; sin errores de página. Madre inspeccionó diff y capturas. |
| Motor real en rama madre | POST del fixture operacional: HTTP 200, validación factible, 2 entregas, 14 kWh netos, 9 kWh recargados, 10 kWh de red y 3580 s de duración. Instancia sintética; no evidencia sobre rutas reales. |
| F03, pruebas del agente | **112/112 Node**, 12 comprobaciones de navegador. Caso operacional con SCIP real; sin incumbente/validación fallida simulados. PDF vigente y anterior de 2 páginas, inspeccionados por implementador, madre y revisor. |
| F05, pruebas del agente | **112/112 Node**, **29 Python + 37 subtests**, dos runners de navegador con cálculo real, mapa fallido, respuestas tardías, sustitución de archivo, Cancelar durante solve y persistencia entre páginas. |
| Revisión independiente | 10 pruebas F02 + 11 F03 + 11 F05; inspección de PDF; runner de navegación F05 repetido con cálculo real sobre SHA final. Sin hallazgos accionables pendientes. |
| Regresión final en rama madre | **133/133 Node**, **347 Python + 37 subtests**, misma única omisión del plugin alternativo SCIP. `python -m pytest -q`: 18,37 s. |
| QA combinado final | **11 comprobaciones aprobadas**, sin errores JS: ejemplo, cancelar/confirmar, coordenadas inválidas, borrador antes/después del primer run, CSV→prepare→SCIP, cargadores/Inicio→Continuar, resumen/impresión/vigencia, nuevo cálculo, exportación exacta y móvil/JSON nativo protegido. |
| Preservación del motor | `git diff a372d03 -- src/ev_routing backend pyproject.toml uv.lock docs/solver-source.json modelamiento.pdf modelamiento.tex`: sin cambios. |

Evidencia local: `.local/features-implementation-2026-10-15/`.
Los logs, capturas, entornos, históricos y datos no se incorporan masivamente a Git.

## Decisiones registradas

- Usar los diseños ya aprobados y los párrafos para Daniel como punto de partida;
  la petición actual autoriza ejecutar sin una nueva ronda de aprobación rutinaria.
- Mantener permisos claros entre agentes; F03 inserta su entrada desde `boot.js`
  para no competir por `plan.js` (F02) ni `run-panel.js` (F05).
- El editor debe tratar por separado ubicaciones editables y grafo nativo. Nunca
  mover un nodo y conservar sus costes como si la red hubiera sido reconstruida.
- La investigación histórica se conserva; el contexto actual corrige el proveedor
  y el estado de integración sin borrar el razonamiento anterior.
- F02 incorpora la pestaña `chargers`; la madre actualizará el enlace «Continuar
  plan» en `home.js` para conservar ese contexto sin competir por archivos.
- El editor no depende de geocodificación externa: confirma texto y coordenadas.
  Nominatim público no permite autocomplete; la selección de un proveedor de
  direcciones se documentará con fuentes y condiciones de almacenamiento.
- En los entornos nuevos, la primera llamada tardó durante importación nativa
  Python/SciPy (`dyld` observado por F03); después la petición pequeña respondió
  en 0,4 s. Se documenta como calentamiento observado, sin cambiar el solver.
- La madre solicitó compactar F03: la primera impresión de un fixture con dos
  entregas ocupaba cinco páginas. Se retiran volcados técnicos duplicados del
  resumen operativo; los detalles completos continúan en la ejecución/JSON.
  La versión final ocupa dos páginas y conserva comprobación, fases y supuestos.
- La madre detectó pérdida de ubicaciones confirmadas al navegar antes de
  recalcular. F05 la reprodujo y corrigió con un borrador separado asociado por
  `draftId`; cuota fallida informa el límite y no repone datos viejos como cambios.
- El arnés combinado inicial usó potencia 0, rechazada correctamente por el
  contrato nativo (`max_power_kw > 0`). Se corrigió la fixture a 50 kW; los
  puertos DC 0 siguen probando cero versus ausencia. Otra aserción se adelantaba
  a la carga asíncrona de Inicio; ahora espera `aria-busy=false`. No requirieron
  modificar producto, solver ni criterios de aceptación. Evidencia inicial
  conservada como `qa/fixture-correction-report.json` y `qa/early-dom-report.json`.

## Reproducción y transferencia

La [entrega](implementation/ENTREGA-FEATURES.md) enlaza las explicaciones breves
para el usuario y el resumen técnico para Daniel. Los prompts originales quedan
en `docs/implementation/F02-chargers.md`, `F03-plan-summary.md` y
`F05-location-editor.md`; no sustituyen este registro de aceptación.

```sh
uv sync --locked --group dev
node --test webapp/tests/*.test.mjs
uv run --locked python -m pytest -q
uv run --locked python -m backend.local_server --port 4310
```

QA de editor reproducible con una instalación existente de Playwright:
`PLAYWRIGHT_MODULE` puede indicar su módulo absoluto y `ZMD_QA_ORIGIN` el servidor.
Ejecutar `node webapp/tests/location-editor.browser.mjs` y
`node webapp/tests/location-navigation.browser.mjs`. No agregar otra dependencia
de producto solo para ejecutar este control opcional.

El arnés de unión y sus capturas están en
`.local/features-implementation-2026-10-15/qa/combined.mjs` y `combined-report.json`.
Esta carpeta conserva su nombre iniciado en la investigación del 15 de octubre;
la entrega consolidada se registra el **16-10-2026**.

## Auditoría ligera posterior · 16-10-2026

Solicitada por Diego como pasada rápida, sobre `7d872c9`, sin ampliar alcance.
Dos agentes nuevos revisaron en paralelo la unión del código y la experiencia
visible. Sin hallazgos reproducibles ni cambios de producto.

- `/root/quick_integration_audit`: **32/32 pruebas específicas** y lectura de
  arranque, Continuar plan, borrador, vigencia, protección nativa y KPIs.
- `/root/quick_visual_audit`: **11 comprobaciones de navegador**, dos cálculos
  sintéticos reales, escritorio 1440 px y móvil 390 px. Capturas inspeccionadas;
  cero errores JS y sin desbordamiento observado en resumen/editor.
- Madre: servidor y tres módulos nuevos responden HTTP 200; motor, backend y
  dependencias siguen sin cambios respecto de la base.

Evidencia: `.local/quick-audit-2026-10-16/visual/combined-report.json` y capturas
en esa misma carpeta. Esta pasada acotada no repitió la regresión Python completa.
