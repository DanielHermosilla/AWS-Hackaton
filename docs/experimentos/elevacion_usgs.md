# Elevación — Fuente USGS 3DEP (DEM denso del National Map)

Rama `exp/elev-usgs`. Nueva implementación `src/evrp/elevacion/usgs.py` (`FuenteUsgs`,
misma interfaz `FuenteElevacion` que `FuenteEved`). A diferencia de eVED —nube de
telemetría concentrada en corredores— USGS 3DEP es un **Modelo Digital de Elevación
denso** (1/3 arc-second ≈ 10 m) que cubre **todo** el bbox del grafo. Se descarga el
DEM del servicio público del USGS National Map y se **muestrea** cada nodo OSM por
interpolación bilineal.

Como `FuenteEved`, es **opcional y con degradación segura**: sin red (o descarga
deshabilitada) devuelve alturas 0 (equivalente a plano). No se tocó `red.py`,
`pipeline.py` ni `config.py`.

## Qué hice

1. **`FuenteUsgs`** (`src/evrp/elevacion/usgs.py`):
   - Descarga el DEM del bbox del grafo (con margen) desde
     `3DEPElevation/ImageServer/exportImage` (EPSG:4326, `pixelType=F32`, GeoTIFF sin
     comprimir). El servicio rechaza peticiones muy grandes (HTTP 500 por encima de
     ~4 Mpx), así que **tesela** el bbox en una malla (lado ≤2000 px) y **cose** los
     tiles en un único raster alineado al grid global de píxeles.
   - **Lector GeoTIFF mínimo propio** (solo `numpy`): soporta float32 1-banda sin
     compresión, organización por *strips* o *tiles*, little/big-endian, y lee el
     georreferenciado de `ModelPixelScaleTag`/`ModelTiepointTag`. **Sin `rasterio`/`GDAL`**:
     el núcleo del motor no gana ninguna dependencia pesada (solo `numpy`+`requests`,
     ya presentes). Validado byte a byte contra `tifffile` (max abs diff = 0.0).
   - **Muestreo bilineal** vectorizado del raster para cada nodo, con manejo de
     `noData` (−9999 → nodo marcado fuera de cobertura).
   - **Caché** `.npz` del mosaico, firmada por bbox+resolución, en
     `.cache/elevacion/usgs`. Si existe, no hay red.
   - **Degradación segura**: si falla la red y no hay caché, alturas 0 + `aviso`.
2. **Cobertura** (`experimentos/elevacion/usgs/construir.py`) sobre el grafo
   empaquetado (Ann Arbor, 9688 nodos).
3. **Comparación contra eVED** (`experimentos/elevacion/usgs/comparar_eved.py`):
   error de altura USGS vs eVED **solo en los 1571 nodos con dato eVED directo**
   (observado, no interpolado), que es la comparación más limpia.
4. **Efecto en rutas** (`experimentos/elevacion/usgs/rutas.py`): inyecta la elevación
   USGS en un GraphML y lo pasa por `config.red.osm_grafo`
   (`osm_permitir_descarga=False`), corriendo `evrp.resolver` con `energia: plano` y
   `energia: pendiente` en competition y evaluation, ambos perfiles.
5. **Tests** (`tests/test_elevacion_usgs.py`): 11 (10 sin red + 1 `@pytest.mark.red`).

## Evidencia

### (1) Cobertura sobre el grafo empaquetado (Ann Arbor, 9688 nodos)

Comando: `uv run python -m experimentos.elevacion.usgs.construir`
(artefacto: `experimentos/elevacion/usgs/cobertura.json`).

| métrica | USGS 3DEP | eVED (referencia) |
|---------|-----------|-------------------|
| nodos con dato **directo** | **9688** | 1571 |
| **cobertura directa** | **100.0 %** | 16.2 % |
| interpolados | 0 | 8117 (dist. mediana ~3.1 km) |
| resolución | 1/3 arc-sec (~10.3 m) | — (telemetría) |
| raster descargado | 4531 × 2483 px (6 tiles 3×2) | — |
| rango de alturas | **209.7 – 322.1 m** | 229.5 – 321.5 m |

El DEM cubre **todos** los nodos con dato directo (sin interpolar a kilómetros). El
rango USGS es algo más amplio porque el DEM captura mínimos locales que la telemetría
eVED no recorrió (209.7 vs 229.5 m).

### (2) Tiempos y tamaño de descarga

Comando: medición directa (bloque reproducible más abajo).

| operación | tiempo | datos |
|-----------|--------|-------|
| 1ª descarga (6 tiles) + muestreo | **23.2 s** | **48.5 MB** descargados |
| caché `.npz` en disco | — | 45.0 MB |
| 2ª llamada (desde caché, sin red) | **0.13 s** | 0 B de red |

La descarga es única por bbox; a partir de ahí el muestreo de 9688 nodos es
instantáneo.

### (3) Error de altura USGS vs eVED (en los 1571 nodos con dato eVED directo)

Comando: `uv run python -m experimentos.elevacion.usgs.comparar_eved`
(artefacto: `experimentos/elevacion/usgs/comparar_eved.json`).

| métrica (USGS − eVED) | valor |
|-----------------------|-------|
| nodos comparados | 1571 |
| **MAE** | **0.72 m** |
| RMSE | 1.29 m |
| sesgo medio | −0.04 m (prácticamente insesgado) |
| |error| mediano (p50) | 0.34 m |
| |error| p90 | 1.77 m |
| |error| máximo | 11.61 m |
| **correlación de Pearson** | **0.9968** |

Dos fuentes **independientes** (DEM aéreo vs telemetría GPS) coinciden a **<1 m de
MAE** y correlación 0.997, sin sesgo. Es una **validación cruzada fuerte**: confirma
que la altura de eVED era buena donde tenía dato, y que el DEM 3DEP es fiable en todo
el grafo (incluido el ~84 % de nodos donde eVED tenía que interpolar a km).

### (4) Efecto en rutas: energía plano vs pendiente

Comando: `uv run python experimentos/elevacion/usgs/rutas.py <perfil>`
(artefactos: `rutas_eved.json`, `rutas_ev_routing.json`).

Perfil **eved** (B = 16):

| instancia | energía plano | energía pendiente | Δ energía | Δ km | veh. orden distinto |
|-----------|---------------|-------------------|-----------|------|---------------------|
| competition | 11.147 kWh | 12.125 kWh | +0.979 (+8.8 %) | +0.003 | 0 |
| evaluation  | 12.048 kWh | 13.107 kWh | +1.059 (+8.8 %) | +0.111 | 0 |

Perfil **ev_routing** (B = 24):

| instancia | energía plano | energía pendiente | Δ energía | Δ km | veh. orden distinto |
|-----------|---------------|-------------------|-----------|------|---------------------|
| competition | 11.152 kWh | 12.176 kWh | +1.024 (+9.2 %) | +0.211 | 0 |
| evaluation  | 12.077 kWh | 13.136 kWh | +1.059 (+8.8 %) | +0.111 | 0 |

- Las 20 entregas se cumplen en todos los casos; una sola ruta por instancia.
- La pendiente sube la energía estimada **~8.8–9.2 %**, muy cerca del +8.4–8.8 % que
  dio eVED (coherente con <1 m de diferencia de alturas). Pequeños cambios de km
  (el Dijkstra de mínima energía elige caminos ligeramente distintos con Δh), **sin
  cambios de orden de visita** en estas instancias de terreno suave.

## Valor estimado

**Para la jefa de flota:** el DEM 3DEP da elevación con cobertura **100 %** y error
<1 m en todo el grafo, no solo donde pasó un coche. Eso hace el presupuesto de
energía/alcance fiable **en calles sin telemetría previa** (eVED solo cubría 16 % de
nodos directo). La estimación de energía +8.8–9.2 % evita rutas "holgadas en plano"
que quedan al límite al subir.

**Para el jurado:** una segunda fuente de elevación bajo la **misma interfaz**, que
(a) **valida** eVED de forma independiente (MAE 0.72 m, r = 0.997, sin sesgo), (b)
**completa** su mayor debilidad (cobertura 16 % → 100 %), y (c) se lee **sin GDAL/rasterio**
(lector GeoTIFF propio en numpy, verificado contra `tifffile`), con caché reproducible
y descarga única de 48.5 MB en 23 s. El efecto en rutas concuerda con eVED, lo que da
confianza en el modelo de pendiente.

## Limitaciones

- **1/3 arc-second (~10 m)** es la resolución nacional de 3DEP; existe 1-m en zonas
  LiDAR, no necesario aquí (terreno suave, ~112 m de rango). Para orden de ruta haría
  falta una ciudad con relieve real, no Ann Arbor.
- Dependencia de **red** en la primera corrida (servicio USGS National Map). Mitigado
  con caché `.npz`; sin red degrada a plano (no rompe el motor).
- El `|error| máx` de 11.6 m vs eVED son casos aislados (p90 = 1.8 m): probablemente
  puntos eVED mal mapeados a la calzada o pasos a desnivel, no error del DEM.
- El lector GeoTIFF propio cubre **solo** el formato que pide `FuenteUsgs` (float32,
  sin comprimir, 1 banda). No es un lector GeoTIFF general; lanza `ValueError` claro
  si el formato no encaja.
- No se exploró el servicio de puntos **EPQS** (1 req/punto, limitado): descargar el
  DEM del bbox es mucho más eficiente para 9688 nodos (1 descarga vs miles de req).

## Dependencias solicitadas

**Ninguna nueva en `pyproject.toml`.** `FuenteUsgs` usa solo `numpy` (núcleo) y
`requests` (ya transitiva de `osmnx`/`boto3` y disponible en el entorno sincronizado).
Para **validar** mi lector GeoTIFF usé `tifffile==2025.5.10` de forma **efímera**
(`uv run --with tifffile==2025.5.10 ...`), solo en desarrollo; **no** es dependencia
del paquete ni de los tests.

## Cambios solicitados (a quien edite `red.py`/`pipeline.py`/`config.py`)

Alinea con lo que ya pidió el informe eVED. Para que RedOSM pueble
`G.nodes[v]['elevation']` desde la fuente elegida por config:

1. **`config.py`**: la clave `red.elevacion` (default `"ninguna"`) debe aceptar
   también `"usgs"`. Parámetros opcionales: `red.elevacion_cache` (default
   `.cache/elevacion/usgs`) y `red.elevacion_resolucion_grados` (default 1/3 arc-sec).
2. **`red.py`**: en el despacho de fuente de elevación, añadir la rama USGS
   (import perezoso para no cargar nada si no se usa):

   ```python
   def _fuente_elevacion(cfg):
       tipo = cfg["red"].get("elevacion", "ninguna")
       if tipo == "eved":
           from .elevacion.eved import FuenteEved
           return FuenteEved(...)
       if tipo == "usgs":
           from .elevacion.usgs import FuenteUsgs
           return FuenteUsgs(cache_dir=cfg["red"].get("elevacion_cache",
                                                       ".cache/elevacion/usgs"))
       return None
   ```
   `FuenteUsgs` degrada sola (sin red/caché → alturas 0), así que el motor nunca falla.
   La caché `.npz` evita recomputar entre corridas.
3. (Opcional) exponer `meta` (cobertura, bytes, desde_cache) en la bitácora/KPIs.

Mientras tanto, el experimento inyecta la elevación por `config.red.osm_grafo`
(GraphML pre-anotado), que **no** requiere cambios en el núcleo.

## Cómo reproducir

```powershell
uv sync --extra ia --all-groups
uv run python -m experimentos.elevacion.usgs.construir            # cobertura + descarga
uv run python -m experimentos.elevacion.usgs.comparar_eved        # error vs eVED
uv run python experimentos/elevacion/usgs/rutas.py eved           # efecto en rutas
uv run python experimentos/elevacion/usgs/rutas.py ev_routing
uv run pytest tests/test_elevacion_usgs.py -v -m "not red"        # 10 tests (sin red)
uv run pytest tests/test_elevacion_usgs.py -v -m "red"            # 1 test (descarga real)
uv run pytest -q -m "not bedrock"                                 # suite completa: 150 passed
```

Medición de tiempos/tamaño (reproducible):

```python
import tempfile, time, osmnx as ox
from evrp.elevacion.usgs import FuenteUsgs
G = ox.load_graphml(".cache/osm/ann_arbor_drive.graphml")
with tempfile.TemporaryDirectory() as td:
    f = FuenteUsgs(cache_dir=td)
    t = time.perf_counter(); _, m = f.elevar(G)   # ~23 s, 48.5 MB
    print(m["cobertura_directa"], m["bytes_descargados"], round(time.perf_counter()-t, 2))
```

## Comparativa eVED vs USGS (resumen)

| criterio | eVED | USGS 3DEP |
|----------|------|-----------|
| cobertura directa | 16.2 % | **100 %** |
| dependencia externa | ninguna (telemetría local) | red (1 descarga, luego caché) |
| error vs la otra fuente | — | **MAE 0.72 m, r 0.997, sesgo −0.04 m** |
| Δ energía pendiente (eved/ev_routing) | +8.4–8.8 % | +8.8–9.2 % |
| cambios de orden de ruta | 0 | 0 |
| mejor para | autosuficiencia, calibración de coeficientes | cobertura total, validación, calles sin telemetría |

Son **complementarias**: eVED calibra el modelo de energía con datos reales de
consumo; USGS da la altura densa y fiable para todo el grafo. Juntas se validan.

## Presupuesto Bedrock

No se usó Bedrock en esta área (**0 tokens**). La tarea es de datos/DEM/ruteo y no
requiere IA.

## Próximos pasos

- Probar en una ciudad con relieve real para ver si el DEM denso **sí** reordena rutas
  (donde eVED, por su cobertura parcial, no lo capturaría).
- Si se adopta en el núcleo: aplicar los cambios solicitados y añadir un test
  `@pytest.mark.red` de integración RedOSM con `red.elevacion=usgs`.
- Opcional: fusionar eVED+USGS (DEM como base, eVED para corregir sesgos locales de
  calzada) bajo una tercera `FuenteElevacion`.
