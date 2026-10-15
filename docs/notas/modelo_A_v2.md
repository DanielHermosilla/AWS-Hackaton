# Modelo A v2 — E-VRP sobre grafo vial contraído (tras validación cruzada con B v1)

Se usa la notación del PDF cuando el concepto existe. Los símbolos nuevos van marcados con ★.

---

## 0. Auditoría de B (modelo_B_v1.md)

Cada afirmación de B se verificó a mano contra el PDF y contra el lema de contracción (§2, P5). Veredictos: ✔ correcta, ✘ error, ◐ correcta pero débil o imprecisa.

### 0.1 Crítica de B al PDF
- ✔ (1)–(6), (8), (10), (14)–(16) son correctas, y la linealización (11)–(13) es válida.
- ✔ Se pueden eliminar γ_kr y (13). Por monotonía de min{B, ·}, el valor de E_total = Σ_k(b_ini + Σq − b_kH) del modelo sin γ es mayor o igual que el físico, y coincide con él en el óptimo de la fase 2.
- ✔ (9) y q_k0 = 0 son redundantes.
- ◐ El "M ajustado" B − b̲ + max(0, −min e) es válido pero no es el más fuerte. Con γ = 1 vale b = B, así que en (13a) basta M₁ = max(0, −min e), y en (13b) basta M₂ = B − b̲. B usa la suma de las dos cotas. No importa en la práctica, porque γ se elimina.
- ✔ Tamaño, H, simetrías (vehículos y lazos (0,0)), ciclos negativos y faltantes: B coincide con A v1. Las estimaciones (H ≈ 500 contra ~10³) son del mismo orden.

### 0.2 Errores y debilidades del modelo B
- ✘ **E1. Falta el filtro de sub-camino (reserva con saturación).** El lema de B (§3.3) enuncia bien la condición max_{s≤t} Σ_{s<r≤t} e_r ≤ B − b̲. Pero sus filtros solo imponen b̲ + P ≤ B, y P es el máximo prefijo, que no capta una subida que viene después de una regeneración saturada.
  - Contraejemplo: se sale de un cargador con B, se baja regenerando 0.5 kWh (se pierden por saturación) y luego se sube consumiendo B − b̲ + 0.3. El pico es P = B − b̲ − 0.2, así que pasa el filtro. El mínimo real de batería es b̲ − 0.3 < b̲.
  - Esto contradice la afirmación de B de que "ninguna solución reportada es infactible". Afecta también al retorno (9).
  - Corrección: eliminar el par si λ̂ > B − b̲ (A v1, P7).
  - En la zona real (desniveles de decenas de metros) es improbable, pero es un error matemático.
- ✘ **E2. La restricción (3) con ρ = 1 hace que los dos vehículos no puedan usar el mismo cargador** y que ninguno lo use dos veces. La frase "sin tiempo de carga, cargar una vez basta" no se demuestra.
  - Contraejemplo: base lejana y dos grupos de clientes que solo se alcanzan pasando por un único cargador compatible "puente". Ahí hacen falta 2 o más visitas a ese cargador, sumando las de ambos vehículos.
  - La exactitud exige ν ≥ (máximo de visitas por cargador), una cota desconocida. Es el mismo problema que H, a menor escala.
  - A v1 no tiene este problema: con carga completa, los cargadores no guardan estado y admiten cualquier número de visitas sin copias.
- ◐ **E3.** "Los ciclos sin cargador ya son infactibles por (5)" falla si dos claves se ajustan al mismo nodo vial (ẽ = 0 en ambos sentidos): el ciclo i→j→i suma 0. B sigue siendo correcto porque su MTZ (10) cubre todos los nodos. Solo la observación es imprecisa.
- ◐ **E4.** MTZ (10) tiene una relajación lineal (LP) débil y obliga a usar x binaria con copias. El flujo de conectividad de A v1 (φ) es más fuerte y admite multiplicidad.
- ◐ **E5.** El modelo de energía de B no tiene eficiencia de tracción en subida (1/η_d). Es un detalle menor: la prueba de ausencia de ciclos negativos y el potencial siguen valiendo.
- ✔ (4) es redundante (se obtiene sumando (2) y (3)), pero no es un error. (5)–(9) son la relajación exacta por cota superior de min{Ĉ, b̄ − ẽ}. Ĉ_uv = B − max_{t≥1}(sufijo) es equivalente a mi B − σ̂_uv cuando b̄ ≤ B (el sufijo completo solo aporta la cota B − ẽ ≥ b̄ − ẽ).
- ✔ La alternativa de un solo MILP con W > |K|·b_ini + |Φ|(B − b̲) es correcta. E_total ≥ 0 porque todo paseo cerrado tiene Σe > 0 y el consumo efectivo es al menos el nominal.

### 0.3 Lo que B hace mejor que A v1 (incorporado en v2)
- **I1. Métrica del PDF.** B usa exactamente E_total = Σ_k(b_ini + Σq − b_final), con q y la batería de regreso como variables. A v1 usaba Σ ê·x (consumo nominal), que es una cota inferior de la métrica del PDF cuando hay regeneración saturada. En v2 la métrica del PDF entra como variante V-PDF (§4); se mantiene la nominal como base, por la razón que se da en §1.
- **I2. Lectura de F_k más precisa:** separar `connector_types` por ";", normalizar, exigir `total_ports` > 0 y excluir filas vacías.
- **I3.** Se excluye el arco (0, 0′): un vehículo sin uso simplemente no sale.
- **I4.** Inicio con heurística constructiva (inserción con desvío a cargador): si entrega |C| clientes, se omite la fase 1.
- **I5.** Sensibilidad en B ∈ {13, 16, 24} kWh. En v2 se agrega por qué B conservador es seguro (§6).

### 0.4 Correcciones a A v1 (detectadas durante la auditoría)
- La dominancia de cargadores de A v1 omitía condiciones. Se reescribe sobre los arcos ya filtrados (P7).
- La "ruta de cuello de botella" de A v1 estaba mal planteada: minimizar max_t s_t no es un camino de cuello de botella por arcos. Se reemplaza por un Dijkstra con poda θ, que es exacto (P5′).

---

## 1. Decisiones de v2

1. **Calles.** Se eligen en un preprocesamiento exacto por par de nodos clave (caminos de mínima energía con estadísticos de batería). El MILP decide la secuencia y las paradas sobre el grafo contraído, y la ruta vial es la concatenación de los P_ij elegidos. No hay H.
2. **Métrica base: E_total nominal = Σ ê·x.**
   - La salida pedida, {vehículo: [node_id]}, no contiene q. El evaluador solo puede recalcular la energía a partir de la secuencia de tramos, y la métrica nominal es la única reproducible desde la salida.
   - Con esta métrica, cargar hasta B es óptimo sin pérdida de generalidad. Así los cargadores no guardan estado y admiten visitas ilimitadas y compartidas entre vehículos, sin copias.
   - Si no hay elevación (e = c·ℓ ≥ 0), la métrica nominal y la del PDF coinciden.
3. **Variante V-PDF (§4).** Usa la métrica exacta del PDF cuando hay regeneración, con copias de cargadores (como B) y el filtro λ̂ corregido.
4. **Vehículos agregados por tipo.** Se elimina la simetría |K|!. Eliminación de subtours por flujo.

---

## 2. Preprocesamiento (todo se calcula desde los archivos; nada queda fijo en el código)

**P1. Grafo vial G = (V, A).**
- Se usa el grafo OSM dirigido "drive" del rectángulo que envuelve los nodos del CSV, más un margen, y se conserva la mayor componente fuertemente conexa.
- Cada fila del CSV (base, cliente, cargador) se ajusta a su nodo vial más cercano. Dos claves en el mismo nodo vial siguen siendo claves distintas, con ê = π̂ = σ̂ = λ̂ = 0 entre ellas.

**P2. Energía por tramo**, en kWh, con ℓ_ij en km, Δh_ij = h_j − h_i en m y [·]^± las partes positiva y negativa:

    e_ij = c·ℓ_ij + μ·( [Δh_ij]⁺/η_d − η_r·[Δh_ij]⁻ ),   μ = m·g/3.6·10⁶ ≈ 0.00433 kWh/m (m ≈ 1590 kg)

- ★ c es el consumo en plano, calibrado con eVED: el promedio debe dar ≈ 0.156 kWh/km. ★ 0 ≤ η_r < 1 ≤ 1/η_d son las eficiencias de regeneración y de tracción.
- Sin elevación: e_ij = c·ℓ_ij.
- Sin ciclos negativos: en un ciclo Σ[Δh]⁺ = Σ[Δh]⁻, luego Σe ≥ c·Σℓ > 0.
- Con el potencial p(v) = μ·η_r·h_v, el costo reducido e_ij + p(i) − p(j) = c·ℓ_ij + μ(1/η_d − η_r)[Δh_ij]⁺ ≥ 0, así que basta Dijkstra. Si e viene de otro modelo, se verifica una vez con Bellman-Ford.

**P3. Compatibilidad.** F_k = { f ∈ F : Conn(f) ∩ Conn_k ≠ ∅, total_ports_f > 0 }.
- Conn(f) sale de separar `connector_types` por ";" y normalizar. Las filas vacías se excluyen.
- Conn_k es un parámetro del tipo de vehículo: {CHADEMO, J1772} para el Leaf 2013. En la instancia de competición quedan 54 cargadores.
- Un cargador incompatible sigue en G como intersección por la que se puede pasar.
- F_* = ∪_k F_k.
- ★ Tipos 𝒯: clases de K con iguales (B, b_ini, F_k). ★ n_τ = |K_τ|. Se escribe F_τ. El código los detecta comparando datos; en la instancia, 𝒯 = {Leaf} y n = 2.

**P4. ★ Nodos clave.** N = {0, 0′} ∪ C ∪ F_*, donde 0′ es la copia de llegada del depósito.

**P5. Caminos y estadísticos.** Desde cada i ∈ {0} ∪ C ∪ F_* se corre un Dijkstra con potenciales, que da el camino de mínima energía ★ P_ij hacia cada clave j. Sobre P_ij = (v₀, …, v_T), sea s_t la energía acumulada (s₀ = 0). Se definen:
- ★ ê_ij = s_T
- ★ π̂_ij = max_t s_t (pico de prefijo)
- ★ σ̂_ij = s_T − min_t s_t (máximo sufijo)
- ★ λ̂_ij = max_{t′≤t}(s_t − s_{t′}) (máximo sub-camino)

Los cuatro se calculan en una pasada padre → hijo del árbol de caminos. Los ê cumplen la desigualdad triangular.

*Lema (exacto).* Al salir de i con s ≤ B y aplicar b ← min{B, b − e} tramo a tramo:
- (i) la batería es ≥ b̲ en todo P_ij ⇔ s ≥ b̲ + π̂_ij y λ̂_ij ≤ B − b̲;
- (ii) la batería de llegada es min{ s − ê_ij , B − σ̂_ij }.

Si e ≥ 0, entonces π̂ = σ̂ = λ̂ = ê.

**P5′. (Opcional; solo importa si hay regeneración.)** Si i ∈ {0} ∪ F_*, la batería de salida está fijada (★ β_i, ver P6). Con un Dijkstra con poda (no expandir nodos con s > θ := β_i − b̲) se obtiene el camino de mínima ê entre los que tienen π̂ ≤ θ. Es exacto porque el conjunto de caminos factibles es cerrado por prefijos y los costos reducidos son ≥ 0. Para i ∈ C se pueden agregar arcos paralelos con unos pocos valores de θ.

**P6. Constantes.**
- ★ β_0 = b_ini = 0.6·B; β_f = B para f ∈ F_*.
- ★ ρ_ij = min{ β_i − ê_ij , B − σ̂_ij } para i ∈ {0} ∪ F_*.

**P7. ★ Arcos A_τ** = {(i,j) : i ∈ {0} ∪ C ∪ F_τ, j ∈ C ∪ F_τ ∪ {0′}, i ≠ j, (i,j) ≠ (0,0′)}. Se eliminan:
- (a) los arcos con λ̂_ij > B − b̲ (corrige E1 de B);
- (b) los arcos con i ∈ {0} ∪ F_* y β_i < b̲ + π̂_ij.

*Dominancia exacta (opcional).* Sobre los arcos ya filtrados, g ∈ F_* domina a f si se cumplen las tres condiciones siguientes. En ese caso f se elimina.
- f ∈ F_τ implica g ∈ F_τ.
- Para todo arco (i,f) existe (i,g) con ê_ig ≤ ê_if y π̂_ig ≤ π̂_if.
- Para todo arco (f,j) existe (g,j) con ê_gj ≤ ê_fj y σ̂_gj ≤ σ̂_fj.

Desde un cargador se sale con B. Por eso la factibilidad de (g,j) es solo del filtro, y la llegada vale B − σ̂.

**Parámetros.**
- B: capacidad útil. Por defecto la mediana de eVED, ≈ 16 kWh (no los 24 nominales).
- b̲: reserva. Es un parámetro con 0 ≤ b̲ ≤ b_ini; se sugiere 0.1·B. El PDF exige b̲ > 0.
- b_ini = 0.6·B.

---

## 3. MILP base (métrica nominal)

**Conjuntos:** 𝒯, C, F_τ, F_*, N, 0, 0′, A_τ. **Parámetros:** B, b̲, b_ini, n_τ, ê_ij, π̂_ij, σ̂_ij, ρ_ij.

**Variables**
- x_ijτ ∈ ℤ≥0, (i,j) ∈ A_τ: número de veces que algún vehículo de tipo τ recorre P_ij. Es binaria de hecho si i ∈ C o j ∈ C, por (2) y (3).
- y_i ∈ {0,1}, i ∈ C: entrega al cliente i (= visitarlo como nodo clave).
- b_i ∈ [b̲, B], i ∈ C: batería al llegar a i, que es la misma al salir.
- ★ φ_ijτ ≥ 0, (i,j) ∈ A_τ: flujo de conectividad.
- E_total ∈ ℝ.
- Abreviatura: ★ X_ij := Σ_τ x_ijτ.
- q del PDF queda implícita: en cada cargador se carga hasta B, es decir q = B − (batería de llegada).

**Restricciones** (las sumas recorren los arcos existentes de A_τ)

    (1)  Σ_j x_0jτ ≤ n_τ                                       ∀τ                        (salidas)
    (2)  Σ_j x_jiτ = Σ_j x_ijτ                                 ∀τ, i ∈ C ∪ F_τ           (continuidad ⇒ retorno a 0′)
    (3)  y_i = Σ_τ Σ_j x_jiτ                                   ∀i ∈ C                    (entrega única)
    (4)  φ_ijτ ≤ |C|·x_ijτ                                     ∀τ, (i,j) ∈ A_τ
    (5)  Σ_j φ_jiτ − Σ_j φ_ijτ = Σ_j x_jiτ                     ∀τ, i ∈ C
    (6)  Σ_j φ_jfτ − Σ_j φ_fjτ = 0                             ∀τ, f ∈ F_τ
    (7)  b_j ≤ B − (B − ρ_ij)·X_ij                             ∀i ∈ {0} ∪ F_*, j ∈ C     (llegada desde 0 o cargador)
    (8)  b_j ≤ b_i − ê_ij + (B − b̲ + ê_ij)(1 − X_ij)           ∀i, j ∈ C, i ≠ j          (consumo)
    (9)  b_j ≤ B − σ̂_ij·X_ij                                   ∀i, j ∈ C, i ≠ j          (saturación)
    (10) b_i ≥ b̲ + π̂_ij·X_ij                                   ∀i ∈ C, j ∈ C ∪ F_* ∪ {0′} (reserva en todo el camino)
    (11) E_total = Σ_τ Σ_{(i,j)∈A_τ} ê_ij·x_ijτ

**Objetivo** (lexicográfico, igual que (16) del PDF)

    (12) Fase 1:  N* = max Σ_{i∈C} y_i         s.a. (1)–(10)
    (13) Fase 2:  min E_total                  s.a. (1)–(11),  Σ_{i∈C} y_i = N*

**Validez**
- *Subtours.* Por (4)–(6), cada cliente visitado absorbe una unidad de φ, que solo nace en 0 y circula por arcos usados del mismo tipo. Así, todo cliente queda conectado a 0 en el multigrafo de τ. Por (1)–(2), ese multigrafo se descompone en ≤ n_τ paseos 0 → 0′ que cubren su componente.
  - Las componentes sin clientes (ciclos solo de cargadores) no transportan φ neto. En la fase 2 tienen costo ê > 0, y en la extracción se descartan.
  - Las claves ajustadas al mismo nodo vial (ê = 0) también quedan cubiertas, porque (5) no depende de ê.
- *Retorno.* Sumando (2) con (1) se obtiene Σ_i x_i0′τ = Σ_j x_0jτ.
- *Batería.* (7)–(9) son la relajación por cota superior del lema (ii), y (10) junto con P7 implementa el lema (i), incluido el retorno.
  - La relajación es exacta: más batería nunca quita factibilidad, y E_total no depende de b.
  - Con X = 0, (8) queda b_j ≤ b_i + B − b̲ ≥ B, que es redundante. El big-M es el mínimo posible, y (7), (9) y (10) no usan big-M.
- *Cargadores sin estado.* Con la métrica (11), cargar hasta B es óptimo sin pérdida de generalidad. Por eso la batería de salida de un cargador es la constante B, y basta x entera para permitir visitas repetidas y compartidas entre vehículos. No hay colas ni puertos (supuesto del equipo).

---

## 4. Variante V-PDF (métrica exacta del PDF con regeneración)

Se usa solo si la elevación produce e < 0 y se quiere E_total = Σ_k(b_ini + Σ_r q_kr − b_kH), como en (14)–(15) del PDF. Con e ≥ 0 coincide con §3, que es más chico y exacto.

- ★ Φ = copias f¹, …, f^ν de cada f ∈ F_*. ★ ν = número de copias. N^Φ = {0, 0′} ∪ C ∪ Φ. Los arcos A_τ^Φ se construyen como en P7, sin arcos entre copias del mismo f.
- La batería de salida de un cargador pasa a ser variable, así que los cargadores guardan estado. Cada copia admite a lo más una visita en total.
- Variables:
  - x_ijτ ∈ {0,1}.
  - b_f, b̄_f ∈ [b̲, B] y q_f ≥ 0 para f ∈ Φ.
  - ★ ω_i ≥ 0, para i ∈ C ∪ Φ: batería al llegar a 0′ desde i.
  - Convenciones: b̄_i ≡ b_i si i ∈ C; b̄_0 ≡ b_ini.
- Se mantienen (1)–(6) (con Φ en lugar de F_τ) y (12)–(13). Se reemplazan (7)–(11) por:

```
(V1) Σ_τ Σ_j x_jfτ ≤ 1                                              ∀f ∈ Φ
(V2) b̄_f = b_f + q_f,   q_f ≤ (B − b̲)·Σ_τ Σ_i x_ifτ                 ∀f ∈ Φ                  (PDF (8),(10))
(V3) b_j ≤ b̄_i − ê_ij + (B − b̲ + ê_ij)(1 − X_ij)                    ∀i ∈ {0} ∪ C ∪ Φ, j ∈ C ∪ Φ
(V4) b_j ≤ B − σ̂_ij·X_ij                                            ∀i ∈ {0} ∪ C ∪ Φ, j ∈ C ∪ Φ
(V5) b̄_i ≥ b̲ + π̂_ij·X_ij                                            ∀i ∈ C ∪ Φ, j ∈ C ∪ Φ ∪ {0′}
(V6) ω_i ≤ b̄_i − ê_i0′ + (B − b̲ + ê_i0′)(1 − X_i0′),  ω_i ≤ (B − σ̂_i0′)·X_i0′    ∀i ∈ C ∪ Φ
(V7) E_total = b_ini·Σ_τ Σ_j x_0jτ + Σ_{f∈Φ} q_f − Σ_i ω_i
(V8) Σ_i X_{i,f^{c+1}} ≤ Σ_i X_{i,f^c}                               ∀f ∈ F_*, c = 1..ν−1     (simetría de copias)
```

- *Exactitud.* Para una secuencia fija, sea q′_f la carga necesaria para llegar a la misma b̄_f desde la batería física. Como la batería física es ≥ b, q′_f ≤ q_f, y el ω físico es ≥ ω. Por lo tanto el E_total físico ≤ (V7), con igualdad en el óptimo de la fase 2.
- La métrica penaliza cargar de más solo a través de la regeneración perdida por saturación.
- Es exacta respecto del grafo contraído solo si ν ≥ el número máximo de visitas por cargador, sumando todos los vehículos (E2). ν = 1 es heurístico; ν = 2 cubre los casos prácticos.

---

## 5. Tamaño y estrategia de solución

| Formulación | Enteras | Continuas |
|---|---|---|
| §3, \|𝒯\| = 1, \|F_*\| = 54 (antes de P7) | ≈ 5.6·10³ | ≈ 5.6·10³ (φ) + 20 |
| §4 V-PDF, ν = 2 | ≈ 1.7·10⁴ | ≈ 1.7·10⁴ + 3·108 |
| B v1, Φ = F_* | ≈ 5.5·10³ binarias | ≈ 300 (MTZ) |
| PDF sobre OSM | ~10⁷ binarias | ~10³ |

- El preprocesamiento son ≈ 75 Dijkstra sobre G, O(|N|·|A| log|V|), del orden de segundos.
- Los tamaños son estimaciones: no se corrió el solver.

**Estrategia**
1. Heurística constructiva (inserción con desvío al cargador compatible de menor ê_ic + ê_cj). Si entrega |C| clientes, entonces N* = |C|, la fase 1 se omite y la heurística se usa como solución inicial (warm start) de la fase 2 con y ≡ 1.
2. Si no los entrega, se resuelve la fase 1 y luego la fase 2 partiendo de la solución de la fase 1.
3. Acelerador declarado como heurístico: para cada par de clientes conservar solo los r cargadores con mejor ê_ic + ê_cj. La dominancia de P7 es exacta y se aplica siempre.

---

## 6. Extracción, validación y robustez

1. Se toma x̄ = round(x). Para cada τ se recorre el multigrafo con Hierholzer desde 0 hasta 0′, una vez por cada salida de 0.
   - En los cargadores (§3) se puede re-emparejar cualquier entrada con cualquier salida, porque siempre se sale con B. Los subciclos que pasan por un cargador se insertan en el recorrido.
   - Las componentes no alcanzables desde 0 se descartan.
   - En V-PDF, cada nodo tiene un sucesor único.
2. Cada paseo se asigna a un vehículo de K_τ. Un vehículo sin uso queda como [BASE, BASE].
3. 0, 0′ → `node_id` de la base. Clientes, cargadores y copias f^c → su `node_id`. Resultado: {k: [BASE, V3, C17, V8, …, BASE]}.
4. Validación independiente del solver: se expande cada par consecutivo a calles con los predecesores de P5, se simula b ← min{B, b − e} arco por arco cargando en cada cargador listado, se verifica b ≥ b̲ en todo punto y la llegada a la base, y se reporta E_total.
5. *Robustez frente a B.* Las trayectorias son monótonas en (B, b_ini). Una ruta factible con B = 16 sigue siendo factible si el evaluador usa B = 24 (y b_ini = 0.6·24), siempre que su consumo por tramo sea ≤ e. Conviene sensibilidad con B ∈ {13, 16, 24} y c en p25–p75 de eVED.

---

## 7. Supuestos y límites

- Sin tiempo, velocidad, jornada, capacidad de paquetes ni colas (supuesto del equipo). Por eso la recarga es instantánea y gratis, y dos vehículos pueden compartir un cargador.
- Se usa un camino por par de claves (más los paralelos opcionales de P5′).
  - Con e ≥ 0 la contracción es exacta: el camino de mínima ê también minimiza π̂, σ̂ y λ̂.
  - Con regeneración es exacta en factibilidad para el camino elegido. Puede perder rutas que usan un camino de mayor ê pero menor pico desde un cliente (efecto ≈ μ·50 m ≈ 0.2 kWh frente a B ≈ 16 kWh).
- La métrica oficial de "energía total" no está especificada. La base (11) es la reproducible desde la salida. V-PDF es la definición del PDF.
