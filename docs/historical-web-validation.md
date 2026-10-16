# Históricos y casos de la hackatón en la web

Validación local del 16 de octubre de 2026 sobre `master`, base `bc4609e` y
los cambios de esta entrega. Los CSV y la red originales permanecen ignorados.

La interfaz carga ubicaciones e histórico EV local en un paso. También carga las
ubicaciones de la hackatón cuando se adjunta un histórico válido sin instancia.
Permite elegir `competition` o `evaluation`, cargar ubicaciones propias y
modificar flota, batería y margen de consumo antes de preparar. Las variantes
seleccionan servicios originales o añaden puntos sobre calles conectadas de la
misma zona; no infieren demanda de los trayectos históricos. El mapa conserva
Ann Arbor y el estilo ya existente del ejemplo.

## Comprobaciones con datos locales

Se enviaron **300.186.836 bytes** de CSV con un cliente HTTP Python. La normalización
aceptó las **170.000 filas** del archivo sintético de prueba. Las pruebas JS verifican
por separado que el navegador envía el `File` directamente, sin convertirlo a texto.
CSV admite hasta 4 GiB y veinte millones de muestras; JSON
conserva 256 MiB porque se materializa para validar su estructura. El lector CSV
selecciona solo columnas necesarias. No se garantiza memoria constante durante
la normalización y ordenamiento de todas las muestras.

Se cargó `competition_routing_nodes.csv`: **81 servicios**, con depósito en
**42.27708, −83.76281**, Ann Arbor, Michigan. Se usó la red local
`artifacts/network/competition_delivery.graphml` sin descargas.

Dos ejecuciones completas usaron el mismo pipeline web, política estándar,
semilla 0, presupuesto solver de 5 s y gap energético 0,005. Supuestos:
2 vehículos, SoC 60 %, capacidad útil 24 kWh, reserva 2,4 kWh y respaldo
0,2 kWh/km. Estos parámetros físicos siguen siendo editables.

| Entrada energética | Entregas | Energía, kWh | Comprobación vial |
|---|---:|---:|---|
| Consumo supuesto | 20/20 | 13,516047 | Aprobada |
| Histórico EV completo | 20/20 | 13,530784 | Aprobada |

El histórico eléctrico contiene **476.308 muestras de 504 viajes** y calibró
**5.347 tramos dirigidos**. Los demás mantienen el consumo supuesto. Los dos
valores energéticos corresponden a estimaciones físicas diferentes; esta tabla
no demuestra mejora ni deterioro del algoritmo. Ambas corridas probaron el máximo
de entregas; ninguna probó óptimo energético exacto. La primera terminó por
tolerancia energética y la segunda con pricing incompleto y cota válida.
No se hicieron llamadas AWS en estos ensayos.

La evidencia detallada local está en
`artifacts/hackathon-ui-qa/live-audit.json`; los resultados expiran al reiniciar
el servidor.

## Carga directa y simulación sobre el mismo histórico

Se verificó `POST /scenarios/hackathon` sin subir archivos desde el navegador:
cargó los 81 servicios y el histórico EV completo en 1,11 s en esta máquina.
Se creó una variante reproducible con semilla 17, **25 clientes y 65 cargadores**,
conservando el depósito y el identificador del histórico. Las diez ubicaciones
adicionales pertenecen a calles conectadas de Ann Arbor. Su generación demoró
11,42 s; la preparación energética y vial completa demoró unos 48–50 s por caso.
Estos tiempos de preparación son independientes del presupuesto del solver.

Se ejecutaron dos cálculos adicionales con política estándar, presupuesto
solver de 5 s, semilla de búsqueda 0 y gap energético 0,005:

| Caso con histórico EV | Flota y batería | Margen | Entregas | Energía, kWh | Calles y batería |
|---|---|---:|---:|---:|---|
| Original: 20 clientes, 60 cargadores | 2 vehículos, 24 kWh, SoC 60 %, reserva 2,4 kWh | 0 % | 20/20 | 13,530784 | Aprobadas |
| Variante: 25 clientes, 65 cargadores | 3 vehículos, 30 kWh, SoC 70 %, reserva 3 kWh | 15 % | 25/25 | 17,877058 | Aprobadas |

Los escenarios tienen demanda y parámetros distintos: la tabla no mide una
mejora energética entre ellos. Ambos probaron el máximo de entregas. El original
terminó con pricing incompleto y cota válida; la variante cerró energía mediante
una ruta validada y la cota de relajación (diferencia de 5,78e-8 kWh), dentro de
las tolerancias numéricas del motor y del modelo resuelto. No se consultó AWS.
La evidencia está en `artifacts/hackathon-ui-qa/variant-audit.json`.

## Pruebas reproducibles sin datos privados

En la revisión final pasaron **279 pruebas Python y 27 subpruebas**, y
**160 pruebas JS**:

```sh
uv run --locked --extra dw pytest -q tests/test_historical_web.py tests/test_historical_energy.py tests/test_web_bridge.py tests/test_simulation.py tests/test_operations.py tests/test_network.py tests/test_history_interpretation.py tests/test_bedrock_history_session.py tests/test_integrated_webapp.py tests/test_refined_web_input.py
node --test webapp/tests/*.test.mjs
```

Las pruebas Python de históricos, interpretación, API y preparación vial verifican
integración temporal, signos, clasificación EV, límites, carga interrumpida,
conservación de campos, reutilización del histórico, simulación reproducible,
rechazo de cantidades imposibles y lectura de casos desde CSV temporales. La suite JS
verifica límites de selección y transporte, entre otros contratos de la interfaz.

`webapp/tests/hackathon-history.browser.mjs` comprueba con respuestas HTTP
simuladas: carga de histórico sin instancia, conservación de cambios de flota
durante la carga, referencia energética enviada a `/prepare`, recuperación del
borrador, retiro del histórico, coordenadas de Ann Arbor, selector de evaluación,
carga directa del caso, variantes y margen de consumo.
Se revisaron capturas de escritorio y móvil. La regresión
`webapp/tests/history-panel.browser.mjs` cubre además AWS, protección de JSON
nativo y navegación. Estas pruebas de navegador no acreditan acceso AWS.

Con el servidor y los datos reales, `artifacts/hackathon-ui-qa/variant_map.mjs`
comprobó también los botones de carga y creación de variante sin respuestas
simuladas. El mapa del resultado muestra 25 entregas, tres vehículos, 65 cargadores
y el depósito en Ann Arbor, con la etiqueta «Simulación sobre el caso histórico».
Se revisaron las capturas `historical-variant-live.png` y
`ann-arbor-variant-live-map.png` del mismo directorio.
