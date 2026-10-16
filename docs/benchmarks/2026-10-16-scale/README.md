# Resultados recientes: standard frente a LLM, 200/400/800 clientes

Se publican **seis corridas terminadas el 16 de octubre de 2026**: una instancia
de cada tamaño, con dos políticas por instancia. Son resultados posteriores a la
[campaña nocturna](../../benchmark-results-2026-10-16.md); no se mezclan sus medias.
Esta publicación solo exporta mediciones existentes. No ejecuta nuevas corridas.

Cada par usa familia sintética `dispatch`, semilla de instancia 2001, semilla
del solver 0, dos vehículos, ocho cargadores, un hilo y **600 segundos por
corrida**. Las ventanas y recargas pertenecen a esas instancias sintéticas; no
son viajes observados de la hackatón. Ambos modos parten de `standard`, sin
piloto ni política fija seleccionada previamente. Los testigos no se entregaron
al solver ni al LLM.

## Resultados por corrida

| Clientes | Política | Entregas | Energía kWh | Gap energía % | Primera cobertura completa s | Solver s | Proceso s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 200 | standard | 200/200 | 60.64065 | 42.1524 | 16.318 | 600.017 | 604.650 |
| 200 | adaptive | 200/200 | 59.22745 | 25.2317 | 21.336 | 600.023 | 604.399 |
| 400 | standard | 400/400 | 84.77890 | 36.9751 | 184.544 | 600.142 | 604.590 |
| 400 | adaptive | 400/400 | 82.85557 | 35.5100 | 98.537 | 601.063 | 605.698 |
| 800 | standard | 452/800 | 108.07469 | 100.0000 | ND | 600.240 | 609.676 |
| 800 | adaptive | 586/800 | 142.07918 | 100.0000 | ND | 600.597 | 611.204 |

Las seis soluciones pasan la validación nativa y la expansión sobre las calles
de sus redes sintéticas. El presupuesto es blando; proceso incluye lectura,
resolución, validación y escritura, pero no la preparación previa de la red.
La primera cobertura completa es una observación del motor, no el tiempo de
finalización ni de prueba del óptimo energético.

## Comparación pareada

- **200 clientes:** ambos cumplen 200/200. El LLM reduce la energía en
  **1.413200 kWh (2.330451%)**, pero observa la primera cobertura completa más
  tarde: 21.336 s frente a 16.318 s.
- **400 clientes:** ambos cumplen 400/400. El LLM reduce la energía en
  **1.923338 kWh (2.268652%)**. Observa la primera cobertura completa en
  98.537 s frente a 184.544 s; ambos siguen buscando hasta aproximadamente 600 s.
- **800 clientes:** el LLM atiende **134 clientes adicionales**, 586 frente a
  452. Los conjuntos atendidos son distintos: la energía no permite afirmar un
  ahorro comparable. Ninguno completa las 800 entregas.

Los casos de 200 y 400 prueban el máximo de entregas por cardinalidad.
**Ninguna corrida alcanza el gap energético objetivo de 0,5% ni prueba energía
óptima.** En 800 tampoco se prueba el máximo de entregas: la cota es 800 para
ambos modos. Sus mejoras energéticas están condicionadas a las entregas
encontradas. Las terminaciones exactas y cotas de ambas fases permanecen en los
archivos `run-audit.json`.

Las tres corridas adaptativas registran cuatro llamadas y cuatro decisiones con
cambios de algoritmo cada una: **12 llamadas reales y 12 cambios en total**,
con `us.openai.gpt-5.6-luna` por Bedrock. Standard registra cero llamadas.
El tiempo de inferencia puede solaparse con la búsqueda y no debe sumarse al
tiempo del solver.

Hay una sola instancia por tamaño. No se calcula una mejora media general ni
se atribuyen las diferencias entre tamaños exclusivamente al número de clientes.
La instancia de 400 usó generador 2 y código con SHA-256
`76cedf9ad0f62f1623e41f8888817cb67167e91e3e9ff6fcbd0e84b32e243ab5`;
las de 200 y 800 usaron generador 3 y
`7c95330cffdf4708e67e06db73cfaff30c694acf91180fe6c0ce1c9f6ecd1f24`.
Dentro de cada par coinciden código, configuración física y hash de instancia.
Estas mediciones no certifican el comportamiento del `main` actualizado al
publicarlas.

## Archivos y procedencia

- [summary.csv](summary.csv): seis filas con métricas, fechas, hashes y validación.
- [200 clientes](n200/kpis.csv), [400 clientes](n400/kpis.csv) y
  [800 clientes](n800/kpis.csv): tablas originales completas, incluidos clientes
  atendidos, tiempos y uso del LLM.
- `n200/`, `n400/` y `n800/` incluyen las diferencias pareadas, agregados,
  manifiesto de ejecución, plan y procedencia del reporte. Los
  `run-audit.json` conservan fases, validaciones, KPIs nativos y SHA-256 de
  los resultados completos, sin copiar las redes ni las rutas masivas.
- [factors.json](factors.json) conserva los supuestos monetarios y ambientales
  aplicados a las tablas. Son estimaciones operacionales, no ahorros medidos en
  terreno. [factors-source.json](factors-source.json) es el archivo original
  cuyo hash figura en la procedencia; `factors.json` incluye sus valores
  normalizados y predeterminados.
- [export.json](export.json) registra archivos y hashes originales/publicados.
  [SHA256.json](SHA256.json) permite verificar todos los archivos de este
  directorio, excepto el propio manifiesto.

Solo se retira el prefijo absoluto del checkout de las copias y se normalizan
los finales de línea CSV a LF, sin cambiar sus valores. Los campos
`result_path` apuntan a originales locales dentro de `artifacts/`, que no se
publican. Los originales se verificaron contra sus archivos `execution.json`;
las cifras de las tablas se contrastaron con los resultados nativos. No se
modifican ni se recalculan esos resultados durante la exportación.
