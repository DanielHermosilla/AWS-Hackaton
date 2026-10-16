# Estado de la implementación

Cada rama `exp/*` mantiene su propio `docs/ESTADO.md` con uno de estos estados por componente:

- **DESARROLLO**: en construcción. Puede estar incompleto y no se debe usar en resultados.
- **EVALUACIÓN**: implementado y con pruebas; se está midiendo su efecto. Apagado por defecto.
- **DEFINITIVA-EVIDENCIA**: integrado. Si está activo por defecto, es porque hay evidencia medida (enlazada).

## main (versión etiquetada `v0.3.0`)

| Componente | Estado | Evidencia |
|---|---|---|
| Preparar / resolver separados (`evrp preparar`, `evrp resolver`) | DEFINITIVA-EVIDENCIA | `tests/test_preparacion.py`; README |
| Caminos: Dijkstra multi-origen con scipy y potencial de altura | DEFINITIVA-EVIDENCIA | `docs/experimentos/caminos.md` (exacto, 4–5× más rápido) |
| Mapa OSM empaquetado + ajuste a la geometría de la calle | DEFINITIVA-EVIDENCIA | `tests/test_motor.py` (instancias oficiales sin internet) |
| Elevación (eved / usgs / copernicus) | EVALUACIÓN (apagada) | `docs/experimentos/elevacion_*.md` |
| MILP compacto con HiGHS, dos fases | DEFINITIVA-EVIDENCIA | Óptimo con gap 0 en 20 clientes |
| Poda top-k (`escala.k_vecinos`) | EVALUACIÓN (`auto` activa k=10 sobre 25 clientes; se propone 0) | `experimentos/topk/` (26 clientes: +1 % de energía) |
| Regla de parada por estancamiento | EVALUACIÓN (apagada por defecto; callbacks highspy 1.11, implementada en vivo) | `tests/test_parada.py`; `docs/experimentos/versiones_parada.md`; `benchmarks/resultados/parada.jsonl` |
| Arnés de benchmarks de versiones (`benchmarks/correr.py`, `comparar.py`) | DEFINITIVA-EVIDENCIA (v0.3.0 vs rama: 200/200 entregas, Δenergía 0, hashes idénticos) | `benchmarks/resultados/v0.3.0.jsonl`, `WT.jsonl`; `docs/experimentos/_tabla_versiones.md` |
| IA generativa: asistente, ingesta, explicación, contexto | EVALUACIÓN (opcional) | `docs/experimentos/ia_*.md` |
| IA: ajuste del solver | EVALUACIÓN, sin beneficio demostrado (benchmark con bug en los ajustes de escala) | `docs/experimentos/ia_tuning.md`, `curvas.py` |

## rama `exp/dijkstra` (extensiones de la etapa de caminos)

Default idéntico a v0.3.0 verificado (competition/eved = 11.1466 kWh, 20/20).
`uv run pytest -q -m "not bedrock"` → 198 passed.

| Componente | Estado | Evidencia |
|---|---|---|
| F0 aviso/contador del clamp `max(red,0)` (`red.avisar_clamp`) | EVALUACIÓN (apagado) | `tests/test_dijkstra_extensiones.py::test_clamp_no_recorta_en_config_real` (0 recortes, min=+1.14e-4) |
| F0 snap con acceso según sentido (`red.snap_sentido`) | EVALUACIÓN (apagado) | `docs/experimentos/dijkstra_extensiones.md`; benchmark: cambia 23–93 % de arcos, +2–22 % energía |
| F2 tiempo por arco `t=ℓ/v_ef` + `t̂` por par + esquema preparada /2 (`red.tiempo_arco`) | EVALUACIÓN (apagado) | `test_dijkstra_extensiones.py::test_tiempo_arco_y_tmax`, `::test_esquema_v2_ida_y_vuelta` |
| F2 filtro `red.t_max_trayecto_min` | EVALUACIÓN (apagado) | `experimentos/dijkstra/resultados.jsonl` (T30→0, T20→56–159, T15→615–940 pares; rutas sin cambio) |
| F1-lite camino alternativo de menor pico (`red.caminos_alternativos`) | EVALUACIÓN (apagado) | `resultados.jsonl` (0 rescates con perfil plano; ~10× coste prep) |
