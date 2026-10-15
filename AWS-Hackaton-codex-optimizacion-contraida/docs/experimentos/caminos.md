# Experimento CAMINOS — algoritmos de caminos de mínima energía

Rama `exp/caminos`. Objetivo: comparar algoritmos de caminos más cortos **exactos**
para la etapa `red` (RedOSM) e integrar el más rápido sin cambiar resultados.

## Qué hice

1. **`src/evrp/caminos.py` (nuevo).** Seis solvers sobre una adyacencia común
   `GrafoCaminos` (costos reducidos ≥ 0 + metadatos para heurísticas):
   `multi_destino` (el actual), `bidireccional`, `a_estrella`, `alt` (landmarks),
   `scipy` (`scipy.sparse.csgraph.dijkstra` multi-origen) y `networkx`
   (`single_source_dijkstra`). Selección por nombre con `resolver_caminos(...)`.
2. **`src/evrp/red.py`.** `preparar()` quedó dividido e **instrumentado** por etapas
   (`carga_grafo`, `ajuste_calle`, `adyacencia`, `caminos` → `red.tiempos`). La
   resolución de caminos ahora delega en `caminos.resolver_caminos`, con el
   algoritmo elegido por `red.algoritmo_caminos` (por defecto `scipy`). Se conserva
   `_dijkstra` para verificación. Caché opcional de la adyacencia en `.npz` con hash
   del grafo + parámetros de energía (`red.cache_adyacencia`, por defecto activa).
3. **`experimentos/caminos/bench.py`.** Harness que genera instancias sintéticas
   (`evrp.sintetico`), mide etapas por separado para N ∈ {21,41,81,121,181} y
   verifica equivalencia de energía por par. **`verif_resultados.py`** comprueba que
   el pipeline da resultados idénticos entre algoritmos en las 4 combinaciones oficiales.
4. **`tests/test_caminos.py`.** 4 pruebas nuevas (grafo juguete, mapa real, pipeline,
   algoritmo inválido).

## Prueba de la heurística A* (admisible y consistente)

Con `e = c·ℓ + κ·([Δh]⁺/η_d − η_r·[Δh]⁻)` y potencial `p(v)=κ·η_r·h(v)`, el costo
reducido `c̃(u,v)=e(u,v)+p(u)−p(v) ≥ 0`. La distancia reducida es telescópica:
`d̃(v,t)=d(v,t)+p(v)−p(t) ≥ Σ c·ℓ + p(v) − p(t) ≥ c·haversine(v,t) + p(v) − p(t)`
(porque `ℓ ≥ haversine` y la suma de cuerdas ≥ la cuerda directa). Por tanto
`h(v)=c·haversine(v,t)+p(v)−p(t)` es admisible (≤ d̃) y consistente. En el perfil
`plano` (eved/ev_routing por defecto) `p≡0` y queda `h=c·haversine`. Detalle en el
docstring de `caminos.py`.

## Evidencia

Comando: `uv run python experimentos/caminos/bench.py --repeticiones 3`
(mapa empaquetado, perfil eved, mejor de 3; etapas base compartidas por N).

### Tiempos de resolución de caminos (s), por N nodos clave

| N | multi_destino | bidireccional | a_estrella | alt | scipy | networkx |
|---|---|---|---|---|---|---|
| 21 | 0.256 | 1.708 | 1.169 | 2.022 | **0.070** | 1.557 |
| 41 | 0.535 | 5.972 | 5.434 | 7.962 | **0.133** | 3.231 |
| 81 | 1.186 | 28.191 | 15.931 | 24.050 | **0.322** | 6.728 |
| 121 | 2.352 | 57.828 | 47.707 | 60.169 | **0.724** | 11.043 |
| 181 | 3.856 | 154.202 | 63.039 | 84.851 | **0.707** | 10.041 |

### Tiempos de las etapas base (s), por N

| N | carga_grafo | ajuste_calle | adyacencia |
|---|---|---|---|
| 21 | 4.339* | 0.951 | 0.039 |
| 41 | 2.248 | 1.360 | 0.052 |
| 81 | 2.310 | 2.155 | 0.039 |
| 121 | 2.255 | 3.165 | 0.055 |
| 181 | 2.851 | 4.070 | 0.052 |

\* La primera carga incluye el arranque de osmnx; en caliente `carga_grafo`≈1.5–2.3 s.

### Verificación de equivalencia (vs multi_destino)

| N | max_err_rel energía | pares con energía distinta |
|---|---|---|
| 21 | 0.00e+00 | 0 |
| 41 | 0.00e+00 | 0 |
| 81 | 0.00e+00 | 0 |
| 121 | 0.00e+00 | 0 |
| 181 | 0.00e+00 | 0 |

**Todos los algoritmos devuelven exactamente la misma energía por par** (error 0.0,
0 pares distintos). Son todos exactos; la diferencia es puro rendimiento.

### Aceleración de la etapa `red` (competition, eved, mejor de 3, caché caliente)

Comando: `uv run python -c "...RedOSM(...).preparar..."` (ver sesión).

| algoritmo | total | carga_grafo | ajuste_calle | adyacencia | caminos |
|---|---|---|---|---|---|
| multi_destino | 4.015 s | 1.567 | 1.419 | 0.035 | 0.993 |
| **scipy** | **3.225 s** | 1.521 | 1.429 | 0.035 | **0.239** |

- Etapa **caminos**: 0.993 → 0.239 s = **4.2× más rápida**.
- Etapa **red** completa: 4.015 → 3.225 s = **1.24× (−0.79 s, −20 %)**.
- A N=181 la etapa caminos pasa de 3.86 s a 0.71 s (**5.4×**).

### Resultados idénticos en instancias oficiales

Comando: `uv run python experimentos/caminos/verif_resultados.py`

```
competition_routing_nodes.csv  eved        IGUAL=True entregas 20/20 energia 11.1466/11.1466 km 71.453/71.453
competition_routing_nodes.csv  ev_routing  IGUAL=True entregas 20/20 energia 11.1521/11.1521 km 71.136/71.136
evaluation_routing_nodes.csv   eved        IGUAL=True entregas 20/20 energia 12.0478/12.0478 km 77.229/77.229
evaluation_routing_nodes.csv   ev_routing  IGUAL=True entregas 20/20 energia 12.0769/12.0769 km 77.035/77.035
```

### Tests

`uv run pytest -q` → **25 passed** (21 originales + 4 nuevos de `test_caminos.py`).
La suite completa bajó de ~72 s a ~55 s gracias al nuevo default.

## Recomendación

**Usar `scipy` como algoritmo de caminos por defecto** (ya integrado). Es el más
rápido en todo el rango de N, exacto (idéntico a Dijkstra), y usa una dependencia ya
disponible en el grupo `bench`. Se conserva `multi_destino` y los demás como opción de
verificación vía `red.algoritmo_caminos`.

Las variantes par-a-par (`bidireccional`, `a_estrella`, `alt`) son correctas y
exactas, pero en Python puro son 1–2 órdenes de magnitud más lentas porque recomputan
por par sin aceleración nativa; su ventaja teórica (podar con heurística) no compensa
el sobrecosto del intérprete frente a `scipy` (C) o al multi-destino amortizado.

## Limitaciones

- Mediciones en una sola máquina Windows; tiempos absolutos variarán, pero el orden
  relativo (scipy ≪ multi_destino ≪ par-a-par) es consistente y amplio.
- `scipy` materializa una matriz CSR densa en memoria por índices de nodo; con el grafo
  de ~9.7k nodos es trivial. Para grafos mucho mayores habría que vigilar memoria.
- La caché `.npz` de adyacencia ahorra poco (adyacencia ya cuesta ~0.05 s); el peso real
  está en `carga_grafo` (load_graphml de osmnx) y `ajuste_calle`, fuera del alcance de
  los caminos. Queda disponible por si se añaden perfiles con pendiente (más caro).
- A* se midió con el perfil `plano` (p≡0). La prueba de admisibilidad cubre el caso con
  pendiente, pero no se midió una instancia con `energia: pendiente`.

## Cambios solicitados (archivos que NO me pertenecen)

- **`src/evrp/config.py`**: añadir a `DEFAULTS["red"]` las claves documentadas
  `"algoritmo_caminos": None` (None = mejor medido = `scipy`) y
  `"cache_adyacencia": True`. Hoy `crear_red` las lee con `cfg["red"].get(...)`, así
  que funcionan sin tocar config; agregarlas al default las haría visibles y validables.
- (Opcional) `pipeline.py`/bitácora: registrar `red.tiempos` por etapa en el evento
  `red` para observabilidad; hoy solo expongo el atributo `RedOSM.tiempos`.

## Próximos pasos

- Atacar `ajuste_calle` (crece con N): vectorizar el snap de todos los nodos clave en
  una sola operación numpy (matriz N×P) en lugar del bucle por nodo.
- Cachear el grafo ya cargado (p. ej. pickle de `G` o de la adyacencia + coords) para
  recortar `carga_grafo` (~1.5–2.3 s), que hoy domina la etapa.
- Medir una instancia con `energia: pendiente` para confirmar empíricamente A*/scipy
  con potencial ≠ 0.
