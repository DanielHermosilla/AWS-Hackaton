# 02 — Datos y física de energía para la etapa de caminos (Dijkstra)

**Rol:** investigador de datos y física de energía.
**Fuente empírica:** `data/eVED_EV.csv` (3 Nissan Leaf 2013, telemetría ~1 Hz, Ann Arbor
2017–18). Análisis propio por *streaming* de 476.308 filas / 504 viajes (CPU < 1 min).
**Modelo de referencia:** `src/evrp/energia.py` →
`e = c·ℓ + κ·([Δh]⁺/η_d − η_r·[Δh]⁻)`, con `κ = m·g/3.6e6` kWh/m de desnivel.

> **Nota de reproducibilidad:** los scripts fueron temporales y se eliminaron (no se tocó
> código fuente ni tests). Las cifras marcadas *[emp]* provienen de ese análisis; las
> marcadas *[lit]* de literatura citada; *[baja conf.]* señala muestra escasa.

---

## 0. Hallazgo crítico sobre el subconjunto empaquetado

- **Convención de signo (verificada):** `Energy_Consumption` > 0 = consumo (tracción),
  < 0 = regeneración. Confirmado porque filas con corriente `I>0` tienen aceleración
  media **−0,68 m/s²** (frenado) y `I<0` tienen **+0,29 m/s²**: la corriente de batería
  usa convención inversa, pero `Energy_Consumption` ya trae el signo físico correcto. *[emp]*
- **`Gradient` está mayormente anulado en este CSV:** sólo **12,1 %** de filas tiene
  gradiente ≠ 0; rango ±8,8 %, elevación 227–312 m (84 m de rango real en Ann Arbor).
  **Consecuencia:** no se puede calibrar `η_d`/`η_r` de forma robusta sólo con este CSV;
  la pendiente fiable debe venir del DEM (USGS/Copernicus) sobre el grafo OSM, no de la
  telemetría empaquetada. *[emp]*

---

## 1. ¿Cuánta energía se regenera y en qué situaciones?

| Métrica | Valor | Fuente |
|---|---|---|
| Energía de regeneración / energía de tracción | **≈ 25 %** (ratio \|regen\|/consumo = 24,9 %) | *[emp]* |
| Consumo neto medio de flota | **0,155 kWh/km** (coincide con 0,157 por defecto) | *[emp]* |
| Potencia de **tracción**: mediana / p95 / p99 / máx | 6,2 / 17,9 / 28,1 / **44,0 kW** | *[emp]* |
| Potencia de **regeneración**: mediana / p95 / p99 / máx | 9,2 / 27,0 / 36,8 / **~110 kW** (picos) | *[emp]* |

- **Frenado vs bajada:** no separable con este CSV (99,9 % de la regen cae en filas con
  gradiente ≈ 0 por el anulado del §0). Físicamente la regen tiene dos orígenes: frenado
  (energía cinética) y bajada sostenida (energía potencial). *[emp + razonamiento]*
- **Regen vs desaceleración:** la potencia de regen **disminuye** al endurecer el frenado
  (decel 0,0→1,5 m/s²: 8,0→2,7 kW mediana), señal de que el **freno de fricción** domina en
  frenadas fuertes y la regen está **acotada por potencia** del inversor/batería. Para
  routing predictivo esto implica: *la regen recuperable por un arco está limitada, no es
  proporcional ilimitada a Δh⁻.* *[emp]*
- **Cota práctica de recuperación:** usar p95 ≈ **27 kW** como potencia de regen sostenible
  (los ~110 kW son transitorios de <1 s, no sostenibles). *[emp]*

---

## 2. Eficiencias empíricas de tracción y regeneración

El cálculo por viaje de `η_d`/`η_r` quedó *[baja conf.]* por el gradiente anulado (muestra
insuficiente con desnivel neto). Señal direccional sí observable:

| Gradiente (filas ≠ 0) | Consumo neto |
|---|---|
| +1 % (subida) | 0,238 kWh/km |
| ±0 % | 0,140 kWh/km |
| −1 % (bajada) | 0,047 kWh/km |

Monótono y del signo esperado: subir cuesta más, bajar recupera. *[emp, baja conf.]*

**Valores recomendados** (coherentes con el modelo actual y literatura de BEV):

| Parámetro | Valor sugerido | Base |
|---|---|---|
| η_d (tracción, batería→rueda) | 0,85–0,90 | *[lit]* típico BEV; modelo usa 0,90 |
| η_r (regeneración, rueda→batería) | 0,55–0,65 | *[lit]*; modelo usa 0,60; consistente con regen≈25 % del consumo *[emp]* |
| m (Leaf 2013 + carga) | 1.520–1.600 kg | *[lit]* Leaf ~1.493 kg vacío; modelo usa 1.590 |

> El producto η_d·η_r ≈ 0,5–0,55 (ida y vuelta de desnivel) es consistente con la
> asimetría observada subida/bajada. *[emp + lit]*

---

## 3. Consumo vs velocidad, temperatura y auxiliares

**Velocidad** (kWh/km netos, bins de 10 km/h) — curva en U suave: *[emp]*

| km/h | 10–20 | 30–40 | 50–60 | 70–80 | 100–110 | 110–120 |
|---|---|---|---|---|---|---|
| kWh/km | 0,131 | 0,165 | 0,134 | 0,146 | 0,146 | 0,193 |

Mínimo ~45–65 km/h; sube en ciudad (arranque/freno) y en autopista (aerodinámica). El
modelo plano `c` captura la media pero no esta curvatura.

**Temperatura (OAT)** — efecto fuerte vía climatización: *[emp]*

| OAT (°C) | −10 | 0 | 10 | 20 | 30 |
|---|---|---|---|---|---|
| kWh/km | 0,226 | 0,178 | 0,131 | 0,127 | 0,121 |

Consumo a −10 °C es **~1,8×** el de 20 °C. Para el CASE a 60 % SoC la temperatura puede
decidir viabilidad.

**Auxiliares (A/C y calefacción):** *[emp]*

| Carga | Mediana | p95 | Máx |
|---|---|---|---|
| A/C (>0) | 400 W | 1.100 W | 3.100 W |
| Calefacción (>0) | 750 W | 3.500 W | 4.250 W |
| Fracción aux/energía total por viaje | 8,4 % | p90 = 29,5 % | — |

Los auxiliares dependen del **tiempo**, no de la distancia → refuerzan la necesidad de
modelar tiempo por arco (§4). Un término aux de potencia constante `P_aux·t_arco` es más
fiel que repartirlo por km.

---

## 4. Velocidad efectiva por tipo de vía / límite (para tiempo por arco)

Velocidad real en movimiento (v > 5 km/h) por límite señalizado — para derivar
`t_arco = ℓ / v_ef(highway, maxspeed)` desde OSM: *[emp]*

| Límite [km/h] | Media | Mediana | p85 | n | ~OSM highway |
|---|---|---|---|---|---|
| 40 | 33,0 | 33,7 | 47,5 | 99.960 | residential |
| 48 (30 mph) | 39,2 | 41,5 | 54,8 | 83.062 | residential/tertiary |
| 56 (35 mph) | 46,5 | 51,5 | 65,2 | 136.179 | secondary |
| 64 (40 mph) | 53,0 | 59,0 | 69,9 | 34.417 | primary |
| 72 (45 mph) | 54,5 | 58,9 | 73,3 | 36.766 | primary |
| 113 (70 mph) | 104,9 | 108,6 | 117,6 | 7.884 | motorway |

**Regla práctica:** `v_ef ≈ 0,80–0,90 · maxspeed` en vías urbanas (media < límite por
semáforos/intersecciones), y `≈ maxspeed` en autopista. Si falta `maxspeed`, usar tabla por
`highway` con la mediana de arriba. Para cotas de tiempo máximo (restricción X min) conviene
la **mediana** (viaje típico) y la **p85** como reserva pesimista.

---

## 5. Modelo de energía por arco OSM recomendado

### 5.1 Fórmula (extiende el modelo actual con tiempo, auxiliares y regen acotada)

Para un arco `a` de longitud `ℓ` (km), desnivel `Δh` (m, del DEM), velocidad efectiva
`v_ef` y duración `t = ℓ/v_ef`:

```
e_a = c(v_ef)·ℓ                         # rodadura+aero, dependiente de velocidad
    + κ·[Δh]⁺/η_d                        # subida (siempre consume)
    − min( κ·η_r·[Δh]⁻ ,  E_regen_máx )  # bajada, ACOTADA
    + P_aux·t / 3600                     # auxiliares por tiempo (kWh, P_aux en kW)
```

con las dos cotas de regeneración (clave para fidelidad y para SoC válido):

```
E_regen_máx = min( P_regen_máx · t / 3600 ,   # cota por POTENCIA del tren motriz
                   (SoC_máx − SoC_v)·Cap )      # cota por BATERÍA LLENA
```

- `P_regen_máx ≈ 27 kW` (p95 sostenible) *[emp]*; `P_aux` desde OAT (ej. 0,4 kW base,
  +hasta 3,5 kW con calefacción) *[emp]*.
- La cota por batería llena **sólo se conoce en ejecución** (depende del SoC en `v`), no es
  atributo estático del arco → ver §6. En la fase estática usar la cota por potencia; la de
  batería llena se aplica al simular SoC a lo largo de la ruta.

### 5.2 Parámetros y cómo calibrar/validar

| Parámetro | Fuente de calibración |
|---|---|
| `c(v_ef)` | regresión del consumo neto vs velocidad en arcos **sin desnivel** (bins §3) |
| `κ, η_d, η_r` | fijar `κ` por física (m,g); `η_d,η_r` de literatura y ajuste fino en viajes con desnivel neto DEM |
| `P_regen_máx` | p95 de potencia de regen observada (§1) |
| `P_aux(OAT)` | A/C + calefacción vs OAT (§3) |
| `v_ef(highway,maxspeed)` | tabla §4 |

- **Validación con separación de viajes (train/test por `Trip`):** calibrar en ~70 % de
  viajes, validar energía total predicha vs real en el 30 % restante. Nunca mezclar filas de
  un mismo viaje entre train y test (fuga temporal).
- **Métrica:** MAE/MAPE de energía por viaje y verificación de signo (no predecir ganancia
  neta de energía en rutas cerradas).

### 5.3 Incertidumbre para reservas (SoC de seguridad)

El consumo por km es dispersó: usar **percentiles** del consumo por viaje como reserva.
*[emp]* el consumo neto medio fue 0,155 kWh/km; recomendación operativa:

| Uso | Valor |
|---|---|
| Energía esperada por arco | mediana de `c` |
| **Reserva de factibilidad (SoC)** | p85–p90 de `c` + penalización por OAT frío |
| Regen a efectos de factibilidad | usar cota **conservadora** (η_r bajo, p25) — no apostar a recuperar el máximo |

Regla asimétrica clave: **para no agotar la batería, sobreestimar consumo y subestimar
regeneración.**

---

## 6. Qué se sabe de una ruta FUTURA (mapa) vs sólo telemetría

| Magnitud | ¿Ruta futura (solo OSM/DEM)? | Sólo en telemetría |
|---|---|---|
| Longitud `ℓ` del arco | ✅ geometría OSM | — |
| Desnivel `Δh` | ✅ DEM (USGS/Copernicus) sobre nodos | (gradiente eVED, anulado aquí) |
| `maxspeed`, `highway` | ✅ OSM | — |
| `v_ef`, `t_arco` | ✅ estimado con tabla §4 | velocidad instantánea real |
| Consumo esperado `c(v_ef)` | ✅ modelo calibrado | consumo real por fila |
| `P_aux` | ✅ si se conoce OAT previsto | A/C/calefacción reales |
| **SoC en cada nodo** | ❌ **sólo por simulación** sobre la ruta elegida | SOC medido |
| Regen limitada por batería llena | ❌ depende de SoC acumulado → simular | — |
| Tráfico/semáforos puntuales | ❌ (no modelado) | implícito en velocidad real |

**Implicación para Dijkstra:** el coste de arco (energía, tiempo) es estático y conocido del
mapa, pero la **factibilidad SoC** (no negativo en ningún punto) y la **regen acotada por
batería llena** son dependientes del estado y deben verificarse simulando el SoC a lo largo
del camino, o resolverse con etiquetas de estado (energía/SoC) — ver documentos de
restricciones y SoC de esta carpeta. El coste de energía puede ser negativo (regen); el
potencial `p(v)=κ·η_r·h(v)` del modelo actual ya reduce los pesos a ≥ 0 para Dijkstra exacto,
pero esa reducción **no** modela las cotas de potencia/batería (que rompen la telescopía): si
se añaden, Dijkstra puro deja de ser exacto y se requiere búsqueda con estado de energía.

---

## Referencias (DOI/URL verificados)

- **García Bustos, J. E.; Brito Schiele, B.; Masserano, B.; et al.** (PHM Society Conf.
  2025). *A novel data-driven framework for driving range prognostics in electric
  vehicles* (grupo PUC Chile; Orchard, Acuña Ureta, Pérez). Autoría **verificada**.
  PDF: https://papers.phmsociety.org/index.php/phmconf/article/download/4370/phmc_25_4370 —
  versión revista: Eng. Appl. Artif. Intell. (2024), DOI
  https://doi.org/10.1016/j.engappai.2024.109925 *(DOI verificado por búsqueda; texto no
  descargado por 403)*.
- **Zhang, S. et al.** *An Extended Vehicle Energy Dataset (eVED)*. arXiv:2203.08630.
  https://arxiv.org/abs/2203.08630 · repo https://github.com/zhangsl2013/eVED (verificado).
- **Oh, G. et al.** *Vehicle Energy Dataset (VED)*. IEEE T-ITS 2020, DOI
  https://doi.org/10.1109/TITS.2020.3035596 (verificado).
- Nissan Leaf 2013: masa en vacío ~1.493 kg, batería ~24 kWh (~21 kWh útil). *[lit, no
  verificado con DOI en esta sesión — confirmar con ficha técnica]*.

*Cifras [emp] calculadas en esta sesión sobre `data/eVED_EV.csv` (476.308 filas, 504
viajes). Scripts temporales, ya eliminados; no se modificó código ni tests.*
