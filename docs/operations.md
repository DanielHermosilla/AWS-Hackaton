# Supuestos operacionales configurables

El backend vigente `scip-routes` conserva estas condiciones en sus rutas
factibles **sin H**. Usar `bash scripts/run_pptx.sh 60 none config/operations.example.json`.
Las secciones sobre H y los resultados Gurobi de este documento describen la
referencia posicional anterior; no condicionan el pricing vigente.

Implementación de (17)–(24) de `modelamiento.pdf`, cuya fuente es
`modelamiento.tex`. Se conserva el modelo base y el objetivo de entregas,
seguido por energía. No son nuevas reglas del concurso.

El escenario se guarda en `ProblemInstance.operations`. Al preparar con
`prepare --config` o `service-graph --config`, se toma esa sección del archivo.
`run --config` sigue usando solo `solver`, nunca cambia el problema preparado.
Las restricciones dependen de parámetros del problema, no de decisiones del LLM.

## Campos

Todos tienen valores neutros por defecto. Las unidades forman parte del nombre.

| Campo de `operations` | Default / desactivación | Efecto |
|---|---|---|
| `service_seconds` | `0` | Duración común por entrega. |
| `service_seconds_by_customer` | `{}` | Excepciones que reemplazan el valor común, por ID. |
| `max_route_seconds` | `null` | Duración máxima de cada vehículo, incluyendo viaje, servicio, carga y espera. |
| `assumed_speed_kph` | `null` | Velocidad explícitamente supuesta donde una calle carece de tiempo; no sustituye tiempos existentes. |
| `include_charging_time` | `false` | Vincula tiempo de recarga con energía y potencia. |
| `charging_power_kw` | `null` | Potencia efectiva del lado de la red, común a estaciones habilitadas. |
| `charging_power_kw_by_station` | `{}` | Excepciones por estación que reemplazan la potencia común. |
| `charging_efficiency` | `1` | Fracción de electricidad que entra a batería; 1 supone ausencia de pérdidas. |
| `final_reserve_soc` | `null` | Reserva adicional exclusivamente al regresar; no reemplaza la reserva durante el recorrido. |
| `energy_margin_fraction` | `0` | Margen sobre descargas nominales; no aumenta la regeneración acreditada. |
| `disabled_charger_ids` | `[]` | Prohíbe recargar en esas estaciones, permite atravesarlas. |
| `use_customer_time_windows` | `false` | Activa las ventanas y relojes. |
| `customer_time_windows` | `{}` | Por ID: `open_seconds` y `close_seconds`; ventana de entrega completa. |

Clientes sin una ventana configurada solo están sujetos a la jornada.
No es obligatorio utilizar ambos vehículos; una jornada puede hacer necesario
repartir entregas para cumplirlas todas.

### Dependencias y procedencia

- Cualquier bloque temporal exige `Arc.travel_time_seconds` o una velocidad
  asumida. En la preparación se suman los tiempos de las calles del camino fijo.
- Un escenario temporal con estaciones de carga habilitadas exige
  `include_charging_time=true`; no se permiten recargas instantáneas para
  cumplir una jornada. Si todas están deshabilitadas, no se necesita potencia.
- Con tiempo de recarga, cada estación habilitada necesita potencia común
  o una excepción. No se infiere de `max_power_kw`: ese campo es un máximo
  reportado de estación, no potencia por conector ni aceptación del vehículo.
  Tampoco se permite superar ese máximo cuando está informado.
- Ventanas activas requieren al menos una entrada y `max_route_seconds`
  finito, que proporciona cotas válidas para los relojes y sus grandes M.
- IDs desconocidos, valores negativos/no finitos, eficiencia fuera de `(0,1]`
  y ventanas invertidas se rechazan antes del solver.
- Si `final_reserve_soc` exige más batería que la inicial, incluso un vehículo
  sin entregas debe encontrar una recarga y regresar. No se relaja silenciosamente.

Las potencias y jornada son comunes a los vehículos homogéneos. No se modelan
curvas de carga, ocupación de puertos, colas, horarios de cargadores, capacidad de
paquetes, reabastecimiento ni consumo auxiliar durante servicio/espera.
Los tiempos de viaje son constantes por escenario. Las opciones no permiten
desactivar compatibilidad física, reserva durante el recorrido ni retorno.

## Modelo y validación

Sin ventanas, la jornada es una suma lineal por vehículo. No se crean relojes.
Con ventanas se añaden llegada e inicio de actividad, espera no negativa,
propagación temporal y apertura/cierre condicionados por `a`, no por `z`.
Las recargas temporizadas se desagregan por estación en variables continuas;
no se usa el producto bilineal entre recarga y ubicación.

La energía nominal permanece en `Arc.energy_kwh`; modelo, heurística,
validador y expansión aplican el margen una vez. Los arcos Dijkstra son no
negativos, así que el margen uniforme mantiene los caminos seleccionados.
Un margen del 10 % es un escenario, no una probabilidad de cumplimiento.

El resultado conserva las mismas rutas y recargas, con su calendario más
temprano. El validador independiente verifica los tiempos publicados, las
ventanas completas, la jornada, estaciones habilitadas y reserva final.
La expansión vuelve a comprobar energía, distancia y tiempo contra cada calle.

`operations` aparece en el JSON, junto con estos campos:

- Por parada: `arrival_seconds`, `service_start_seconds`, `departure_seconds`,
  `service_duration_seconds`, `charging_duration_seconds`, `travel_time_seconds`.
- Por vehículo: `duration_seconds`, desde salida común en 0 hasta retorno.
- KPIs: `operational_duration_seconds` es el máximo de duraciones;
  `total_vehicle_time_seconds` es su suma; `route_duration_seconds` las desglosa.
- `grid_energy_kwh` es la suma de cargas a batería dividida por eficiencia
  cuando se activa ese bloque. No se deduce electricidad comprada del consumo neto.
- Sin bloque temporal, sus campos son `null`. Ahorros y emisiones continúan
  en `null` sin referencias documentadas.

## H y solución inicial

Con jornada, ventanas o reserva final mayor que la reserva base, la prueba
actual de H queda fuera de sus hipótesis. `auto` escribe diagnóstico y se
detiene; no aplica la cota estructural anterior. Indicar un H explícito permite
un ensayo condicionado a ese valor. No se afirma que 21 o 30 sean suficientes
para el óptimo sin límite bajo las extensiones.

Una heurística greedy sin recargas puede obtener un arranque parcial,
distribuyendo entregas entre vehículos y validando cada inserción. No prueba
optimalidad ni H. Tiene un presupuesto blando de 0,5 s; método y tiempo quedan
registrados. Se comprueban las calles antes de enviar el arranque y se cargan
también las nuevas variables temporales de Gurobi. SCIP mantiene su limitación
documentada de warm start.

## Ejecución con el grafo completo

`config/operations.example.json` es un escenario ilustrativo, no calibrado:
5 minutos por entrega, jornada de 4 horas, velocidad asumida de 30 km/h donde
falta tiempo, potencia efectiva de 3 kW, eficiencia de 90 %, reserva final
15 % y margen energético 10 %. Las ventanas quedan desactivadas.

```bash
bash scripts/run_pptx.sh 60 30 config/operations.example.json
```

El tercer argumento es opcional. El segundo es H, no horas ni segundos.
Como antes, ejecutar el archivo mediante `bash`, sin `source` ni pegar su cuerpo
en una shell interactiva.

Para conservar el baseline, preparar y resolver en archivos distintos:

```bash
uv run --locked ev-routing service-graph \
  --road-instance artifacts/hackathon/instance.json \
  --config config/operations.example.json \
  --service-movements 30 \
  --output artifacts/operations/service-instance.json \
  --path-archive artifacts/operations/service-paths.json

uv run --locked ev-routing run \
  --instance artifacts/operations/service-instance.json \
  --road-instance artifacts/hackathon/instance.json \
  --path-archive artifacts/operations/service-paths.json \
  --initial-solution artifacts/operations/service-instance.start.json \
  --config config/operations.example.json \
  --output artifacts/operations/result.json
```

Después, para cambiar parámetros sin recalcular Dijkstra, añadir al primer
comando:

```text
--reuse-instance artifacts/operations/service-instance.json
--reuse-path-archive artifacts/operations/service-paths.json
```

Se puede escribir en otras rutas para conservar el escenario anterior.
Se validan las huellas antes de reutilizar; se regeneran tiempos derivados,
análisis de H, arranque y hashes. No se modifican la red ni los caminos.
En el script, `HACKATHON_REUSE_SERVICE_GRAPH=1` habilita la misma reutilización.

Los contratos anteriores no contenían los campos nuevos: regenerar los
artefactos una vez después de actualizar el código. No ignorar discrepancias
de hash ni reutilizar un arranque con otras opciones.

Ejemplo para activar una ventana real proporcionada por el cliente:

```json
{
  "use_customer_time_windows": true,
  "customer_time_windows": {
    "ID_DEL_CLIENTE": {"open_seconds": 1800, "close_seconds": 3600}
  }
}
```

Este fragmento se integra en `operations`, conservando jornada, viaje y recarga
válidos. Reemplazar el ID y horarios ilustrativos por datos del cliente.
El reloj es relativo al inicio de operación; `Timestamp` histórico no proporciona
estos horarios.

## Alcance

Solo se optimiza entre los caminos fijos precalculados. Una ruta de menor
energía puede ser demasiado lenta y no representamos todas sus alternativas
rápidas. Las opciones temporales no convierten el grafo contraído en una
reformulación exacta de toda la red vial.

`tests/test_operations.py` comprueba ambos backends, óptimos pequeños calculados
a mano, tiempo de recarga con pérdidas, ventanas y tránsito sin servicio,
reserva final, margen, validación de calendarios alterados, compatibilidad,
neutralidad de opciones desactivadas y reutilización de Dijkstra sin volver
a ejecutarlo.

## Verificación local del 15 de octubre de 2026

La suite completa pasó 459 pruebas, sin omisiones, incluyendo Gurobi y SCIP.
Ruff y la sintaxis del script también pasaron.

Se ejecutó la instancia completa de 81 servicios con el ejemplo de opciones,
H explícito de 21, Gurobi, dos threads y presupuesto blando de 20 segundos:

| Resultado | Valor |
|---|---|
| Entregas | 20/20; máximo probado en la variante |
| Reparto | 18 y 2 entregas |
| Energía del escenario, incluido margen 10 % | 12,238379 kWh |
| Gap energético | 11,5299 %; terminó por tiempo, no óptimo energético probado |
| Duración operacional máxima | 12.792,883 s, menor a 14.400 s |
| Batería mínima | 3,775911 kWh, superior a la reserva final exigida de 3,6 kWh |
| Recargas | Ninguna en esta corrida; duración de carga comprobada en pruebas sintéticas |
| Arranque inicial | 20 entregas, 19,364223 kWh, construcción en 0,070 s |
| Auditoría de servicios y calles | Factible, incluidos tiempos |
| Certificado automático de H | Desactivado por las extensiones |
| Tiempo del pipeline de resolución | 26,75 s; el presupuesto del solver es blando |

Artefactos locales: `artifacts/operations/summary.json`, `result.json`,
`service-instance.json`, `service-paths.json` y `solve.log`.
El log nativo confirma carga del MIP start en ambas fases. Esta corrida no
demuestra aceleración frente a otra configuración. La ruta vial expandida no
cabe en el H original de 200 calles; el resultado corresponde a H=21 servicios.
