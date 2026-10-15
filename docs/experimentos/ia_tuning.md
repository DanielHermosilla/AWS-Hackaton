# IDEA E — Ajuste del solver estilo LLM4MIP

## Qué

Un LLM recibe un **perfil estructural compacto** del MILP ya construido (nº de
columnas, filas, binarias, continuas, no-ceros, densidad, rango de coeficientes,
clientes, vehículos, y gap/tiempo/energía de la corrida base) y propone, en JSON
validado contra una **lista blanca**, parámetros de HiGHS. Nunca cambia datos,
objetivo ni tolerancias (`mip_rel_gap`/`gap_relativo` y `threads`/`hilos` quedan
fijos). Se compara, con **presupuesto total idéntico (55 s, 1 hilo)**:

- **base**: config del perfil `ev_routing` sin cambios.
- **haiku**: propuesta de `us.anthropic.claude-haiku-4-5-20251001-v1:0`.
- **sonnet**: propuesta de `us.anthropic.claude-sonnet-4-6`.
- **aleatorio** (control): una muestra uniforme de la **misma** lista blanca, con
  el **mismo número de pruebas** (1 propuesta por corrida).

Para las variantes LLM, la **latencia de Bedrock se descuenta del presupuesto del
MILP** (se cuenta dentro del tiempo total), de modo que la comparación es a reloj
total igual.

Código propio:
- `src/evrp/ia/tuning/perfil.py` — extrae el perfil desde el objeto `highspy.Highs`
  (`getLp()`, `getNumNz`, integralidad y cotas de columnas).
- `src/evrp/ia/tuning/whitelist.py` — lista blanca con dominios, validación/saneo
  de propuestas, inyección por ruta (`solver` vs `escala`) y muestreo aleatorio.
- `src/evrp/ia/tuning/llm.py` — construye el `toolSpec` desde la lista blanca,
  fuerza la tool (JSON estructurado) y mide latencia/tokens.
- `experimentos/ia_tuning/bench.py` — orquesta base/haiku/sonnet/aleatorio.
- `tests/test_ia_tuning.py` — 12 pruebas unitarias + 1 marcada `bedrock` (real).

### Lista blanca efectiva

| parámetro | ruta | tipo | dominio |
|---|---|---|---|
| `mip_heuristic_effort` | `escala` | real | [0.0, 1.0] |
| `presolve` | `escala` | categórico | on / off / choose |
| `k_vecinos` | `escala` | entero | [0, 20] |
| `cargadores_por_arco` | `solver` | entero | [1, 6] |

`mip_detect_symmetry` figura en la metodología de la idea pero **no se incluye**:
la clase `ModeloCompacto` del motor base (no editable en este rol) sólo consume
`mip_heuristic_effort` y `presolve` del bloque `escala`. Incorporarlo requiere un
cambio de una línea en `src/evrp/milp_compacto.py` (ver *Cambios solicitados*).

## Evidencia

Instancias: sintéticas 40 y 60 clientes (semillas 1–3) + competition (20), perfil
`ev_routing`, 2 vehículos, 2 repeticiones, 55 s de presupuesto total, 1 hilo.
56 corridas en total (`experimentos/ia_tuning/resultados.json`). Todas las
variantes y todas las instancias entregan el 100 % de los clientes (factible).

### Agregado por variante (syn40 + syn60; medias sobre 12 corridas c/u)

| variante | energía (kWh) | gap | t_milp (s) | t_total (s) | tokens LLM | latencia LLM (s) |
|---|---|---|---|---|---|---|
| base | **14.6202** | **0.0816** | 47.71 | 54.65 | 0 | 0.00 |
| haiku | 14.6347 | 0.0828 | 45.77 | 54.28 | 1365 | 1.42 |
| sonnet | 14.6347 | 0.0836 | 46.06 | 54.47 | 1341 | 1.24 |
| aleatorio | 14.6403 | 0.0863 | 47.50 | 54.74 | 0 | 0.00 |

### Enfrentamiento vs base (por instancia·semilla·rep, syn40/60)

| variante | gap mejor | igual | peor | Δenergía media (kWh) | Δenergía máx |
|---|---|---|---|---|---|
| haiku | 4 | 0 | 8 | +0.0145 | +0.0871 |
| sonnet | 2 | 4 | 6 | +0.0145 | +0.0871 |
| aleatorio | 3 | 1 | 8 | +0.0201 | +0.2417 |

### Instancia competition (20 clientes)

Se resuelve a **gap = 0 en < 1 s** en todas las variantes (energía 11.1521 kWh).
Aquí el LLM sólo añade coste: el `t_total` sube de ~4.0 s (base/aleatorio) a
~5.1–5.8 s (haiku/sonnet) por la llamada a Bedrock, sin ninguna mejora posible.

### Propuestas del LLM (primera aparición por instancia)

| modelo | instancia | propuesta |
|---|---|---|
| haiku | syn40/syn60/competition | `presolve=on, mip_heuristic_effort=0.8, k_vecinos=5, cargadores_por_arco=2` |
| sonnet | syn40 | `presolve=on, mip_heuristic_effort=0.35, k_vecinos=10, cargadores_por_arco=3` |
| sonnet | syn60 | `presolve=on, mip_heuristic_effort=0.35, k_vecinos=10, cargadores_por_arco=2` |
| sonnet | competition | `presolve=on, mip_heuristic_effort=0.5, k_vecinos=8, cargadores_por_arco=3` |

Perfil estructural (ejemplo syn60_s1): `cols=11556 filas=26754 binarias=11435
densidad=0.0004 rango_coef_log10=3.70 base_gap=0.0729`. Son modelos muy ralos
(densidad ~4–8·10⁻⁴) y casi enteramente binarios.

### Coste total del LLM

- Tokens Bedrock totales: **37 888** (in=34 948, out=2 940) — muy por debajo del
  tope de 100k del rol.
- Latencia LLM acumulada: **37.2 s** sobre las 28 llamadas (1.2–1.5 s cada una).

## Valor

**No hay mejora.** Con presupuesto total igual, la configuración base iguala o
supera a las dos propuestas LLM y al control aleatorio en gap y energía:

- Energía: base es la mejor en media (14.6202 vs 14.6347 kWh de haiku/sonnet,
  +0.1 % peor); la diferencia máxima individual es +0.09 kWh (desfavorable al LLM).
- Gap: base es el mejor en media (0.0816); haiku empeora el gap en 8/12 casos,
  sonnet en 6/12. El control aleatorio también empeora (8/12), lo que indica que la
  lista blanca **no contiene palancas de mejora** para estas instancias a 55 s.
- La causa dominante del deterioro es `k_vecinos > 0`: ambos modelos proponen podar
  arcos (5–10 vecinos), lo que reduce el espacio factible y descarta parte del
  óptimo. Coincide con lo medido en el experimento `escala`: a ≤ 60 clientes el
  MILP exacto (k=0) rinde mejor dentro del presupuesto.
- El LLM responde JSON válido de forma consistente (0 errores en 28 llamadas) y es
  barato en tokens, pero su latencia (~1.3 s) es tiempo neto perdido para el solver;
  en instancias fáciles (competition) ese coste es puro overhead.

Conclusión: para este motor, perfiles y presupuesto, **el ajuste de HiGHS vía LLM
no aporta** sobre los valores por defecto afinados del proyecto. El montaje
(perfil→lista blanca→JSON validado→control aleatorio) queda listo y probado para
reutilizarse si en el futuro la lista blanca incorpora palancas con más margen.

## Limitaciones

- La lista blanca efectiva es pequeña (4 parámetros) por la restricción de no
  editar el motor; `mip_detect_symmetry` y otras opciones de HiGHS no se exploran.
- 1 propuesta por corrida (sin bucle de realimentación LLM↔solver ni varios
  intentos): es un ajuste *one-shot*, no una búsqueda guiada iterativa.
- Instancias de 20–60 clientes; a esta escala el MILP exacto ya es competitivo y
  deja poco margen. El valor del tuning podría aparecer en instancias mayores
  (≥ 80–100 clientes) donde la poda sí ayuda, pero eso excede el alcance pedido.
- La energía depende del gap residual; con gaps del 5–13 % las diferencias entre
  variantes están dentro del ruido del corte por tiempo de HiGHS.

## Cambios solicitados

1. **`mip_detect_symmetry` en `ModeloCompacto`** (`src/evrp/milp_compacto.py`,
   dentro de `__init__`, junto al bloque que lee `escala`):
   ```python
   if esc.get("mip_detect_symmetry") is not None:
       h.setOptionValue("mip_detect_symmetry", bool(esc["mip_detect_symmetry"]))
   ```
   Con eso, bastaría añadir el `Param` correspondiente a la lista blanca para
   cubrir la metodología completa sin tocar más código.
2. (Opcional) Exponer en `cfg["escala"]` las opciones de HiGHS ya soportadas de
   forma declarativa (p. ej. un passthrough `escala.highs_opts: {clave: valor}`
   con validación), para ampliar la lista blanca sin nuevos `if` por parámetro.
