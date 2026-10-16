# Integración y refinamiento ZMD — 16 de octubre de 2026

Solicitud: integrar `origin/main@9f03027` con F02 (cargadores), F03 (resumen) y F05 (editor), y completar el feedback de producto. Base previa recuperable: `codex/pre-main-refinement@d3e045a`. Sin push ni despliegue público.

La referencia vigente incluye preprocesamiento vial, SCIP sin H y Bedrock de main. La exclusión histórica del preprocesador quedó reemplazada por la autorización actual. Conservar validación independiente, física y prioridad de entregas. La preferencia de tema persistente reemplaza iniciar siempre en claro.

## Resultado y explicaciones breves

| Prioridad práctica | Mejora | Estado | Explicación para el usuario y resumen para Daniel |
|---|---|---|---|
| 1 · desbloquea los cálculos | Integración del motor y archivos válidos | Implementado y probado | [Motor y archivos](GUIA-MOTOR-Y-ARCHIVOS.md) |
| 2 · evita errores de configuración | Panel, ayuda y ejemplos configurables | Implementado y probado | [Panel de cálculo](GUIA-PANEL-DE-CALCULO.md) |
| 3 · permite revisar y continuar | Resultados, tema, etiquetas y navegación | Implementado y probado | [Resultados y navegación](GUIA-RESULTADOS-Y-NAVEGACION.md) |

El orden prioriza factibilidad y cálculo real, después preparación y lectura.
No atribuye una mejora de entregas o energía al rediseño ni convierte la rúbrica en pesos del solver.

## Backlog de aceptación

| ID | Resultado esperado | Estado / evidencia |
|---|---|---|
| I01 | Main fusionado con historia y F02/F03/F05 | Implementado: f5b4ea8; origin/main incluido |
| I02 | CSV completos de data/raw y JSON grandes válidos | Implementado: ambos CSV de 81 nodos; ida y vuelta HTTP de 9,44 MB |
| I03 | Tema oscuro entre páginas | Implementado: Inicio, Plan, recarga y salida en navegador |
| I04 | Cantidades de clientes y cargadores | Implementado: controles configurables, hasta 200 ubicaciones |
| I05 | Diseño del caso sintético | Implementado: sección desplegable y acción Crear caso |
| I06 | Selector de archivo | Implementado: botón propio y nombre visible |
| I07 | Sintético no se ajusta a calles ajenas | Implementado: haversine explícito; 100 m vial conservado |
| I08 | Ayuda con ? por hover/foco/toque | Implementado: navegador y teclado, Escape independiente |
| I09 | Tarjeta Flota y supuestos | Implementado: incluye red y explicación breve |
| I10 | Tarjeta Parámetros del motor | Implementado: presupuesto, gap, búsqueda y semilla efectivos |
| I11 | CPU automático, sin control visible | Implementado: 8 CPU efectivos en este equipo, máximo SCIP 64 |
| I12 | Datos y límites recuperables | Implementado: reapertura al terminar y Ver resultados |
| I13 | Retirar checkbox | Implementado; la validación de datos sigue activa |
| I14 | Producto sin nombres del equipo | Implementado; procedencia original se conserva en JSON |
| I15 | Terminaciones comprensibles | Implementado: presentación por fase, sin falsear optimalidad |
| I16 | Ruta sintética de dos clientes visible | Implementado: 2/2 comprobadas, trazado discontinuo aproximado |
| I17 | Etiquetas legibles de paradas | Implementado: nombres de lugares y salida/regreso, IDs intactos |
| I18 | Retirar hash de cabecera | Implementado |
| I19 | Descargar → Ver resultados | Implementado; descargas permanecen dentro del panel |
| I20 | Rellenar parámetros del JSON | Implementado: flota y motor; grafo nativo protegido |
| I21 | Acción disponible con errores claros | Implementado: campos faltantes/archivo inválido; doble envío bloqueado |
| I22 | Scroll de Inicio con explicación abierta | Implementado: escritorio 1440 px y móvil 390 px |
| I23 | Explicación breve de indicadores | Implementado: menos de 50 palabras, sin frase de telemetría |
| I24 | Revisión independiente y pruebas integradas | Completado: un problema de exportación corregido y revalidado |

## Priorización y causas

P0: integración, carga y casos que no resuelven o no muestran ruta (I01/I02/I07/I16).
P1: persistencia, parámetros efectivos y conservación de resultados (I03/I04/I10/I11/I12/I20/I21).
P2: panel, ayuda, claridad y navegación (I05/I06/I08/I09/I13–I19/I22/I23).
P3: transiciones y ajustes visuales finales. I24 verifica todos los niveles.

Confirmado: choque Santiago/Ann Arbor en sintéticos; límites de importación/transporte distintos; tema forzado claro; formulario recarga la página al resolver. Las pruebas reproducen cada corrección; solicitudes de diseño no se describen como defectos del solver.

## Límites de la verificación

Los históricos eVED contienen telemetría, no destinos. No convertir filas en clientes ni truncar un archivo silenciosamente. Una geometría sintética debe identificarse como aproximación por distancia. No relajar el umbral vial para esconder ubicaciones fuera de cobertura. No acreditar una invocación de AWS mediante mocks ni prometer mejora del LLM sin medición.

## Verificación final

- **716 pruebas Python, 37 subtests y 146 pruebas JavaScript aprobadas.**
  Diez omisiones: ejecutable SCIP alternativo de Pyomo o backend no disponible
  para una prueba de warm start. El SCIP/PySCIPOpt usado por la web sí se ejecutó.
- Navegador integrado: panel real, seis grupos de editor, dos de navegación,
  ocho comprobaciones de experiencia y regresión de exportación. Cero excepciones JS.
  Escritorio y móvil, temas claro/oscuro; capturas inspeccionadas.
- CSV real `competition_routing_nodes.csv`: 81 ubicaciones, 20/20 entregas,
  60 cargadores conservados, geometrías y comprobador vial correctos. Consumo
  supuesto 0,16 kWh/km; 24 kWh útiles; 2,4 kWh de reserva; 60 % inicial. Resultado 10,775 kWh;
  gap energético 0,2274 %, dentro del 0,5 %, sin certificado exacto de energía.
- Primera preparación 73,9 s; petición de resolución 4,28 s con presupuesto 10 s.
  Son etapas distintas. La red OSM delivery local conserva 106.759 nodos y 211.755 arcos;
  el preprocesamiento entrega 81 nodos y 6.006 arcos al motor. No se amplió el acceso de 100 m.
- Archivo grande: petición 9,44 MB, exportación 28,34 MB, reimportación y resolución
  válidas por HTTP. Usa datos sintéticos y relleno en procedencia para aislar transporte;
  no es una medición de escalabilidad matemática.
- El revisor reprodujo exportación de una entrada vial anterior después de fallar
  un cálculo nativo. `5424359` la vincula a la instancia vigente; prueba roja/verde
  y repetición independiente aprobadas.
- Se estabilizó una prueba heredada cuyo doble vencía en 10 ms y reiniciaba pricing
  cada 100 ms. Ahora prueba decisiones con ejecución controlada y conserva la exigencia
  de óptimo. Las pruebas asíncronas siguen separadas. **Sin cambios a src/ev_routing,
  formulación ni dependencias respecto de main.**

## Reproducción

```sh
uv sync --locked --extra dw --group dev
uv run --locked --extra dw python -m pytest -q
node --test webapp/tests/*.test.mjs
uv run --locked --extra dw python -m backend.local_server --port 4310 \
  --graphml artifacts/network/competition_delivery.graphml --network-profile delivery
```

La red es un artefacto local ignorado; otro clon debe aportar su GraphML o prepararlo
según `docs/webapp-integration.md`. Las pruebas normales no descargan calles ni llaman
a AWS. Esta ola no repitió una invocación real de Bedrock: se conserva la integración
heredada y se prueban sus contratos/dobles, sin atribuirle mejoras medidas.

Los runners `run-panel.browser.mjs`, `run-export.browser.mjs`,
`location-editor.browser.mjs`, `location-navigation.browser.mjs` y
`experience.browser.mjs` admiten `PLAYWRIGHT_MODULE` y `ZMD_QA_ORIGIN`.
La experiencia puede reproducir un resultado real capturado; eso se distingue de
las pruebas HTTP con solver real. Evidencia madre en
`.local/full-integration-2026-10-16/`; panel en `.local/refined-panel/`.

Rama local `codex/features-implementation`. Sin push ni despliegue público.
