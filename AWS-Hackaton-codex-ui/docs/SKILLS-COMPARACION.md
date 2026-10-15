# Comparación y adaptación del repertorio ZMD Mobility

Nomenclatura actualizada el 14-10-2026: ZMD Mobility identifica nuestra consultora; CASE identifica la empresa del desafío. Los artefactos anteriores mantienen los nombres `case-*`; aquí se usan los equivalentes vigentes `zmd-*`.

**14-10-2026. Cambio solicitado por Diego; implementación de instrucciones, no del producto.** Se interpretaron las “últimas cinco” como las cinco posteriores a contract-first en la selección anterior. Se compararon todas y también se conservó el contrato como capacidad separada.

## Qué cambió al comparar las cinco

| Candidata ECC | Comparada con | Decisión incorporada |
|---|---|---|
| **code-reviewer** | Google Engineering Practices y Superpowers requesting-code-review | Conservar hallazgos con disparador, consecuencia y evidencia. Google aporta complejidad evaluada por comprensión y cierre sin perfeccionismo. Quitar revisión obligatoria de cada edición, cuotas, recetas React y umbrales rígidos. Resultado: modo revisión de `zmd-code-review`. |
| **code-simplifier** | Criterios de complejidad de Google, reviewer ECC y flujo actual ZMD Mobility | Fusionar con review, pero distinguir lectura de edición. Simplificar solo dentro del encargo y preservar comportamiento; no borrar logs útiles ni reducir líneas como objetivo. “Revisa y corrige” ya autoriza ambos modos. |
| **browser-qa** | Vercel Web Interface Guidelines, W3C, Playwright, break-ui e Impeccable local | Conservar interacción real y sumar datos difíciles por la frontera existente. Distinguir prueba real/simulada/omitida y defectos observados/inferidos. No añadir toggle demo, detector, score, tema oscuro o framework por obligación. Resultado: `zmd-ui-qa`. |
| **team-agent-orchestration** | Superpowers dispatching-parallel-agents y subagent-driven-development | Conservar dueño, alcance, evidencia y un integrador; paralelizar dominios independientes. Quitar tablero, daemon y dos revisores por cada microtarea. Resultado: sección condicional en `zmd-project-context`, sin skill adicional. |
| **context-and-decisions** | Contexto ZMD Mobility existente y criterio de alcance de skill-creator | Mantener una entrada breve y consultar documentos por tema. Reutilizar glosario y separar hechos de pendientes. No importar ADR, router documental o memoria automática para satisfacer una taxonomía. Resultado: mejora de la skill existente. |

Fuentes ECC fijadas: [reviewer](https://github.com/affaan-m/ECC/blob/b92f181b3b748d1abbc2afd94af6aa7d8c8fca29/agents/code-reviewer.md), [simplifier](https://github.com/affaan-m/ECC/blob/b92f181b3b748d1abbc2afd94af6aa7d8c8fca29/agents/code-simplifier.md), [browser-qa](https://github.com/affaan-m/ECC/blob/b92f181b3b748d1abbc2afd94af6aa7d8c8fca29/skills/browser-qa/SKILL.md), [orchestration](https://github.com/affaan-m/ECC/blob/b92f181b3b748d1abbc2afd94af6aa7d8c8fca29/skills/team-agent-orchestration/SKILL.md), [context](https://github.com/affaan-m/ECC/blob/b92f181b3b748d1abbc2afd94af6aa7d8c8fca29/skills/context-and-decisions/SKILL.md).

Google distingue hechos de preferencias y desaconseja exigir perfección para aceptar una mejora; su guía exige comprobar que las pruebas detecten el comportamiento roto. Se adoptó ese criterio, no normas internas de Google. [Qué revisar](https://google.github.io/eng-practices/review/reviewer/looking-for.html), [estándar de revisión](https://google.github.io/eng-practices/review/reviewer/standard.html).

Las copias locales de Superpowers se compararon como material de consulta. Se conservó independencia y contexto del encargo; no su secuencia completa de implementador, dos revisores, commits y bucles obligatorios. Referencia del proyecto: [Superpowers](https://github.com/obra/superpowers/tree/bb92a77741419a4ab5f06e711a283343f1ada0c3).

## Apple Design: añadida y adaptada

Se partió de [apple-design de Emil](https://github.com/emilkowalski/skills/blob/2d228630ba1446365f614a108cb8252f1feda202/skills/apple-design/SKILL.md), comparada con su `emil-design-eng`, el brief de Diego y [Apple Typography](https://developer.apple.com/design/human-interface-guidelines/typography) / [Apple Motion](https://developer.apple.com/design/human-interface-guidelines/motion).

**Conservado:** jerarquía, legibilidad, feedback, control de la persona, continuidad y movimiento que explique algo. Emil refuerza considerar propósito y frecuencia antes de animar. Apple HIG respalda usar movimiento de forma deliberada, breve y cancelable, y mantener una jerarquía tipográfica legible.

**Adaptado:** se eliminaron respuesta inicial ceremonial, vidrio/translucidez por defecto, parámetros fijos de springs, gestos y dependencias obligatorias. La preferencia Apple/Notion se traduce en claridad; no obliga a imitar un sistema operativo. La fuente del sistema, superficies opacas y ausencia de animaciones son opciones válidas.

`zmd-apple-design` dirige una decisión visual. `zmd-ui-qa` comprueba lo que ocurrió al usarla. Evitar que una auditoría se convierta por defecto en rediseño o que una propuesta visual se presente como prueba.

## Precisiones que mejoran QA

- La guía [Vercel](https://vercel.com/design/guidelines) incluye una alternativa que limita zoom mientras también pide respetarlo. Nuestra adaptación conserva zoom; contrasta criterios con W3C en lugar de copiar toda la guía.
- “Focus visible” y “Focus not obscured” son criterios diferentes. Un borde de foco no basta si otro elemento tapa el control. [W3C](https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum.html).
- Probar texto ampliado es útil, pero no certifica toda la accesibilidad ni todo el reflow. Los mapas/tablas pueden necesitar una disposición bidimensional. [Resize Text](https://www.w3.org/WAI/WCAG22/Understanding/resize-text.html), [Reflow](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html).
- Se retiraron ejemplos ECC de tracing y esperas de red incorrectos. La skill pide comportamiento observable y APIs de la versión instalada. [Playwright](https://playwright.dev/docs/best-practices).
- De break-ui se tomó variar datos plausibles; de Impeccable, foco en operación y tareas. No se instalaron sus runtimes ni se adoptaron sus artefactos/checklists completos.

## Por qué el contrato sigue separado

[Contract-first](https://github.com/affaan-m/ECC/blob/b92f181b3b748d1abbc2afd94af6aa7d8c8fca29/skills/contract-first/SKILL.md) y `test-collaboration` cubren una necesidad distinta: que ambos lados respeten el mismo significado y representación. Un glosario explica “SOC”; el contrato fija su escala y tratamiento de ausencia; QA comprueba una ejecución. Ninguno sustituye validar energía y restricciones del motor.

La adaptación admite un tipo o archivo compartido y mantiene dudas explícitas. No obliga a OpenAPI, REST ni generadores. Los datos reales y los mocks se contrastan por separado; una prueba del mock no demuestra integración.

## Límite del resultado

Estas cinco skills son instrucciones locales escritas para ZMD Mobility, con atribución y licencias MIT de las fuentes adaptadas. No son una instalación del runtime ECC ni una copia integral de Apple Design. No establecen solver, arquitectura, stack o nueva funcionalidad.

La selección de cinco es una decisión práctica actual, no un número que haya que conservar si el uso real demuestra otra necesidad. El catálogo amplio previo quedó archivado reversiblemente. Las skills globales de otros proyectos no se eliminaron.
