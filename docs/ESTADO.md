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
| Regla de parada por estancamiento | DESARROLLO (pendiente) | Simulación en `experimentos/topk/regla_parada.py` |
| IA generativa: asistente, ingesta, explicación, contexto | EVALUACIÓN (opcional) | `docs/experimentos/ia_*.md` |
| IA: ajuste del solver | EVALUACIÓN, sin beneficio demostrado (benchmark con bug en los ajustes de escala) | `docs/experimentos/ia_tuning.md`, `curvas.py` |

## exp/max-clientes

| Componente | Estado | Evidencia |
|---|---|---|
| Verificación de maximización de clientes (fase 1 MILP) vs oráculo independiente | DEFINITIVA-EVIDENCIA | `tests/test_max_clientes.py` (8 OK); `docs/experimentos/max_clientes.md`; `experimentos/max_clientes/resultados.json` |
| Mínima energía con N\* fijo (fase 2) vs oráculo | DEFINITIVA-EVIDENCIA | energía idéntica al oráculo en 5/5 pequeñas (`max_clientes.md`) |
| Respaldo a formulación completa para cadenas F→F | DEFINITIVA-EVIDENCIA | `peq_cadena_F_F`: compacta N\*=3 → completa N\*=4=oráculo (`test_respaldo_completa_para_cadena_F_F`) |
| Grandes (20 clientes, infactible): fase 1 agota presupuesto; respaldo "cortes" puede no entregar solución | EVALUACIÓN (hallazgo) | `max_clientes.md` §Discrepancias; `g20_dos_veh_anillo`, `g20_cadena_F_F` |
