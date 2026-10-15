# Experimento ESCALA — escalar el motor E-VRP a 100 clientes

Agente: ESCALA. Rama `exp/escala`. Objetivo: soportar hasta 100 clientes y 2–5
vehículos con tiempo total < 60 s (ideal < 30, mejor < 15) sin perder calidad a
20 clientes (óptimo probado: competition ≈ 11.15 kWh, perfil `eved`, OSM).

Todas las mediciones usan instancias sintéticas
`evrp.sintetico.generar(N, semilla, 'data/competition_routing_nodes.csv')`, perfil
`ev_routing`, red **OSM empaquetada**. Script: `experimentos/escala/bench.py` (separa
tiempos red/heurística/MILP). Entorno: `uv sync --extra ia --all-groups`, Python 3.12.

## Qué hice

1. **Línea base medida** (`baseline_s1.json`): confirmé que el MILP ignoraba el
   presupuesto (40 c alcanzaban 67–92 s de total) y que, a partir de 40 clientes, el
   MILP **no mejora el arranque heurístico** dentro de los 60 s (la energía final =
   energía de la heurística; el `gap` reportado es contra la cota dual, no una mejora).

2. **2-opt del tour gigante acelerado** (`heuristica.py`): reescribí el 2-opt de
   O(n³) (recalculaba el costo completo dentro del doble bucle) a **evaluación
   incremental O(n²)** (delta de las 2 aristas que cambian) + tope de tiempo
   configurable. Resultado idéntico; solo acelera. La suite de tests bajó de ~89 s a
   ~38 s por este cambio.

3. **Poda k-vecinos de arcos cliente→cliente** (`instancia.py`,
   `_podar_k_vecinos`): por cada cliente conserva solo sus `k` arcos de menor energía
   (entrantes y salientes); conserva siempre base/cargadores/fin. Es **heurística
   (puede perder el óptimo exacto)**, por eso es **opcional y configurable**
   (`escala.k_vecinos`, por defecto 0 = desactivada). Reduce el modelo ~40 % y, con
   presupuesto suficiente, mejora la calidad porque el MILP explora un modelo más
   compacto.

4. **Presupuesto de reloj total** (`bench.py` + `milp_compacto._presupuesto_adaptativo`):
   el MILP recibe `total − (tiempo_red + tiempo_heurística) − margen`, con un piso
   `escala.min_s`. Así el **tiempo total** queda acotado (antes solo se acotaba el MILP).
   Para instancias pequeñas (≤ 25 clientes) se mantiene el presupuesto completo para no
   degradar el óptimo probado.

5. **Parámetros HiGHS configurables** (`milp_compacto.py`): `escala.mip_heuristic_effort`
   y `escala.presolve` se leen de forma defensiva (ausentes = valores por defecto de HiGHS).

Las claves nuevas se leen con `cfg...get('clave', defecto)` dentro de mis archivos; **no
edité** `config.py`, `pipeline.py`, `api.py`, `red.py` ni `asesor.py`.

## Evidencia

### Línea base vs. mejorado (semilla 1, perfil ev_routing, OSM)

Mejorado = `k_vecinos=10`, `--total 55`. Línea base = `k=0`, `tiempo_limite_s=60`.
Comando: `uv run python experimentos/escala/bench.py ... --salida ...`;
resumen con `uv run python experimentos/escala/resumen.py`.

| cli × veh | base: t(s) | base: E(kWh) | base: gap | mej: t(s) | mej: E(kWh) | mej: gap | ΔE |
|-----------|-----------:|-------------:|----------:|----------:|------------:|---------:|----:|
| 20 × 2 | 24.0 | 9.722 | 0.000 | 27.1 | 9.722 | 0.000 | +0.00% |
| 20 × 3 | 23.3 | 9.722 | 0.000 | 20.0 | 9.722 | 0.000 | +0.00% |
| 20 × 5 | 30.2 | 9.722 | 0.000 | 20.3 | 9.722 | 0.000 | +0.00% |
| 40 × 2 | 67.7 | 12.595 | 0.064 | 52.9 | **12.513** | 0.052 | −0.65% |
| 40 × 3 | 67.1 | 12.595 | 0.064 | 52.9 | **12.513** | 0.052 | −0.65% |
| 40 × 5 | 68.0 | 12.595 | 0.064 | 52.8 | **12.513** | 0.052 | −0.65% |
| 60 × 2 | 71.7 | 16.369 | 0.068 | 54.1 | 16.492 | 0.075 | +0.76% |
| 60 × 3 | 74.2 | 16.369 | 0.070 | 53.8 | 16.876 | 0.096 | +3.10% |
| 60 × 5 | 74.4 | 16.369 | 0.068 | 54.1 | 16.876 | 0.096 | +3.10% |
| 80 × 2 | 76.6 | 20.971 | 0.136 | 55.2 | **20.473** | 0.111 | −2.38% |
| 80 × 3 | 80.7 | 20.971 | 0.135 | 55.0 | **20.473** | 0.111 | −2.38% |
| 80 × 5 | 76.7 | 20.971 | 0.135 | 55.0 | **20.473** | 0.111 | −2.38% |
| 100 × 2 | 88.4 | 21.426 | 0.083 | 56.6 | **21.345** | 0.084 | −0.38% |
| 100 × 3 | 92.4 | 21.426 | 0.083 | 57.1 | **21.345** | 0.084 | −0.38% |
| 100 × 5 | 92.2 | 21.426 | 0.083 | 56.6 | **21.345** | 0.084 | −0.38% |

Todas las filas: **factible, 100 % de entregas**. El mejorado deja **todo < 60 s**
(la base superaba 60 s desde 40 clientes) con energía igual o mejor en 4 de 5 tamaños.
A 20 clientes la energía se mantiene idéntica (9.722, gap 0 = óptimo).

Robustez (semillas 2–3, 2 veh, `after_s23.json`): todas factibles, 100 % entregas,
52–57 s; el MILP mejora la heurística en varias celdas (p. ej. 40 c s2: 12.11 → 11.64;
60 c s2: 16.23 → 15.44).

### Máximo de clientes por umbral de tiempo total (semilla 1, 2 veh, k=10)

Medido con `--total {15,30,55}`; archivos `after_t15.json`, `after_t30.json`, `after_s1.json`.

| Umbral | Clientes que caben (todos factibles, 100 % entregas) | Nota |
|--------|------------------------------------------------------|------|
| **< 15 s** | hasta **~40** (40 c = 15.6 s) | el piso lo marca red (~5–7 s) + heurística |
| **< 30 s** | hasta **80** (80 c = 30.0 s; 100 c = 31.9 s) | |
| **< 60 s** | hasta **100** (100 c = 56.6 s) | |

El cuello para umbrales pequeños es el **sobrecosto fijo**: preparación de red OSM
(~5–7 s) + heurística (hasta ~7 s a 100 c tras acelerar el 2-opt). Con ≥ 80 clientes,
red+heurística ya suman ~12 s, de modo que < 15 s de total es inalcanzable aunque el
MILP se recorte al piso.

### Preservación del óptimo real (competition, eved, OSM)

```
uv run python -c "from evrp import resolver; r=resolver('data/competition_routing_nodes.csv', \
  {'red':{'osm_permitir_descarga':False},'solver':{'tiempo_limite_s':30}}, ['eved'])"
default: entregas 20  energia 11.1466  tiempo 6.372
k=10:    entregas 20  energia 11.1466  tiempo 4.283
```

Ambos dan **11.1466 kWh** (= óptimo conocido ≈ 11.15); con k=10 además es más rápido.

### Tests

- 21 tests existentes: **pasan** (`uv run pytest -q` → `28 passed`, incluye los nuevos).
- `tests/test_escala.py`: **7 tests nuevos rápidos** (3.4 s) — poda reduce arcos y
  conserva factibilidad/entregas, piso del presupuesto adaptativo, tour 2-opt válido,
  y comportamiento base cuando no hay claves `escala`.

## Limitaciones

- La **poda k-vecinos es heurística**: puede perder el óptimo exacto. Por eso está
  desactivada por defecto (`k_vecinos=0`) y documentada como configurable. En 20
  clientes reales no afecta el óptimo (verificado arriba).
- A **60 clientes** el mejorado quedó ligeramente peor (+0.8 % a +3.1 %) porque el
  recorte de tiempo le da al MILP menos margen justo en el tamaño donde todavía mejoraba
  con 65 s. Es un intercambio tiempo/calidad; se puede recuperar subiendo `--total` o
  `escala.min_s` en ese rango.
- Resultados del MILP con límite de tiempo son **no deterministas** entre corridas
  (variación observada ~0.1–0.5 kWh a 40–60 c).
- El tiempo de **red OSM** (5–12 s, caché en frío vs. caliente) es ruidoso y no está en
  mis archivos; es el principal sobrecosto para umbrales < 15 s.
- Medí sólo el perfil `ev_routing` en el barrido grande; el perfil `eved` se verificó en
  la instancia real.

## Cambios solicitados (fuera de mis archivos)

1. **`config.py`** — añadir un bloque `escala` a `DEFAULTS` para exponerlo oficialmente:
   ```python
   "escala": {"k_vecinos": 0, "adaptativo": False, "min_s": 10.0,
              "overshoot_margen_s": 3.0, "mip_heuristic_effort": None, "presolve": None},
   ```
   Hoy mis módulos leen estas claves de forma defensiva (`cfg...get(...)`), así que
   funcionan sin este cambio, pero conviene documentarlas y validarlas.

2. **`pipeline.py`** — para que el presupuesto de reloj **total** aplique en el motor
   real (no solo en el bench), el pipeline debería (a) medir el tiempo de red+heurística
   y pasar al solver `tiempo_limite_s = total − elapsed − margen`, y (b) propagar
   `cfg["escala"]` dentro de `cfg["solver"]` antes de instanciar `ModeloCompacto`
   (el modelo solo recibe `cfg["solver"]`). Hoy lo hago en `bench.py`.

3. **`red.py`** (opcional) — cachear/compartir el grafo OSM entre llamadas para reducir
   los 5–12 s de preparación; es el límite para los umbrales de tiempo más agresivos.

## Próximos pasos

- Barajar la poda k-vecinos **adaptativa** (k en función de |C|: p. ej. k=15 a 40 c, k=8
  a 100 c) para no sacrificar calidad en tamaños medios como 60 c.
- Añadir **ruptura de simetría** entre vehículos idénticos (ordenar las salidas de la
  base por índice) para acelerar la fase 2 del MILP; midiendo que no cambie el óptimo.
- Evaluar **ALNS** (`alns.py`) como refinamiento de la heurística para 80–100 c, donde
  hoy el MILP aporta poco: destrucción peor/relacionada + reparación por inserción con
  reparación de batería, con tope de tiempo.
- Explorar **cortes de conectividad más fuertes** (ya existen en la formulación
  `completa`/`cortes`) portados a la compacta como desigualdades válidas.
