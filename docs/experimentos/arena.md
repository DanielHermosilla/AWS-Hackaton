# Arena neutral: motores (evrp vs ev_routing) y solvers

Comparación sin editar el código de ningún motor. La arena materializa instancias
comunes, ejecuta cada motor, **revalida las rutas de forma independiente** sobre el
mismo grafo OSM y mide tiempos/energía. No declara ganador: presenta evidencia.

## Qué se hizo

1. **Esquema de escenario** (`arena/esquema_escenario.json`) + ejemplos en
   `arena/escenarios/`: `smoke.json`, `escala_clientes.json`, `flota.json`
   (y variantes cortas `escala_corta_ambos.json`, `escala_corta_evrp.json`,
   `flota_evrp.json` para correr en minutos).
2. **Adaptadores** (`arena/adaptadores/`):
   - `evrp_adaptador.py`: in-process vía `evrp.resolver` / `MotorEvrp`.
   - `ev_routing_adaptador.py` + `ev_routing_runner.py`: subproceso en el entorno del
     compañero (`uv run --project ... --with highspy==1.11.0`). El runner importa la API
     pública de `ev_routing` (`inputs`, `network`, `model`, `contracts`) y conduce la
     resolución lexicográfica en dos fases con **Pyomo + appsi_highs**, sin tocar su código.
3. **Validador neutral** (`arena/validador_neutral.py`): reconstruye la física desde las
   primitivas de evrp (`datos`, `red`, `energia`). Verifica inicio/fin en BASE, clientes
   únicos, cargadores compatibles, batería ≥ reserva tramo a tramo con saturación `min{B,·}`
   y recalcula energía con el mismo consumo. Admite rutas de nodos clave (expande con el
   camino de mínima energía de evrp) y rutas calle a calle (usa los tramos del motor).
4. **Competencia de solvers** (`arena/solvers.py`): exporta el MILP compacto de evrp a MPS
   con `highspy.writeModel` (construido vía `ModeloCompacto` sin modificar el archivo) y lo
   resuelve con HiGHS (highspy), SCIP (pyscipopt) y CBC (pulp).
5. **Runner CLI** (`python -m arena correr <escenario> --out <dir>`): escribe
   `resultados.jsonl`, `tabla_motores.csv` y `reporte.md`. Mide memoria pico con `tracemalloc`.
6. **Pruebas** `tests/test_arena.py` (9, rápidas, sin red): validador neutral, adaptador evrp,
   competencia de solvers y carga de esquema/escenarios.

Todas las corridas usan el **mismo mapa OSM empaquetado** de evrp
(`ann_arbor_drive.graphml.gz`), descomprimido una vez a `results/arena/.cache/osm/`.
Supuestos del perfil `ev_routing`: B=24 kWh, reserva 2.4, SoC 0.6, 0.1567712473 kWh/km.

## Evidencia

### Humo (`smoke.json`): 3 clientes de competition, ambos motores, 60 s

`uv run python -m arena correr arena/escenarios/smoke.json --out results/arena/smoke`

| motor | instancia | veh | entregas/clientes | energia_val_kwh | km | t_total_s | t_solver_s | gap | estado | factible_neutral |
|---|---|---|---|---|---|---|---|---|---|---|
| evrp | comp_c3 | 2 | 3/3 | 5.917 | 37.74 | 26.04 | 0.027 | 0 | ok | sí |
| ev_routing | comp_c3 | 2 | 0/3 | 0 | 0 | 101.6 | 85.24 | — | ok | sí |

Competencia de solvers sobre el MILP de evrp (misma instancia):

| fase | solver | estado | objetivo | cota | gap | tiempo_s | columnas | filas |
|---|---|---|---|---|---|---|---|---|
| entregas | highs | Optimal | 3 | 3 | 0 | 0.038 | 58 | 91 |
| entregas | scip | optimal | 3 | 3 | 0 | 0.015 | 58 | 91 |
| entregas | cbc | no_disponible | — | — | — | — | 58 | 91 |
| energia | highs | Optimal | 5.917 | 5.917 | 0 | 0.029 | 58 | 92 |
| energia | scip | optimal | 5.917 | 5.917 | 0 | 0.008 | 58 | 92 |
| energia | cbc | no_disponible | — | — | — | — | 58 | 92 |

El objetivo de energía del MPS (5.917 kWh) coincide con la energía validada del motor evrp:
el export a MPS reproduce el modelo que resuelve el motor.

### Escalamiento en clientes

Ambos motores (`escala_corta_ambos.json`, 60 s):

| motor | instancia | entregas/clientes | energia_val_kwh | km | t_total_s | t_solver_s | estado | factible_neutral |
|---|---|---|---|---|---|---|---|---|
| evrp | comp_c1 | 1/1 | 1.721 | 10.98 | 26.4 | 0.004 | ok | sí |
| ev_routing | comp_c1 | 0/1 | 0 | 0 | 119.7 | 103.6 | ok | sí |
| evrp | comp_c2 | 2/2 | 4.622 | 29.48 | 30.0 | 0.024 | ok | sí |
| ev_routing | comp_c2 | 0/2 | 0 | 0 | 123.6 | 107.4 | ok | sí |
| evrp | comp_c3 | 3/3 | 5.917 | 37.74 | 28.3 | 0.033 | ok | sí |
| ev_routing | comp_c3 | 0/3 | 0 | 0 | 114.3 | 98.1 | ok | sí |
| evrp | comp_c5 | 5/5 | 6.763 | 43.14 | 31.2 | 0.031 | ok | sí |
| ev_routing | comp_c5 | 0/5 | 0 | 0 | 112.7 | 97.3 | ok | sí |

Solo evrp a mayor escala (`escala_corta_evrp.json`, 120 s):

| motor | instancia | entregas/clientes | energia_val_kwh | km | t_total_s | t_solver_s | gap | estado | factible_neutral |
|---|---|---|---|---|---|---|---|---|---|
| evrp | comp_c20 | 20/20 | 11.152 | 71.14 | 35.2 | 0.443 | 0 | ok | sí |
| evrp | sint_c40 | 40/40 | 12.595 | 80.34 | 164.2 | 120.1 | 0.064 | ok | sí |

### Barrido de flota (`flota_evrp.json`, 5 clientes, 2..5 vehículos)

| vehiculos | entregas/clientes | energia_val_kwh | km | t_total_s | gap | estado | factible_neutral |
|---|---|---|---|---|---|---|---|
| 2 | 5/5 | 6.763 | 43.14 | 29.5 | 0 | ok | sí |
| 3 | 5/5 | 6.763 | 43.14 | 28.3 | 0 | ok | sí |
| 4 | 5/5 | 6.763 | 43.14 | 28.4 | 0 | ok | sí |
| 5 | 5/5 | 6.763 | 43.14 | 27.3 | 0 | ok | sí |

evrp usa solo los vehículos necesarios; añadir flota no cambia energía ni km.

## Lectura de la evidencia (sin ganador)

- **Modelos distintos, no solo solvers.** evrp contrae la red a caminos de mínima energía
  entre nodos clave: su MILP para 3 clientes tiene **58 columnas y 91 filas**. ev_routing
  modela la red vial completa indexada por posición con cota `H`: con el mapa empaquetado
  son **10.855 nodos y 25.738 arcos**, y variables `z[V,K,R]` ≈ 10.855·vehículos·(H+1).
- **ev_routing = 0 entregas** en todas las corridas con `H=10`: con una red tan grande, 10
  movimientos no alcanzan a ningún cliente (fase 1 demuestra óptimo = 0 entregas). Esto es un
  **resultado**, no un error de la arena: coincide con la advertencia del propio README del
  compañero (una `H` pequeña excluye entregas; aumentar `H` agranda el MILP). Su tiempo lo
  domina la **construcción del modelo Pyomo** (~85–107 s), no la resolución.
- Ambos conjuntos de rutas pasan el **validador neutral independiente** (la ruta vacía de
  ev_routing es trivialmente válida: no viola batería ni repite clientes).
- En la competencia de solvers, **HiGHS y SCIP** resuelven el MILP de evrp a óptimo con
  gap 0 en centésimas de segundo; **CBC no está disponible** (ver limitaciones).

## Limitaciones

- **CBC no disponible.** `pulp==4.0.1` no empaqueta un ejecutable CBC en esta plataforma
  (`COIN_CMD.available()` devuelve `None`, no hay `solverdir`). La arena lo registra como
  `no_disponible` en vez de fallar. Para habilitarlo haría falta un `cbc.exe` en PATH.
  Evidencia: `from pulp.apis import COIN_CMD; COIN_CMD().available()` → `None`.
- **SCIP para el modelo Pyomo del compañero.** Su `solve.py` usa el plugin Pyomo `scip`,
  que requiere el **ejecutable SCIP** (`.nl`), no instalado globalmente (`shutil.which('scip')`
  → `None`). El `pyscipopt` del grupo `arena` **no** sirve para ese plugin. Por eso el runner
  de ev_routing usa `appsi_highs`; se documenta que SCIP-vía-Pyomo quedó fuera por falta de
  ejecutable. (La competencia de solvers sí usa `pyscipopt` directamente sobre el MPS de evrp.)
- **Export a MPS del modelo Pyomo del compañero.** No se incluyó en la competencia: su modelo
  vive en otro entorno y su tamaño (decenas de miles de binarias con el mapa completo) hace el
  MPS poco comparable con el MILP contraído de evrp. Queda como próximo paso.
- **Accesos > 100 m.** El importador de ev_routing rechaza servicios a más de
  `max_snap_distance_m` (100 m) de la calle. En competition, V2 queda a 256.7 m. Para que
  ev_routing acepte la instancia oficial se usó `max_snap_distance_m=500` en los escenarios y
  queda **registrado**; con 100 m rechazaría la instancia.
- **Memoria.** `tracemalloc` mide solo asignaciones Python del proceso de la arena; para
  ev_routing (subproceso) marca ~0 MB porque el trabajo ocurre fuera del proceso medido.
- Tiempos medidos en una sola máquina Windows, 1 hilo, sin repeticiones múltiples.

## Cambios solicitados (a archivos que no me pertenecen)

- **Ninguno imprescindible.** No se modificó `pyproject.toml` ni el código de `evrp` ni de
  `ev_routing`. `tests/test_arena.py` inserta la raíz del repo en `sys.path` para importar el
  paquete `arena` (que no está declarado como paquete instalable en `pyproject.toml`). Si se
  desea instalar `arena` como paquete, habría que añadirlo en
  `[tool.hatch.build.targets.wheel].packages` de `pyproject.toml` (archivo no propio): **cambio
  solicitado, opcional**.

## Próximos pasos

- Exportar el modelo Pyomo del compañero a MPS (`model.write(...)` de Pyomo) desde el runner
  externo y sumarlo a la competencia de solvers, para comparar los dos MILP sobre el mismo backend.
- Dar a ev_routing una oportunidad real de entregar: construir su instancia sobre un **subgrafo
  acotado** (bbox alrededor de los nodos) en vez del mapa completo, o barrer `H` crecientes
  midiendo el crecimiento del MILP vs. entregas logradas.
- Añadir `repeticiones>1` para reportar variabilidad de tiempos (mediana/IQR).
- Habilitar CBC con un `cbc.exe` fijado y SCIP-vía-Pyomo con el ejecutable, para completar la matriz.
