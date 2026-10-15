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

## rama `exp/eval-energia-20` (evaluaciones de energía, 20 clientes)

| Componente | Estado | Evidencia |
|---|---|---|
| E1 Sensibilidad al modelo (plano vs pendiente eVED vs temperatura; reoptimización) | DEFINITIVA-EVIDENCIA | `docs/experimentos/energia_20.md`; `experimentos/energia20/e1_sensibilidad.json`; fig. `energia20_e1_sensibilidad.png` |
| E2 Robustez (distribución eVED por viaje; p50 planifica, p75/p90/p95 validan) | DEFINITIVA-EVIDENCIA | `experimentos/energia20/e2_robustez.json`; fig. `energia20_e2_robustez.png` |
| E3 Variabilidad y flota (10 sintéticas × veh {1,2,3} × usar_todos on/off) | DEFINITIVA-EVIDENCIA | `experimentos/energia20/e3_flota.json`; fig. `energia20_e3_flota.png` |

Conclusión: en estas instancias (Ann Arbor, terreno casi plano) el modelo de pendiente/temperatura
cambia los **kWh** (−12 %…+8 % nominal; <0 °C vuelve infactibles 10/12 rutas) pero **reoptimizar no
reduce energía** frente a la ruta óptima-plano evaluada bajo pendiente (Δ medio ≈ 0, sin ganancia).
→ No se justifica más fidelidad de pendiente para el *ruteo*; sí conviene un **margen de batería**
(planificar con percentil alto) por la variabilidad real de consumo.
