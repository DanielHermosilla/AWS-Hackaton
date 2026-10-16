# Benchmark de versiones + regla de parada

Rama `exp/versiones-parada`. Todo con `solver.hilos=1`, un proceso, sin paralelismo.

## 1. Arnés de versiones (`benchmarks/`)
- `correr.py <ref ...>`: por cada ref (tag/rama o `WT`=working tree) crea un worktree temporal
  en `.cache/bench-wt/` (sin tocar ramas) y ejecuta su propio código evrp con el intérprete ya
  sincronizado (mismo pin de deps en todos los refs evrp), vía `PYTHONPATH` al `src/` del ref.
  Escenarios fijos: competition, evaluation y sintéticos 20 clientes semillas 1–3, perfiles
  `ev_routing` y `eved` (10 escenarios, 30 s c/u). Guarda `resultados/<ref>.jsonl` con entregas,
  energía, km, tiempo total y por etapa (red/MILP), gap y hash de rutas.
- `comparar.py <ref1> <ref2>`: tabla con diferencias de energía, tiempo y si las rutas cambian.

Resultado v0.3.0 vs rama (`docs/experimentos/_tabla_versiones.md`): **200/200 entregas en ambos,
energía total idéntica (96.988 kWh, ΔkWh=0.0000), hash de rutas igual en los 10 escenarios**.
La rama no introduce regresión (la regla de parada va apagada por defecto). Cada corrida ≈2–3 min.

## 2. Regla de parada por estancamiento (`src/evrp/milp_compacto.py`)
`solver.parada = {activar, t_min_s:15, sin_mejora_s:8}`, **APAGADA por defecto**. Implementada con
callbacks reales de highspy 1.11: `setCallback`/`startCallback` sobre `kCallbackMipImprovingSolution`
(sigue la incumbente) y `kCallbackMipInterrupt` (pide `input.user_interrupt=True`). Solo actúa en la
fase de energía: corta cuando han pasado ≥`t_min_s` y la mejor solución lleva ≥`sin_mejora_s` sin
mejorar; no se activa si ya se probó el óptimo. Tests unitarios en `tests/test_parada.py` (6, pasan).

Medición 30 y 40 clientes, semillas 1–2, 60 s, 1 hilo (`benchmarks/resultados/parada.jsonl`):

| clientes | semilla | E off | E on | ΔE% | t off | t on | ahorro |
|---|---|---|---|---|---|---|---|
| 30 | 1 | 10.864 | 10.956 | +0.85 | 58.9 | 23.2 | 35.7 s |
| 30 | 2 | 9.740 | 9.960 | +2.26 | 58.7 | 22.8 | 35.9 s |
| 40 | 1 | 12.567 | 12.567 | +0.00 | 59.5 | 29.5 | 29.9 s |
| 40 | 2 | 11.635 | 12.105 | +4.04 | 59.6 | 25.1 | 34.5 s |

En los 4 casos el MILP no probó óptimo a 60 s (gap 3–10 %) y la regla interrumpió. **Entregas
intactas (objetivo 1)**; coste en energía (objetivo 2) de 0 a +4 % (media ≈+1.8 %) a cambio de
~30–36 s menos de cómputo (objetivo 3), reduciendo el tiempo a la mitad. Útil cuando prima el
tiempo; se deja apagada hasta decidir el compromiso. `uv run pytest -q -m "not bedrock"` sigue
pasando (193).
