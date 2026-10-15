# Exploración de producto e identidad

**Feedback posterior, 15-10-2026:** Diego rechazó las cuatro interfaces y las treinta identidades: «no tienen nada que ver con el tema». Ninguna está seleccionada. Nueva ronda en `explorations/round-2/`, centrada en vehículos eléctricos, batería, entregas y recargas; la identidad vuelve a partir de ZMD y elementos eléctricos reconocibles. Se conserva lo anterior como historial descartado.


14-10-2026, Chile. Prototipos para elegir con Diego; **no son el frontend definitivo ni una integración con el motor**.

```sh
python3 -m http.server 4173 --bind 127.0.0.1 --directory explorations
```

Abrir `http://127.0.0.1:4173/`. HTML, CSS, JavaScript y SVG locales, sin instalación de dependencias de aplicación. Los prototipos funcionan sin solicitar recursos externos.

## Cuatro formas de trabajar

| Dirección | Interacción principal | Ventaja | Límite |
|---|---|---|---|
| Atlas | Mapa amplio, capas, selección e inspector persistente | Relacionar operación y lugares sin cambiar de página | Cuidar espacio de controles y acceso al detalle técnico |
| Cuaderno | Documento con escenario, recorridos desplegables y mapa vinculado | Lectura clara y explicación del resultado | Menos espacio para el mapa y mayor recorrido vertical |
| Secuencia | Preparar → revisar → explorar el plan, con contexto cartográfico | Orientación para primer uso y demostración | Más cambios de etapa para operación frecuente |
| Balance | Vehículos en paralelo, mapas y perfiles de batería | Comparar recorridos y revisar diferencias | Necesitará filtros cuando aumente la flota |

La recomendación histórica, retirada tras el rechazo de Diego, era **Atlas** como base por la centralidad del mapa, conservando la claridad de los detalles de Cuaderno. Es una propuesta: Diego puede escoger otra o combinar partes. No supone aprobar un stack.

Los ejemplos incluyen ocho entregas ficticias y dos vehículos. Las líneas son **esquemas**, no calles ni geometrías viales del motor. Las cifras no son medidas, optimizaciones, predicciones o pruebas de factibilidad. El modo parcial conserva entregas pendientes; sin resultado no significa infactibilidad probada. Un resultado obsoleto retira las cifras anteriores. Vacío no equivale a batería cero.

La exportación de Cuaderno/Balance usa `design-fixture-0`, marcada como sintética; no es el JSON del evaluador ni el contrato aprobado del backend.

## Identidad

La primera ronda conserva seis conceptos y 18 SVG en `identity/`. Tras el feedback de Diego —electromovilidad, eficiencia, ahorro y/o IA, priorizando minimalismo y muchas alternativas—, `identity-lab/` incorpora **24 conceptos nuevos y 72 SVG**.

La segunda comparativa ofrece filtros por significado, una preselección de seis, fondos claros/oscuros, tamaños de 20/32/64 px y detalle con firmas editables. Se pueden destacar propuestas; esa acción no publica ni aprueba una identidad. Los originales y sus riesgos permanecen disponibles.

Los SVG son vectores editables, sin raster incrustado ni recursos externos. Los logotipos usan texto editable con fuente de sistema; la tipografía final se fija al elegir. Las pruebas visuales no son una búsqueda de marcas registradas.

## Autoría y uso de modelos

Astra (`ultra`) integró contexto, contrato propuesto, Cuaderno, Balance y las galerías. Sol (`max`) investigó, diseñó las identidades, revisó y construyó los prototipos de respaldo Atlas/Secuencia.

Kiro verificó Opus 5.5 y Sonnet 5.5 con esfuerzo `max` mediante configuración y respuestas reales. Sonnet aportó microcopy y reglas de diagnóstico/obsolescencia. Las construcciones largas por Kiro fallaron y **no se les atribuyen los archivos de respaldo**. El estado final de sus aportes y sesiones está en [KIRO-Y-AGENTES](../docs/KIRO-Y-AGENTES.md).

## Comprobación y límites

Pruebas en Chrome local mediante Playwright, con movimiento reducido, escritorio y anchos de 768/390/320 px. Se revisaron controles, selección, variantes de resultado, exportación, diálogos y foco. Balance perdió foco al seleccionar por teclado; se corrigió y se volvió a comprobar. Se corrigió también el encuadre de las rutas para no recortar paradas.

Los logos se inspeccionaron a 20/32/80 px sobre ambos fondos. La galería de 24 se comprobó con filtros, detalle, descargas, selección y cambio de tamaño/fondo. Hubo ajustes de espacio negativo y de símbolos demasiado parecidos entre familias.

La evidencia estructurada se conserva en `docs/evidence/` y en las carpetas `qa/` de identidad. Son comprobaciones acotadas; no certifican accesibilidad completa, rendimiento del mapa real, consumo energético o solución del desafío. Esas pruebas corresponden a la implementación elegida y al motor real.

## Después de elegir

Construir una sola interfaz, conectarla a un ejemplo acordado del motor y añadir MapLibre con cartografía autorizada. La UI debe dibujar la geometría del mismo recorrido que respalda el balance energético; no sustituirla por una ruta nueva obtenida después de optimizar.

[Estado y handoff](../docs/ESTADO-Y-HANDOFF.md) · [contrato propuesto](../docs/contracts.md) · [investigación cartográfica](../docs/MAPA-Y-BASE.md).
