# Evaluaciones de energía — 20 clientes (`exp/eval-energia-20`)

Rama de evaluación (no toca `src/`). Instancias: `competition`, `evaluation` y 10 sintéticas
`evrp.sintetico.generar(20, s, competition_routing_nodes.csv)`, s=1..10. Preparación una vez
por instancia; variación de parámetros en etapa 2. **1 núcleo** (`solver.hilos=1`), sin procesos
en paralelo. Modelo de energía: `e = c·km + κ·([Δh]⁺/η_d − η_r·[Δh]⁻)`. Elevación eVED (Ann Arbor).
Código: `experimentos/energia20/{comun,e1_sensibilidad,e2_robustez,e3_flota,graficos}.py`.

## E1 — Sensibilidad al modelo (`e1_sensibilidad.json`, fig. `energia20_e1_sensibilidad.png`)
Ruta óptima con modelo **plano**, luego su energía recalculada con pendiente nominal, pendiente
**calibrada eVED** (c=0.110, η_d=0.50, η_r=0.94) y factores de temperatura (<0 °C 0.236; 20–30 °C 0.127).
Reoptimización con pendiente y comparación de rutas (% arcos distintos) + Δenergía bajo el mismo modelo.
- Pendiente nominal vs plano: **+0.6 %…+8.7 %** de kWh (media ≈ +6 %). Calibración eVED **baja** la
  energía (η mejores): competition 11.15→9.80, evaluation 12.05→10.59 kWh.
- Temperatura **<0 °C vuelve INFACTIBLES 10/12** rutas óptimas-plano (la batería B=16 baja de la reserva).
- Reoptimizar con pendiente **no reduce energía**: Δ medio = −2.4 % (negativo = la reopt no mejora;
  en oficiales 0 %). Los arcos cambian en las sintéticas (media 33.8 %, máx 84 %) pero son
  reordenamientos de energía equivalente, no ahorros.

## E2 — Robustez (`e2_robustez.json`, fig. `energia20_e2_robustez.png`)
Consumo por viaje eVED integrando `Energy_Consumption·Δt` y km (n=379). Percentiles kWh/km:
p10 0.094 · p25 0.117 · **p50 0.144** · p75 0.180 · p90 0.232 · p95 0.263. Por banda OAT la mediana
sube con el frío (**<0 °C: 0.228**; 20–30 °C: 0.120), coherente con los factores del enunciado.
Planificando con **p50** y validando con p75/p90/p95 (misma ruta):
- `eved` B=16: infactibles **7/12 (p75)**, 9/12 (p90), 11/12 (p95).
- `ev_routing` B=24: infactibles **2/12 (p75)**, 7/12 (p90), 10/12 (p95).
→ Planificar al consumo mediano **no es robusto**; conviene margen (percentil alto) o B mayor.

## E3 — Variabilidad y flota (`e3_flota.json`, fig. `energia20_e3_flota.png`)
10 sintéticas × vehículos {1,2,3} × `usar_todos_vehiculos` {off, on}, perfil `eved`.
- **Siempre 20/20 entregas** con 1–3 vehículos: un solo vehículo basta para 20 clientes.
- `usar_todos=off`: energía media **≈8.68 kWh estable** con 1–3 veh (el optimizador usa lo mínimo).
- `usar_todos=on`: fuerza más vueltas a base → energía sube (8.68→**9.24** con 3 veh) y aumenta el rango.
- Tiempo de cómputo medio 8–18 s (1 hilo); `usar_todos=on` resuelve más rápido (menos combinaciones).

## Conclusión (decisión pedida)
Los cambios de modelo (pendiente, temperatura, calibración) cambian **el número de kWh**, no las
**rutas** óptimas en estas instancias: reoptimizar con pendiente no baja la energía frente a la ruta
óptima-plano reevaluada. En terreno casi plano (Ann Arbor) **no se justifica** implementar más
fidelidad de pendiente para el *ruteo*. Lo que sí importa es la **variabilidad real de consumo**
(E2): el modelo debe reservar margen de batería (planificar con percentil alto, no la mediana) y
evitar `usar_todos_vehiculos` por defecto (E3), que gasta energía sin aportar entregas.

## Reproducir
```
uv run python experimentos/energia20/e1_sensibilidad.py
uv run python experimentos/energia20/e2_robustez.py
uv run python experimentos/energia20/e3_flota.py
uv run --with matplotlib==3.9.2 python experimentos/energia20/graficos.py
```
Nota: `experimentos/energia20/comun.py` fija `red.elevacion_csv` a ruta absoluta de `data/eVED_EV.csv`
(si es relativa y el CWD no es la raíz, la elevación eVED degrada a plano en silencio).
