---
name: zmd-ui-qa
description: "Prueba o audita un flujo ejecutable de ZMD Mobility: integración visible, datos difíciles, errores y accesibilidad. Úsala al verificar una pantalla o hito de integración; no decide otra dirección visual ni certifica el motor."
---

# QA visible de ZMD Mobility

Acota el recorrido y su resultado esperado desde el contrato vigente. Usa las herramientas disponibles; no instales un framework para completar una checklist. Si solo hay código, capturas o bocetos, distingue lo inferido de lo comprobado y declara qué falta para probar la interacción.

Selecciona las comprobaciones pertinentes:

- Recorrer escenario → ejecución → resultado y comparar cifras, unidades, IDs y estado con esa ejecución del motor.
- Cambiar entrada y comprobar que una respuesta anterior no figure como actual, también cuando las respuestas lleguen en otro orden.
- Ejercitar espera, vacío, error, tiempo agotado o parcial según lo que soporte el contrato. Un mock solo demuestra el comportamiento simulado.
- Probar texto largo, cero/uno y campos opcionales ausentes mediante fixtures sintéticos o la frontera existente. No copiar datos privados a fixtures ni añadir siempre un toggle de demo.
- Usar teclado y revisar foco visible/no oculto, nombres de controles, zoom, contraste y movimiento reducido. Si hay modal, comprobar entrada/salida del foco y cierre. Elegir anchos pertinentes al uso y presentación; revisar controles y texto alrededor de mapas/tablas.

Para criterios concretos de accesibilidad, consulta W3C. Un escáner limpio o una prueba rápida no certifican conformidad completa. Sin una referencia previa puedes revisar el diseño actual, pero no afirmar ausencia de regresión visual.

Si automatizas, prueba comportamiento observable con esperas vinculadas al resultado; evita pausas arbitrarias. Usa APIs verificadas de la versión instalada. No dependas de ausencia de tráfico para demostrar que una interacción terminó.

Reporta por comprobación **aprobada, fallida o no comprobada**, con pasos, esperado/observado, impacto y evidencia suficiente. Cero hallazgos es válido. Corrige dentro de la autorización existente y repite lo afectado, sin ampliar el producto ni rediseñarlo por gusto.

Fuentes, 14-10-2026: [ECC browser-qa](https://github.com/affaan-m/ECC/blob/b92f181b3b748d1abbc2afd94af6aa7d8c8fca29/skills/browser-qa/SKILL.md), [Vercel](https://vercel.com/design/guidelines), [W3C APG](https://www.w3.org/WAI/ARIA/apg/) y [Playwright](https://playwright.dev/docs/best-practices). Criterios adaptados; sus catálogos no se cargan por defecto.
