# Maximización de clientes cuando no se puede atender a todos

Objetivo: verificar que el motor **maximiza entregas** (fase 1 del MILP) y luego
**minimiza energía con N\* fijo** (fase 2), en instancias de 20 y pequeñas donde NO
es factible atender a todos. Verdad de referencia: un **oráculo independiente**
(`experimentos/max_clientes/oraculo.py`) por enumeración exhaustiva de subconjuntos y
permutaciones (≤ 8 clientes), con simulación de batería tramo a tramo y cadenas F→F por
Dijkstra; sin usar HiGHS, la heurística ni los estadísticos del MILP. RedHaversine
(sin internet), `solver.hilos=1`.

Reproducir: `uv run python -m experimentos.max_clientes.runner` · tests: `uv run pytest -q tests/test_max_clientes.py` (8 OK, 3.6 s). Datos: `experimentos/max_clientes/resultados.json`.

## Pequeñas (oráculo = verdad) — motor == oráculo en N\* y energía
| instancia | nC | N\* orac | N\* motor | E orac | E motor | formulación |
|---|--:|--:|--:|--:|--:|---|
| peq_bateria_corta | 6 | 3 | 3 | 4.059 | 4.059 | compacta |
| peq_incompatibles | 5 | 2 | 2 | 2.481 | 2.481 | compacta |
| peq_lejano_aislado | 8 | 6 | 6 | 4.285 | 4.285 | compacta+completa |
| peq_cadena_F_F | 4 | 4 | 4 | 12.628 | 12.628 | compacta+completa |
| peq_dos_veh | 6 | 4 | 4 | 6.765 | 6.765 | compacta+completa |

Coinciden N\* y energía (fase 2) en las 5. **F→F**: en `peq_cadena_F_F` la compacta sola
certifica N\*=3; el respaldo a la **completa** eleva a N\*=4 (= oráculo), confirmando que
el respaldo es necesario y correcto (`test_respaldo_completa_para_cadena_F_F`).

## Grandes (20 clientes, infactible atender a todos) — completa = referencia exacta
| instancia | N\* comp | N\* full | E comp | E full | t comp | t full | gap fase2 |
|---|--:|--:|--:|--:|--:|--:|--:|
| g20_bateria_pequena | 11 | 11 | 19.7–27.8 | 22.13 | 60 | 30 | 0.42–0.57 |
| g20_dos_veh_anillo | 15 | 0† | 28.32 | — | 60 | 30 | — |
| g20_cadena_F_F | 4 | 0‡ | 3.383 | 3.383‡ | 35 | 15 | 0.0 |

N\* de la fase 1 coincide (11, 15, 4) cuando ambas formulaciones la resuelven. La energía
(fase 2) queda con gap > 0 por tope de tiempo (20–30 s), no por error del modelo.

## Discrepancias y hallazgos
- **†Respaldo "cortes" puede no entregar solución**: en `g20_dos_veh_anillo` la completa
  (conectividad por cortes) agotó 30 s en fase 2 con "cortes pendientes" y devolvió None
  (N\*=0); la **compacta sí entregó N\*=15**. Aquí la compacta es la mejor opción; el pipeline
  real se queda con la mejor de ambas, así que el resultado publicado sería 15.
- **‡Fase 1 consume el presupuesto**: en `g20_cadena_F_F` la fase 1 (max entregas) agotó su
  mitad del tiempo (compacta "Time limit reached" en N\*=4; completa ni terminó fase 1).
  Con cadenas F→F obligatorias el modelo se vuelve duro y la fase 1 domina el reloj.
- No se detectó ningún caso donde el motor **sub-maximice** respecto al oráculo (la
  heurística, que no certifica, sí quedó por debajo: p.ej. 3 vs 4 en `peq_cadena_F_F`).

## Pendiente (tope de tiempo)
- Certificar energía (gap 0) en las grandes requeriría más presupuesto o k-vecinos.
- No se encontró bug en `src/`; no hay cambios solicitados.
