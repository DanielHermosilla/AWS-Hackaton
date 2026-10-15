# Skills: búsqueda, pruebas y selección para ZMD Mobility

**14-10-2026.** Encargo de Diego: instalar el buscador y comprobar capacidades, incluida la posible pérdida de detalle al adaptar las skills. El producto sigue en planificación.

**Nomenclatura actualizada por Diego, 14-10:** ZMD Mobility es nuestra consultora; CASE es la empresa del desafío. Los artefactos originales se ejecutaron con nombres `case-*`; las recomendaciones de este documento usan sus equivalentes actuales `zmd-*`. El cambio de nombre no repite ni altera los ensayos.

## Resultado

**Mantener las cinco skills de ZMD Mobility como núcleo y consultar especialistas según el problema.** Los ensayos no justifican instalar otra suite completa. Sí muestran que una síntesis puede conservar el criterio y perder una técnica importante: Apple Design recupera ahora detalle de interrupción de animaciones en una referencia condicional.

`find-skills` quedó instalada globalmente en Codex desde [Vercel Labs](https://github.com/vercel-labs/skills/tree/13e4063a1cf913f5606d57d42ab83a86f5001e04/skills/find-skills). Fuente y copia coinciden; formato validado. Estará disponible para descubrimiento en el siguiente turno. Se usó realmente su CLI, fijada en `skills@1.7.2`, para buscar diseño, movimiento, accesibilidad, rendimiento, pruebas, depuración y planificación.

Las diez salidas de búsqueda conservadas contienen **176 identificadores distintos**. Esto no significa que se hayan leído o probado 176 skills: hubo selección por pertinencia, lectura de candidatas y **siete ensayos aplicados**. La popularidad sirvió para encontrarlas, no para aprobarlas.

## Originales frente a adaptadas

Dos agentes separados resolvieron los mismos cinco encargos, sin leer las respuestas del otro. Otro agente auditó resultados, ejecutó comprobaciones e hizo pruebas adicionales.

| Capacidad | Resultado observado | Decisión |
|---|---|---|
| Revisión de código | Ambas detectaron los seis fallos principales: cero/null, energía incompleta, timeout, resultado antiguo, caché entre cargas y HTML no confiable. La adaptada añadió rechazo de API, con salvedad sobre el consumidor ausente. | Mantener `zmd-code-review`; no recuperar cuotas ni listas genéricas por cada edición. |
| Contrato | Ambas conservaron IDs, cero/null, unidades pendientes y separación timeout/inviabilidad. El original produjo schema y más variantes; la adaptada comprobó conservación del ejemplo. | En planificación basta la propuesta honesta. Al implementar, recuperar variantes y validación de ambos extremos; el ejemplo no certifica integración. |
| Apple Design | Ambas produjeron HTML autónomo y estados honestos. La original conservó mejor continuidad: la adaptada reiniciaba opacity al invertir, aunque preservaba transform. | Recuperar la técnica en [detalle de interacción](../.agents/skills/zmd-apple-design/references/detalle-de-interaccion.md), consultado solo al implementar movimiento. |
| QA | Ambas reprodujeron errores de SOC y respuestas fuera de orden. La adaptada evitó exigir cierre y Escape a una sección no modal sin requisito. | Mantener `zmd-ui-qa`; no convertir preferencias en defectos. |
| Contexto | Ambas respetaron planificación, responsables y pendientes, sin construir producto ni delegar por su cuenta. | Mantener la entrada breve. No hay pérdida esencial observada. |

**Límites:** una ejecución por versión y tarea no demuestra superioridad general ni efecto causal. Además, el navegador bloqueó `file://` para el brazo original; la adaptada sí consiguió navegador mediante HTTP local. La diferencia de capturas no se atribuye a las instrucciones. No se probó el motor ni hubo participantes humanos.

El ajuste de Apple se verifica aparte, sin reemplazar las salidas de la comparación. El original completo de Emil y las demás skills globales siguen disponibles.

**Ensayo posterior del ajuste:** otro agente recibió un controlador distinto y la skill actual, sin leer la auditoría. Conservó transform y opacity al invertir y evitó finalizaciones/foco obsoletos. Once pruebas Node pasan; la entrada defectuosa falla ocho de esas once. Es una comprobación numérica y de llamadas con un adaptador simulado, no una evaluación visual humana. [Reporte](../../memoria-hackaton/10-planificacion/skills-benchmark/replay-motion/REPORTE.md).

## Siete candidatas probadas

| Skill y fuente | Prueba realizada | Utilidad para nosotros |
|---|---|---|
| [animate — Emil](https://github.com/emilkowalski/skills/tree/2d228630ba1446365f614a108cb8252f1feda202/skills/animate) | Feedback de presión, valores intermedios, inversión, teclado y movimiento reducido en navegador. | **Especialista útil, ya instalada.** Recupera curva, tiempos y tacto para una interacción concreta. Sus recetas no son obligaciones universales. |
| [systematic-debugging — Superpowers](https://github.com/obra/superpowers/tree/bb92a77741419a4ab5f06e711a283343f1ada0c3/skills/systematic-debugging) | Colisión `001`/`1` y desconocidos convertidos en cero; arreglo localizado con cinco expectativas correctas. | **Útil ante un fallo**, disponible como `superpowers-systematic-debugging`. No requiere adoptar toda la suite. |
| [React Best Practices — Vercel](https://github.com/vercel-labs/agent-skills/tree/063bee94c3f4df8453406c830b0a7df0f2860278/skills/react-best-practices) | Consultas independientes paralelas conservando permisos y dependencias; siete expectativas correctas. JSX simplificado por inspección, sin ejecutar React. | **Buena candidata si elegimos React/Next.** No decide stack ni acredita rendimiento del producto. Leer las reglas pertinentes, no las 70 siempre. |
| [frontend-design — Anthropic](https://github.com/anthropics/skills/tree/dbd4588f9e1033efb41dad4bef2f7947c8993d44/skills/frontend-design) | Dirección visual, HTML y capturas a 1280/390; detalle por teclado. | **Útil como segunda dirección visual.** Se solapa con Impeccable y Apple; no instalar por acumular opciones. |
| [web-design-guidelines — Vercel](https://github.com/vercel-labs/agent-skills/tree/063bee94c3f4df8453406c830b0a7df0f2860278/skills/web-design-guidelines) | Auditoría estática: foco, control no semántico y riesgo de overflow. | Referencia complementaria. No detectó fallos de SOC/selección en ese ensayo; no sustituye QA de ZMD Mobility. |
| [design-critique — Anthropic](https://github.com/anthropics/knowledge-work-plugins/tree/f652327d4e953d7957d99e735c3c7f9964e9d2e5/design/skills/design-critique) | Crítica de vocabulario, siguiente acción y numeración ambigua. | Poco aporte adicional. Conservar la idea de explicar también lo que funciona. |
| [brainstorm-experiments-existing — Phuryn](https://github.com/phuryn/pm-skills/tree/c68487d721e419ec87af1ae6412a842978eab785/pm-product-discovery/skills/brainstorm-experiments-existing) | Protocolo de comprensión con tres tareas y hoja vacía de observaciones. | Aprovechar el artefacto cuando podamos preguntar a personas. **No se realizaron sesiones ni se validó comprensión.** No añadir todo su workflow. |

Solo se instaló `find-skills`. Las novedades se probaron aisladamente; las capacidades globales existentes no se reinstalaron.

## Descartes

- **User story mapping:** la candidata prescribe al menos 45 tareas al combinar sus mínimos. Puede fabricar trabajo en esta fase. Se leyó y descartó, no se ejecutó.
- **Anthropic webapp-testing:** se leyó, pero insiste en `networkidle` para determinar preparación. [Playwright](https://playwright.dev/docs/api/class-page#page-wait-for-load-state) desaconseja usarlo así en pruebas. No sustituir criterio por reputación del autor.
- Suites completas, marketing, despliegue y configuración de cuentas no resuelven este encargo. No se eligió framework, proveedor o arquitectura por aparecer en el catálogo.

## Evidencia y uso

[Método e índice](../../memoria-hackaton/10-planificacion/skills-benchmark/README.md) · [auditoría independiente](../../memoria-hackaton/10-planificacion/skills-benchmark/AUDITORIA-INDEPENDIENTE.md) · [ensayos de diseño](../../memoria-hackaton/10-planificacion/skills-benchmark/candidatas/design/REPORT.md).

La auditoría descubrió un hueco en el test React: podía omitir una aserción si se absorbía un error. Se corrigió con `assert.rejects` y se comprobó que una implementación deliberadamente defectuosa falla. Es evidencia a favor de revisar pruebas, no una mejora atribuible a la skill.

Para Diego: `zmd-apple-design` al diseñar; `animate` cuando toque afinar una interacción; una segunda dirección con `frontend-design` si necesitamos explorar alternativas. Revisar con `zmd-code-review` y probar con `zmd-ui-qa` en hitos útiles. El contrato se trabaja con Daniel/Lucas cuando puedan fijar la frontera. No es una cadena obligatoria por cada cambio.
