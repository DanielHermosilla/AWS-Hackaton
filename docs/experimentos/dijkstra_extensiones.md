# Extensiones de la etapa de caminos (Dijkstra): F0, F2, F1-lite

Rol: completar la etapa de caminos **sin cambiar el comportamiento por defecto**.
Todas las opciones están APAGADAS por defecto. Evidencia: `tests/test_dijkstra_extensiones.py`
(23 pruebas, verde) y `experimentos/dijkstra/resultados.jsonl`.
Verificado: default competition/eved = **11.1466 kWh, 20/20** (idéntico a v0.3.0);
`uv run pytest -q -m "not bedrock"` → **198 passed**.

## Qué se implementó (opciones de `red.*`, todas off)
- **F0 clamp** (`avisar_clamp`): registra/avisa el recorte `max(red,0)` en lugar de
  recortar en silencio. Medido en config real: `min_reducido=+1.14e-4`, **0 arcos
  recortados** sobre 24014 (coincide con doc 03). No altera energía.
- **F0 snap_sentido** (`snap_sentido`): acceso punto→calle con dos arcos según sentido
  (salida al extremo aguas abajo, entrada desde aguas arriba) en vez de un único nodo.
- **F2 tiempo por arco** (`tiempo_arco`): `t = ℓ/v_ef·60`. `v_ef` = `maxspeed·0.80`
  (si existe) o tabla por `highway`. Calibración eVED: la velocidad media de marcha es
  ~0.78–0.82× el límite en vías urbanas (40–72 km/h, n>30k c/u). Propagado a `t̂` por par
  y a la instancia preparada (esquema **/2** opcional; se sigue leyendo /1).
- **F2 T_max** (`t_max_trayecto_min`): descarta pares con `t̂ > T_max`.
- **F1-lite** (`caminos_alternativos`): para cada par, Dijkstra con penalización de
  subidas; se adopta si reduce el pico π̂.

## Benchmark (20 clientes, semillas 1–5 + competition + evaluation)
`experimentos/dijkstra/resultados.jsonl`. % arcos distintos = diferencia simétrica de
arcos de ruta vs base / unión.

| versión | energía vs base | arcos distintos | pares T_max | rescatados |
|---|---|---|---|---|
| base / tiempo_arco / tmax_30 / alternativos | **idéntica** en las 7 instancias | 0 % | 0 (T=30) | 0 |
| tmax_20 | idéntica | 0 % | 56–159 descartados | 0 |
| tmax_15 | idéntica | 0 % | 615–940 descartados | 0 |
| snap_sentido | **+2 % a +22 %** (nunca mejora) | 23–93 % | 0 | 0 |

Energías base (kWh): s1 9.69 · s2 7.51 · s3 8.00 · s4 7.55 · s5 9.77 · comp 11.15 · eval 12.05.
`snap_sentido` sube: comp 11.15→13.24, s3 8.00→9.73, s5 9.77→11.24.
Tiempo de preparación: 3–8 s salvo `alternativos` (**42–61 s**, ~10× por un Dijkstra extra por par).

## ¿Cambian las rutas?
- **No** con F2/T_max/alternativos en estas instancias: el camino de mínima energía ya
  es corto en tiempo (p95 de `t̂` ≈ 18 min; T_max=30 no corta nada) y, con perfil **plano**
  (eved no usa pendiente), π̂ ya es mínimo ⇒ no hay nada que rescatar.
- **Sí** con `snap_sentido`, pero empeora la energía: respetar el sentido en el acceso
  obliga rodeos. Es un cambio de *modelo* (más realista), no de optimización.

## Recomendación
- **Implementar y dejar como EVALUACIÓN (apagadas):** F0-clamp (coste nulo, blindaje), F2
  tiempo+`t̂`+esquema /2 y T_max. No cambian el default y habilitan realismo (T_max por
  jornada) y la regen acotada por potencia (requiere `t`). T_max útil solo con T≤20 y
  cuando las rutas usen tramos largos (no es el caso de 20 clientes en Ann Arbor).
- **snap_sentido:** correcto conceptualmente pero sensible (−/+ energía por rodeos);
  dejar apagado hasta validar los accesos reales (doc 05 lo marca como "Baja").
- **caminos_alternativos (F1-lite):** sin beneficio con perfil plano y caro; **no activar**
  hasta usar pendiente real (DEM), donde π̂ sí varía entre caminos (doc 03 §2, doc 04 B1).
- **Pendiente (lo que falta):** el rescate y T_max solo rinden con elevación real; el
  siguiente paso de mayor impacto es el frente Pareto por par con DEM (doc 04 F1/F3), no
  cubierto aquí por el tope de tiempo.
