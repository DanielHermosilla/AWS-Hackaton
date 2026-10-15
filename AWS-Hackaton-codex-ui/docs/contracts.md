# Frontera UI–motor: propuesta para acordar

14-10-2026. Aplicación de `zmd-contract` al encargo de Diego. **Documento propuesto; no existe todavía un contrato implementado, API verificada ni aceptación de Daniel/Lucas.** El detalle normativo del motor sigue en AGENTS/PDF; esta frontera no lo sustituye.

## Primero un ejemplo real

El siguiente paso con el motor es recibir una instancia, una salida y el comando o callable que las conecta. No se exige REST ni un servicio nuevo. JSON por archivo basta para integrar el primer recorrido si ese es el formato disponible.

La interfaz normaliza entrada para presentarla y muestra resultados del proveedor. No construye restricciones, recalcula energía o decide factibilidad. Un adapter local permite reemplazar una fixture por la salida real sin cambiar cada componente.

## Campos que hacen falta para presentar correctamente

| Grupo | Mínimo y semántica |
|---|---|
| Identidad | `schema_version`, `scenario_id`/hash de entrada, `run_id`, hash de configuración. IDs opacos como strings; no números de fila. |
| Entrada | Nodos `base/visit/charger`, coordenadas y campos CSV; flota y parámetros explícitos no incluidos en el CSV. Datos inválidos conservan su registro y error. |
| Ejecución | Estado del solver y motivo separados del estado del comprobador. Límite con incumbente, límite sin solución, infactibilidad probada y error son diferentes. |
| Cobertura | Entregas realizadas, total e IDs pendientes. No deducir entregas de cada nodo por el que pasa una ruta. |
| Itinerario | `vehicle_id`, pasos ordenados con ID propio (un nodo puede repetirse), nodo/arco, acción de entrega o recarga, batería de llegada y salida en kWh. |
| Energía | Consumo por tramo y total con definición. Separar consumo neto efectivo de batería, energía añadida a batería y electricidad de red. Porcentajes solo con escala/capacidad documentadas. |
| Geometría | GeoJSON `[longitude, latitude]` o arcos del motor, procedencia e identidad de red. Ausencia explícita: esquema, no ruta conducible. Un servicio externo no altera silenciosamente las calles seleccionadas. |
| Comprobador | Estado, violaciones y alcance de validación; mínimo energético del perfil completo. Desconocido no equivale a cero ni a válido. |
| Evidencia | Fases del solver con sentido, incumbente, cota/gap, terminación y tiempo; supuestos y límites H/red/energía. No inventar un único gap de fases incompatibles. |
| Tiempos y tuning | Solver y total distintos; estado aplicado/rechazado/fallback de Bedrock; región/modelo cuando existan. Costos y tokens desconocidos como `null` con razón. |
| Procedencia | `synthetic`, medido, calculado o supuesto; origen y fecha/versiones. La UI conserva esas distinciones. |

## Reglas de interacción

- Cambiar el escenario o parámetros invalida el resultado visible como actual. Una respuesta vieja no reemplaza la última ejecución.
- Cero es un valor válido. Datos faltantes usan `null` y motivo, no cero, `NaN` ni infinito.
- Un resultado parcial puede ser útil para diagnosticar; no satisface el objetivo de cobertura completa de Diego.
- La UI no impone reserva de 10–15 % ni resuelve por sí sola `b>0` frente a llegada ≥0.
- Coordenadas fuera de rango, no finitas o de orden ambiguo producen mensajes accionables. No ocultar visitas inválidas al graficar.
- Una estación del catálogo no se muestra como disponible en vivo. Coincidencia de conectores se identifica con su alcance real.
- Sin geometría exacta, mostrar lista y, si aporta, esquema explícito. No solicitar rutas a otro proveedor para acreditar energía del motor.

## Fixture de exploración

Las propuestas actuales usan `explorations/shared/demo.js` y/o fixtures autocontenidas. No son una implementación de `RunResult`: son datos de composición e interacción con ocho destinos ficticios, dos vehículos y estados completo/parcial/sin resultado. El JSON exportado lleva versión `design-fixture-0` y advertencia explícita; no está destinado al evaluador.

Antes del producto se reemplaza o adapta ese formato a un ejemplo acordado. No se construyen generadores, repositorios genéricos ni múltiples backends alrededor de una fixture de diseño.

## Pendientes con responsables

Daniel/Lucas: salida y ejecución reales, decisiones de reserva/cobertura, capacidad y modelo energético, formato/procedencia de geometría y alcance del comprobador. Diego/equipo UI: composición elegida, validación visible y consumo del contrato. Un integrador acordado mantiene una sola definición compartida.
