# Elevación — Fuente Copernicus DEM 30 m (AWS Open Data)

Rama `exp/elev-copernicus`. Segunda fuente detrás de la interfaz `FuenteElevacion`
(`src/evrp/elevacion/__init__.py`), para comparar contra `FuenteEved` con las mismas
métricas. `FuenteCopernicus` deriva la altura por nodo OSM muestreando el DEM global
Copernicus GLO-30 (30 m, 1 arcosegundo) servido en `s3://copernicus-dem-30m` (acceso
anónimo, Registry of Open Data on AWS).

Igual que eVED, es **opcional y con degradación segura**: si falta `rasterio`, no hay
tesela, o un nodo cae fuera del área cubierta, devuelve altura 0 y lo reporta (perfil
plano). No se tocó `red.py`, `pipeline.py` ni `config.py`.

## Qué hice

1. **`FuenteCopernicus`** (`src/evrp/elevacion/copernicus.py`):
   - Calcula las teselas 1°×1° que cubren la caja del grafo. Para el mapa empaquetado
     (lat 42.17–42.38, lon −83.95…−83.55) es **una sola tesela**: `N42/W084`.
   - Descarga de S3 **solo** esas teselas a `.cache/elevacion/copernicus` con `boto3`
     y firma deshabilitada (`UNSIGNED`, anónimo). Reutiliza la caché si ya existen.
     Teselas inexistentes (océano) se saltan sin fallar.
   - Lee el GeoTIFF (COG, EPSG:4326, float32, 3600×3600) con `rasterio` (import
     perezoso) y muestrea cada nodo con interpolación **bilineal** (o vecino) sobre
     el raster.
   - **Caché** `.npz` del resultado por grafo (firma = hash grafo + teselas + muestreo).
   - Cobertura **densa**: a diferencia de eVED, hay dato para todo nodo dentro del
     área → `cobertura_directa` ≈ 1.0.
2. **Tests** (`tests/test_elevacion_copernicus.py`): 11 (10 puros + 1 `@datos`).
   Los puros no requieren red ni `rasterio` (helpers de teselado, muestreo con un
   dataset *fake*, degradación sin `rasterio` por monkeypatch, grafo vacío).
3. **Experimentos** (`experimentos/elevacion/copernicus/`): cobertura/descarga,
   error de altura vs eVED en nodos con dato directo, y efecto en rutas plano vs
   pendiente en `competition`/`evaluation` para los perfiles `eved` y `ev_routing`,
   inyectando la elevación por `config.red.osm_grafo` (sin tocar el núcleo).

## Evidencia

### (1) Cobertura, descarga y tiempos (grafo empaquetado, 9688 nodos)

Comando: `uv run --with rasterio==1.4.3 python -m experimentos.elevacion.copernicus.construir bilineal`
(artefacto: `experimentos/elevacion/copernicus/cobertura.json`).

| métrica | valor |
|---------|-------|
| nodos del grafo | 9688 |
| nodos con dato directo | **9688** |
| cobertura directa | **100 %** |
| teselas descargadas | 1 (`N42/W084`) |
| tamaño de descarga (una vez) | **42 738 162 B ≈ 40.8 MiB** |
| tiempo de descarga S3 | ~15 s (medido al bajar la tesela) |
| tiempo de muestreo (9688 nodos, bilineal) | **~1.0 s** |
| rango de alturas | **208.8 – 329.0 m** |

- La descarga es **una sola tesela** porque toda la ciudad cae en un cuadrado de 1°.
  Tras la primera vez, `bytes_descargados = 0` (caché local) y solo cuenta la lectura.
- Cobertura **total** por ser un DEM denso: no hay interpolación entre nodos (se
  interpola *dentro* del raster, a escala de 30 m), que es la gran diferencia frente
  a eVED (~16 % directo, interpolación mediana ~3 km).

### (2) Error de altura Copernicus vs eVED (nodos con dato directo eVED)

Comando: `uv run --with rasterio==1.4.3 python -m experimentos.elevacion.copernicus.comparar_eved 120`
(artefacto: `comparacion_eved.json`). Comparación justa: solo los **1571 nodos** donde
eVED tiene telemetría directa (radio 120 m, mediana por nodo); Copernicus cubre el 100 %.

| métrica (Copernicus − eVED) | valor |
|-----------------------------|-------|
| nodos comparados | 1571 |
| MAE | **2.53 m** |
| RMSE | **3.48 m** |
| sesgo medio | **+2.02 m** |
| mediana \|error\| | 1.88 m |
| p90 \|error\| | 5.45 m |
| máx \|error\| | 17.76 m |
| correlación de Pearson | **0.985** |
| rango Copernicus / eVED | 227.5–329.0 m / 229.5–321.5 m |

- Las dos fuentes **concuerdan muy bien** (Pearson 0.985, MAE 2.5 m), un control
  cruzado fuerte: dos orígenes independientes (telemetría vs satélite) dan la misma
  topografía de Ann Arbor.
- **Sesgo +2 m**: Copernicus GLO-30 es un DSM (modelo de *superficie*, incluye dosel/
  edificios), así que tiende a quedar ligeramente por encima de la calzada medida por
  eVED. Es pequeño y sistemático; no cambia los Δh de arco (lo que importa para energía).

### (3) Efecto en rutas: energía plano vs pendiente

Comando: `uv run --with rasterio==1.4.3 python -m experimentos.elevacion.copernicus.rutas <perfil>`
(artefactos: `rutas_eved.json`, `rutas_ev_routing.json`). GraphML con `elevation`
Copernicus inyectado por `config.red.osm_grafo` (`osm_permitir_descarga=False`), sin
tocar `red.py`.

Perfil **eved** (B = 16):

| instancia | energía plano | energía pendiente | Δ energía | Δ km | veh. orden distinto |
|-----------|---------------|-------------------|-----------|------|---------------------|
| competition | 11.147 kWh | 12.488 kWh | +1.341 (**+12.0 %**) | +0.045 | 0 |
| evaluation  | 12.048 kWh | 13.391 kWh | +1.344 (**+11.2 %**) | +0.150 | 0 |

Perfil **ev_routing** (B = 24):

| instancia | energía plano | energía pendiente | Δ energía | Δ km | veh. orden distinto |
|-----------|---------------|-------------------|-----------|------|---------------------|
| competition | 11.152 kWh | 12.541 kWh | +1.389 (**+12.5 %**) | +0.337 | 0 |
| evaluation  | 12.077 kWh | 13.421 kWh | +1.344 (**+11.1 %**) | +0.150 | 0 |

- Las 20 entregas se cumplen en ambos modos; una sola ruta por instancia (sobra flota).
- La pendiente con Copernicus **sube la energía estimada ~11–12.5 %**, algo más que
  eVED (~8–9 % en la tanda anterior), coherente con que el DEM capta más detalle de
  relieve que la interpolación eVED a ~3 km. Pequeños cambios de km, **sin cambios de
  orden** (terreno suave, ~120 m de rango).

### Comparación directa eVED vs Copernicus (misma instancia/perfil)

| instancia / perfil | Δ energía eVED | Δ energía Copernicus |
|--------------------|----------------|----------------------|
| competition / eved | +8.4 % | **+12.0 %** |
| evaluation / eved  | +8.4 % | **+11.2 %** |
| competition / ev_routing | +8.8 % | **+12.5 %** |
| evaluation / ev_routing  | +8.4 % | **+11.1 %** |

## Valor estimado

**Para la jefa de flota:** Copernicus da elevación de **cobertura total** sin depender
de que la flota haya circulado por ahí (eVED solo cubre corredores con telemetría).
Para zonas nuevas o clientes fuera de las rutas históricas, es la fuente fiable. El
margen de energía por pendiente (~11–12 %) es la diferencia entre una ruta "holgada" y
una que llega al límite de batería: planificar con pendiente evita sorpresas de alcance.

**Para el jurado:** una segunda fuente de elevación detrás de la **misma interfaz**,
validada contra eVED (Pearson 0.985, MAE 2.5 m) — dos orígenes independientes que
concuerdan. Descarga mínima y dirigida (1 tesela, 40.8 MiB), caché reproducible,
muestreo bilineal sub-segundo, y degradación segura si falta la dependencia. Deja el
terreno listo para que RedOSM elija la fuente por configuración.

## Limitaciones

- **DSM, no DTM**: GLO-30 es modelo de superficie (dosel/edificios); sesgo sistemático
  de +2 m frente a la calzada eVED. Pequeño y constante; no afecta los Δh de arco.
- **Resolución 30 m**: en calles paralelas muy juntas o pasos a desnivel, dos nodos
  cercanos pueden caer en el mismo píxel. Suficiente para Δh de red; no para detalle fino.
- **Dependencia de lectura externa**: requiere `rasterio` (no está en `pyproject`; se
  usa vía `uv run --with rasterio==1.4.3`). El módulo **degrada a plano** si falta, así
  que el núcleo y la suite `-m "not bedrock"` no dependen de ella. `boto3` ya está en el
  extra `ia`.
- **Terreno suave de Ann Arbor** (~120 m de rango): la pendiente cambia la **energía**,
  no el **orden** de ruta. El impacto en orden se vería en ciudades con relieve.

## Cambios solicitados

1. **Dependencia `rasterio`** (a quien gestione `pyproject.toml`): añadir
   `rasterio==1.4.3` como extra opcional (p. ej. `elevacion = ["rasterio==1.4.3"]`),
   fijada `==`. No la añadí yo (no edito `pyproject.toml`). Mientras tanto, los
   experimentos corren con `uv run --with rasterio==1.4.3` y el módulo degrada solo.

2. **`red.aplicar_elevacion`** (a quien edite `red.py`): hoy solo implementa `eved`.
   Para registrar Copernicus, extender el despacho (import perezoso, misma firma):

   ```python
   elif fuente == "copernicus":
       from .elevacion.copernicus import FuenteCopernicus
       f = FuenteCopernicus(
           cache_tiles=opciones.get("copernicus_cache", ".cache/elevacion/copernicus"),
           muestreo=opciones.get("copernicus_muestreo", "bilineal"))
   ```
   `aplicar_elevacion` ya captura excepciones y degrada a plano, así que no hay riesgo
   para el motor. La fuente no usa `csv/radio_m/interpolacion` (son de eVED).

3. **`config.py`**: incluir `"copernicus"` entre las opciones válidas de
   `red.elevacion` (junto con `ninguna`/`eved`) y, opcionalmente, las claves
   `red.copernicus_cache` y `red.copernicus_muestreo`.

Con eso, `evrp.resolver(..., {"pipeline": {"energia": "pendiente"}, "red": {"elevacion": "copernicus"}})`
poblaría `G.nodes[v]['elevation']` sin que el experimento fabrique un GraphML.

## Cómo reproducir

```powershell
uv sync --extra ia --all-groups
# Tesela ya en .cache/elevacion/copernicus (si no, la descarga sola en el 1er run):
#   aws s3 cp s3://copernicus-dem-30m/Copernicus_DSM_COG_10_N42_00_W084_00_DEM/Copernicus_DSM_COG_10_N42_00_W084_00_DEM.tif .cache/elevacion/copernicus/ --no-sign-request
uv run --with rasterio==1.4.3 python -m experimentos.elevacion.copernicus.construir bilineal   # cobertura/descarga
uv run --with rasterio==1.4.3 python -m experimentos.elevacion.copernicus.comparar_eved 120    # error vs eVED
uv run --with rasterio==1.4.3 python -m experimentos.elevacion.copernicus.rutas eved            # efecto en rutas
uv run --with rasterio==1.4.3 python -m experimentos.elevacion.copernicus.rutas ev_routing
uv run pytest tests/test_elevacion_copernicus.py -v                        # 10 pass, 1 skip (datos)
uv run --with rasterio==1.4.3 pytest tests/test_elevacion_copernicus.py -m datos   # el @datos pasa
uv run pytest -q -m "not bedrock"                                          # suite completa: 149 passed, 1 skipped
```

## Próximos pasos

- Comparar también contra **USGS 3DEP** (DTM, sin dosel) para aislar el sesgo DSM.
- Probar en una ciudad con relieve real para ver cambios de **orden** de ruta.
- Si se adopta en el núcleo: aplicar los **cambios solicitados** y un test
  `@pytest.mark.red`/`@pytest.mark.datos` de integración RedOSM con `red.elevacion=copernicus`.

## Presupuesto Bedrock

No se usó Bedrock en esta área (0 tokens). La tarea es de datos geoespaciales/ruteo y
no requiere IA.
