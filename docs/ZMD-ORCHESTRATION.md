# ZMD · orquestación

Sesión madre: **ZMD Features Implementation**,
`01a1415b-d61e-7a51-b306-2ef1441f7bf0`.
Contexto: [ZMD-MASTER-CONTEXT.md](ZMD-MASTER-CONTEXT.md).
Base de producto: `a372d03efc270b0ac23769e5d4334c2d3f4144ff`.

## Objetivo y mecanismo

Goal persistente activo para consolidar contexto, implementar F02/F03/F05,
revisar, probar y preparar integración local. No se asignó presupuesto de tokens.
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
| Contexto, contratos de integración y coordinación | Madre | `codex/features-implementation`; worktree `features-review` | Contexto consolidado; baseline en curso | Base fijada tras fetch |
| F02 · información de cargadores | Agente de cargadores | Se asignará al crear el worktree gestionado | Especificación preparada | Metadatos nativos existentes |
| F03 · resumen imprimible | Agente de resumen | Se asignará al crear el worktree gestionado | Especificación preparada | Resultado API 3.0 y vigencia |
| F05 · editor de ubicaciones | Agente de editor | Se asignará al crear el worktree gestionado | Especificación preparada | `/prepare`, grafo nativo protegido |
| Autocomplete de direcciones | Madre; transferir conclusión a F05 | Rama madre, documento de investigación | Investigación de fuentes primarias en curso | Acceso comercial/AWS no confirmado |
| Revisión e integración | Madre + agente revisor tras terminar implementación | Rama madre | Pendiente de entregas | Diff, tests y QA de cada feature |

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
| Baseline Python | En ejecución en entorno propio sincronizado con `uv.lock` |
| Entorno | `uv` no estaba en PATH; se localizó la herramienta existente y se usa su ruta explícita, sin otro gestor |
| QA de nuevas funciones | No ejecutada todavía |

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
