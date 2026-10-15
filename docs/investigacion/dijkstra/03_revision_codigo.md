# 03 — Revisión de código (etapa red y caminos)

Revisor de código, solo lectura. Archivos: `src/evrp/red.py`, `caminos.py`,
`energia.py`, `instancia.py`, `preparacion.py`, `validador.py`, uso en
`milp_compacto.py`. Evidencia: `uv run pytest -q -m "not bedrock"` sobre
`test_caminos.py test_motor.py test_preparacion.py` → **33 passed in 75.96s**.
Mediciones con `competition_routing_nodes.csv` (grafo empaquetado, 9688 nodos /
24014 arcos). Lo no verificado se marca con ⚠.

## 1. Corrección del Dijkstra con potencial y aristas negativas

El potencial `p(v)=κ·η_r·h(v)` se arma en `red.py:220-221` y el costo reducido
en `red.py:230` como `max(red, 0.0)`, con `red = e(u,v)+p(u)−p(v)`.

| Caso | Hallazgo | Ref |
|---|---|---|
| Descenso `Δh<0` | `e=κ·η_r·Δh`, `p(u)−p(v)=−κ·η_r·Δh` ⇒ reducido **=0 exacto** | energia.py:38-41 |
| Ascenso `Δh>0` | reducido `=κ·Δh·(1/η_d−η_r)`. Como `η_d≤1` y `η_r≤1` ⇒ `1/η_d−η_r≥0` **siempre** | post_init energia.py:30-34 |
| ¿η_r>η_d rompe? | **No** mientras el potencial use η_r (no η_d). Verificado: con η_d=0.5, η_r=0.9 el reducido de ascenso sigue ≥0 (1/η_d−η_r=1.1) | — |

- **`max(red,0.0)` SÍ puede ocultar errores** (red.py:230): en la config real nunca
  recorta (medido: `min_reduced_pre_clamp=+1.1e-4`, `arcos_clamped=0`), pero el clamp
  es silencioso. Si alguien cambiara el potencial a `κ·η_d·h` o introdujera un término
  de tiempo/giros negativo, el clamp **falsearía la energía del arco** sin avisar.
  Recomendación: `assert red >= -EPS` (o `log.warning` + contador) antes de recortar.
- **Elevación ruidosa**: el modelo asigna un desnivel neto por arco; el ruido crea
  pares con `Δh` espurio. No genera **ciclos negativos** porque los reducidos son ≥0
  (medido: 0 reducidos negativos con `eved`; 201 arcos con energía *cruda* negativa,
  todos saneados por el potencial). Riesgo real: subestimar energía de bajadas
  (regenera "de más") — ver §3. Validado contra realidad ⚠ no.
- **Aristas paralelas**: resueltas en red.py:224-228 quedándose con el arco de **menor
  energía** por par `(u,v)` (`mejor[(u,v)]`). Correcto para energía, pero descarta
  info de longitud/sentido de los paralelos; si luego se añade tiempo, elegir por
  energía puede no ser el arco de menor tiempo (bug latente, ver §3).
- **Acceso punto→calle** (`_ajustar_calle`, red.py:155-187): snap vectorizado a la
  geometría de la calle (no al cruce), con `stub_km` sumado como tramo **plano
  (Δh=0)** y en **línea recta** (red.py:289-295). Supuesto: el acceso no tiene
  pendiente ni sentido; aceptable para accesos cortos, cuestionable si `stub_km` es
  grande. `max_acceso_m` por defecto `None` ⇒ **no hay tope** (un nodo lejano se
  conecta igual). ⚠ revisar con los nodos reales.
- **Sentido de las calles**: el grafo es dirigido (`graph_from_bbox(network_type=
  "drive")` + `largest_component(strongly=True)`, red.py:134-137) y la adyacencia solo
  usa `G.edges` dirigidos ⇒ sentidos respetados. El snap, en cambio, asigna **un solo
  nodo** por extremo de calle; en calles de un sentido el acceso podría caer en el
  extremo "equivocado" y forzar un rodeo. ⚠ no verificado.

**Consistencia entre algoritmos**: `test_caminos.py` confirma que los 6 algoritmos
dan la misma energía por par (juguete y mapa real, tol 1e-9). Dijkstra con este
potencial es exacto. ✔

## 2. ¿El camino de mínima energía puede ser infactible por SoC?

**Sí, y es el riesgo central del diseño "un solo camino por par".** La elección se
hace por **energía total ê** en `caminos.py` (Dijkstra), *antes* de conocer la
batería. Los estadísticos de SoC (π̂ pico, λ̂ tramo continuo, σ̂) se calculan en
`instancia.py:30-37` (`estadisticos`) sobre **ese único camino ya fijado**.

Demostración (toy, verificada): dos caminos con la **misma** ê=1.0 kWh; A con
`π̂=2.0` y B con `π̂=1.0`. Con margen disponible 1.5 kWh, **B es factible y A no**.
Como ê empata (o A es menor), Dijkstra puede devolver A y los filtros descartan el
par entero, aunque B existía.

Dónde se detecta/descarta hoy:

| Mecanismo | Archivo:línea | Qué hace |
|---|---|---|
| Filtro (a) λ̂ | instancia.py:198-200 | descarta arco si `λ̂ > B−b_min` |
| Filtro (b) π̂ | instancia.py:201-204 | salida de base/cargador: `β < b_min+π̂` ⇒ descarta |
| Filtro (c) π̂ | instancia.py:205-206 | entrada cliente: `b_min+π̂ > B` ⇒ descarta |
| `rho` | instancia.py:66-68 | batería a la llegada: `min(β−ê, B−σ̂)` (σ̂ satura regen) |
| Validador | validador.py:38-57 | re-simula tramo a tramo; `b < b_min` ⇒ error (red.py vía `red.tramos`) |

Consecuencia: el motor **descarta el par** (lo marca infactible) en vez de buscar
otro camino con menor π̂ ⇒ **puede declarar infactible un arco que sí tenía ruta
válida**. El validador (independiente) solo revisa la ruta elegida por el MILP; no
rescata el par. Mitigación correcta = top-k / Pareto por par (ver docs 01/02 y §3).

## 3. Supuestos codificados y dónde tocar para extender

| Supuesto | Dónde está codificado | Para añadir… |
|---|---|---|
| **Sin tiempo / sin velocidad** | `Tramo=(km,Δh)` red.py:21; `energia.tramo` ignora v | añadir `t_arco` a la adyacencia red.py:224-230 y a `Tramo`; nuevo potencial/segundo peso en `GrafoCaminos` caminos.py:46-83 |
| **Sin giros** | adyacencia por nodo, no por arco (red.py:224) | expandir a grafo de líneas (arco→nodo) o penalización de giro en `_construir_adyacencia` |
| **Sin límite de potencia de regen** | `energia.tramo` usa `η_r·Δh` lineal, sin tope (energia.py:38-41); σ̂ limita *almacenamiento* no *potencia* | tope por tramo en `tramo()` (requiere km/velocidad ⇒ depende de tiempo) |
| **Regen solo por bajadas** | `Δh<0 ⇒ η_r·Δh` (energia.py:40) | ya es el modelo del PDF; refinar con curva v-dependiente ⚠ |
| **Un camino por par (min ê)** | `resolver_caminos` caminos.py:598-604; resumen `_estad_par` instancia.py:191 | devolver **k caminos** o frente Pareto (ê, π̂, t) desde `caminos.py`; `instancia.construir` debe iterar sobre varios caminos por par y dejar que el MILP elija |
| **Límite de tiempo por trayecto X min** | no existe | filtro nuevo tras `_estad_par` (descartar par con `t̂ > X`) y/o restricción en `milp_compacto.py` |
| **Pareto (ê, π̂, t)** | hoy solo ê | Dijkstra multiobjetivo/etiquetas (NAMOA\*) en `caminos.py`; `GrafoCaminos.ady` debe llevar `(v, red, km, dh, t)` |

Para **tiempo por arco + tope por trayecto**: tocar `Tramo`, `_construir_adyacencia`
(red.py:208-233), `GrafoCaminos` (caminos.py), `_estad_par`/`construir`
(instancia.py:191,215-239) y añadir restricción en `ModeloCompacto._construir`
(milp_compacto.py:160-205). El `Arco` compacto (milp_compacto.py:60-67) también
necesita campo `t`.

## 4. Eficiencia (medido, config real `scipy`, descarga off)

| Etapa | Tiempo (s) plano | con `eved` | Cuello |
|---|---|---|---|
| carga_grafo | 5.49 | 5.55 | **dominante** (I/O + osmnx `load_graphml`) |
| ajuste_calle | 1.95 | 1.67 | 2.º; itera `G.edges` en Python (red.py:160-179) |
| elevacion | — | 0.08 | bajo |
| adyacencia | 0.055 | 0.075 | bajo (cacheable en .npz, red.py:235) |
| caminos (scipy) | 0.56 | 0.36 | bajo |

- `carga_grafo` domina; la caché de adyacencia (`_cargar_adyacencia`, red.py:255-274)
  **no** cachea el grafo cargado, solo la adyacencia derivada. ⚠ oportunidad: cachear
  CSR del grafo.
- `_ajustar_calle` recorre todos los arcos y sus geometrías en bucle Python
  (red.py:160-179); escala O(aristas·puntos). Para mapas mayores conviene vectorizar
  o usar `ox.distance.nearest_edges`.
- `scipy` es el mejor algoritmo medido (caminos.py:591 `ALGORITMO_POR_DEFECTO`),
  coherente con `docs/experimentos/caminos.md`. ✔
- `GrafoCaminos._csr` se reconstruye tras limpiar `_csr=None` en los tests
  (caminos.py:541-559); en producción se arma una vez. OK.

## 5. Bugs / riesgos concretos

1. **(Alto) Infactibilidad por SoC oculta** — §2. Un solo camino por par elegido por
   ê puede tener π̂ alto y ser descartado aun existiendo ruta factible. instancia.py:
   191,198-206. Fix: top-k/Pareto por par.
2. **(Medio) `max(red,0.0)` silencioso** — red.py:230. No recorta hoy (medido) pero
   ocultaría un potencial mal definido o un peso negativo futuro. Añadir asserción.
3. **(Medio) `max_acceso_m=None` sin tope** — red.py:70,180-184. Un nodo mal
   geocodificado se enlaza con stub arbitrariamente largo, plano y recto; sesga ê.
4. **(Medio) Stub de acceso plano y recto** — red.py:285-295, `tramos()`. Ignora
   pendiente y sentido del tramo de acceso; `Δh=0` fijo.
5. **(Bajo) Arcos paralelos elegidos por energía** — red.py:224-228. Al añadir tiempo,
   el arco de menor energía puede no ser el de menor tiempo.
6. **(Bajo) `_firma_adyacencia` redondea elevación a 3 decimales** — red.py:252.
   Cambios de elevación < 1 mm reutilizan caché; irrelevante en la práctica.
7. **(Bajo) Validador recorre `red.tramos` por ruta** — validador.py:38,98-104. En
   `_energia_efectiva` repite la expansión de tramos (O(nodos·tramos)); correcto pero
   podría memoizarse si se validan muchas rutas.
8. **(Nota) Elevación degrada a plano en silencio** — red.py:312-318
   (`aplicar_elevacion` captura toda excepción y usa terreno plano con `log.warning`).
   El resultado cambia sin fallar; queda en `meta_elevacion.error`. ⚠ verificar en KPIs.

**Conclusión**: el Dijkstra con potencial es correcto y exacto para la métrica de
energía (tests ✔, reducidos ≥0 verificados). La limitación de corrección "realista"
no está en Dijkstra sino en el **compromiso de un solo camino por par** (§2) y en los
supuestos de acceso/tiempo/regen (§3). Prioridad: top-k/Pareto por par y asserción en
el clamp.
