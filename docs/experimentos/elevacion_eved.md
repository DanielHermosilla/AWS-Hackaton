# Elevación — Fuente eVED (sin dependencias externas)

Rama `exp/elev-eved`. Subpaquete nuevo `src/evrp/elevacion` con la interfaz
`FuenteElevacion` y la implementación `FuenteEved`, que deriva la altura por nodo
OSM a partir de la telemetría eVED (sin DEM externo, sin red). Incluye calibración
de los coeficientes del modelo de energía con viajes eVED y la medición del efecto
de la pendiente en las rutas de `competition` y `evaluation`.

Todo lo aquí descrito es **opcional y con degradación segura**: el motor sigue
funcionando sin esta fuente (perfil plano), y si no hay puntos eVED la fuente
devuelve alturas 0 (equivalente a plano). No se tocó `red.py`, `pipeline.py` ni
`config.py`.

## Qué hice

1. **Interfaz `FuenteElevacion`** (`src/evrp/elevacion/__init__.py`): contrato
   `elevar(G) -> (alturas{nodo→m}, metadatos)`, más utilidad `aplicar(G)` que
   escribe `G.nodes[v]['elevation']`. Pensada para comparar eVED con Copernicus y
   USGS en la tanda siguiente con las mismas métricas.
2. **`FuenteEved`** (`src/evrp/elevacion/eved.py`):
   - Lee `Matched Latitude/Longitude[deg]` + `Elevation Smoothed[m]` (fallback a
     `Elevation Raw[m]`) de `data/eVED_EV.csv` (solo EV: no hay PHEV/HEV/ICE en
     `data/`).
   - Proyección equirectangular local + `scipy.cKDTree`: asigna cada punto al nodo
     OSM más cercano dentro de un **radio** configurable y agrega por **mediana**
     (robusta a ruido). Interpola los nodos sin dato por **IDW** (k vecinos) o
     **vecino más cercano**.
   - **Caché** `.npz` con firma = hash(grafo: nodos+coords) + hash(CSV) +
     parámetros. Recomputa solo si algo cambia.
   - Reporta **cobertura**: % nodos con dato directo, nº interpolados y distribución
     de la **distancia de interpolación**.
3. **Calibración** (`experimentos/elevacion/eved/calibrar.py`): NNLS de
   `E_obs ≈ c·L + (κ/η_d)·S⁺ − (κ·η_r)·S⁻` por viaje; validación **separando
   viajes** (70/30 y 5-fold); comparación plano vs pendiente.
4. **Efecto en rutas** (`experimentos/elevacion/eved/rutas.py`): inyecta la
   elevación en un GraphML de caché y lo pasa por `config.red.osm_grafo`
   (`osm_permitir_descarga=False`), sin tocar `red.py`. Corre `evrp.resolver` con
   `energia: plano` y `energia: pendiente` en ambas instancias y ambos perfiles.

## Evidencia

### (1) Cobertura de elevación sobre el grafo empaquetado (Ann Arbor, 9688 nodos)

Comando: `uv run python experimentos/elevacion/eved/construir.py <radio> idw`
(artefacto: `experimentos/elevacion/eved/cobertura.json`).

| radio (m) | nodos directos | cobertura directa | pts/nodo (mediana) | dist. interp. mediana | tiempo |
|-----------|----------------|-------------------|--------------------|-----------------------|--------|
| 60        | 1438           | 14.8 %            | 87                 | 3067 m                | ~6 s   |
| **120**   | **1571**       | **16.2 %**        | **96**             | **3122 m**            | **~5 s** |
| 200       | 1646           | 17.0 %            | 97                 | 3149 m                | ~6 s   |

- 476 308 puntos eVED válidos; ~420 k asignados a nodos dentro de 120 m.
- Rango de alturas resultante: **229.5 – 321.5 m** (≈92 m de desnivel total), coherente
  con Ann Arbor.
- **Optimización medida**: la primera versión O(puntos×nodos) por bloques tardaba
  **2470 s**; con `cKDTree` sobre proyección local baja a **~5 s** (≈530×), con el
  mismo resultado (diferencia de 2 puntos asignados por desempates, despreciable).

Lectura honesta de la cobertura: solo ~16 % de los nodos tienen dato **directo** y la
distancia de interpolación mediana es ~3 km, porque los viajes eVED se concentran en
ciertos corredores. Como el relieve de Ann Arbor es suave, la IDW sobre esas
distancias sigue dando alturas plausibles (rango estrecho), pero esta es la mayor
limitación de la fuente eVED frente a un DEM denso (Copernicus/USGS).

### (2) Calibración del modelo de energía con viajes eVED

Comando: `uv run python experimentos/elevacion/eved/calibrar.py 1590`
(artefacto: `experimentos/elevacion/eved/calibracion.json`). 379 viajes válidos
(L > 2 km, energía integrada con Δt real; subida/bajada por Δ de `Elevation Smoothed`).

Ajuste global (NNLS, masa 1590 kg, κ = 0.004333 kWh/m):

| coeficiente | valor | nota |
|-------------|-------|------|
| c (kWh/km)  | 0.110 | consumo plano |
| η_d (tracción) | 0.50 | el crudo NNLS cae en 0.50 (vs 0.90 nominal) |
| η_r (regeneración) | 0.94 | alta recuperación en bajada |

Subida/bajada mediana por viaje: **+52 m / −52 m**.

Validación **por viaje** (no por fila), error de energía por viaje en test:

| validación | MAE plano | MAE pendiente | mejora MAE | MAPE plano → pendiente |
|------------|-----------|---------------|------------|------------------------|
| split 70/30 | 0.260 kWh | 0.234 kWh | **10.0 %** | 34.8 % → 27.6 % |
| 5-fold (media) | 0.233 kWh | 0.210 kWh | **9.9 %** | 33.7 % → 26.6 % |

El modelo con pendiente **reduce el error de energía por viaje ~10 %** de forma
consistente entre validaciones. El η_d calibrado (0.50) es más bajo que el nominal
(0.90): refleja que la energía real en subida incluye pérdidas y cargas auxiliares
que el modelo atribuye a la tracción. Es un valor de calibración empírica, no una
eficiencia física de motor.

### (3) Efecto en rutas: energía plano vs pendiente

Comando: `uv run python experimentos/elevacion/eved/rutas.py <perfil>`
(artefactos: `rutas_eved.json`, `rutas_ev_routing.json`). GraphML con `elevation`
inyectado por `config.red.osm_grafo`, sin tocar `red.py`.

Perfil **eved** (B = 16):

| instancia | energía plano | energía pendiente | Δ energía | Δ km | veh. con orden distinto |
|-----------|---------------|-------------------|-----------|------|-------------------------|
| competition | 11.147 kWh | 12.088 kWh | +0.942 (+8.4 %) | +0.037 | 0 |
| evaluation  | 12.048 kWh | 13.063 kWh | +1.016 (+8.4 %) | +0.054 | 0 |

Perfil **ev_routing** (B = 24):

| instancia | energía plano | energía pendiente | Δ energía | Δ km | veh. con orden distinto |
|-----------|---------------|-------------------|-----------|------|-------------------------|
| competition | 11.152 kWh | 12.130 kWh | +0.978 (+8.8 %) | +0.245 | 0 |
| evaluation  | 12.077 kWh | 13.093 kWh | +1.016 (+8.4 %) | +0.054 | 0 |

- Las 20 entregas se cumplen en ambos modos; una sola ruta por instancia (sobra flota).
- La pendiente **sube la energía estimada ~8–9 %** y produce pequeños cambios de km
  (el Dijkstra de mínima energía elige caminos ligeramente distintos con Δh), pero
  **no cambia el orden de visita** en estas instancias.
- Interpretación: en terreno suave (~92 m de rango) la pendiente importa para el
  **presupuesto de energía/alcance** (viabilidad de batería), no para la secuencia.
  El impacto en el orden se espera mayor en ciudades con relieve, que es justo donde
  la comparación con Copernicus/USGS aportará más.

## Valor estimado

**Para la jefa de flota (usuario final):** una estimación de energía ~8–9 % más alta
y ~10 % más precisa por viaje significa menos sorpresas de batería: rutas que el
modelo plano daría por "holgadas" pueden quedar al límite al subir. Es seguridad de
alcance sin hardware ni servicios externos — solo con la telemetría que la flota ya
genera. En ciudades con relieve, además, puede reordenar entregas para ahorrar
energía o evitar quedarse sin carga.

**Para el jurado:** demuestra una fuente de elevación **autosuficiente** (sin DEM
de pago ni llamadas de red), con cobertura y error cuantificados, caché reproducible,
calibración validada por viaje (no por fila, evitando fuga de datos) y una interfaz
limpia lista para comparar eVED vs Copernicus vs USGS en igualdad de condiciones.

## Limitaciones

- **Cobertura directa ~16 %**: los viajes eVED se concentran; la interpolación cubre
  el resto a ~3 km de distancia mediana. Fiable aquí por el relieve suave; en terreno
  accidentado la IDW perdería detalle. Es la razón de existir de las fuentes DEM.
- **η_d calibrado = 0.50** choca con el nominal 0.90: es un ajuste empírico que absorbe
  pérdidas/auxiliares, no una eficiencia de motor. No conviene reinterpretarlo como tal.
- MAPE de energía por viaje ~27 % aun con pendiente: hay dispersión intrínseca
  (clima, estilo de conducción, HVAC) que el modelo c·ℓ + pendiente no captura.
- Solo datos **EV** (no hay PHEV/HEV/ICE en `data/`).
- `scipy` (ya presente en el grupo `bench` y usado por `caminos.py`) se importa de
  forma perezosa dentro de `elevar`/`calibrar`; el núcleo del motor **no** depende del
  subpaquete.

## Cambios solicitados (a quien edite `red.py`/`pipeline.py`/`config.py`)

Para que RedOSM pueble `G.nodes[v]['elevation']` desde la fuente elegida por config,
sin que el experimento tenga que fabricar un GraphML:

1. **`config.py`**: añadir en `red` la clave `elevacion: "ninguna"` (default) con
   opciones `{"ninguna", "eved", "copernicus", "usgs"}`, y validarla en `OPCIONES`
   (o un bloque análogo). Parámetros opcionales: `red.elevacion_radio_m` (default
   120), `red.elevacion_interpolacion` ("idw"), `red.elevacion_csv`
   (default `data/eVED_EV.csv` para eved).
2. **`red.py` (`RedOSM._descargar` o justo después de cargar `G`)**: si
   `cfg.red.elevacion != "ninguna"` y `energia.usar_pendiente`, instanciar la fuente
   y hacer `fuente.aplicar(G)` **antes** de construir la adyacencia (que ya lee
   `elevation`). Esquema sugerido:

   ```python
   from .elevacion.eved import FuenteEved  # import perezoso
   def _fuente_elevacion(cfg):
       tipo = cfg["red"].get("elevacion", "ninguna")
       if tipo == "eved":
           return FuenteEved(cfg["red"].get("elevacion_csv", "data/eVED_EV.csv"),
                             radio_m=cfg["red"].get("elevacion_radio_m", 120.0),
                             interpolacion=cfg["red"].get("elevacion_interpolacion", "idw"))
       # copernicus / usgs: tanda siguiente
       return None
   ```
   La fuente ya degrada sola (sin datos → alturas 0), así que el motor nunca falla por
   esto. La caché `.npz` de la fuente evita recomputar en cada corrida.
3. (Opcional) exponer la cobertura (`meta`) en la bitácora/KPIs para trazabilidad.

Mientras tanto, el experimento inyecta la elevación por `config.red.osm_grafo`
(GraphML pre-anotado), que **no** requiere ningún cambio en el núcleo.

## Cómo reproducir

```powershell
uv sync --extra ia --all-groups
uv run python experimentos/elevacion/eved/construir.py 120 idw     # cobertura
uv run python experimentos/elevacion/eved/calibrar.py 1590         # calibración
uv run python experimentos/elevacion/eved/rutas.py eved            # efecto en rutas
uv run python experimentos/elevacion/eved/rutas.py ev_routing
uv run pytest tests/test_elevacion_eved.py -v                      # 7 tests (1 @datos)
uv run pytest -q -m "not bedrock"                                  # suite completa: 62 passed
```

## Próximos pasos

- **Copernicus y USGS** detrás de la misma `FuenteElevacion`, comparando cobertura
  directa, error de altura vs eVED en los nodos observados y efecto en rutas.
- Probar en una ciudad con relieve real para ver cambios de **orden** de ruta, no solo
  de energía.
- Validar el Δh por arco contra la columna `Gradient` de eVED como control cruzado.
- Si se adopta en el núcleo: aplicar los **cambios solicitados** y añadir un test
  `@pytest.mark.red`/`@pytest.mark.datos` de integración RedOSM con `red.elevacion=eved`.

## Presupuesto Bedrock

No se usó Bedrock en esta área (0 tokens). La tarea es de datos/calibración/ruteo y no
requiere IA.
