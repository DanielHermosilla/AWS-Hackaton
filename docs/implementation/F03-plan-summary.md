# F03 · resumen del plan e impresión

## Encargo del agente

Implementar un resumen legible e imprimible de la ejecución, manteniendo diseño
y contrato. Leer contexto maestro, registro de orquestación, README, API 3.0 y
skills ZMD de contrato, diseño y QA. La ejecución está autorizada.

## Alcance y arquitectura

Añadir «Ver resumen» accesible desde Inicio y Plan, usando el resultado vigente.
Reunir estado/validación, entregas previstas/pendientes, energía con su definición,
tiempo de cómputo separado del operacional, supuestos y advertencias.
Por vehículo: secuencia, servicio explícito, batería y recarga disponibles.
Incluir identificador de corrida y procedencia suficiente para reconocer el plan.
Imprimir con el navegador/guardar PDF, sin librería PDF ni cálculo alternativo.

Responsabilidad: `webapp/boot.js`, nuevos `webapp/plan-summary.js`,
`webapp/plan-summary.css`, `webapp/shared/plan-summary-model.js` y pruebas propias.
Inicializar desde boot después de `runPanel.setData(data)` y añadir el control sin
editar `run-panel.js` o `plan.js`. No crear otro estado global ni endpoint.
Consultar vigencia al abrir e imprimir; no presentar una corrida anterior como
plan actual tras editar. Si no hay resultado, explicar la ausencia.

## Secuencia y aceptación

- [ ] Pruebas de presentación a partir de fixtures API 3.0: normal, parcial,
  sin incumbente, validación fallida, datos nulos, energía negativa y visita repetida.
- [ ] Reutilizar formateo/escape y métricas existentes, con nombre de unidades.
  Ninguna entrega planificada se denomina completada en terreno.
- [ ] Construir vista/diálogo con entrada/salida de foco, Escape y acción de imprimir.
- [ ] Estilos de impresión: sin navegación/mapa obligatorio, contraste legible,
  encabezados de tabla y saltos que no corten filas; móvil sin overflow.
- [ ] Probar corrida vigente y antigua, ausencia/expiración y cambio entre páginas.
- [ ] `node --test webapp/tests/*.test.mjs`; `git diff --check`.
- [ ] QA visual escritorio/móvil y medio print; generar PDF sintético solo para
  verificar páginas. Conservar las métricas del mismo JSON y declarar origen.
- [ ] Commit acotado y entrega estructurada con capturas y comandos.

No editar `src/ev_routing/`, backend ni contratos. Si una cifra no está informada,
mostrar el motivo o ausencia; no rellenarla ni prometer un KPI nuevo.

## Entrega

Reportar rama/worktree, SHA, archivos, prueba de concordancia, comandos y resultados,
capturas de pantalla/impresión, estados simulados y limitaciones. La madre actualiza
documentación global e integra después de revisar.
