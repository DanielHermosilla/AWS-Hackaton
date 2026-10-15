# Base de conocimiento — E-VRP por turnos (hackatón)

Estado: borrador de modelado. Fuente de datos: `DATA/` (nodos + eVED) y `dict/README.es.md`.

---

## 1. Datos conocidos (extraídos de `DATA/`)

### 1.1 Nodos (`competition_routing_nodes.csv` / `evaluation_routing_nodes.csv`)

| Elemento | Valor | Comentario |
|---|---|---|
| Bases | 1 (`BASE`, 42.27708, −83.76281) | Única base. **No es cargador** (cargador más cercano a 0.99 km) |
| Clientes | 20 (`V1`–`V20`) | Distintos entre competición y evaluación. Sin demanda, sin ventana horaria, sin tipo entrega/recolección |
| Cargadores | 60 (`C1`–`C62`, faltan C21 y C57) | Idénticos en ambos archivos. 321 puertos en total |
| Distancia recta BASE→cliente | 1.0 – 7.8 km (mediana ≈ 5 km) | Haversine, sin red vial |
| Máx. distancia entre dos puntos (base + clientes) | 13.7 km | ≈ 18 km por calle con factor 1.3 |
| Cargador compatible más lejano a un cliente | 2.97 km | Todo cliente tiene un cargador cerca |

### 1.2 Vehículo (`eVED_EV.csv`, `vehicle_types.csv`, README)

| Parámetro | Valor | Fuente / cómo se obtuvo |
|---|---|---|
| Modelo | Nissan Leaf 2013 (los 3 EV del dataset) | README §2.2 |
| Batería nominal | 24 kWh | README §2.2 |
| Batería útil efectiva | **≈ 16 kWh** (mediana; p25–p75: 13.0–17.3) | Energía integrada / ΔSOC en 49 viajes con ΔSOC ≥ 10 % |
| Batería al salir | 0.6 · B_max ≈ 9.7 kWh (con 16 kWh) | Dato del enunciado |
| Consumo | **0.156 kWh/km** global (mediana por viaje 0.144; p10–p90: 0.094–0.235) | 379 viajes > 2 km, energía integrada con Δt real |
| Autonomía al salir | ≈ 62 km con 9.7 kWh y 0.156 kWh/km | Derivado |
| Velocidad media | ≈ 33 km/h (mediana por viaje, incluye detenciones) | eVED_EV |
| Conectores del vehículo | J1772 (AC) y CHAdeMO (DC) | Especificación del Leaf 2013 (no está en los datos) |
| Potencia AC a bordo | 3.3 o 6.6 kW según versión | Especificación del Leaf 2013 (supuesto) |
| Potencia DC máx. | ≈ 50 kW (CHAdeMO) | Especificación del Leaf 2013 (supuesto) |
| Peso | 3,500 lb (≈ 1,590 kg), redondeado | `vehicle_types.csv` |

**Ojo:** `Energy_Consumption` debe multiplicarse por Δt real (s) antes de sumar; la suma directa sobrestima ≈ 2.1×. (README §9.1)

### 1.3 Cargadores y compatibilidad con el Leaf

| Grupo | Cargadores | Potencia efectiva para el Leaf |
|---|---|---|
| Incompatibles (solo CCS y/o NACS) | C1, C2, C4, C5, C11, C14 | No se pueden usar |
| DC con CHAdeMO | C3, C6, C7, C8, C9, C10, C12 | min(max_power_kw, 50) |
| Solo AC (J1772) | Los 47 restantes | min(max_power_kw, 6.6) |

Varios cargadores DC "potentes" del archivo (C1 400 kW, C2 350 kW) son inútiles para este vehículo.

### 1.4 Datos que NO están y hay que definir o suponer

| Dato | Necesario para | Propuesta si el enunciado no lo da |
|---|---|---|
| Número de vehículos \|K\| | Conjunto K | Parámetro; probar 1–5 |
| Capacidad de carga Q_k (kg o unidades) | Restricción de capacidad | Parámetro |
| Demanda d_i de cada cliente | Restricción de capacidad | Unitaria (d_i = 1) si no se da |
| Tiempo de servicio s_i | Tiempo | 5–10 min |
| Horizonte / jornada H | Tiempo | 8 h |
| Batería mínima de reserva B_min | Seguridad | 10–20 % de B_max |
| Batería final exigida al volver | Cierre | ≥ B_min |
| Número de turnos R | Tamaño del modelo | Ver §4 |
| Matriz de distancias real | e_ij, t_ij | Haversine × 1.3, o OSRM/OSMnx |

---

## 2. Notación

| Símbolo | Tipo | Significado |
|---|---|---|
| K | conjunto | Vehículos |
| R = {0, …, R̄} | conjunto | Turnos (posición en la secuencia de la ruta, **no** es tiempo) |
| C | conjunto | Clientes (V1–V20) |
| F | conjunto | Cargadores **compatibles** (54) |
| N = {0} ∪ C ∪ F | conjunto | Nodos; 0 = BASE |
| B̄ | parámetro | Capacidad útil de batería (≈ 16 kWh) |
| β = 0.6 | parámetro | Fracción de carga inicial |
| B_min | parámetro | Reserva mínima |
| Q_k | parámetro | Capacidad de carga del vehículo k |
| d_i | parámetro | Demanda del cliente i |
| e_ij | parámetro | Energía para ir de i a j = h · dist_ij (h = 0.156 kWh/km) |
| t_ij | parámetro | Tiempo de viaje de i a j |
| P_i | parámetro | Potencia efectiva del cargador i para el Leaf (§1.3) |
| s_i | parámetro | Tiempo de servicio en el cliente i |
| H | parámetro | Duración máxima de la jornada |
| x_kri ∈ {0,1} | variable | El vehículo k está en el nodo i en el turno r |
| z_krij ∈ {0,1} | variable | El vehículo k va de i (turno r) a j (turno r+1) |
| y_i ∈ {0,1} | variable | El cliente i es atendido |
| b_kr ≥ 0 | variable | Batería de k al **llegar** en el turno r |
| g_kr ≥ 0 | variable | Energía **recargada** por k en el turno r |
| B_kr ≥ 0 | variable | Batería de k al **salir** en el turno r: B_kr = b_kr + g_kr |
| q_kr ≥ 0 | variable | Energía **consumida** por k al viajar del turno r al r+1 |
| T_kr ≥ 0 | variable | Hora de llegada de k en el turno r |

Cambios respecto de la notación original del equipo:
- La capacidad se llama **B̄** para no confundirla con B_kr (batería al salir).
- Se separan **g_kr** (energía recargada) y **q_kr** (energía consumida en el trayecto). Con una sola variable no se puede escribir el balance.

---

## 3. Restricciones

### 3.1 Ubicación y secuencia

```
(R1) Un nodo por vehículo y turno:     Σ_{i∈N} x_kri = 1                         ∀k, r
(R2) Inicio en la base:                x_k,0,0 = 1                               ∀k
(R3) Fin en la base:                   x_k,R̄,0 = 1                               ∀k
(R4) Enlace de movimiento:             Σ_j z_krij = x_kri                        ∀k, r<R̄, i
                                       Σ_i z_krij = x_k,r+1,j                    ∀k, r<R̄, j
(R5) Esperar solo en la base (relleno de turnos sobrantes):
                                       z_kr00 permitido; z_krii = 0              ∀i ≠ 0
```

### 3.2 Clientes

```
(R6) Cada cliente a lo más una vez:    Σ_k Σ_r x_kri ≤ 1                         ∀i∈C
(R7) Atendido ⇔ visitado:              y_i = Σ_k Σ_r x_kri                       ∀i∈C
(R8) Capacidad de carga:               Σ_{i∈C} d_i · Σ_r x_kri ≤ Q_k             ∀k
```

### 3.3 Batería

```
(R9)  Batería inicial:                 b_k0 = β · B̄
(R10) Batería al salir:                B_kr = b_kr + g_kr                        ∀k, r
(R11) Tope de batería:                 B_kr ≤ B̄                                  ∀k, r
(R12) Recarga solo en cargadores compatibles:
                                       g_kr ≤ B̄ · Σ_{i∈F} x_kri                  ∀k, r
(R13) Consumo del tramo:               q_kr = Σ_i Σ_j e_ij · z_krij              ∀k, r<R̄
(R14) Balance:                         b_k,r+1 = B_kr − q_kr                     ∀k, r<R̄
(R15) Reserva mínima:                  b_kr ≥ B_min                              ∀k, r
```

(R15) también hace que nunca se tome un tramo sin batería suficiente.

### 3.4 Tiempo

```
(R16) Llegada al turno siguiente:
      T_k,r+1 ≥ T_kr + Σ_{i∈C} s_i x_kri + τ_kr + Σ_ij t_ij z_krij
(R17) Tiempo de carga según el cargador:
      τ_kr ≥ g_kr / P_i − M(1 − x_kri)                                           ∀k, r, i∈F
(R18) Jornada:                         T_k,R̄ ≤ H                                ∀k
```

### 3.5 Opcionales

```
(R19) Romper simetría (vehículos idénticos):   Σ_r Σ_{i∈C} x_kri ≥ Σ_r Σ_{i∈C} x_k+1,r,i
(R20) Carga lineal válida solo hasta ~80 %:    B_kr ≤ 0.8 · B̄ si se carga en DC
```

### 3.6 Función objetivo

Si no se premia y_i, la solución óptima es no atender a nadie. Propuesta lexicográfica:

```
max  W · Σ_{i∈C} y_i  −  Σ_k Σ_r q_kr  −  λ · Σ_k T_k,R̄          (W ≫ 1)
```

---

## 4. Lo que se está pasando por alto

1. **Función objetivo.** Con "a lo más una vez" y y_i binaria, falta decir qué se optimiza. Si hay que atender a todos, (R6) pasa a ser "= 1" y y_i deja de hacer falta.
2. **Enlace entre turnos.** El consumo depende del par (nodo en r, nodo en r+1). El producto x_kri · x_k,r+1,j no es lineal, así que hace falta z_krij (R4, R13).
3. **Recarga y consumo mezclados.** La definición original de q ("energía usada durante la visita") junto con B = b + recarga deja la recarga sin variable propia. Ya están separadas (g, q).
4. **Recargar solo en cargadores (R12).** Sin esta restricción, el modelo recarga en clientes o en la base.
5. **Compatibilidad de conectores.** 6 de los 60 cargadores no sirven para el Leaf, y la potencia efectiva está limitada a 6.6 kW (AC) o 50 kW (DC).
6. **El turno no es tiempo.** Dos vehículos en el mismo turno r pueden estar en momentos muy distintos. Una restricción de puertos del tipo "Σ_k x_kri ≤ ports_i por turno" es **incorrecta**. Con 321 puertos y pocos vehículos se puede ignorar, o modelarla en tiempo si se exige.
7. **Turnos sobrantes.** Si R̄ es fijo, los vehículos que terminan antes necesitan un estado de espera (R5). Si no, el modelo es infactible o inventa visitas.
8. **Cierre de la ruta.** Hay que volver a la base (R3), con reserva mínima (R15).
9. **Tamaño del modelo.** z tiene |K|·R̄·|N|² variables. Con N = 75 (sin incompatibles), K = 3 y R̄ = 12 son ≈ 200 mil binarias. Conviene **preseleccionar cargadores**: por ejemplo, el mejor por zona o los 2–3 más cercanos a cada cliente, para quedar en unos 10–15. Una cota útil es R̄ ≥ ⌈|C|/|K|⌉ + (paradas de carga) + 2.
10. **Capacidad real de la batería.** El dato de 24 kWh es nominal. Los datos muestran unos 16 kWh útiles (Leaf 2013 degradado). El 60 % de una o de otra cambia la autonomía de 90 a 62 km.
11. **Variabilidad del consumo.** p10–p90 va de 0.09 a 0.24 kWh/km (calefacción en invierno, velocidad). Conviene usar un valor conservador o hacer un análisis de sensibilidad.
12. **Factibilidad individual.** Todo cliente está a menos de 3 km de un cargador compatible y a menos de 8 km (recta) de la base. Ningún cliente es inalcanzable. La batería restringe la ruta completa, no cada visita.
13. **Doble sentido de "carga".** "Capacidad máxima de carga" puede ser de mercadería (Q) o de batería (B̄). Los datos no traen demandas, así que Q no se puede calibrar sin el enunciado.


---

## 5. Versión 2: supuestos y formulación sobre el grafo vial (propuesta del compañero)

### 5.1 Supuestos acordados
- Se ignoran el tiempo de carga y la velocidad: no hay tiempo, ni jornada, ni potencia de cargador. Solo importa la compatibilidad (F_k).
- Consumo por tramo e_ij determinista. Puede ser negativo (regeneración).
- Nodos = grafo vial (intersecciones) ∪ clientes ∪ cargadores ∪ depósito. x_ijkr = recorrer el tramo (i,j) en el movimiento r; z_ikr = ubicación.
- a_ikr = entrega en una visita concreta. Se puede pasar varias veces por un cliente.
- q_kr = energía recargada. b_kr = batería al llegar, b̄_kr = b_kr + q_kr = batería al salir.
- Objetivo lexicográfico: máx Σ y_i y luego mín E_total.

### 5.2 Observaciones pendientes
1. "Todos los nodos exactamente una vez" se aplica a los **clientes** (entrega), no a los nodos viales.
2. Con estos datos y supuestos, todas las entregas son factibles, así que máx Σy_i = |C|. Puede fijarse Σ a_ikr = 1 y dejar solo mín E_total.
3. Escala: el grafo vial completo con índice de posición r significa H ≈ cientos o miles de movimientos y decenas de millones de x. Propuesta: precalcular caminos de mínima energía entre los nodos clave (depósito, clientes, cargadores) con Bellman-Ford o Johnson, que admiten e_ij < 0, y resolver el E-VRP sobre ese grafo reducido.
4. min{B, ·} se lineariza sin binarias: b_{k,r+1} ≤ b̄_kr − Σe·x y b_{k,r+1} ≤ B. El objetivo de minimizar E_total empuja b hacia arriba.
5. Desapareció la capacidad de carga: falta Σ_i d_i Σ_r a_ikr ≤ Q_k. Sin ella, ni el tiempo ni la carga limitan a un solo auto, y la flota no importa.
6. Falta definir de dónde salen e_ij (modelo de consumo calibrado con eVED: largo, pendiente, límite de velocidad), la fuente de elevación de los tramos y el ajuste (snapping) de las coordenadas de clientes y cargadores a nodos del grafo.
7. Falta conocer la métrica de evaluación del concurso (¿energía? ¿distancia?) y cómo se usa `evaluation_routing_nodes.csv`.


---

## 6. Enunciado oficial (`DATA/bb-assets-c1-presentation.pptx`, CASE FCFM)

- Flota: **2 Nissan Leaf 2013**, ambos con **60 % de SoC inicial**.
- Red: 1 centro de distribución (inicio y término de ambos), 20 locales, 60 cargadores (6.2–400 kW).
- Objetivo: **maximizar entregas cumplidas** sin que ningún vehículo se quede sin batería.
- Desempate: **menor consumo energético total (kWh)** y **menor tiempo de cómputo (s)**.
- Invalida o penaliza: no volver al centro, o batería en un nivel insuficiente para seguir operando.
- Evaluación: grafo **reservado** con el mismo formato y distinta ubicación del centro, los locales y los cargadores. Se ejecuta el mismo código cambiando solo los archivos de entrada. **No hardcodear IDs ni compatibilidades.**
- Escalabilidad: 20+ nodos y 2+ vehículos.
- Jurado: innovación 25 %, impacto 25 %, factibilidad 20 %, escalabilidad 15 %, presentación 15 %.
- No se mencionan capacidad de carga, demandas, ventanas horarias ni tiempo de ruta como KPI.


---

## 7. Implementación preliminar (`evrp/`)

- Comando: `.venv\Scripts\python -m evrp solve --nodes <csv> [--config config.yaml] [--out results] [--red osm] [--tiempo s] [--vehiculos n]`. Calibración: `python -m evrp calibrar`.
- Pipeline configurable (`config.yaml`): red haversine|osm (respaldo automático a haversine si falla OSM) → instancia contraída (ê, π̂, σ̂, λ̂, filtros, dominancia de cargadores) → heurística (tour + 2-opt + split + búsqueda local; certifica N*=|C|) → MILP HiGHS → validador independiente → salidas.
- MILP por defecto, "compacta": el cargador es un atributo del arco (≤1 cargador entre paradas, Pareto por par), con MTZ elevado. Si quedan clientes sin atender, cae a la "completa" (grafo con cargadores y cortes de conectividad), que admite cadenas F→F.
- Resultados con haversine: competición 11.22 kWh y evaluación 10.83 kWh, ambas óptimas y 20/20, con 1 vehículo. Con OSM, competición 11.85 kWh. Con `usar_todos_vehiculos: true`, competición 11.43 kWh.
- IA generativa: interfaz `Asesor` (nulo por defecto; Bedrock opcional con lista blanca de ajustes y explicación de rutas).
