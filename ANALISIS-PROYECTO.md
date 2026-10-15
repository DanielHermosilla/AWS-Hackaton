# Análisis del proyecto AWS-Hackaton — Ruteo de vehículos eléctricos (EVRP)

> Documento de diagnóstico. Resume estructura, algoritmos, datos reales medidos,
> el mapa de la UI y recomendaciones de mejora. Elaborado a partir de la lectura
> directa del código y de un análisis cuantitativo de las instancias reales.
> Fecha: 2026-10-15.

---

## 1. Qué es el proyecto

Sistema de **ruteo de vehículos eléctricos (EV Routing Problem, EVRP)** para una
hackathon. Escenario: empresa CASE, consultora ZMD Mobility. Con **2 vehículos
eléctricos** y **81 ubicaciones de servicio**, el objetivo es:

1. **Maximizar el número de entregas** (prioridad 1).
2. **Minimizar la energía neta consumida** (prioridad 2), con el número de
   entregas ya fijado.

Es un objetivo **lexicográfico** en dos fases: primero entregas, luego energía.

Zona geográfica: **Ann Arbor, Michigan** (centro aprox. `[-83.753, 42.274]`).

### Estructura de carpetas

```
AWS-Hackaton-main/
├─ AWS-Hackaton-modelamiento/   ← rama de modelado (motor MILP, la principal)
├─ AWS-Hackaton-main/           ← copia/variante del modelado
├─ AWS-Hackaton-codex-ui/       ← interfaz de usuario (mapas, exploraciones)
├─ Electromovilidad/            ← datos (CSV de nodos y dataset eVED de energía)
├─ Diccionario/                 ← glosario/documentación
├─ analyze_instance.py          ← script de diagnóstico del grafo real (añadido)
└─ ANALISIS-PROYECTO.md         ← este documento
```

---

## 2. Datos reales medidos (instancias oficiales)

Medido con `analyze_instance.py` sobre `competition_routing_nodes.csv` y
`evaluation_routing_nodes.csv` (ambas idénticas en estructura):

| Métrica | Valor |
|---|---|
| Nodos totales | 81 |
| — base | 1 (`BASE`) |
| — visitas (clientes) | 20 |
| — cargadores | 60 |
| Distancia base→visita | 1,0 – 7,8 km (media ~4,9) |
| Diámetro de la zona (entre visitas) | 13,7 km |
| Capacidad de batería | 24 kWh |
| Reserva | 2,4 kWh |
| SoC inicial | 60 % |
| Energía utilizable inicial | 12,0 kWh |
| **Alcance con SoC inicial** | **80 km** (@ 0,15 kWh/km) |
| **Alcance a batería llena** | **144 km** |
| Visitas sin ida+vuelta directa sin recargar | **0 de 20** |
| Peor distancia visita→cargador más cercano | 2,97 km |

### Conclusión clave de los datos

El área es **pequeña** (13,7 km) frente a un alcance **grande** (80–144 km). Por
tanto **la restricción de batería está holgada**: la recarga casi nunca es un
cuello de botella en estas instancias. Esto hace que el problema se parezca más
a un **VRP clásico de 20 clientes + 2 vehículos** (tratable) que a un EVRP con
recarga apretada (difícil).

El verdadero costo computacional **no** viene del algoritmo ni de la recarga,
sino de una **decisión de modelado** (ver sección 5).

---

## 3. Algoritmos y componentes de optimización

> Importante: el proyecto **no** usa una metaheurística propia. Formula un
> **MILP** (programación lineal entera mixta) en Pyomo y lo resuelve con solvers.

### 3.1 Núcleo: MILP lexicográfico (`model.py` + `solve.py`)

Traduce directamente las ecuaciones (1)–(16) de `modelamiento.pdf`.

**Variables:**
- Binarias: `y` (entrega), `z` (ocupación de nodo), `x` (arco recorrido),
  `a` (servicio), `gamma` (saturación de batería).
- Continuas: `b` (batería al llegar), `b_departure` (al salir), `q` (recarga),
  `u`, `E`, `E_total` (energía).

**Dos fases:**
- Fase 1: maximizar entregas (`deliveries_objective`).
- Fase 2: fijar ese número con una igualdad y minimizar energía
  (`energy_objective`).

**Características a tener en cuenta:**
- **Red vial dirigida real**, no una matriz TSP entre clientes. Cada
  `x[i,j,k,r]` selecciona un tramo elemental de calle.
- `r` cuenta **movimientos**, no tiempo ni segundos.
- Horizonte `H` (`movement_limit`, por defecto 30): límite de movimientos.
  Reducirlo puede hacer el problema **infactible** aunque sobre energía.
- **Batería con regeneración saturada:** `b[k,r+1] = min(B, u)` linealizado
  exactamente con `gamma` (ec. 13). La energía regenerada que no cabe se
  descarta y **no** reduce el consumo efectivo (por eso el objetivo no es
  `sum(e*x)`).
- Parámetros oficiales: 2 vehículos, `initial_soc=0.6`, capacidad/reserva/SoC
  compartidos. El depósito **nunca** es cargador.

### 3.2 Solvers (`solve.py`, `docs/solvers.md`)

- **Backends:** Gurobi (vía `gurobi_direct`) y SCIP.
- **Modo `auto`:** intenta Gurobi y hace *fallback* a SCIP **solo** por
  indisponibilidad/licencia (no por infactibilidad, timeout ni cota débil).
- **Parámetros configurables:** presupuesto de tiempo, gap, hilos, semilla, tee.

| Config | Gurobi | SCIP |
|---|---|---|
| Tiempo | `TimeLimit` | `limits/time` |
| Gap | `MIPGap` | `limits/gap` |
| Hilos | `Threads` | `parallel/maxnthreads` |
| Semilla | `Seed` | `randomization/randomseedshift` |

- **Presupuesto compartido:** un reloj desde antes de construir Pyomo. 70 % del
  tiempo restante para entregas (`DELIVERY_BUDGET_FRACTION=0.7`), el 30 % + lo
  no usado para energía. Nunca se reinicia al cambiar de backend.
- **Límites blandos:** construcción/arranque/retorno pueden exceder el tiempo.
- **Certificados:** distingue `feasible` de `optimal`; `lexicographic_optimal`
  solo si ambas fases prueban optimalidad. Tolerancia `1e-7`.

### 3.3 Red / grafo vial (`network.py`)

- Usa **OSMnx + NetworkX + pyproj**. Carga GraphML local o descarga de
  OpenStreetMap (solo con `allow_download=True`, `simplify=False`).
- Requiere red **dirigida** en EPSG:4326; no inventa sentidos.
- **Snapping:** cada servicio se conecta a su intersección más cercana con dos
  arcos de acceso bidireccionales (`max_snap_distance_m=100`).
- Subdivide paralelos y autoarcos para cumplir el contrato `(i,j)` del PDF.
- Distancia por **haversine**; energía por arco = distancia × `kwh_per_km`.
- **Sin regeneración en arcos OSM** (`"regeneration_on_osm_arcs": False`) → los
  pesos de energía son **positivos**.
- Registra procedencia con SHA-256, atribución OSM (ODbL) y supuestos.

### 3.4 Modelo de energía (`energy.py`)

- Calibración **distancia-only**: `kWh/km = energía neta total / distancia`
  sobre intervalos válidos del dataset eVED.
- Integra con pandas/numpy, Δt real por `(VehId, Trip)`, cuadratura de extremo
  derecho, excluye huecos > 10 s, **no interpola**.
- Determinista; no modela pendiente, tráfico, clima ni auxiliares.
- Caché invalidada por SHA-256 del contenido.

### 3.5 Validación independiente (`validation.py`)

Comprueba las rutas del solver de forma **independiente** (no confía en los
valores internos del modelo). Toda solución, aunque el solver la declare óptima,
debe pasar este validador.

### 3.6 Tuning LLM (`llm/tuning.py`)

- **Desactivado a propósito** (`status: "disabled"`, `propose_tuning` lanza
  `NotImplementedError`).
- Esqueleto futuro para sugerir parámetros de solver vía AWS Bedrock (LLM4MIP).
- **No** ejecuta LLM ni cambia B, reserva, H ni objetivos. No cuenta como
  "algoritmo" hoy.

---

## 4. Sobre Dijkstra y "el mejor algoritmo"

Hay **dos problemas anidados**, cada uno con su mejor algoritmo:

### Nivel 1 — Decisión global (qué entregar, qué vehículo, qué orden, cuándo recargar)
- Es el EVRP. Su mejor algoritmo es el **MILP lexicográfico ya existente**.
- Da el **óptimo certificado** (valioso en un hackathon).
- **Dijkstra NO sirve aquí:** no decide asignación de vehículos, ni qué clientes
  servir, ni el orden. Solo encuentra un camino entre dos puntos.

### Nivel 2 — Subproblema (ir de A a B con mínima energía respetando reserva)
- **Aquí Dijkstra SÍ es el mejor**, porque los pesos de energía son **positivos**
  (sin regeneración en arcos OSM). Dijkstra es óptimo y eficiente exactamente
  con pesos no negativos.

### ¿Cuándo Dijkstra dejaría de ser el mejor?

| Situación | Mejor algoritmo |
|---|---|
| Pesos positivos (caso actual) | **Dijkstra** ✅ |
| Arcos con energía negativa (regeneración real en calles) | Bellman-Ford / labeling SPPRC |
| Camino factible con estado de batería como recurso | A\* / SPPRC con etiquetas |
| Grafo gigante, se busca rapidez con heurística geográfica | A\* (Dijkstra + heurística) |

Como los pesos son positivos y el grafo es pequeño, **Dijkstra puro es correcto
y no hay nada mejor que aporte valor real aquí**. A\* sería una micro-optimización
innecesaria a esta escala.

---

## 5. El cuello de botella real (y la mejora de mayor impacto)

El MILP **no** opera sobre los 81 nodos de servicio. `network.py` engancha cada
uno a la **red vial OSM completa** y crea binarias:

- `x[i,j,k,r]`: arco × vehículo × posición → `|A| · K · H`
- `z[i,k,r]`: nodo × vehículo × posición → `|V| · K · (H+1)`

Con `|A|` del orden de cientos–miles de arcos viales, `K=2`, `H=30`, esto son
**decenas o cientos de miles de binarias**. Con `time_limit=60 s` rara vez cierra
el gap en instancias reales (solo lo logra en los *fixtures* pequeños de tests).

**El problema nunca fue el algoritmo. Fue la arquitectura del modelo.**

### Solución: descomposición en 2 capas

1. **Capa inferior:** precalcular con **Dijkstra** (pesos positivos) la
   energía/distancia mínima entre cada par de {base, 20 visitas, cargadores
   útiles}, respetando la reserva en cada tramo elemental.
2. **Capa superior:** resolver el **MILP** sobre ese grafo reducido de ~decenas
   de nodos en vez de la red vial completa.

**Advertencia (del propio `model.md`):** la descomposición solo es válida si el
Dijkstra de la capa inferior respeta la reserva **durante** todo el camino, no
solo al final. Con pesos positivos y batería decreciente entre recargas, el
camino de mínima energía es también el que menos exige la reserva, así que
Dijkstra sigue siendo correcto.

---

## 6. Recomendaciones priorizadas (mayor a menor retorno)

### Preprocesamiento
1. **Descomposición 2 capas + Dijkstra con reserva** → resuelve el cuello real.
2. **Poda de cargadores:** 60 cargadores con batería holgada; muchos nunca se
   usarán. Filtrar a los útiles reduce `z` y `F_compatible`.
3. **Ajuste de `H`:** sobre el grafo reducido, `H` cuenta visitas/cargas (no
   tramos de calle), así que un `H` mucho menor basta y recorta dimensiones.

### Solver (ganancias "gratis")
4. **`threads` = núcleos reales** (hoy está en 1).
5. **Warm start:** solución inicial greedy (vecino más cercano respetando
   batería) como incumbente → acelera el cierre del gap.
6. **Reparto de presupuesto:** con grafo reducido la fase 1 es trivial; dar más
   tiempo a la fase 2 (energía).

### Lo que NO conviene cambiar
7. Dejar el **MILP lexicográfico** y los **solvers** como están: son correctos.
   Solo cambia *sobre qué grafo* corren.
8. **No** usar metaheurísticas (ALNS, tabú, genéticos): sobre-ingeniería para 20
   clientes con batería holgada.
9. **No** contar con el **LLM tuning**: está desactivado a propósito.

---

## 7. El mapa en los archivos

**Sí hay mapa**, en la UI (`AWS-Hackaton-codex-ui`), no en la rama de modelado.

- **Mapa funcional:** `explorations/webapp/map.js` y versiones en
  `round-2/shared/map.js`, `round-3/shared/map.js`.
  - **MapLibre GL JS** (vendorizado local, BSD-3), estilo **Positron**,
    centrado en `[-83.753, 42.274]`, zoom 11.3.
  - Dibuja los 81 nodos (base/paradas/cargadores) y rutas por vehículo,
    selección por ID, manejo de errores (muestra lista de paradas como respaldo).
- **Exploración dedicada:** `explorations/round-2/mapa/` (`app.js`, `index.html`).
- **Decisión cartográfica:** `docs/MAPA-Y-BASE.md` recomienda MapLibre GL JS como
  renderer + Amazon Location Maps como proveedor (alternativa MapTiler), con
  análisis de licencias (OSM/ODbL) y costos AWS.
- **Skill de mapa:** `.kiro/skills/zmd-map-ui/`, `.claude/...`, `.agents/...`.
- **Evidencia de precios:** `docs/evidence/map-pricing-20261014.json`.

### Cómo ejecutar el mapa en localhost

```powershell
# 1. Generar el fixture local (requiere internet; consulta OSRM una vez):
python explorations/round-2/shared/prepare-local-fixture.py `
    ..\..\..\Electromovilidad\competition_routing_nodes.csv

# 2. Levantar el servidor:
python -m http.server 4173 --bind 127.0.0.1 --directory explorations

# 3. Abrir en el navegador:
#    http://127.0.0.1:4173/round-2/mapa/
#    http://127.0.0.1:4173/round-2/      (comparar las 4 vistas)
```

### ⚠️ Punto crítico sobre el mapa

El mapa es **solo visualización con datos de diseño inventados a mano** (lo dice
su propio `README.md` y el diálogo "Acerca de"). Las rutas y energías que muestra
(p. ej. 35,4 y 75,2 km) **NO vienen del solver**: salen de OSRM sobre un orden de
visitas escrito manualmente. Sirve para *ver* la geografía, no para decidir el
algoritmo ni acreditar factibilidad/optimalidad. Eso lo decide el motor MILP y lo
verifica `validation.py`.

---

## 8. Herramienta de diagnóstico añadida

`analyze_instance.py` (en la raíz) calcula las métricas de la sección 2 a partir
de los CSV reales, usando distancias haversine. Reproduce con:

```powershell
python analyze_instance.py
# o para un CSV específico:
python analyze_instance.py ruta\al\archivo_routing_nodes.csv
```

No usa el solver ni inventa rutas: es un diagnóstico puro de las instancias.

---

## 8-bis. ACTUALIZACIÓN — El nuevo motor `AWS-Hackaton-codex-optimizacion-contraida`

> Esta sección se añadió **después** de redactar el resto del documento, al
> detectar una carpeta nueva en la raíz: `AWS-Hackaton-codex-optimizacion-contraida/`
> (paquete `evrp` / "evrp-lab"). Es relevante porque **implementa precisamente la
> mejora de mayor impacto que recomendaba la sección 5** (descomposición en 2
> capas) y añade capacidades que el motor `modelamiento` no tenía. Verificado
> leyendo su código (`src/evrp/`), no solo su README.

### Qué es

Un **segundo motor E-VRP "contraído"** para el mismo desafío CASE. En vez de
resolver el MILP sobre toda la red vial OSM, hace la descomposición en 2 capas:

1. **Etapa "preparar" (preprocesamiento):** lee la red vial OSM, engancha cada
   nodo clave a la calle y **precalcula el camino de mínima energía entre cada
   par** de {base, clientes, cargadores}. Produce una *instancia preparada*
   (`evrp.instancia_preparada/1`, JSON/gzip ~0,3–0,9 MB) que ya es el **grafo
   reducido de nodos clave** con sus tramos elementales `tramos["i|j"]`.
2. **Etapa "resolver" (solver):** aplica poda de cargadores, heurística, MILP y
   validador sobre ese grafo pequeño. Se puede re-resolver con otra batería,
   flota o nodos excluidos **sin volver a preparar**.

Esto confirma el diagnóstico de la sección 5: el cuello de botella era
arquitectónico, y la solución correcta es contraer la red antes del MILP.

### Diferencias clave frente al motor `modelamiento`

| Aspecto | `AWS-Hackaton-modelamiento` | `codex-optimizacion-contraida` (`evrp`) |
|---|---|---|
| Arquitectura | MILP sobre toda la red vial | **2 capas: Dijkstra/A\* + MILP sobre grafo reducido** |
| Solver MILP | Gurobi / SCIP (Pyomo) | **HiGHS** (`highspy`), sin licencia comercial |
| Caminos capa inferior | — (lo hace el MILP) | scipy (defecto), **Dijkstra, A\*, bidireccional, ALT, networkx** |
| Energía | distancia-only | distancia-only **+ pendiente/elevación opcional** |
| Elevación | no | **eVED, USGS, Copernicus** (`src/evrp/elevacion/`) |
| Heurística inicial | no (o warm start manual) | **tour gigante + 2-opt + split + reparación de batería** |
| LLM | esqueleto desactivado | **asesor Bedrock real** (opcional, con lista blanca) |
| Idioma del código | inglés | español |

### Algoritmos y cosas a tener en cuenta (verificado en código)

**Capa inferior — caminos de mínima energía (`caminos.py`):**
- Varios algoritmos exactos sobre un `GrafoCaminos` común con **costos reducidos
  no negativos**: `c̃(u,v) = e(u,v) + p(u) − p(v) ≥ 0`, con potencial
  `p(v) = κ·η_r·h(v)`. Esto permite usar **Dijkstra incluso con pendiente**
  (regeneración), porque los costos reducidos quedan ≥ 0.
- **A\*** con heurística admisible y consistente `h(v) = c·haversine(v,t) + p(v) − p(t)`.
  En perfil "plano" `p≡0` y queda `h(v) = c·haversine(v,t)`.
- Opciones: `scipy` (defecto, el más rápido medido), `multi_destino`,
  `bidireccional`, `a_estrella`, `alt`, `networkx`. Todos deben dar la **misma
  energía por par** (se verifica).

**Capa superior — MILP compacto (`milp_compacto.py`):**
- Formulación **compacta**: los cargadores se modelan como **atributo de arco**
  `a = (i, j, f)` (ir de i a j directo o pasando por un cargador f). Por defecto
  carga completa e instantánea; con `carga.max_min_por_parada` se acota la carga
  por parada (restricciones 7' y 10').
- Para cada par (i,j) conserva solo los cargadores **Pareto-óptimos** en
  (energía, batería requerida al salir, batería al llegar), hasta
  `cargadores_por_arco`.
- Conectividad por **MTZ con elevación de Desrochers–Laporte** (o cortes).
- Caso F→F (encadenar cargadores por alcance) queda fuera de la compacta → usar
  `solver.formulacion = completa` (`milp.py`).
- Dos fases lexicográficas (igual que el otro motor): maximizar entregas, luego
  minimizar energía.

**Heurística (`heuristica.py`):** tour gigante → 2-opt → split (partición óptima)
→ reparación de batería insertando cargadores. Sirve como (1) warm start del
MILP, (2) certificado de N\* cuando atiende a todos, y (3) solver autónomo
(`pipeline.solver = heuristica`).

**Escala y poda (`config.py`):** `k_vecinos="auto"` → **exacto hasta 25 clientes**
(`umbral_exacto`), k-vecinos por encima; esto encaja con los **20 clientes
reales** medidos en la sección 2 → el problema es exacto sin podar. Presupuesto
con piso (`min_s=10 s`) y `presupuesto_total_s`.

**Asesor IA (`asesor.py`):** ahora sí hay integración **Bedrock real** (modelo
por defecto `us.anthropic.claude-sonnet-4-6`), pero con salvaguardas fuertes:
- `AsesorNulo` es el valor por defecto; el motor **nunca depende** del LLM.
- Solo puede tocar 3 claves de config vía **lista blanca** (`AJUSTES_PERMITIDOS`):
  `pipeline.cargadores`, `cargadores.top_r` (1–10), `solver.tiempo_limite_s` (1–600).
- Toda propuesta se **filtra y pasa por el validador**. Cualquier fallo degrada a
  vacío/None. También puede **explicar** la solución en lenguaje natural.

**Parámetros por defecto a tener en cuenta (`config.py`):**
- Vehículo `leaf2013`: batería 16 kWh, SoC inicial 60 %, reserva 10 %, consumo
  0,156 kWh/km, conectores CHAdeMO/J1772, DC 50 kW / AC 6,6 kW. (El perfil
  `ev_routing` sube a **24 kWh** para igualar los supuestos de `modelamiento`.)
- `pipeline`: red `osm`, energía `plano`, cargadores `dominancia`, inicial
  `insercion`, solver `milp`.
- Mapa vial **empaquetado**: `src/evrp/assets/osm/ann_arbor_drive.graphml.gz`
  → corre **sin internet**. La línea recta solo se usa si se activa
  `red.respaldo_linea_recta`.

### Cómo ejecutarlo

```powershell
uv sync --extra ia                 # + --extra elevacion para Copernicus
# Etapa 1 (preparar) + Etapa 2 (resolver) de una vez:
uv run evrp solve --nodes data/competition_routing_nodes.csv --perfil ev_routing --out results/comp
# O por separado (re-resolver sin re-preparar):
uv run evrp preparar --nodes data/competition_routing_nodes.csv --perfil ev_routing --out results/comp.json.gz
uv run evrp resolver --instancia results/comp.json.gz --perfil ev_routing --vehiculos 3 --out results/comp
uv run pytest -q -m "not bedrock"
```

### Lectura conjunta de los dos motores

- `modelamiento` = **referencia fiel al PDF** (ecuaciones 1–16, Gurobi/SCIP),
  pesada en instancias grandes.
- `codex-optimizacion-contraida` = **misma lógica EVRP pero con la mejora de la
  sección 5 ya implementada** (contracción + Dijkstra/A\* + HiGHS gratis +
  heurística + elevación + Bedrock opcional). Es la vía práctica para resolver
  las 81 ubicaciones reales en tiempo de hackathon.
- Ambos conservan la separación sana: **el motor decide y un validador
  independiente comprueba**; el mapa de la UI solo visualiza.

---

## 9. Resumen en una frase

El motor (MILP lexicográfico + Gurobi/SCIP) y los algoritmos (Dijkstra para
caminos, MILP para la decisión global) **ya son los correctos**; el problema es
**arquitectónico** —el MILP corre sobre toda la red vial en vez de un grafo
reducido—, y las instancias reales son **pequeñas y poco restringidas**, así que
la mejora de mayor retorno es la **descomposición en 2 capas**, no cambiar de
algoritmo.
