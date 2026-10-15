# 04 — Diseño del algoritmo de caminos (Dijkstra → RCSPP Pareto)

**Rol:** razonador / diseñador de algoritmo. Síntesis de `01_literatura.md`,
`02_datos_energia.md`, `03_revision_codigo.md`. Objetivo: dejar especificado un
subproblema de caminos entre nodos clave que sea **correcto** (SoC ≥ 0 en todo punto,
tope batería), **eficiente** (81–200 nodos clave sobre ~10k viales) y **defendible**
(energía con regeneración acotada, tiempo por trayecto). No se edita código; esto es
diseño.

Convención: **[V]** verificado con DOI/URL; **[P]** parcial; **[NV]** no verificado.

---

## A. Formulación precisa del subproblema de caminos

### A.1 Grafo y atributos por arco

Grafo **dirigido** `G = (V, A)`, `|V| ≈ 9.7k`, `|A| ≈ 24.5k` (OSM Ann Arbor,
`network_type="drive"`, componente fuertemente conexa). Subconjunto de **nodos clave**
`K ⊂ V`: base `o`, 20 clientes `C`, ~54 cargadores compatibles `F` ⇒ `|K| ≈ 75`
(81–200 según variante). Cada arco `a=(u,v)` lleva:

| Atributo | Símbolo | Fuente | Signo |
|---|---|---|---|
| Longitud | `ℓ_a` (km) | geometría OSM | ≥0 |
| Desnivel | `Δh_a` (m) | DEM USGS/Copernicus | con signo |
| Tiempo | `t_a` (min) | `ℓ_a / v_ef(highway,maxspeed)` (tabla §4 doc 02) | ≥0 |
| Energía | `e_a` (kWh) | modelo §C | **con signo** (regen ⇒ e_a<0) |

Constantes de vehículo: capacidad útil `B` (kWh, ajustada por SoH
A2 [V]); reserva `b̲` (kWh, mínimo operativo, p.ej. 10 % de B); SoC de salida `β`
(0,60·B nominal en el CASE).

### A.2 Dinámica de SoC con tope de batería

Recorriendo un camino `P = (v_0=s, …, v_k=d)` desde SoC inicial `β`, el estado evoluciona
con **saturación por batería llena** (la regeneración no puede sobrepasar `B`):

```
b_0 = β
b_{i} = min{ B ,  b_{i-1} − e_{a_i} }         (regen ⇒ −e_a>0 ⇒ sube, topado en B)
Factibilidad:  b_i ≥ b̲   para TODO i = 0..k    (nunca por debajo de reserva)
```

Dos observaciones que condicionan el algoritmo (doc 02 §6, doc 03 §2):

1. **El `min{B,·}` destruye la telescopía.** La energía neta de un camino deja de ser la
   suma de `e_a` cuando hay bajadas que "desbordan" la batería; `b_k` ya no es
   `β − Σe_a`. Por eso Dijkstra con potencial (exacto para `Σe_a`) **no** es exacto para
   el SoC real cuando la batería se llena en una bajada.
2. **La factibilidad punto a punto no es una función de la energía total.** Dos caminos
   de igual `Σe_a` pueden diferir en el **pico de consumo acumulado** `π̂` (máxima caída
   de SoC desde la salida). Ejemplo verificado en doc 03 §2: `ê` empata, `π̂`=2.0 vs 1.0;
   con margen 1.5 solo el de `π̂`=1.0 es factible.

### A.3 Estadísticos por camino (interfaz con el MILP actual)

Para un camino se resumen (como hoy en `instancia.py`, extendido con tiempo):

| Estadístico | Definición | Rol |
|---|---|---|
| `ê` | energía neta recomendada = `Σ e_a` **con regen conservadora** | coste de arco MILP |
| `π̂` | `max_i (β − b_i)` sin saturar = **pico de consumo acumulado** | SoC de salida requerido: `β ≥ b̲ + π̂` |
| `σ̂` | energía regenerada que se perdería por saturación (regen − aceptada) | corrige SoC de llegada |
| `λ̂` | mayor subida continua (tramo monótono de consumo) | cota `λ̂ ≤ B − b̲` |
| `t̂` | `Σ t_a` | restricción temporal (§A.4) |

Batería a la llegada en función de la de salida (doc 03 `rho`):
`b_llegada(β) = min{ β − ê ,  B − σ̂ }`, válido solo si el camino es SoC-factible desde `β`.

### A.4 Restricción temporal: definición de "trayecto" (dos opciones)

La frase "cada trayecto dura ≤ X minutos" admite dos lecturas; **recomiendo la primera**
y expongo ambas:

| Lectura | Definición | Dónde se impone | Consecuencia MILP | Veredicto |
|---|---|---|---|---|
| **(i) Entre paradas** (recomendada) | `t̂_{s→d} ≤ T_max` para cada par de nodos clave | **en caminos**: podar camino/arco con `t̂ > T_max` | Simple: elimina arcos del MILP (o filtra Pareto). Local, descomponible | ✅ Preserva la separación caminos/MILP; T_max actúa como recurso local no-negativo (B6/B7 [V]) |
| **(ii) Ruta completa** | `Σ_tramos t̂ + t_servicio + t_carga ≤ Jornada` | **en MILP**: restricción de recurso acumulado sobre la ruta | Requiere variable de tiempo acumulado por vehículo (como E-VRPTW, B8 [V]) | Útil como jornada global; **no** sustituye (i) |

Lo correcto es **ambas, en capas distintas**: (i) poda caminos irrealistas por tramo en
la etapa de caminos; (ii), si se requiere, se modela como ventana/jornada global en el
MILP. La (i) es puramente local y no acopla vehículos ⇒ no complica el MILP; la (ii) sí
añade una fila de recurso por ruta. Para el CASE (2 Leaf, max entregas → min energía),
(i) basta para realismo de tramo; (ii) solo si hay límite de jornada explícito.

---

## B. Algoritmo recomendado, alternativas y corrección

### B.1 Por qué un único camino por par deja de bastar

Hoy `caminos.py` devuelve el camino de **mínima energía** por par y lo fija antes de
conocer `β`. Doc 03 §2 demuestra (toy, verificado) que ese camino puede ser **infactible
por SoC** aunque exista otro factible con mayor `ê` pero menor `π̂`/`t̂`; los filtros de
`instancia.py` descartan entonces el **par entero**. Al añadir tiempo aparece un segundo
eje de conflicto (menor energía ≠ menor tiempo, doc 03 bug §5.5). ⇒ Un escalar no captura
el compromiso; hay que entregar un **frente de Pareto por par**.

### B.2 Qué guardar en el frente de Pareto (por par `s→d`)

Un camino domina a otro si es ≤ en todos estos ejes y < en alguno:

| Eje | Por qué está en el frente |
|---|---|
| `ê` (energía neta) | objetivo del MILP (min energía) |
| `π̂` (pico de consumo) | determina la **batería mínima de salida** `b̲+π̂`; dos caminos con igual `ê` difieren aquí |
| `t̂` (tiempo) | restricción T_max y objetivo secundario; min energía ≠ min tiempo |
| (derivado) `b_llegada(β)` | función de `β` vía `ê` y `σ̂`; no es eje independiente, se reconstruye de `ê,σ̂` |

El frente `{(ê, π̂, t̂, σ̂, geometría)}` sustituye al escalar `ê`. La "batería al llegar en
función de la de salida" es `min{β−ê, B−σ̂}`, parametrizada por `β`; por eso **no** se
guarda un número sino `(ê, σ̂)` y el MILP la evalúa para cada `β`.

### B.3 Algoritmo recomendado: **label-setting RCSPP con dominancia**

Marco canónico (Irnich–Desaulniers 2005, B7 [V]), especializado para EV con energía con
signo (Artmeier 2010 B1 [P], Baum 2019/2020 B4/B5 [V], Storandt 2012 B6 [P]). Multi-origen
desde los `|K|` nodos clave; etiqueta por nodo `v`:

```
Etiqueta L en v: (ê, π̂, t̂, σ̂, pred)
   ê   = energía neta acumulada s→v
   π̂   = max(π̂_pred, consumo_acumulado(s→v))   # pico de SoC gastado
   t̂   = tiempo acumulado (recurso no-negativo)
   σ̂   = regen perdida por saturación acumulada

extend(L, arco a=(v,w)):
   ê'  = ê + e_a
   cons' = max(cons_acum, cons_acum + e_a)       # solo cuando e_a>0 sube el pico
   π̂'  = max(π̂, cons')
   t̂'  = t̂ + t_a
   σ̂'  = σ̂ + regen_perdida(a, SoC implícito)      # ver nota de estado §B.5
   if t̂' > T_max: descartar                       # poda temporal (lectura i)
   if π̂' > B − b̲: descartar                       # infactible para cualquier β≤B
   return (ê', π̂', t̂', σ̂', v)

dominancia:  L1 ≼ L2  si  ê1≤ê2 ∧ π̂1≤π̂2 ∧ t̂1≤t̂2 ∧ σ̂1≤σ̂2   (y < en alguno)
```

Pseudocódigo (una fuente `s`; repetir o batch multi-origen):

```
PQ ← { etiqueta inicial (0,0,0,0,·) en s }
Fronteras[v] ← ∅  ∀v
while PQ no vacío:
    L ← extrae de PQ el de menor (ê)            # orden lexicográfico ê,t̂
    if L dominado por algún L' ∈ Fronteras[L.v]: continue
    Fronteras[L.v] ← Fronteras[L.v] ∪ {L}  (podando dominados)
    for a=(L.v, w) ∈ A:
        L' ← extend(L, a)
        if L' ≠ descartado y no dominado en Fronteras[w]:
            PQ.push(L')
return { Fronteras[d] : d ∈ K }                 # frente de Pareto por destino clave
```

**Corrección.** Es label-setting con recursos **monótonos no decrecientes al extender**:
`t̂` crece (`t_a≥0`); `π̂` es un `max` acumulado (no decrece); `σ̂` acumula (no decrece). La
energía `ê` puede bajar (regen), por eso **no** se usa `ê` como clave de parada exacta sin
cuidado; la correción del label-setting multicriterio no exige que todos los recursos sean
no-negativos, exige que la **regla de dominancia sea válida** y que las etiquetas no
dominadas se expandan una vez. Para energía con signo se preserva corrección usando el
**potencial físico** `p(v)=κ·η_r·h(v)` (Johnson/Sachenbacher, B2/B3 [V]) sobre `ê` para
ordenar la cola con pesos reducidos ≥0 (doc 03 §1 verificó reducidos ≥0, 0 clamps) ⇒ el
componente energía queda bien ordenado sin ciclos negativos. `π̂, t̂, σ̂` ya son no-negativos
monótonos. ∴ el algoritmo termina y devuelve el frente de Pareto exacto. ∎

### B.4 Alternativas (tabla comparativa)

| Enfoque | Ventaja | Límite | Uso aquí |
|---|---|---|---|
| **Dijkstra + potencial** (actual) | exacto para `Σe_a`, scipy, 0.4–0.6 s (doc 03 §4) | 1 solo criterio; no SoC-punto, no tiempo | Base; úsese como **subrutina**: potencial para ordenar `ê` y como heurística A* |
| **RCSPP label-setting** (recomendado) | frente Pareto, SoC-factible, T_max | explosión de etiquetas si poca dominancia | Núcleo del diseño; dominancia + T_max podan |
| **A\* con potencial de altura** (B3 [V]) | acelera consultas punto-a-punto | 1-a-1, no multiobjetivo nativo | Para el eje energía dentro del label-setting |
| **NAMOA\*** (A* multiobjetivo) | frente Pareto con heurística | implementación más compleja | Alternativa si el label-setting plano no escala |
| **Preprocesamiento (CH/Johnson)** (B2 [V]) | consultas casi O(Dijkstra) | coste de construcción; CH multicriterio es delicado | Johnson ya implícito en `p(v)`; CH opcional a futuro |

### B.5 Nota de estado: energía dependiente de SoC

`σ̂` (regen perdida por batería llena) depende del SoC real, que depende de `β`
(desconocido en la etapa estática). Dos tratamientos:

- **Conservador estático (recomendado fase 1):** calcular el camino con regen **acotada
  solo por potencia** (cota estática `P_regen_máx·t`, doc 02 §5.1) e **ignorar** la cota
  por batería llena (asumir que no se desborda). Da `ê` conservador (subestima regen) y
  `π̂` exacto; el MILP decide con esto. Preserva separación caminos/MILP.
- **Con estado (fase 2):** si el jurado exige fidelidad, expandir etiquetas con SoC
  explícito `b_i` para capturar `min{B,·}`; es la versión exacta pero multiplica el espacio
  de estados por el rango de SoC discretizado (doc 02 §6).

### B.6 Complejidad y eficiencia (81–200 nodos clave / ~10k viales)

| Técnica | Efecto |
|---|---|
| Multi-origen por lotes (scipy CSR ya existe, caminos.py) | 1 pasada por fuente clave; reusar CSR cacheado |
| Potencial `p(v)` como heurística A* | poda nodos lejanos; exacto (consistente, B3 [V]) |
| Dominancia agresiva (ê,π̂,t̂,σ̂) + poda T_max y `π̂>B−b̲` | corta ramas infactibles temprano |
| Límite **k caminos** por par (top-k Pareto, p.ej. k≤5) | acota el frente que pasa al MILP |
| Cachear CSR del **grafo cargado** (doc 03 §4: carga_grafo 5.5 s domina) | mayor ahorro global, independiente del algoritmo |

Costo esperado: `|K|` búsquedas RCSPP sobre 24.5k arcos; con dominancia y A* el término
dominante sigue siendo la **carga del grafo** (5.5 s), no las búsquedas (hoy 0.4–0.6 s;
el multicriterio las sube pero T_max/dominancia las contienen). Para `|K|≤200` es
tratable en segundos.

### B.7 Encaje con el MILP actual (arcos paralelos Pareto)

El MILP `milp_compacto.py` hoy recibe **un** `Arco(ê, π̂, σ̂, λ̂)` por par. Diseño:
emitir **varios arcos paralelos** `(s,d)`, uno por punto Pareto, con atributos
`(ê, π̂, σ̂, λ̂, t̂)`. El MILP elige a lo sumo uno por par usado (selección ya natural si
los arcos paralelos comparten extremos y el modelo escoge el de menor coste factible).
Añadir campo `t` a `Arco` (doc 03 §3) y, si se usa lectura (ii), fila de tiempo acumulado
por ruta. Así el MILP **rescata** pares que hoy se descartan por elegir el camino de menor
`ê` infactible (doc 03 bug Alto §5.1).

---

## C. Modelo de energía por arco y reserva robusta

### C.1 Fórmula recomendada (de doc 02 §5.1)

```
e_a = c(v_ef)·ℓ_a                              # rodadura+aero (curva en U, doc 02 §3)
    + κ·[Δh_a]⁺/η_d                            # subida: siempre consume
    − min( κ·η_r·[Δh_a]⁻ ,  E_regen_máx )      # bajada: regen ACOTADA
    + P_aux·t_a/60                             # auxiliares por tiempo (kWh)
E_regen_máx = min( P_regen_máx·t_a/60 ,  (B − SoC_v) )   # 2ª cota solo con estado (§B.5)
```

Parámetros (doc 02): `κ = m·g/3.6e6`; `η_d≈0,85–0,90`, `η_r≈0,55–0,65` (modelo usa
0,90/0,60, coherente con regen≈25 % [emp]); `P_regen_máx≈27 kW` (p95 sostenible [emp]);
`c(v)` curva en U con mínimo 45–65 km/h; `P_aux(OAT)` 0,4–3,5 kW [emp].

### C.2 Citas de García Bustos y regeneración

- **A1** (García Bustos et al., *Eng. Appl. Artif. Intell.* 142 (2025) 109925, DOI
  10.1016/j.engappai.2024.109925 [V DOI, texto no accedido]): energía por **segmento**
  físico+ML ⇒ sustituir consumo plano por `c(v_ef)` calibrado por tramo. **[P]** si
  usa VED/eVED y cómo trata regen: por confirmar en PDF.
- **A2** (SoH, *Batteries* 11(12) 451, DOI 10.3390/batteries11120451 [V]): capacidad
  efectiva por SoH ajusta `B` real de los Leaf 2013.
- **Fiori 2016 VT-CPEM** (DOI 10.1016/j.apenergy.2016.01.097 [P]) + [emp] doc 02 §1:
  regeneración **decrece** con el frenado fuerte y está **acotada por potencia**; por eso
  la cota `P_regen_máx·t` es física, no arbitraria.

### C.3 Reserva robusta (regla asimétrica)

Doc 02 §5.3: **sobreestimar consumo, subestimar regen.**

| Uso | Valor |
|---|---|
| Energía esperada (objetivo MILP) | mediana de `c` |
| Factibilidad SoC (`π̂`, reserva) | p85–p90 de `c` + penalización OAT frío (−10 °C ≈1,8× [emp]) |
| Regen a efectos de factibilidad | `η_r` p25 (conservador) |
| Reserva `b̲` | ≥10 % de B, elevable con SoH (A2) y clima (A3 [NV] DOI) |

---

## D. Otras consideraciones (priorizadas por impacto/esfuerzo)

| # | Consideración | Impacto | Esfuerzo | Prioridad |
|---|---|---|---|---|
| 1 | **Pareto/top-k por par** (rescata pares infactibles, doc 03 §5.1) | Alto | Medio | **P0** |
| 2 | **Reserva robusta de SoC** (p85–p90 + frío) | Alto | Bajo | **P0** |
| 3 | **Tiempo por arco + T_max por trayecto** (realismo CASE) | Alto | Medio | **P0** |
| 4 | **Regen acotada por potencia** (`P_regen_máx`, Fiori+emp) | Medio-Alto | Bajo | **P1** |
| 5 | **DEM real (USGS/Copernicus)** — gradiente eVED anulado (doc 02 §0) | Alto | Medio | **P1** |
| 6 | **Assert en `max(red,0.0)`** (clamp silencioso, doc 03 §5.2) | Medio | Bajo | **P1** |
| 7 | **Tope `max_acceso_m`** y stub con pendiente (doc 03 §5.3-5.4) | Medio | Bajo | **P1** |
| 8 | **Carga no lineal / límites de potencia de cargadores** (Montoya B9 [V]) | Medio | Alto | P2 |
| 9 | **Temperatura/SoH** sobre `B` (A2/A3) | Medio | Medio | P2 |
| 10 | **Giros/semáforos** (grafo de líneas o penalización) | Bajo-Medio | Alto | P3 |
| 11 | **Incertidumbre** (PHM A4 [P]) → margen probabilístico | Medio | Alto | P3 |
| 12 | **Validación independiente** (split por Trip, MAE energía, doc 02 §5.2) | Alto (defensa) | Medio | **P1** |

Para el jurado del CASE la combinación más defendible: P0 (Pareto + reserva + T_max) +
P1 (regen acotada + DEM + validación por Trip). Lo demás es refinamiento.

---

## E. Requisitos de la interfaz de cálculo (qué debe soportar)

### E.1 Entradas

| Grupo | Debe soportar |
|---|---|
| **Grafo dirigido** | `G=(V,A)` con atributos por arco: `ℓ` (km), `Δh` (m, DEM), `t`/`v_ef` (min, km/h), `highway`, `maxspeed`, geometría; respeto de sentidos |
| **Nodos clave tipados** | base `o`, clientes `C` (con demanda/servicio), cargadores `F` (con potencia/tipo); mapeo nodo-vial ↔ parada |
| **Flota y física** | `m`, `κ`, `η_d`, `η_r`, `P_regen_máx`, `P_aux(OAT)`, `B` (ajustable por SoH), `β` SoC inicial, `b̲` reserva |
| **Límites** | `T_max` por trayecto, (opc.) jornada global `H_t`, `H`=capacidad del compañero, `k` máx de caminos Pareto por par |
| **Modelo de energía intercambiable** | función `e_a = f(ℓ,Δh,v_ef,t,OAT; θ)` reemplazable (plano 0.157 ↔ `c(v)` ↔ A1 físico+ML) sin tocar el buscador |

### E.2 Salidas

| Salida | Contenido |
|---|---|
| **Frente de Pareto por par** `(s,d)` | lista de caminos `{(ê, π̂, σ̂, λ̂, t̂)}` no dominados |
| **Estadísticos** | por camino, los de §A.3; `b_llegada(β)=min{β−ê, B−σ̂}` |
| **Geometría** | secuencia de nodos/arcos y polilínea para mapa/validador |
| **Procedencia** | modelo de energía usado, versión DEM, parámetros `θ`, flag `elevacion_degradada` (doc 03 §5.8) |
| **Garantías** | SoC-factibilidad punto a punto para `β≥b̲+π̂`; `t̂≤T_max`; corrección Pareto; reproducibilidad por firma |

### E.3 Compatibilidad

- **Modelo posicional del compañero** (`H`, `ProblemInstance` de `ev_routing`): `B≡H`;
  cada punto Pareto se expone como arco posicional con sus estadísticos.
- **MILP actual** (`milp_compacto.py`): emitir **arcos paralelos** por punto Pareto con
  campo `t` añadido a `Arco`; el MILP elige uno por par usado (§B.7).
- **Validador** (`validador.py`): recibe geometría + estadísticos para re-simular SoC
  tramo a tramo con el mismo modelo de energía (evitar divergencia caminos↔validador).

---

## F. Plan de implementación por fases

| Fase | Alcance | Esfuerzo | Riesgos |
|---|---|---|---|
| **F0 — Blindaje** | assert en clamp `red≥−EPS`; tope `max_acceso_m`; stub con `Δh` (doc 03 §5.2-5.4) | 0,5 d | Bajo; reversible |
| **F1 — Pareto por par** | label-setting RCSPP con `(ê,π̂,t̂,σ̂)` y dominancia; emitir top-k; arcos paralelos al MILP; campo `t` en `Arco` | 3–5 d | Explosión de etiquetas si poca dominancia ⇒ limitar k, usar A* con `p(v)` |
| **F2 — Tiempo + T_max** | `t_a` desde `v_ef(highway,maxspeed)`; poda `t̂>T_max`; (opc.) jornada global en MILP | 1–2 d | Datos `maxspeed` faltantes ⇒ tabla por `highway` (doc 02 §4) |
| **F3 — Energía realista** | DEM real; `c(v)` calibrada; regen acotada por potencia; reserva p85–p90 | 2–4 d | DEM/alineación nodos; gradiente eVED inútil (doc 02 §0) ⇒ usar DEM |
| **F4 — Validación/defensa** | split por Trip, MAE/MAPE energía, sensibilidad OAT/SoH; informe para jurado | 1–2 d | Fuga temporal si se mezclan filas de un Trip (doc 02 §5.2) |
| **F5 (opc.) — Estado SoC** | etiquetas con `b_i` para `min{B,·}` exacto; carga no lineal cargadores | 3–5 d | Multiplica estado; solo si jurado exige fidelidad exacta de regen saturada |

Ruta mínima para el CASE: **F0→F1→F2→F3→F4**. F5 es refinamiento de fidelidad.

---

## Referencias clave (de 01/02)

RCSPP label-setting: Irnich & Desaulniers 2005, DOI 10.1007/0-387-25486-2_2 [V].
Potencial/Johnson y A* físico: Eisner-Funke-Storandt 2011 [V]; Sachenbacher 2011 [V].
Tiempo+energía / Pareto: Baum 2019 DOI 10.1287/trsc.2018.0889 [V]; Baum 2020 DOI
10.1287/trsc.2020.0981 [V]; Storandt 2012 DOI 10.1145/2442942.2442947 [P]. E-VRPTW:
Schneider 2014 DOI 10.1287/trsc.2013.0490 [V]. Carga no lineal: Montoya 2017 DOI
10.1016/j.trb.2017.02.004 [V]. Regen: Fiori 2016 DOI 10.1016/j.apenergy.2016.01.097 [P].
García Bustos: A1 DOI 10.1016/j.engappai.2024.109925 [V DOI], A2 DOI
10.3390/batteries11120451 [V]. Datos: eVED arXiv:2203.08630 [V]; VED DOI
10.1109/TITS.2020.3035596 [V]. [NV]: DOI térmica A3; ficha Leaf 2013.
