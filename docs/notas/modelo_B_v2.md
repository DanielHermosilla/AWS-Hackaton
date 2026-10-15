# Modelo B v2 — E-VRP sobre grafo vial contraído (revisión cruzada con A v1)

Notación del PDF del equipo cuando el concepto existe; b̲ = reserva (b subrayada). Símbolos nuevos marcados con ★. Desde esta versión se adoptan los nombres de A v1 para los estadísticos de camino (ê, π̂, σ̂, λ̂, β, ρ, φ), que reemplazan a (ẽ, P, Ĉ) de B v1 (Ĉ = B − σ̂, P = π̂).

---

## 0. Auditoría de A v1

Cada afirmación se verificó a mano (álgebra o contraejemplo). No se ejecutó código.

### 0.1 Afirmaciones verificadas como correctas
| Afirmación de A | Verificación |
|---|---|
| Lema: batería en v_t = min{s − s_t, min_{t′≤t}(B − (s_t − s_{t′}))} | Inducción sobre b_t = min{B, b_{t−1} − e_t}. El término t′ = 0 da B − s_t ≥ s − s_t (porque s ≤ B), así que no altera el resultado. |
| (i) reserva en todo el camino ⇔ s ≥ b̲ + π̂ y λ̂ ≤ B − b̲; (ii) llegada = min{s − ê, B − σ̂} | Se sigue directo del lema. σ̂ ≥ max{0, ê} porque s₀ = 0 y s_T = ê. |
| No hay ciclos negativos si c > 0 y η_r ≤ 1 ≤ 1/η_d; con p(v) = κη_r h_v el costo reducido es ≥ cℓ | En un ciclo, ΣΔh⁺ = ΣΔh⁻, luego Σe = cΣℓ + κ(1/η_d − η_r)ΣΔh⁺ > 0. El costo reducido vale cℓ si Δh ≤ 0 y cℓ + κΔh(1/η_d − η_r) si Δh > 0. Generaliza mi B v1 (que tenía η_d = 1). |
| Cargar hasta B es óptimo s.p.g. **cuando E_total es (11) de A** | La dinámica es no decreciente en la batería de salida y (11) no depende de q. Ver 0.2-E4 para el caso con la definición del PDF. |
| (7)–(10) correctos, big-M de (8) | Con x = 0, (8) queda b_j ≤ b_i + B − b̲ ≥ B y es redundante. (7), (9) y (10) son lineales en x. Σ_k x_ijk ≤ 1 en arcos que tocan un cliente, por (3). |
| Flujo φ (4)–(6) elimina subtours | El flujo solo se genera en 0 (en los clientes se consume, en los cargadores se conserva, y 0′ no tiene salida), así que todo cliente atendido es alcanzable desde 0 en el soporte de k. Con el balance (2), la componente de 0 admite un paseo euleriano 0 → 0′. |
| Ciclos solo-cliente infactibles sin φ | Sumando (8) a lo largo del ciclo: 0 ≤ −Σê < 0 (salvo ciclos de energía 0). Por eso φ solo es indispensable para ciclos que pasan por cargadores. |
| M₁ = max(0, −min e) en (13a) y M₂ = B − b̲ en (13b) del PDF | Con γ = 1: b = B y u ≤ B − min e. Con γ = 0: hace falta B − M₂ ≤ b̲. Es más fino que lo que dije en B v1 (un solo M con u − M ≤ b̲, que es suficiente pero no necesario). |
| (9) y q_k0 = 0 del PDF son implicadas; γ y (13) sobran | Coincide con B v1. |
| Tamaños: \|A_k\| ≈ 5.5·10³; PDF contraído con H = 25 ≈ 2.8·10⁵ | Aritmética correcta: 5 551 arcos por tipo (§3.3). |

### 0.2 Errores u omisiones en A v1
- **E1. La poda por dominancia (P7) es incompleta.** Del lado entrante solo exige ê_ig ≤ ê_if y π̂_ig ≤ π̂_if. Falta exigir que (i,g) exista, es decir λ̂_ig ≤ B − b̲. Contraejemplo: si (i,f) ∈ A_k pero (i,g) fue podado por λ̂, eliminar f pierde soluciones. Corrección: agregar λ̂_ig ≤ λ̂_if, o directamente (i,f) ∈ A_k ⇒ (i,g) ∈ A_k.
- **E2. Dominios mal puestos al agregar por tipo (§5).** A declara binarios los arcos 0→F, F→0′ y 0→0′. Al agregar por tipo, varios vehículos pueden usar el mismo arco (por ejemplo, los dos Leaf cargan primero en el cargador más cercano a la base). Esos arcos deben ser enteros en [0, |K_θ|]; si no, se cortan soluciones factibles.
- **E3. Variables x_ff′ sin cota y ciclos de energía 0.** Si dos cargadores caen en el mismo nodo vial, ê = 0 en ambos sentidos. En ese caso la frase "los ciclos de cargadores cuestan energía" es falsa, y x en F×F puede crecer sin límite sin cambiar el objetivo. Corrección: fusionar los cargadores que caen en el mismo nodo y acotar x_fg ≤ U = |C| + |K| (demostración en §3.4).
- **E4. Cambio de definición de E_total.** (11) de A es el consumo nominal Σê·x y no la (15) del PDF, que es efectiva: descuenta la regeneración perdida por saturación. A lo declara, pero "cargar a B s.p.g." solo vale con (11). Con (15), cargar a B antes de una bajada pierde regeneración. Es una decisión de modelado y no un error, pero debe ser explícita. En §5 muestro que el post-proceso con "carga mínima" minimiza (15) para la ruta elegida.
- **E5. §7, "camino que minimiza max_t s_t (cuello de botella)".** No es un problema de cuello de botella: s_t son sumas de prefijo, no máximos de arcos. Se resuelve con etiquetas bicriterio (s, pico), un Dijkstra multietiqueta. Es una afirmación imprecisa, no inválida.
- **E6. Estrategia, paso 2.** "Si P2 con y = 1 es infactible…": demostrar que un MILP es infactible puede costar tanto como resolverlo. Se puede certificar N* = |C| en tiempo polinomial, antes del MILP (§3.5).
- **E7. Faltan desigualdades válidas** que endurezcan la relajación: φ_ij ≥ x_ij en arcos que entran a un cliente, y fijar y_i = 0 en clientes sin arco factible de entrada o de salida.
- Menor: el arco (0,0′) existe y además (1) usa "≤ 1". Es redundante, pero no incorrecto.

### 0.3 Mejoras de A sobre B v1 (incorporadas en v2)
1. **Cargadores sin memoria** (bajo E nominal). Elimina de B v1 las copias ρ, q_f, b̄_f, b_f y β_i, y permite revisitas ilimitadas. B v1 limitaba a una visita por copia, lo que es una pérdida potencial.
2. **Flujo φ en lugar de MTZ.** MTZ no admite revisitas de cargadores.
3. **Filtro λ̂ explícito.** B v1 enunciaba la condición en el lema pero no la aplicaba como filtro: era un error de B v1.
4. Modelo de energía con η_d, SCC antes del snapping, extracción con Hierholzer, estrategia de "fijar y = 1".

Se conserva de B v1: la agregación por tipo en el modelo principal, la variante con E efectiva y el atajo con heurística o warm start.

---

## 1. Idea

La salida pedida es {vehículo: [BASE, clientes, cargadores, BASE]}. Las calles se eligen en el preprocesamiento con caminos de mínima energía, y cada camino P_ij se resume de forma exacta con (ê, π̂, σ̂, λ̂). El MILP es un problema de flujo en arcos sobre {0, 0′} ∪ C ∪ F_*. No tiene índice r ni H; los vehículos idénticos se agregan por tipo, y los cargadores devuelven la batería a B y no llevan estado.

---

## 2. Preprocesamiento (todo se lee de los archivos de entrada)

**P1. Grafo vial.**
- Grafo OSM "drive" G = (V, A), dirigido, sobre el bbox de los nodos del CSV más un margen, con elevación h_v (DEM).
- Se queda la mayor componente fuertemente conexa (SCC).
- Snapping: cada fila (`base`, `visit`, `charger`) se asocia al nodo más cercano de la SCC.
- Los cargadores que caen en el mismo nodo vial se fusionan: un representante con la unión de conectores, cuyo id se usa en la salida.

**P2. Energía por tramo** (kWh), con ℓ_ij en km y Δh_ij = h_j − h_i en m:
```
e_ij = c·ℓ_ij + κ·( [Δh_ij]⁺ / η_d − η_r·[Δh_ij]⁻ ),   κ★ = m·g / 3.6·10⁶,   0 ≤ η_r ≤ 1 ≤ 1/η_d
```
- c★ se calibra con eVED (≈ 0.156 kWh/km; para robustez, p75).
- m se lee de `vehicle_types.csv`.
- No hay ciclos negativos (§0.1). Potencial p_v★ = κη_r h_v, de modo que se usa Dijkstra sobre e_ij + p_i − p_j ≥ 0.

**P3. Compatibilidad y tipos.**
- F_k = {f ∈ F : Conn(f) ∩ Conn_k ≠ ∅, puertos_f > 0}. Conn(f) se obtiene partiendo `connector_types` por ";" y normalizando; Conn_k es un parámetro del modelo de vehículo.
- Θ★ = clases de vehículos con iguales (B, b_ini, F_k); K_θ★ es la clase θ y n_θ★ = |K_θ|. Se escribe F_θ = F_k para k ∈ K_θ, y F_* = ∪_θ F_θ.
- Con los datos actuales: |Θ| = 1, n_θ = 2, |F_*| = 54.
- Un cargador incompatible sigue siendo una intersección por la que se puede pasar.

**P4. Nodos clave.** N★ = {0, 0′} ∪ C ∪ F_*, donde 0′ es la copia de llegada de la base.

**P5. Caminos y estadísticos.**
- Un Dijkstra desde cada i ∈ {0} ∪ C ∪ F_* da el árbol de caminos P_ij★.
- Sobre P_ij = (v₀, …, v_T) con energía acumulada s_t (s₀ = 0):
```
ê_ij = s_T     π̂_ij = max_t s_t     σ̂_ij = ê_ij − min_t s_t     λ̂_ij = max_t ( s_t − min_{t′≤t} s_{t′} )
```
- Se calculan por programación dinámica padre → hijo en el árbol: s(v) = d_red(v) − p_i + p_v; π̂(v) = max{π̂(pa), s(v)}; m(v) = min{m(pa), s(v)}; λ̂(v) = max{λ̂(pa), s(v) − m(v)}.
- Pares en el mismo nodo vial: todos los estadísticos valen 0.
- Los ê_ij son distancias mínimas, así que cumplen la desigualdad triangular.

**P6. Constantes.**
- β_0★ = b_ini = 0.6·B; β_f = B para f ∈ F_*.
- ρ_ij★ = min{β_i − ê_ij, B − σ̂_ij} para i ∈ {0} ∪ F_*.
- U★ = |C| + |K|.

**P7. Arcos A_θ★.** Son los (i,j) con i ∈ {0} ∪ C ∪ F_θ, j ∈ C ∪ F_θ ∪ {0′}, i ≠ j. Se eliminan:
- (a) los arcos con λ̂_ij > B − b̲;
- (b) los arcos con i ∈ {0} ∪ F_θ y β_i < b̲ + π̂_ij;
- (c) los arcos con i ∈ C y b̲ + π̂_ij > B.

Si un cliente queda sin arco de entrada o de salida, se fija y_i = 0. Dominancia opcional: la de A con la corrección E1.

**P8. Certificado de N\* = |C|** (§3.5).

Parámetros:
- B = capacidad útil (por defecto ≈ 16 kWh, la mediana eVED; 24 es la nominal).
- b̲ = reserva (parámetro, por ejemplo 0.1·B; 0 < b̲ ≤ b_ini).
- b_ini = 0.6·B.

---

## 3. Modelo MILP

### 3.1 Variables
| Variable | Dominio | Significado (equivalente en el PDF) |
|---|---|---|
| x_ijθ | {0,1} si i ∈ C o j ∈ C; {0,…,n_θ} si i = 0 o j = 0′ (sin clientes); {0,…,U} si (i,j) ∈ F_θ×F_θ | Veces que la clase θ recorre P_ij (x_ijkr del PDF, agregada por r y por k ∈ K_θ) |
| y_i | {0,1}, i ∈ C | Entrega (y_i del PDF; las a_ikr quedan implícitas) |
| b_i | [b̲, B], i ∈ C | Batería al llegar a i (b_kr); al salir, b̄_i = b_i porque no carga |
| φ_ijθ★ | ≥ 0, (i,j) ∈ A_θ | Flujo de conectividad |
| E_total | ℝ | Consumo total (ver (11)) |

Las q_kr, b̄_kr en cargadores, u_kr, γ_kr y E_kr del PDF no se necesitan. q se reconstruye en el post-proceso (§5).

### 3.2 Restricciones (las sumas recorren solo arcos de A_θ)
```
(1)  Σ_j x_0jθ = n_θ                                           ∀θ               (cada vehículo sale una vez; (0,0′) = no usado)
(2)  Σ_j x_jiθ = Σ_j x_ijθ                                     ∀θ, i∈C∪F_θ      (continuidad ⇒ Σ_i x_i0′θ = n_θ: todos vuelven)
(3)  y_i = Σ_θ Σ_j x_jiθ                                       ∀i∈C             (entrega ⇔ visita como nodo clave; ≤ 1)
(4)  φ_ijθ ≤ |C|·x_ijθ                                         ∀θ, (i,j)∈A_θ
(5)  Σ_j φ_jiθ − Σ_j φ_ijθ = Σ_j x_jiθ                         ∀θ, i∈C
(6)  Σ_j φ_jfθ − Σ_j φ_fjθ = 0                                 ∀θ, f∈F_θ
(7)  b_j ≤ B − (B − ρ_ij)·Σ_θ x_ijθ                            ∀i∈{0}∪F_*, j∈C  (salida con β_i, incluye saturación)
(8)  b_j ≤ b_i − ê_ij + (B − b̲ + ê_ij)·(1 − Σ_θ x_ijθ)         ∀i≠j∈C           (consumo entre clientes)
(9)  b_j ≤ B − σ̂_ij·Σ_θ x_ijθ                                  ∀i≠j∈C           (regeneración no almacenable)
(10) b_i ≥ b̲ + π̂_ij·Σ_θ x_ijθ                                  ∀i∈C, j∈C∪F_*∪{0′} (reserva en cada intersección y al volver)
(11) E_total = Σ_θ Σ_{(i,j)∈A_θ} ê_ij·x_ijθ
(12) φ_ijθ ≥ x_ijθ                                             ∀θ, (i,j)∈A_θ, j∈C   (desigualdad válida)
```
Las cotas de los dominios de x (n_θ, U) son parte del modelo.

### 3.3 Objetivo (lexicográfico, (16) del PDF)
```
(13) P1:  N* = max Σ_{i∈C} y_i       s.a. (1)–(10), (12)
(14) P2:  min E_total                s.a. (1)–(12),  Σ_{i∈C} y_i = N*
```

### 3.4 Validez (resumen de las demostraciones)
- **Batería.** Por el lema, la llegada exacta a j es min{b̄_i − ê_ij, B − σ̂_ij}. Para i ∈ {0} ∪ F, eso es ρ_ij. Las restricciones (7)–(9) imponen "≤" y no "=". La relajación es exacta porque más batería nunca quita factibilidad: el mapa es no decreciente y (10) es una cota inferior. Por eso no hacen falta binarias γ.
- **Reserva.** (10) junto con (a) y (c) garantiza la reserva en todo punto de los arcos que salen de clientes. (b) la garantiza en los arcos que salen de 0 y de cargadores, incluidos los que llegan a 0′. Esto cubre la causal de invalidez "batería insuficiente".
- **Cargadores sin estado.** Con (11), q no aparece en el objetivo. Cargar hasta B domina en factibilidad y no cambia E, así que es s.p.g. Por la desigualdad triangular de ê, visitar un cargador nunca reduce E: solo aparece si hace falta (o si hay empate, cuando el cargador está sobre el camino).
- **Conectividad.** Por (4)–(6), todo cliente atendido por θ es alcanzable desde 0 en el soporte de θ. Se agregan n_θ arcos 0′ → 0. La componente de 0 queda euleriana y conexa, y su circuito se corta en n_θ paseos 0 → 0′. Con esto, "volver al depósito" se cumple por construcción.
  - Los ciclos de solo-cargadores no alcanzables desde 0 no tienen clientes. Como ê ≥ 0, se descartan sin aumentar E.
  - Reemparejar entradas y salidas en un cargador es inocuo, porque siempre se sale con B. Cada cliente tiene un único predecesor y un único sucesor, así que su b_i es independiente de cómo se corten los paseos.
- **Cota U = |C| + |K|.** Sea una solución óptima. Entre dos nodos consecutivos que no son cargadores, la cadena de cargadores no repite ninguno: si repite, el ciclo intermedio se puede quitar, porque sale y vuelve con B y tiene ê ≥ 0. Hay a lo más |C| + |K| cadenas, y cada arco f→g aparece a lo más una vez por cadena. La cota vale también para P1.
- **Agregación.** Con F_k distintos, |Θ| = |K| y el modelo coincide con A v1 por vehículo. Con vehículos idénticos desaparece la simetría |K|!.

### 3.5 Certificado polinomial de N* = |C| (se omite P1)
Para una clase θ con n_θ ≥ 1, sea D_θ el subgrafo de A_θ sobre {0, 0′} ∪ F_θ. Sea S una componente fuertemente conexa de D_θ alcanzable desde 0 y que alcanza a 0′. Se define C★ = {i ∈ C : ∃ f, g ∈ S con (f,i), (i,g) ∈ A_θ y ρ_fi ≥ b̲ + π̂_ig}.

Entonces un solo vehículo puede recorrer 0 ⇝ f₁ → i₁ → g₁ ⇝ f₂ → i₂ → … ⇝ 0′, que es factible porque cada cliente queda "emparedado" entre cargadores. Por lo tanto N* ≥ |C★|, y si C★ = C, entonces N* = |C|.

El costo es O(|C|·|F|²) más una búsqueda de SCC, y la ruta construida sirve de solución inicial para P2. Con los datos actuales (todo cliente a ≤ 3 km de un cargador compatible y B ≈ 16 kWh) es esperable que C★ = C, aunque no lo verifiqué numéricamente. Si C★ ≠ C, se resuelve P1 con warm start desde esa ruta.

---

## 4. Tamaño y estrategia

Arcos por clase con |C| = 20 y |F_*| = 54, antes de la poda (aritmética exacta):

| Grupo | Arcos | Dominio |
|---|---|---|
| que tocan un cliente (0→C, C→C, C→F, F→C, C→0′) | 2 580 | binarios |
| 0→F, F→0′, 0→0′ | 109 | {0..n_θ} |
| F→F | 2 862 | {0..U} |
| φ | 5 551 | continuas |
| b, y | 40 | — |

Comparación: el PDF sobre OSM tiene ~10⁷ binarias. El tamaño escala con (|C| + |F_*|)² y no depende del grafo vial ni de H. El preprocesamiento son |N| Dijkstra, O(|N|·|A| log|V|).

Estrategia:
1. P1–P8.
2. Si C★ = C: resolver solo P2 con y_i = 1 ∀i y la ruta del certificado como warm start.
3. Si no: P1 y luego P2.

Aceleraciones (no exactas, se declaran si se usan):
- (i) Eliminar los arcos F→F. Solo sirven cuando un salto cargador–cargador es necesario por perfil de energía, algo improbable con un alcance de ≈ 100 km desde B.
- (ii) Quedarse con los r mejores cargadores por par (i,j) según ê_if + ê_fj.
- (iii) Cambiar φ por cortes de conectividad perezosos en un callback.

---

## 5. Extracción del diccionario y post-proceso

1. Redondear x. Para cada θ, armar el multigrafo, agregar n_θ arcos 0′→0 y aplicar Hierholzer desde 0. Cortar el circuito en n_θ paseos y descartar las componentes no alcanzables desde 0.
2. Asignar los paseos a los vehículos de K_θ en orden.
   - Mapear 0 y 0′ → id de la base, cliente → su id, cargador → su id (el representante si hubo fusión).
   - Salida: `{k: [BASE, V.., C.., …, BASE]}`. Un vehículo sin usar queda como [BASE, BASE].
   - Opcional: borrar los cargadores cuya q resulte 0 (paso 3).
3. **Carga mínima (inducción hacia atrás).** En cada segmento entre paradas de carga, R_last = b̲ + π̂_{last,next} y R_i = max{b̲ + π̂_ij, R_j + ê_ij}. En cada cargador f, q_f = max{0, R_f − b_f}.
   - Esta trayectoria es puntualmente mínima. La pérdida por saturación en el arco (i,j) es max{0, b̄_i − ê_ij − (B − σ̂_ij)}, no decreciente en b̄_i.
   - Por lo tanto, para la ruta fija, minimiza el E efectivo del PDF: (15) = Σ_k(b_ini + Σq − b_final).
4. Validación independiente del solver: expandir cada par a calles (predecesores de P5) y simular b ← min{B, b − e} arco por arco. Verificar b ≥ b̲ en todo el recorrido y la llegada a la base. Reportar E nominal (11) y E efectivo (15).

---

## 6. Variante exacta con E efectiva (15) del PDF

Si el jurado mide E como (15), con la saturación descontada, una ruta óptima para (11) puede no serlo para (15): la diferencia es solo la regeneración perdida, que es 0 si e ≥ 0 o si la ruta nunca satura. Para optimizar (15) de forma exacta hay que darle estado a los cargadores:

- copias f¹…f^ρ de cada cargador, cada una visitada a lo más una vez;
- b_f, q_f ∈ [0, B − b̲] y b̄_f = b_f + q_f ∈ [b̲, B];
- (7)–(9) con b̄_i en lugar de β_i, y retorno β★_i ≤ min{b̄_i − ê_i0′, B − σ̂_i0′}, con x;
- E_total = b_ini·|K| + Σ_f q_f − Σ_i β★_i, con φ igual que en §3.

Es la formulación de B v1 §4.3, corregida con el filtro λ̂ y con φ en lugar de MTZ. Se pierde la ausencia de estado y el tamaño crece con ρ. Recomendación: usar §3 y reportar (15) desde el post-proceso.

---

## 7. Supuestos y límites
- Supuestos del equipo: sin tiempo, velocidad, jornada, capacidad de paquetes ni colas; dos vehículos pueden usar el mismo cargador.
- La optimalidad es exacta respecto del grafo contraído. La pérdida frente al grafo vial completo viene solo de guardar un camino por par:
  - con e ≥ 0 la contracción es exacta (π̂ = σ̂ = λ̂ = ê);
  - con regeneración, otro camino con mayor ê pero menor π̂/λ̂ o menor σ̂ podría servir con poca batería. Se corrige con arcos paralelos Pareto (ê, π̂, σ̂, λ̂) mediante etiquetas multicriterio (ver E5).
- B, b̲, c, η_r y η_d son parámetros. Conviene sensibilidad con B ∈ {13, 16, 24} y c en p25–p90 de eVED.
- Se desconoce la métrica exacta de "consumo total" del jurado; por eso se reportan (11) y (15).
