# Arena SCIP: comparación justa evrp (HiGHS) vs ev_routing (flujo propio + SCIP)

Segunda arena, corrigiendo lo señalado en `arena.md`. Objetivo: comparar el motor del
compañero usando **su propio flujo de resolución** (`ev_routing.solve.solve_instance` con
`SolverConfig(solver='scip')`, **sin Gurobi**, sin reimplementar su lógica lexicográfica)
contra el motor `evrp` (HiGHS), sobre instancias de `competition`, con un **validador
neutral independiente de ambos motores**. No se declara ganador: se presenta evidencia
medida con comandos reales. No se editó código de `evrp` ni de `ev_routing`.

## Qué se hizo

1. **SCIP real por el flujo del compañero.** `arena/adaptadores/ev_routing_runner.py`
   gana el modo `--flujo-companero --solver scip`: construye la instancia con
   `build_osm_instance` y llama **`solve_instance(instance, SolverConfig(solver='scip', …))`**
   tal cual. SCIP 9.2.4 se detecta vía el plugin Pyomo `SCIPAMPL` agregando
   `…\scip-9.2.4\bin` al **PATH solo del subproceso** del compañero (nunca global). Verificado:
   `SolverFactory('scip').available()` → `True`, `version` → `9.2.4.0`.
2. **Barrido H ∈ {30, 60, 100}** (su default es H=30), vehículos=2, semilla 0, 1 hilo,
   `relative_gap=0`.
3. **Validador neutral INDEPENDIENTE** (`arena/validador_osm.py`): lee el **mismo GraphML**
   con networkx (sin importar `evrp` ni `ev_routing`), snapea cada servicio a su intersección
   más cercana (haversine), calcula energía por el **camino vial de mínima longitud** y simula
   batería con saturación `min{B,·}`, piso de reserva y recarga a `B` en cargadores
   compatibles. Valida rutas de **cualquier** motor.
4. **`max_snap_distance_m`**: se registra el mínimo que acepta cada instancia (ver tabla).
5. **Orquestador** `arena/scip_arena.py` + CLI `uv run python -m arena scip`. Materializa
   subconjuntos de `competition`, recorta un **subgrafo OSM simétrico** por bbox (mismo grafo
   para el compañero y el validador neutral), corre ambos motores y escribe
   `results/arena_scip/{tabla.md,resultados.jsonl,snaps.json}`.
6. **Pruebas** `tests/test_arena.py` (15, rápidas, sin red): nuevas para el validador OSM
   (factible, cliente repetido, cargador incompatible, no-inicia-en-base), subset de
   cargadores y wiring de `scip_arena`. `uv run pytest -q -m "not bedrock"` → **145 passed**.

Supuestos idénticos para ambos (perfil `ev_routing`): B=24 kWh, reserva 2.4, SoC 0.6,
0.1567712473 kWh/km, conectores {CHADEMO, J1772}.

## Evidencia (comando: `uv run python -m arena scip --hs 30 60 100 --instancias c1 c2 c3 c5`)

Clientes de `competition`: c1={V5}, c2={V5,V15}, c3={V5,V15,V13}, c5={V5,V15,V13,V16,V11}.
evrp corre sobre el mapa completo; ev_routing sobre el subgrafo acotado (su mejor
oportunidad) con un **subconjunto de 5 cargadores cercanos** (ver limitación de snap).

| motor | solver | H | inst | entregas/clientes | energía_val_kwh (neutral) | km | t_constr_s | t_solver_s | gap | estado | factible_neutral |
|---|---|---|---|---|---|---|---|---|---|---|---|
| evrp | highs | — | c1 | 1/1 | 1.007 | 6.42 | — | 0.016 | 0 | ok | sí |
| ev_routing | scip | 30 | c1 | 0/1 | 0 | 0 | 0.65 | 42.5 | — | time_limit | sí |
| ev_routing | scip | 60 | c1 | 0/1 | 0 | 0 | 0.71 | 49.6 | — | time_limit | sí |
| ev_routing | scip | 100 | c1 | 0/1 | 0 | 0 | 0.66 | 55.2 | — | time_limit | sí |
| evrp | highs | — | c2 | 2/2 | 2.985 | 19.04 | — | 0.023 | 0 | ok | sí |
| ev_routing | scip | 30 | c2 | 0/2 | 0 | 0 | 1.04 | 50.3 | — | time_limit | sí |
| ev_routing | scip | 60 | c2 | 0/2 | 0 | 0 | 1.07 | 69.6 | — | time_limit | sí |
| ev_routing | scip | 100 | c2 | 0/2 | 0 | 0 | 1.10 | 99.5 | — | time_limit | sí |
| evrp | highs | — | c3 | 3/3 | 2.991 | 19.08 | — | 0.026 | 0 | ok | sí |
| ev_routing | scip | 30 | c3 | 0/3 | 0 | 0 | 1.00 | 48.0 | — | time_limit | sí |
| ev_routing | scip | 60 | c3 | 0/3 | 0 | 0 | 0.94 | 65.7 | — | time_limit | sí |
| ev_routing | scip | 100 | c3 | 0/3 | 0 | 0 | 1.24 | 89.3 | — | time_limit | sí |
| evrp | highs | — | c5 | 5/5 | 3.614 | 23.06 | — | 0.306 | 0 | ok | sí |
| ev_routing | scip | 30 | c5 | 0/5 | 0 | 0 | 1.82 | 55.6 | — | time_limit | sí |
| ev_routing | scip | 60 | c5 | 0/5 | 0 | 0 | 1.12 | 69.6 | — | time_limit | sí |
| ev_routing | scip | 100 | c5 | 0/5 | 0 | 0 | 1.13 | 95.9 | — | time_limit | sí |

Notas de la tabla:
- `energía_val_kwh` y `km` son **recalculados por el validador neutral** (networkx + CSV),
  no por el motor. Para evrp coincide muy de cerca con su propia energía (c5: motor 3.607 vs
  neutral 3.614 kWh; la pequeña diferencia es por caminos de mínima-energía de evrp vs
  mínima-longitud del validador neutral).
- ev_routing devuelve **ruta vacía** (0 entregas) en todos los H: una ruta vacía es
  **trivialmente factible** para el validador neutral (no viola batería ni repite clientes),
  por eso `factible_neutral = sí`. El estado del solver es `time_limit`: SCIP **no encontró
  ningún incumbente** en la fase 1 (max entregas) dentro del presupuesto.
- SCIP confirmado: `solver_usado=scip`, `solver_version=9.2.4.0` en todos los JSON de
  `results/arena_scip/ev_routing/`.

### `max_snap_distance_m` por instancia

| inst | subset_cargadores | acceso_base+clientes_m | acceso_subset_m | snap_usado_m | acceso_TODOS_cargadores_m | default_100m_acepta_todos | subgrafo_nodos | subgrafo_arcos |
|---|---|---|---|---|---|---|---|---|
| c1 | 5 | 79.4 | 82.8 | 83.8 | 415.8 | **no** | 780 | 2042 |
| c2 | 5 | 79.4 | 82.8 | 83.8 | 415.8 | **no** | 1846 | 4780 |
| c3 | 5 | 79.4 | 82.8 | 83.8 | 415.8 | **no** | 1628 | 4188 |
| c5 | 5 | 79.4 | 148 | 149 | 415.8 | **no** | 2216 | 5756 |

- El **default 100 m rechaza la instancia oficial con los 62 cargadores**: C7 queda a
  **415.8 m** de la calle (también C19 a 399.9 m, C14 294 m, C22 292.4 m). El `max_snap`
  mínimo que acepta **todos** los cargadores es **≈ 416 m**.
- Si solo se exige base + clientes, basta **79.4 m** (V5 es el más alejado).
- Con el **subconjunto de 5 cargadores cercanos** usado para dar oportunidad al compañero,
  el mínimo baja a **82.8 m** (c1–c3) y **148 m** (c5, por C53/C55 algo más lejanos).
- Comparación con la arena previa: aquí el mapa es el mismo (`ann_arbor_drive`) y la base
  está en el sur (Briarwood), por lo que el cliente problemático de la primera arena (V2/V8)
  no está en estos subconjuntos; el patrón se reproduce con otros cargadores lejanos.

## Lectura de la evidencia (sin ganador)

- **Es una diferencia de modelo, no solo de solver.** evrp contrae la red a caminos de
  mínima energía entre nodos clave y resuelve un MILP pequeño con HiGHS a óptimo (gap 0) en
  centésimas de segundo. ev_routing indexa la red vial completa por **posición** con cota H:
  su MILP tiene ≈ `nodos_red · vehículos · (H+1)` binarias (p.ej. c5/H=100 sobre 2216 nodos
  ≈ 4.5·10⁵ binarias).
- **H cuenta segmentos elementales, no distancia.** El GraphML empaquetado es **no
  simplificado**: una "calle" = un segmento OSM corto. Medido con el validador neutral, ir de
  BASE a V5 cuesta **27 saltos** (34 por el camino de mínima longitud); el viaje redondo
  BASE→V5→BASE son ~54–68 saltos. Por eso **H=30 ni siquiera puede alcanzar y volver** del
  cliente; H=100 sí tendría saltos suficientes para V5, pero el MILP resultante es demasiado
  grande para que SCIP halle un incumbente en el presupuesto.
- **Resultado, no error de la arena.** SCIP (vía el flujo del compañero) termina en
  `time_limit` **sin incumbente** en fase 1 para todo H ∈ {30,60,100} y toda instancia 1–5
  clientes, incluso dándole un subgrafo acotado y hasta ~100 s de solver. Coincide con la
  advertencia del propio README del compañero (una H pequeña excluye entregas; subirla agranda
  el MILP). La construcción del modelo es rápida (<2 s en el subgrafo); el cuello es el solver.
- Ambos conjuntos de rutas pasan el **validador neutral independiente** (la ruta vacía de
  ev_routing es trivialmente válida).

## Cruce con el validador del compañero

Se intentó validar las rutas de evrp con `ev_routing.validation.validate_solution`. **Su API
no lo permite directamente**: exige un `Solution` con `routes[].steps` de **H+1 posiciones**,
cada una con `battery_arrival/departure`, `charged_to_battery` y energías de arco **referidas
a los nodos/arcos de su propia red** (`osm:<id>` + accesos). Las rutas de evrp están en nodos
clave sobre su red **contraída** (otros arcos), de modo que no se pueden mapear a un `Solution`
válido sin reimplementar la expansión calle-a-calle de ev_routing. Por eso el **piso común**
es el validador neutral de `arena/`, que recalcula batería/energía sobre el **mismo GraphML**
para ambos motores sin confiar en ninguno. (Su `validate_solution` sí se usa internamente en
su propio flujo sobre sus propias soluciones.)

## Limitaciones

- **ev_routing = 0 entregas con SCIP** en 1–5 clientes y H ∈ {30,60,100}. No es porque SCIP
  sea débil, sino por el tamaño del MILP posicional sobre una red no simplificada. No se probó
  H ≫ 100 (el MILP crece linealmente en H y empeora).
- **Subgrafo acotado y subconjunto de cargadores** para el compañero: reducción **simétrica**
  (mismo grafo para el validador neutral) y 5 cargadores cercanos, documentada para darle su
  mejor oportunidad. Con el mapa completo (10.797 nodos) la fase 1 también agota el tiempo con
  0 incumbente (verificado para c1/H=30 y H=100).
- **Instancia de 20 clientes**: no se corrió el barrido completo del compañero; dado que ni 1
  cliente entrega en el presupuesto, 20 clientes solo multiplicaría los `time_limit`. evrp sí
  escala 20 clientes (ver `arena.md`, 20/20 en ~0.4 s de solver).
- **Límite de tiempo de SCIP (SCIPAMPL) es blando**: el round-trip AMPL (`.nl`/`.sol`) y la
  carga del modelo hacen que `t_solver_s` supere algo el presupuesto (p.ej. 99.5 s con
  presupuesto 50 s en fase 2 cuando la fase 1 ya consumió su parte). Se mide el tiempo real.
- Tiempos en una sola máquina Windows, 1 hilo, sin repeticiones múltiples. La energía neutral
  usa caminos de mínima longitud (no de mínima energía), por eso difiere levemente de la de
  cada motor.

## Cambios solicitados (a archivos que no me pertenecen)

- **Ninguno imprescindible.** No se tocó `pyproject.toml`, ni `evrp`, ni `ev_routing`, ni el
  repo externo. Dependencias usadas: `networkx` (ya presente), `pyscipopt==6.3.0` (grupo
  `arena`, para la competencia de solvers previa) y el **ejecutable SCIP** del subproceso.
  `tests/test_arena.py` inserta la raíz en `sys.path` para importar `arena`.
- Opcional (ya anotado en `arena.md`): declarar `arena` como paquete instalable en
  `[tool.hatch.build.targets.wheel].packages` de `pyproject.toml` si se quisiera instalar en
  vez de usar `sys.path`.

## Reproducir

```powershell
# (SCIP se agrega al PATH solo del subproceso automaticamente por el orquestador)
uv run python -m arena scip --out results/arena_scip `
  --presupuesto-companero 50 --presupuesto-evrp 60 --hs 30 60 100 --instancias c1 c2 c3 c5
uv run pytest -q -m "not bedrock"   # 145 passed
```
