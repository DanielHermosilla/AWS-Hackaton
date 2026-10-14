# eVED — Extended Vehicle Energy Dataset

[🇬🇧 English](README.md) · 🇪🇸 Español


Registros de conducción de **384 autos** (a gasolina o diésel, híbridos, híbridos enchufables y eléctricos) conducidos por sus propietarios en su uso cotidiano en **Ann Arbor, Michigan (EE. UU.)** entre **noviembre de 2017 y noviembre de 2018**, enriquecidos con información del camino obtenida de mapas: elevación, pendiente, límite de velocidad, intersecciones, paraderos de bus, semáforos y más.

Esta edición es nuestro preprocesamiento (limpieza de datos y corrección de errores) de dos conjuntos de datos publicados: **VED**, de Oh, LeBlanc y Peng [[1]](#referencias), y **eVED**, de Zhang, Fatih, Abdulqadir, Schwarz y Ma [[2]](#referencias) [[3]](#referencias). Ambos conjuntos contienen los registros de los mismos vehículos en la misma ventana de tiempo, con información complementaria que unimos en esta edición. En todo este documento, *el paper de VED* es [1] y *el paper de eVED* es [2] / [3]. Las referencias completas y el BibTeX están en la [sección 12](#12-cómo-citar-licencias-y-créditos).

Este documento está escrito para alguien que **nunca ha visto los datos**. Explica de dónde vienen, cómo se registraron, qué significa cada columna, qué les hicimos durante el procesamiento y qué debe considerarse al usarlos. Si se lee una sola sección antes de modelar, se recomienda que sea la **[9. Consideraciones](#9-consideraciones-de-los-datos-antes-de-modelar)**.

> **Nota sobre los números:** usamos coma para los miles y punto para los decimales (`13,129,462`; `0.6 s`), igual que en los archivos y en el código.

---

## Contenido

1. [Resumen](#1-resumen)
2. [De dónde vienen los datos](#2-de-dónde-vienen-los-datos)
3. [Descripción general del dataset](#3-descripción-general-del-dataset)
4. [Estructura del repositorio](#4-estructura-del-repositorio)
5. [Cómo leer los archivos](#5-cómo-leer-los-archivos)
6. [Diccionario de columnas](#6-diccionario-de-columnas)
7. [Valores faltantes](#7-valores-faltantes)
8. [Qué cambiamos respecto de los archivos originales de eVED](#8-qué-cambiamos-respecto-de-los-archivos-originales-de-eved)
9. [Consideraciones de los datos antes de modelar](#9-consideraciones-de-los-datos-antes-de-modelar)
10. [Cómo reproducir nuestro procesamiento](#10-cómo-reproducir-nuestro-procesamiento)
11. [Glosario](#11-glosario)
12. [Cómo citar, licencias y créditos](#12-cómo-citar-licencias-y-créditos)

---

## 1. Resumen

- **Qué es:** 22.4 millones de muestras (filas) con marca de tiempo, de 32,552 viajes de 384 autos reales. Cada fila es un instante de tiempo dentro de un viaje en particular: posición GPS, velocidad, señales del motor o de la batería, e información sobre el camino en que iba el auto.
- **Punto de partida:** la carpeta [`data/processed/`](data/processed/) contiene cuatro archivos CSV: tres con los datos de cada instante de cada viaje, separados por tipo de motorización, y `vehicle_types.csv`, que describe las características de cada vehículo según su ID.

| Archivo | Vehículos | Viajes | Filas | Columnas | Tamaño |
|---|---|---|---|---|---|
| `eVED_ICE.csv` | 264 autos a gasolina/diésel (ICE) | 18,936 | 13,129,462 | 26 | 2.9 GB |
| `eVED_PHEV_HEV.csv` | 93 híbridos (HEV) + 24 híbridos enchufables (PHEV) | 13,112 | 8,830,937 | 32 | 2.2 GB |
| `eVED_EV.csv` | 3 autos eléctricos (EV) | 504 | 476,308 | 24 | 0.1 GB |
| `vehicle_types.csv` | los 384 vehículos: tipo, motor, peso... | — | 384 | 7 | 14 KB |

- **Cómo se conectan:** cada fila tiene un `VehId` (id anónimo del vehículo) y un `Trip` (id del viaje). El par `(VehId, Trip)` identifica un viaje de forma única. `VehId` se une con `vehicle_types.csv`.
- **Datos faltantes:** se escriben como `nan`. Muchos son *estructurales* (un auto eléctrico no tiene RPM del motor) o provienen de sensores que un auto no reporta. **No imputamos ninguna medición**; cómo tratarlos queda a criterio de cada participante (ver [7](#7-valores-faltantes)).
- **Ejemplo mínimo de uso:**

```python
import pandas as pd

# información de cada vehículo según su ID
veh = pd.read_csv("data/processed/vehicle_types.csv")  

ev  = pd.read_csv("data/processed/eVED_EV.csv", parse_dates=["Timestamp"])   # 0.1 GB, los 3 autos eléctricos

trip = ev[(ev["VehId"] == 455) & (ev["Trip"] == 1720)]                       # un viaje = un (VehId, Trip)
print(trip[["Timestamp", "Vehicle Speed[km/h]", "HV Battery SOC[%]", "HV Battery Current[A]"]].head())
```

- **Archivos grandes:** `eVED_ICE.csv` y `eVED_PHEV_HEV.csv` pesan entre 2 y 3 GB. Se recomienda leer solo las columnas necesarias (`usecols=[...]`) o procesarlos por partes (`chunksize=2_000_000`).
- **Análisis de ejemplo:** [`preprocess.ipynb`](preprocess.ipynb) incluye el código de limpieza, figuras de cada variable principal y el análisis detallado de un viaje.

---

## 2. De dónde vienen los datos

### 2.1 El linaje en una imagen

```
 Autos con registradores OBD-II ──►  VED (registros crudos)  ──►  eVED (agrega información de mapas)  ──►  este repositorio
 (Ann Arbor, 2017-2018)              Universidad de Michigan      Chalmers / U. de Gotemburgo             limpio, documentado y separado
                                     CSV semanales                CSV semanales, +13 columnas             por tipo de motorización
                                     tablas estáticas             (map matching, elevación,               (preprocess.ipynb)
                                                                  límite de velocidad, intersecciones...)
```

Tres capas, elaboradas por tres grupos distintos:

1. **VED (Vehicle Energy Dataset)** [[1]](#referencias) — los registros de conducción crudos. Creado por la Universidad de Michigan.
2. **eVED (Extended VED)** [[2]](#referencias) [[3]](#referencias) — los mismos registros con posiciones GPS corregidas y atributos del camino obtenidos de servicios de mapas. Creado por investigadores de la Universidad Tecnológica de Chalmers, la Universidad de Gotemburgo y la Universidad Tecnológica de Xi'an.
3. **Esta edición** — nuestra versión limpia y documentada de eVED, preparada para una hackatón. **No** es una publicación oficial de ninguno de los dos proyectos. Los archivos eVED originales, sin modificar, se conservan en [`data/eVED/`](data/eVED/).

### 2.2 VED: cómo se obtuvieron los registros de conducción

*Fuente: [[1]](#referencias) Oh, LeBlanc y Peng, "Vehicle Energy Dataset (VED), a large-scale dataset for vehicle energy consumption research", IEEE Trans. on Intelligent Transportation Systems, 2020 ([doi](https://doi.org/10.1109/TITS.2020.3035596) · [arXiv:1905.02081](https://arxiv.org/abs/1905.02081)).*

- **Quiénes y para qué.** La Universidad de Michigan, el Argonne National Laboratory y el Idaho National Laboratory estudiaron cómo usan la energía los conductores humanos y cuánto se podría ahorrar con tecnologías de conducción eficiente (*eco-driving*). El trabajo fue financiado por el Departamento de Energía de EE. UU.
- **Participantes.** Se reclutó a dueños de autos particulares que vivían o trabajaban en Ann Arbor, Michigan. Como en 2017 los híbridos, híbridos enchufables y eléctricos eran raros, los investigadores hicieron un esfuerzo especial por reclutar dueños de esos autos.
- **El registrador.** Con el consentimiento de los dueños, se instaló en cada auto un **registrador de datos OBD-II**. OBD-II es el puerto de diagnóstico estándar que tiene todo auto de pasajeros vendido en EE. UU. desde 1996; da acceso a la red interna del auto (bus CAN) y a un conjunto estándar de señales. Los registradores enviaban los datos en tiempo real a una base de datos por la red celular, **durante aproximadamente un año**.
- **Señales registradas.** Tres grupos:
  - GPS: latitud y longitud.
  - Señales OBD-II *estándar*: velocidad del vehículo, régimen del motor, flujo de aire, carga del motor, ajustes de combustible y temperatura del aire exterior.
  - Señales *personalizadas por el fabricante* (específicas de cada marca): corriente, voltaje y estado de carga de la batería de alto voltaje, y la potencia usada por el aire acondicionado y por el calefactor eléctrico. Solo existen para autos enchufables y eléctricos.
- **Período.** Del 1 de noviembre de 2017 al 9 de noviembre de 2018 según el paper (los archivos que tenemos llegan hasta el 10 de noviembre de 2018).
- **Flota:**

| Tipo | Vehículos | Notas |
|---|---|---|
| ICE (motor de combustión interna) | 264 | 249 con señales de combustible, 15 sin ellas |
| HEV (híbrido, no enchufable) | 93 | 91 con señales de combustible, 2 sin ellas |
| PHEV (híbrido enchufable) | 24 | 4 modelos |
| EV (eléctrico a batería) | 3 | los tres son Nissan Leaf 2013, batería anunciada de 24 kWh |
| **Total** | **384** | |

  Los vehículos y las señales de combustible (el auto reporta `MAF` o `Absolute Load`) están contados en los archivos; los modelos y la batería vienen del paper de VED.
- **Viajes.** Según el paper de VED, los viajes promedian 11.4 millas (mediana 9.4 millas). El paper reporta 32,940 viajes; los archivos que tenemos contienen 32,552 pares `(VehId, Trip)` distintos.
- **Variedad.** Autos de pasajeros (coupés, hatchbacks, sedanes, convertibles, crossovers, autos de lujo) y camionetas livianas (pickups, SUV, minivans, station wagons). Según el paper de VED, los 264 ICE son 107 modelos distintos de 26 fabricantes y los HEV son 18 modelos de 10 fabricantes. Los recorridos abarcan desde autopistas hasta el denso centro urbano, en todas las estaciones del año.
- **Privacidad: los datos fueron desidentificados.** Como el inicio y el fin de un viaje pueden revelar dónde vive o trabaja alguien, los autores aplicaron tres pasos antes de publicar (sus parámetros no se divulgan):
  1. *Niebla aleatoria (random fogging):* se eliminaron las muestras GPS del comienzo y del final de cada viaje siguiendo formas generadas al azar.
  2. *Geocerca (geo-fencing):* solo se conservó lo que cae dentro de un rectángulo alrededor de la ciudad de Ann Arbor.
  3. *Acotado por intersecciones principales:* cada viaje se recortó a la parte entre su primera y su última **intersección principal**.

  Marca, modelo, año, versión y peso exacto del vehículo se eliminaron o se generalizaron (el peso se entrega en pasos de 500 lb). Se conservó la información general del tren motriz (tipo de motor, transmisión). **Implicancia para el uso de los datos:** los viajes no comienzan ni terminan en el domicilio o el lugar de trabajo del conductor, sino cerca de intersecciones principales, y no existen registros fuera de Ann Arbor.
- **Dos componentes.** VED tiene *datos estáticos* (una fila por vehículo, aquí `vehicle_types.csv`) y *datos dinámicos* (las series de tiempo, una fila por muestra).

### 2.3 eVED: lo que se agregó sobre VED

*Fuente: [[2]](#referencias) Zhang, Fatih, Abdulqadir, Schwarz y Ma, "Extended Vehicle Energy Dataset (eVED): An Enhanced Large-Scale Dataset for Vehicle Energy Consumption Analysis", IEEE VTC2025-Spring, 2025 ([doi](https://doi.org/10.1109/VTC2025-Spring65109.2025.11174415)), y su preprint anterior [[3]](#referencias) ([arXiv:2203.08630](https://arxiv.org/abs/2203.08630)). Los detalles técnicos de abajo siguen el preprint [3]; repositorio: <https://github.com/zhangsl2013/eVED>.*

Las posiciones GPS de VED son ruidosas (el registrador va en un auto que vibra y se mueve), por lo que muchos puntos caen fuera del camino por el que realmente iba el auto. Eso impide cruzar los datos con información de mapas. Por eso los autores de eVED primero **corrigieron las posiciones** y luego **agregaron atributos del camino**:

| Paso | Qué hicieron | Columnas que produce |
|---|---|---|
| **Map matching** | La traza GPS de cada viaje se ajustó a la secuencia de calles más probable con un *modelo oculto de Markov* (biblioteca Valhalla / Meili, algoritmo de Viterbi, calles de OpenStreetMap). Este método es preferible a asignar la calle más cercana, que puede seleccionar una calle paralela incorrecta. Más del 99 % de los registros quedó ajustado. | `Matched Latitude[deg]`, `Matched Longitude[deg]`, `Match Type` |
| **Límite de velocidad** | Descargaron las calles transitables y las etiquetas `maxspeed` de OpenStreetMap (Overpass Turbo) y las asociaron con QGIS. Agregaron una *clase* de límite y el límite *en el sentido de circulación* (comparando el rumbo del tramo de calle con el rumbo del viaje). | `Class of Speed Limit`, `Speed Limit with Direction[km/h]` |
| **Elevación** | Consultaron la API de Elevación de Google Maps para cada posición. Como los puntos GPS se repiten en varias filas, la elevación cruda presenta un perfil escalonado; por eso se agregó un promedio móvil de 5 puntos (2 muestras antes, la muestra y 2 después). | `Elevation Raw[m]`, `Elevation Smoothed[m]` |
| **Pendiente del camino** | Se calcula con la elevación suavizada y la distancia geodésica entre puntos consecutivos (ver [`Gradient`](#63-contexto-del-camino-y-del-mapa)). | `Gradient` |
| **Intersecciones** | Extrajeron con QGIS todas las coordenadas de intersecciones de Ann Arbor desde OpenStreetMap y marcaron los registros que caen en una. | `Intersection` |
| **Paraderos de bus** | Ubicaciones de paraderos del catálogo de datos abiertos de la ciudad de Ann Arbor. Se trazó un radio de 10 m alrededor de cada paradero y se marcan los registros dentro. | `Bus Stops` |
| **Puntos de interés (focus points)** | 16 tipos de elementos del camino que pueden cambiar la velocidad de un auto (semáforos, pasos de cebra, señales de pare...) tomados de OpenStreetMap. Un registro a 3 m o menos se etiqueta con el tipo de elemento. | `Focus Points` |
| **Energía** | Un valor de energía por muestra calculado a partir de las señales (está implementado en el notebook de los autores [`code/EnergyConsumptionCalculation.ipynb`](code/EnergyConsumptionCalculation.ipynb); el paper no lo describe). | `Energy_Consumption` |

Los notebooks de los autores de eVED para estos pasos están en [`code/`](code/) (`map-matching`, `spatial-join`, `EnergyConsumptionCalculation`, `export-processed-data`, `visualize-osm-data`).

### 2.4 Esta edición: qué hicimos

Leímos los 54 archivos CSV semanales de eVED (35 columnas cada uno), clasificamos cada vehículo como ICE/HEV/PHEV/EV con las tablas estáticas, corregimos errores de tipeo y columnas duplicadas, unimos las dos columnas de tiempo en una sola `Timestamp`, convertimos en `nan` las lecturas imposibles de los sensores, eliminamos las columnas vacías para cada tipo de motorización y escribimos tres archivos CSV. **No rellenamos mediciones faltantes.** La lista completa, con cantidades, está en [8](#8-qué-cambiamos-respecto-de-los-archivos-originales-de-eved).

---

## 3. Descripción general del dataset

| Motorización | Vehículos | Viajes | Filas (muestras) | Tiempo de conducción |
|---|---|---|---|---|
| ICE | 264 | 18,936 | 13,129,462 | ≈ 2,743 h |
| HEV | 93 | 9,507 | 5,587,565 | ≈ 1,412 h |
| PHEV | 24 | 3,605 | 3,243,372 | ≈ 615 h |
| EV | 3 | 504 | 476,308 | ≈ 80 h |
| **Total** | **384** | **32,552** | **22,436,707** | **≈ 4,850 h** |

- **Período:** del 2017-11-01 al 2018-11-10 (54 archivos semanales).
- **Zona:** Ann Arbor, Michigan (latitud ≈ 42.22–42.33, longitud ≈ −83.80 a −83.67), elevaciones de 227 a 324 m.
- **Balance:** los datos están muy desbalanceados. Los autos eléctricos son 3 vehículos (2 % de las filas), por lo que cualquier conclusión sobre EV descansa en muy pocos autos.

---

## 4. Estructura del repositorio

```
eved-dataset/
├── README.md · README.es.md      este documento (inglés / español)
├── preprocess.ipynb              nuestro pipeline completo: limpieza, tres CSV, figuras, recorrido de un viaje
├── data/
│   ├── eVED/                     54 CSV semanales ORIGINALES de los autores de eVED (35 columnas, ≈ 5.8 GB)
│   └── processed/                ◄── datos procesados
│       ├── eVED_ICE.csv
│       ├── eVED_PHEV_HEV.csv
│       ├── eVED_EV.csv
│       └── vehicle_types.csv
├── VED/                          el repositorio original de VED (Apache 2.0)
│   └── Data/                     tablas estáticas de vehículos (.xlsx) y datos dinámicos originales (.7z)
├── code/                         notebooks de los autores de eVED (map matching, spatial join, energía...)
└── figures/                      figuras con formato de publicación científica (PDF vectorial + PNG a 300 dpi) generadas por preprocess.ipynb
```

- Los datos procesados están en `data/processed/`. `data/eVED/` contiene los datos crudos, que conservamos como referencia y para poder reproducir el procesamiento.
- Todos los CSV son texto UTF-8 separado por comas, con línea de encabezado y fines de línea de Windows (`\r\n`), igual que los originales.

---

## 5. Cómo leer los archivos

### 5.1 Una fila = una muestra de un vehículo

Cada fila es un registro instantáneo de un vehículo en un momento de un viaje: su posición, su velocidad, el estado de su motor o de su batería y el tipo de camino en que se encontraba. Las filas de un viaje están una tras otra y en orden de tiempo.

### 5.2 Vehículos y viajes

- `VehId`: un entero anónimo (de 2 a 630, no consecutivos). No tiene significado por sí mismo; se usa para unir con `vehicle_types.csv`.
- `Trip`: un entero que identifica un viaje de ese vehículo.
- **`(VehId, Trip)` es único:** identifica exactamente un viaje, y un viaje nunca se reparte entre dos archivos semanales. Para obtener los viajes se puede usar `groupby(["VehId", "Trip"])`.
- Los viajes **no** están garantizados en orden cronológico según su número. Por ejemplo, en los vehículos 269, 356, 535 y 592 (semana del 2018-04-25) el viaje con `Trip` mayor ocurrió *justo antes* que el menor. Cuando se requiera una cronología estricta, se debe ordenar por `["VehId", "Timestamp"]` (no por `Trip`).

### 5.3 Tiempo

- La columna `Timestamp` (texto `YYYY-MM-DD HH:MM:SS.mmm`, precisión de milisegundos) es el instante de la muestra. Puede leerse con `parse_dates=["Timestamp"]`.
- **Reemplaza a dos columnas originales.** En los archivos originales, `DayNum` era "días transcurridos desde una fecha de referencia" (`DayNum` 1 = 2017-11-01 00:00:00, 1.5 = 2017-11-01 12:00:00) y es **constante dentro de un viaje**; `Timestamp(ms)` era el desfase en milisegundos de cada muestra respecto de esa referencia. Las combinamos: `Timestamp` = referencia + desfase.
- **Zona horaria:** ninguno de los dos papers la indica; las marcas de tiempo deben interpretarse como el reloj local del registrador, sin información de zona horaria.
- **Las filas no están espaciadas uniformemente.** Medido en 14 de las 54 semanas: el tiempo entre filas consecutivas de un viaje tiene mediana ≈ 0.6 s, percentil 90 ≈ 1.4 s y percentil 99 ≈ 2.8 s, con huecos ocasionales de minutos (el mayor es de cerca de 1.75 horas dentro de un viaje). No debe suponerse un paso fijo; deben usarse las marcas de tiempo.
- **Las señales se registran a distinta frecuencia** (tiempos nominales de muestreo publicados en el paper de VED):

| Señal | Actualización nominal |
|---|---|
| Velocidad del vehículo, corriente de la batería | 1 s |
| Régimen del motor (RPM), flujo de aire (MAF) | 2 s |
| Latitud/longitud GPS | 3 s |
| Tasa de combustible, carga absoluta, ajustes de combustible de corto plazo, voltaje de la batería | 5 s |
| Ajustes de combustible de largo plazo | 30 s |
| Temperatura del aire exterior, estado de carga (SOC), potencia del aire acondicionado y del calefactor | 60 s |

- **Los valores repetidos son normales, no son duplicados.** El registrador unió señales de distinta frecuencia en una sola tabla, por lo que una señal lenta repite su último valor en las filas intermedias. El paper de eVED lo dice para el GPS ("parte de las coordenadas GPS registradas están duplicadas en varios registros consecutivos"); nosotros vimos lo mismo en otras columnas (por ejemplo, el estado de carga cambia cerca de una vez por minuto y forma un perfil escalonado).

### 5.4 Tipos de vehículo

Cada vehículo pertenece a un tipo de motorización, dado por `EngineType` en `vehicle_types.csv`:

| `EngineType` | Significado | Tiene señales de combustible/motor | Tiene señales de batería |
|---|---|---|---|
| `ICE` | Motor de combustión interna (gasolina; unos pocos diésel) | sí (la mayoría) | no |
| `HEV` | Vehículo eléctrico híbrido. Motor + motor eléctrico, **no** se enchufa | sí | prácticamente no (solo 1 de 93) |
| `PHEV` | Híbrido enchufable. Motor + motor eléctrico, batería que se carga de la red | sí (algunos) | sí |
| `EV` | Vehículo eléctrico a batería, sin motor de combustión | no | sí |

El archivo `eVED_PHEV_HEV.csv` mezcla filas HEV y PHEV de forma intencional (comparten casi todas las columnas). **Para distinguirlos, se debe unir con `vehicle_types.csv`:**

```python
df = pd.read_csv("data/processed/eVED_PHEV_HEV.csv", usecols=["VehId", "Trip", "Timestamp", "HV Battery SOC[%]"])
df = df.merge(veh[["VehId", "EngineType"]], on="VehId")
phev = df[df["EngineType"] == "PHEV"]
```

### 5.5 Coordenadas: registradas vs ajustadas

- `Latitude[deg]`, `Longitude[deg]` es lo que registró el GPS (7 decimales, ruidoso, actualizado cada ~3 s).
- `Matched Latitude[deg]`, `Matched Longitude[deg]` es la posición corregida sobre la red de calles. Se recomienda usarlas al cruzar los datos con mapas.
- `Match Type` indica cómo se obtuvo la posición ajustada (ver [6.3](#63-contexto-del-camino-y-del-mapa)).

### 5.6 Valores faltantes en el CSV

- Un valor faltante se escribe como el texto **`nan`**. `pandas.read_csv` lo lee como `NaN` automáticamente; en otras herramientas debe declararse `nan` como marcador de valor faltante.
- `Focus Points` usa el texto normal `none` (en minúsculas) para "sin punto de interés". **No** es un valor faltante.

### 5.7 Recomendaciones de carga

```python
# Leer solo lo necesario
cols = ["Timestamp", "VehId", "Trip", "Vehicle Speed[km/h]", "Energy_Consumption"]
ice = pd.read_csv("data/processed/eVED_ICE.csv", usecols=cols, parse_dates=["Timestamp"])

# Leer un archivo grande por partes
for chunk in pd.read_csv("data/processed/eVED_PHEV_HEV.csv", chunksize=2_000_000):
    ...

# Segundos desde el inicio de cada viaje
t0 = ice.groupby(["VehId", "Trip"])["Timestamp"].transform("min")
ice["t_s"] = (ice["Timestamp"] - t0).dt.total_seconds()
```

---

## 6. Diccionario de columnas

Todos los archivos siguen el **mismo orden de columnas**. Más abajo, *Origen* dice de dónde viene el valor: **registrador** = grabado por el registrador OBD-II del auto; **eVED** = agregado por los autores de eVED desde mapas o por cálculo; **nuestro** = creado o cambiado en esta edición.

### 6.1 Qué columnas están en cada archivo

| Columna | `ICE` | `PHEV_HEV` | `EV` |
|---|:-:|:-:|:-:|
| Timestamp, VehId, Trip | ✓ | ✓ | ✓ |
| Latitude, Longitude, Vehicle Speed | ✓ | ✓ | ✓ |
| MAF, Engine RPM, Absolute Load | ✓ | ✓ | — |
| OAT | ✓ | ✓ | ✓ |
| Fuel Rate | — (ver [7](#7-valores-faltantes)) | ✓ | — |
| Air Conditioning Power, Heater Power | — | ✓ | ✓ |
| HV Battery Current, SOC, Voltage | — | ✓ | ✓ |
| Short/Long Term Fuel Trims (bancos 1 y 2) | ✓ | ✓ | — |
| Elevation Raw/Smoothed, Gradient, Energy_Consumption | ✓ | ✓ | ✓ |
| Matched Latitude/Longitude, Match Type | ✓ | ✓ | ✓ |
| Class of Speed Limit, Speed Limit with Direction | ✓ | ✓ | ✓ |
| Intersection, Bus Stops, Focus Points | ✓ | ✓ | ✓ |

Dejamos una columna fuera de un archivo solo cuando está (casi) vacía para esa motorización.

### 6.2 Tiempo, vehículo y señales registradas por el auto

| Columna | Unidad / tipo | Qué es | Origen |
|---|---|---|---|
| `Timestamp` | texto `YYYY-MM-DD HH:MM:SS.mmm` | Instante de la muestra (ver [5.3](#53-tiempo)). | nuestro (desde `DayNum` + `Timestamp(ms)`) |
| `VehId` | entero | Id anónimo del vehículo. | registrador |
| `Trip` | entero | Id del viaje; `(VehId, Trip)` es único. | registrador |
| `Latitude[deg]`, `Longitude[deg]` | grados | Posición GPS tal como se registró (ruidosa). | registrador |
| `Vehicle Speed[km/h]` | km/h | Velocidad que reporta el auto (resolución de 1 km/h; algunos PHEV/EV reportan decimales). Entre 5 y 15 % de las muestras valen 0 (auto detenido). | registrador |
| `MAF[g/sec]` | g/s | *Mass air flow*: masa de aire que entra al motor. Junto con los ajustes de combustible permite estimar el consumo (paper de VED, Algoritmo 1). | registrador |
| `Engine RPM[RPM]` | rev/min | Régimen del motor. `0` significa motor apagado (común en híbridos: 29 % de las muestras de HEV y 73 % de las de PHEV). | registrador |
| `Absolute Load[%]` | % | *Absolute load value* de OBD-II: cuánto aire admite el motor respecto de su capacidad. Normalmente 0–100 %, en algunos motores puede superar 100 %. Convertimos en `nan` los valores sobre 300 %. | registrador, nuestro (valores imposibles) |
| `OAT[DegC]` | °C | *Temperatura del aire exterior*, del sensor del propio auto. Algunos sensores registran valores superiores a los reales (radiación solar, calor del motor) o muestran el valor de relleno −40 °C. Convertimos en `nan` los valores fuera de −30…45 °C. | registrador, nuestro (valores imposibles) |
| `Fuel Rate[L/hr]` | L/h | Consumo de combustible **reportado por la electrónica del fabricante**. Solo algunos PHEV lo reportan (ver [7](#7-valores-faltantes)). Es la única medición *directa* de combustible en los datos. | registrador |
| `Air Conditioning Power[Watts]` | W | Potencia usada por el compresor del aire acondicionado. En los archivos originales unos autos usaban kW y otros W en dos columnas separadas; las unificamos en W. | registrador, nuestro (unión de unidades) |
| `Heater Power[Watts]` | W | Potencia usada por el calefactor eléctrico de la cabina. | registrador |
| `HV Battery Current[A]` | A | Corriente en el borne de la batería de tracción de alto voltaje. **Positiva = cargando** (por ejemplo, frenado regenerativo), **negativa = descargando** (durante la marcha). | registrador |
| `HV Battery SOC[%]` | % | *Estado de carga*: nivel de carga de la batería de alto voltaje (0–100 %). Cambia cerca de una vez por minuto, por lo que presenta un perfil escalonado. | registrador |
| `HV Battery Voltage[V]` | V | Voltaje de la batería de alto voltaje. Convertimos en `nan` los valores de 0 V (sensor sin lectura). | registrador, nuestro (valores imposibles) |
| `Short Term Fuel Trim Bank 1[%]`, `... Bank 2[%]` | % | Corrección instantánea que aplica la unidad de control del motor a la cantidad de combustible (rango −100…99.2 %). Un *banco* es una fila de cilindros; el banco 2 existe solo en motores con dos bancos (por ejemplo V6, V8); en otro caso es `nan`. | registrador |
| `Long Term Fuel Trim Bank 1[%]`, `... Bank 2[%]` | % | Versión lenta y acumulada de la misma corrección. | registrador |

### 6.3 Contexto del camino y del mapa

| Columna | Unidad / tipo | Qué es | Origen |
|---|---|---|---|
| `Elevation Raw[m]` | m | Altura sobre el nivel del mar en la posición, según la API de Elevación de Google. Presenta un perfil escalonado porque las posiciones se repiten en filas consecutivas. | eVED |
| `Elevation Smoothed[m]` | m | Promedio móvil de la elevación cruda sobre 5 puntos (2 antes, el punto, 2 después). Se recomienda para calcular pendientes. | eVED |
| `Gradient` | razón (subida / recorrido) | Pendiente del camino: `0.05` es una subida de 5 %, `−0.05` una bajada de 5 %. Se calcula con puntos consecutivos (casos en la tabla de abajo). La mayoría de los valores es exactamente 0 (cerca de 81 % en una muestra de cuatro semanas). | eVED |
| `Energy_Consumption` | kWh **por fila** | Energía de la muestra, definida por los autores de eVED ([6.5](#65-cómo-se-calcula-energy_consumption)). **Debe leerse [9](#9-consideraciones-de-los-datos-antes-de-modelar), punto 1, antes de usarla.** | eVED |
| `Matched Latitude[deg]`, `Matched Longitude[deg]` | grados | Posición ajustada a la calle por el map matching. (Los archivos originales tenían el error de tipeo `Matchted Latitude[deg]`; lo corregimos.) | eVED, nuestro (tipeo) |
| `Match Type` | 0 / 1 / 2 | Cómo se obtuvo la posición ajustada (tabla más abajo). | eVED |
| `Class of Speed Limit` | −1, 0, 1, 2, 3 | De dónde sale el límite de velocidad (tabla más abajo). | eVED |
| `Speed Limit with Direction[km/h]` | km/h | Límite de velocidad **del sentido en que iba el auto**. Los valores son límites de EE. UU. en mph convertidos a km/h (40 = 25 mph, 48 = 30, 56 = 35, 72 = 45, 89 = 55, 113 = 70). | eVED |
| `Intersection` | 0 / 1 | 1 si la posición está en una intersección (según OpenStreetMap). | eVED, nuestro (vacío → 0) |
| `Bus Stops` | 0 / 1 | 1 si la posición está a 10 m o menos de un paradero de bus. | eVED, nuestro (vacío → 0) |
| `Focus Points` | texto | Tipo de elemento del camino a 3 m o menos, o `none`. Los 16 tipos: `crossing`, `traffic_signals`, `stop`, `give_way`, `roundabout`, `mini_roundabout`, `turning_loop`, `turning_circle`, `motorway_junction`, `level_crossing`, `hump`, `bump`, `gate`, `lift_gate`, `swing_gate`, `bollard` (términos de OpenStreetMap). Diez filas llevan el valor combinado `gate;lift_gate`. | eVED, nuestro (vacío → `none`) |

**`Match Type`** (proporción de las filas de los archivos):

| Código | Etiqueta | Significado | Proporción de filas |
|---|---|---|---|
| `0` | matched (emparejada) | Una nueva lectura GPS, ajustada a una calle. El 99 % de estas filas difiere de la coordenada de la fila anterior. | 15–20 % |
| `1` | interpolated (interpolada) | La coordenada cruda repite la de la fila anterior (98.6 %), por lo que el punto ajustado es el mismo. | 80–87 % |
| `2` | unmatched (sin emparejar) | No se encontró calle; la posición ajustada es igual a la cruda. | menos de 1 % |

Los papers nombran las tres etiquetas pero no sus códigos numéricos; los códigos de la tabla los comprobamos con los datos (en el primer millón de filas de `eVED_EV.csv`).

**`Gradient`** (se calcula con puntos consecutivos):

| Situación | Valor |
|---|---|
| Las elevaciones de los dos puntos son iguales | `0` |
| Las elevaciones son distintas | (diferencia de altura) / (distancia geodésica entre los dos puntos) |
| El vehículo no se movió entre las dos filas | `nan`. En el 99.7 % de las filas `nan`, la coordenada GPS es igual a la de la fila anterior, coherente con una división por cero |

**`Class of Speed Limit`** (proporción de los registros crudos, según el paper de eVED):

| Clase | Significado | Proporción |
|---|---|---|
| `0` | Límite máximo legal señalizado en la calle (`maxspeed`) | 81.7 % |
| `1` | Sin señal explícita: rigen los límites **por defecto** de Michigan (autopista 70 mph, troncal/primaria/no clasificada 55, secundaria 45, terciaria 35, residencial/servicio 25) | 14.4 % |
| `-1` | El límite es distinto en cada sentido de circulación (`maxspeed:forward/backward`); `Speed Limit with Direction` da el que corresponde | 0.57 % |
| `2` | Velocidad recomendada (no obligatoria) | 0.93 % |
| `3` | Velocidad promedio práctica/realista cuando no hay límite legal | 0.03 % |

Cantidades de `Focus Points` en todo eVED (paper, Tabla 4): crossing 312,196 · traffic signal 195,856 · stop 29,397 · turning loop 5,848 · level crossing 4,053 · turning circle 3,554 · motorway junction 2,938 · gate 1,105 · give way 985 · hump 223 · mini roundabout 195 · bump 108 · lift gate 96 · roundabout 81 · bollard 1 · swing gate 4.

### 6.4 La tabla de vehículos `vehicle_types.csv`

Una fila por vehículo (384 filas). Fuente: las dos tablas estáticas de VED (`VED/Data/VED_Static_Data_*.xlsx`), que unificamos.

| Columna | Qué es | Completitud |
|---|---|---|
| `VehId` | Id del vehículo (se une con los CSV). | 384 / 384 |
| `EngineType` | `ICE` (264), `HEV` (93), `PHEV` (24) o `EV` (3). *Las dos tablas de origen llamaban distinto a esta columna (`Vehicle Type`, `EngineType`).* | 384 / 384 |
| `Vehicle Class` | `Car` o `SUV`. | solo 32 vehículos (todos los PHEV y EV, y 5 más) |
| `Engine Configuration & Displacement` | Texto como `4-FI 2.4L` (4 cilindros, inyección de combustible, 2.4 litros), `4-GAS/ELECTRIC 1.8L` (híbrido), `8-DSL 6.7L T/C` (8 cilindros, diésel, turbo; es nuestra lectura de `DSL` y `T/C`) o `ELECTRIC`. | 384 / 384 |
| `Transmission` | Por ejemplo `CVT`, `5-SP AUTOMATIC`, `5-SP MANUAL` (las pasamos a mayúsculas). | 95 / 384 (ICE 79, HEV 4, PHEV 12) |
| `Drive Wheels` | `FWD` (tracción delantera). | solo PHEV y EV (27) |
| `Generalized_Weight` | Peso en **libras**, redondeado a propósito en pasos de 500 lb (2,000–6,500) por privacidad. | 368 / 384 |

Las tablas de origen usaban el texto `NO DATA` para lo desconocido; lo convertimos en una celda vacía.

### 6.5 Cómo se calcula `Energy_Consumption`

Definida por los autores de eVED e implementada en [`code/EnergyConsumptionCalculation.ipynb`](code/EnergyConsumptionCalculation.ipynb) (el paper no la describe). La unidad es **kWh por fila**. Los autores supusieron en su código que **cada fila dura exactamente 1 segundo** (de ahí los divisores `/3600` de las fórmulas; lo justifican con que la velocidad y la corriente se muestrean cada 1 s) y no usaron las marcas de tiempo. Como la energía real de una fila es `Energy_Consumption × Δt` (Δt en segundos entre filas), para sumar sobre un viaje debe usarse el `Timestamp` (ver [9](#9-consideraciones-de-los-datos-antes-de-modelar), punto 1).

| | PHEV y EV | ICE y HEV |
|---|---|---|
| Fórmula por fila | `−corriente × voltaje / 3.6·10⁶` | `(velocidad/3600)/100 × (MAF × 3.78541) × (1 + AjusteCorto1/100 + AjusteLargo1/100) / 14.08`, convertida luego a kWh con 1 kWh = 0.1123 L de gasolina |
| Viene de | potencia eléctrica medida | una fórmula basada en el flujo de aire |
| Signo | positivo = la batería se descarga (consumo); negativo = regeneración | combustible quemado, expresado como energía |
| Auto detenido | la fórmula no usa la velocidad | **vale exactamente 0**, aunque el motor esté en ralentí y consumiendo combustible, porque la fórmula multiplica por la distancia recorrida en la muestra (en filas ICE con velocidad 0 y MAF presente vale 0 o `nan`, sin otros valores posibles) |
| Es `nan` cuando | falta la corriente o el voltaje | falta `MAF` o un ajuste de combustible del banco 1 |

La fórmula de ICE/HEV es distinta de la estimación de consumo del paper de VED (Algoritmo 1: `MAF × (1 + STFT/100 + LTFT/100) / AFR`, con AFR = 14.08 para combustible E10, promediando los ajustes de ambos bancos cuando existe el banco 2). Para obtener el flujo de combustible, debe calcularse a partir de `MAF[g/sec]` y los ajustes. Los valores eléctricos y los de combustión no son directamente comparables.

---

## 7. Valores faltantes

### 7.1 Por qué faltan valores

1. **El auto no tiene el sensor.** Un EV no tiene motor de combustión, por lo que no tiene RPM ni MAF; un ICE no tiene batería. Quitamos esas columnas del archivo de esa motorización.
2. **El auto tiene el sensor pero el registrador no lo capturó.** Para un vehículo dado, una señal suele estar presente en casi todas las filas o ausente por completo: un auto no reporta MAF en algunas filas y en otras no. Por ejemplo, 15 ICE y 2 HEV no reportan ninguna señal de combustible (paper de VED, Tabla I).
3. **Faltan viajes completos.** En las semanas que inspeccionamos, *ninguna* celda `nan` de las columnas de sensores tenía una lectura válida a menos de 30 segundos dentro de su propio viaje. Los datos faltan por viajes completos o vehículos completos, no como huecos cortos. Por lo tanto, interpolar dentro de un viaje rellena muy pocos valores.
4. **`Gradient` es `nan` cuando el auto no se movió** entre filas consecutivas (ver [6.3](#63-contexto-del-camino-y-del-mapa)).
5. **Las columnas de límite de velocidad** (`Class of Speed Limit`, `Speed Limit with Direction[km/h]`) **son `nan`** donde el cruce con el mapa no asignó ningún límite (los papers no documentan la causa; lo más probable es que sean posiciones que no están en la red de calles mapeada).
6. **Lecturas imposibles que dejamos en blanco** (`OAT`, `Absolute Load`, `HV Battery Voltage`): ver [8](#8-qué-cambiamos-respecto-de-los-archivos-originales-de-eved).
7. **`Energy_Consumption` es derivada** de otras columnas, por lo que es `nan` cuando lo son sus entradas (para ICE/HEV: falta MAF o un ajuste de combustible del banco 1; ver [6.5](#65-cómo-se-calcula-energy_consumption)).

### 7.2 Cuánto falta (porcentaje de las filas de cada archivo)

| Columna | `ICE` | `PHEV_HEV` | `EV` |
|---|--:|--:|--:|
| Timestamp, VehId, Trip, Latitude, Longitude, Elevation Raw/Smoothed, Matched Lat/Lon, Match Type, Intersection, Bus Stops, Focus Points | 0 | 0 | 0 |
| Vehicle Speed | ≈ 0 | ≈ 0 | 0 |
| Engine RPM | ≈ 0 | ≈ 0 | — |
| MAF | 20.8 | 11.0 | — |
| Absolute Load | 16.6 | 37.4 | — |
| OAT | 58.7 | 19.1 | 0 |
| Fuel Rate | — | 89.9 | — |
| Air Conditioning Power | — | 63.2 | 0 |
| Heater Power | — | 95.4 | 0 |
| HV Battery Current / SOC / Voltage | — | 63.2 | 0 |
| Short Term Fuel Trim Bank 1 | 10.2 | 33.3 | — |
| Short Term Fuel Trim Bank 2 | 59.6 | 83.1 | — |
| Long Term Fuel Trim Bank 1 | 20.0 | 47.1 | — |
| Long Term Fuel Trim Bank 2 | 69.2 | 96.9 | — |
| Gradient | 2.0 | 2.2 | 1.5 |
| Energy_Consumption | 37.0 | 11.3 | 0 |
| Class of Speed Limit, Speed Limit with Direction | 2.6 | 1.9 | 1.4 |

Notas: en `PHEV_HEV` las columnas de batería están 63.2 % vacías porque el archivo mezcla PHEV (que las reportan) con HEV (solo 1 de 93 lo hace). Los porcentajes son por archivo, por lo que mezclan vehículos que reportan una señal con vehículos que nunca la reportan: conviene revisarlos **por vehículo** antes de decidir cómo tratar una columna.

### 7.3 Lo que hicimos al respecto

**Solo dejamos en blanco las lecturas imposibles.** Deliberadamente **no** imputamos ni interpolamos ninguna medición (`OAT`, `Gradient`, `MAF`, ajustes de combustible, señales de batería...). Los participantes pueden tratarlas con el método que consideren adecuado (descartar, estadísticos por vehículo o por viaje, imputación basada en modelos, modelos que aceptan `nan`...). Dos datos que pueden ayudar: la temperatura ambiente es esencialmente la misma para toda la ciudad a una hora dada, por lo que el `OAT` de otros vehículos en esa hora aporta información; y `Gradient` se deriva de `Elevation Smoothed[m]` y de las posiciones, por lo que puede recalcularse.

Los únicos rellenos que hicimos no son estadísticos: la unión de unidades de `Air Conditioning Power`, y las banderas de "sin evento" (`Intersection`, `Bus Stops` → 0; `Focus Points` → `none`).

---

## 8. Qué cambiamos respecto de los archivos originales de eVED

Los archivos originales están en [`data/eVED/`](data/eVED/). Todo lo que sigue está implementado en [`preprocess.ipynb`](preprocess.ipynb), y las cantidades se ven en su registro de ejecución.

| # | Problema en el original | Qué hicimos | Efecto |
|---|---|---|---|
| 1 | Error de tipeo en el encabezado `Matchted Latitude[deg]` | Renombramos a `Matched Latitude[deg]` | todos los archivos |
| 2 | Error en el encabezado `Focus Points;` (con punto y coma, solo en la semana 180124), y valores que terminan en `;` en esa semana (`crossing;`) | Renombramos a `Focus Points` y quitamos el `;` final | 1 semana |
| 3 | La columna del tipo de vehículo se llama `Vehicle Type` en una tabla estática y `EngineType` en la otra | Unificamos como `EngineType` | `vehicle_types.csv` |
| 4 | Potencia del aire acondicionado en dos columnas (`[kW]` en unos autos, `[Watts]` en otros; ningún auto tiene ambas) | Unimos en `Air Conditioning Power[Watts]` (kW × 1000) | ≈ 0.9 M de valores convertidos |
| 5 | `Speed Limit[km/h]` duplica a `Speed Limit with Direction[km/h]`, con valores mezclados de texto y número como `40-48` | La eliminamos. El caso que depende del sentido sigue marcado con `Class of Speed Limit = -1` | 1 columna menos |
| 6 | El mismo instante de un vehículo (mismo `VehId`, `DayNum` y `Timestamp(ms)`) aparecía en **dos viajes distintos** (4 viajes de la semana 180425, todos ICE) | Conservamos la copia del viaje con `Trip` menor; eliminamos la otra. Las copias eliminadas coincidían en sensores y posición y diferían, a lo más, en columnas derivadas del mapa | **101 filas eliminadas** |
| 7 | Lecturas imposibles | Las convertimos en `nan`: `OAT` fuera de −30…45 °C (32,368 valores), `Absolute Load` sobre 300 % (340), `HV Battery Voltage` igual a 0 V (5). También revisamos, sin encontrar casos: velocidad fuera de 0–200 km/h y ajustes de combustible fuera del rango OBD-II −100…99.2 % | 32,713 valores |
| 8 | `Intersection`, `Bus Stops`, `Focus Points` vacíos realmente significan "sin evento" | Los rellenamos con `0`, `0`, `none` | 3 columnas |
| 9 | Dos columnas de tiempo (`DayNum` + `Timestamp(ms)`) | Las unimos en una sola `Timestamp` (aritmética entera en milisegundos, verificada de forma independiente). En 4 viajes el desfase `Timestamp(ms)` era negativo; es válido y queda con el `Timestamp` correcto (ver [5.2](#52-vehículos-y-viajes)) | 2 columnas → 1 |
| 10 | `VehId`, `Trip`, `Match Type` almacenados como decimales (`8.0`) | Los guardamos como enteros | — |
| 11 | Columnas vacías para una motorización | Las quitamos del archivo de esa motorización cuando están ≥ 99 % vacías | ver 6.1 |
| 12 | Una sola tabla grande con motorizaciones mezcladas | La separamos en `ICE`, `PHEV_HEV`, `EV`; conservamos el orden de las filas (cronológico por semana, luego por viaje) | 3 archivos |

**Lo que *no* hicimos:** ninguna imputación ni interpolación; ningún remuestreo a una frecuencia fija; ninguna conversión de unidades salvo la unión del aire acondicionado; ninguna eliminación de filas aparte de las 101 repetidas; ninguna normalización ni escalamiento; ningún cambio en las posiciones ajustadas, los límites de velocidad ni los valores de energía.

**Comprobaciones.** El notebook se detiene si falla cualquiera de estas.

- *En los archivos semanales originales:* el tiempo está ordenado dentro de cada viaje; hay un solo `DayNum` por viaje; cada `(VehId, Trip)` aparece en una sola semana; todo `VehId` tiene tipo; los archivos semanales tienen columnas idénticas.
- *En los tres archivos finales:* el encabezado y el número de filas esperados; solo vehículos de su propio tipo; tiempo estrictamente creciente dentro de cada viaje; ningún vehículo con viajes solapados; ninguna columna duplicada.
- *Además,* comparamos la salida fila a fila con los archivos originales de varias semanas (incluidas las dos anómalas) y confirmamos que solo cambiaron las columnas listadas arriba.

**Dataset original y esta edición:**

| | Dataset original (archivos VED/eVED) | Esta edición |
|---|---|---|
| Vehículos | 384 | 384 |
| HEV | 93 | 93 |
| Viajes | 32,552 | 32,552 |
| Último día | 2018-11-10 | 2018-11-10 |
| Filas | 22,436,808 | 22,436,707 |

---

## 9. Consideraciones de los datos antes de modelar

1. **`Energy_Consumption` requiere cuidado, sobre todo al sumarla.** Definición y fórmulas: [6.5](#65-cómo-se-calcula-energy_consumption).
   - **Para obtener la energía de un viaje, se debe integrar con las marcas de tiempo (`Energy_Consumption × Δt`); no deben sumarse directamente las filas.** La columna está en **kWh por fila** y los autores de eVED calcularon cada valor como si la fila durara exactamente 1 segundo, pero las filas están en promedio a ≈ 0.6 s y de forma irregular. Por eso la suma directa sobrestima la energía: en los 329 viajes de EV de más de 5 min con energía neta relevante, fue cerca de **2.1 veces** (cuartiles 2.03–2.17) la energía obtenida integrando la potencia de la batería en el tiempo real, y una comprobación aparte en PHEV y EV dio una mediana de cerca de 1.5. Con los datos de este repositorio:

     ```python
     dt = df.groupby(["VehId", "Trip"])["Timestamp"].diff().dt.total_seconds().fillna(0)   # segundos entre filas
     trip_kwh = (df["Energy_Consumption"] * dt).groupby([df["VehId"], df["Trip"]]).sum()
     ```

     Comprobamos que el resultado coincide con la integral de la potencia de la batería en el tiempo real en los 504 viajes de EV (diferencia del orden de 1e-13 kWh), y con la fórmula de ICE recalculada con el Δt real en 911,541 filas ICE.
   - **En ICE y HEV vale exactamente 0 siempre que el auto está detenido, aunque el motor esté en ralentí y consumiendo combustible.** Para obtener el flujo de combustible, debe calcularse a partir de `MAF[g/sec]` y los ajustes.
   - Los valores eléctricos y los de combustión no son directamente comparables: unos vienen de potencia eléctrica medida, los otros de una fórmula basada en el flujo de aire.
2. **Se debe usar el `Timestamp` para derivar e integrar.** Las filas no están igualmente espaciadas (mediana ≈ 0.6 s) y los valores se repiten. Las tasas (derivadas por segundo) y las integrales deben calcularse con las marcas de tiempo, no con conteos de filas. Los valores idénticos consecutivos son el efecto normal de señales registradas a distinta frecuencia ([5.3](#53-tiempo)).
3. **Cuidado con la fuga de información al dividir los datos.** Las filas de un mismo viaje son muy parecidas entre sí, y también lo son los viajes de un mismo auto. Si las filas se reparten al azar entre entrenamiento y prueba, la información se filtra de un conjunto al otro. Se recomienda dividir en bloques completos: por vehículo (mide la generalización a autos nuevos) o por rango de fechas (mide la generalización a fechas posteriores); ver también el punto 11.
4. **Muy pocos EV (3) y pocos PHEV (24).** Los resultados promedio para estos tipos pueden depender de un solo auto. Los tres EV son el mismo modelo (Nissan Leaf 2013).
5. **Vehículos distintos tienen sensores distintos.** La disponibilidad cambia por vehículo, no solo por tipo (ver [7](#7-valores-faltantes)). Antes de usar una columna, se debe verificar su cobertura por vehículo.
6. **Solo 1 de 93 HEV tiene señales de batería.** Los análisis de batería son, en la práctica, PHEV + EV.
7. **`Fuel Rate[L/hr]` es escasa.** Existe para cerca de la mitad de los PHEV. Entre los ICE solo la reporta el vehículo 119 (un diésel turbo de 8 cilindros y 6.7 L, 5 viajes, 1,822 filas), y como para la población ICE está 99.99 % vacía, la **eliminamos de `eVED_ICE.csv`**. Sigue estando en los archivos originales de `data/eVED/`.
8. **Columnas de GPS y mapa.** El GPS crudo es ruidoso: para trabajar con mapas se recomienda usar las coordenadas ajustadas. Cerca del 80 % de las filas repite la posición anterior (`Match Type = 1`). Los límites de velocidad son los de OpenStreetMap en la época del trabajo de eVED.
9. **Zona horaria desconocida** (ver [5.3](#53-tiempo)). Los análisis por hora del día suponen hora local.
10. **El clima y otro contexto no están en los datos.** Solo se incluye la temperatura del aire exterior y, en muchos autos, falta.
11. **El número de vehículos que registran cambia a lo largo del año.** Los vehículos van saliendo del estudio: por ejemplo, los ICE con al menos un viaje bajan de 222 (84 % de la flota ICE) en noviembre de 2017 a 126 (48 %) en octubre de 2018, y los viajes ICE por mes de 2,318 a 1,090. Los viajes *por vehículo activo* se mantienen aproximadamente constantes (ICE y HEV: unos 8–12 por mes), por lo que el período seleccionado cambia tanto la cantidad de datos como *qué* autos se observan. Esto debe considerarse al definir los períodos de entrenamiento y validación.

---

## 10. Cómo reproducir nuestro procesamiento

Todo lo que generó `data/processed/` y `figures/` está en [`preprocess.ipynb`](preprocess.ipynb):

1. Carga las tablas estáticas y clasifica cada vehículo.
2. Limpia cada archivo semanal ([8](#8-qué-cambiamos-respecto-de-los-archivos-originales-de-eved)) y lo guarda temporalmente en Parquet.
3. Decide qué columnas quitar por motorización y escribe los tres CSV.
4. Verifica los archivos.
5. Dibuja las figuras (secciones 8 y 9 del notebook) y las guarda en `figures/` como PDF vectorial y PNG de 300 dpi.

Para ejecutarlo: Python ≥ 3.10 con `pandas` (≥ 2), `numpy`, `pyarrow`, `openpyxl`, `matplotlib` y Jupyter. El notebook debe abrirse desde la raíz del repositorio y ejecutarse por completo. En un equipo de 16 GB el procesamiento toma unos minutos; se requieren cerca de 10 GB de disco libre para las salidas. Para una prueba rápida, se puede establecer `MAX_WEEKS = 2` en la celda de configuración.

La sección 9 del notebook muestra un viaje en detalle (`TRIP_ID = (455, 1720)`, un auto eléctrico; puede reemplazarse por otro viaje): velocidad, elevación, estado de carga, voltaje, corriente, energía por muestra, la ruta en un mapa y la energía acumulada.

---

## 11. Glosario

| Término | Significado |
|---|---|
| **ICE** | Vehículo con motor de combustión interna (gasolina o diésel). |
| **HEV** | Vehículo eléctrico híbrido: motor + motor eléctrico, recarga su batería sin conexión a la red eléctrica y no se enchufa. |
| **PHEV** | Híbrido enchufable: como el HEV pero su batería se puede cargar de la red; circula en "modo EV" o "modo híbrido". |
| **EV / BEV** | Vehículo eléctrico (a batería): solo batería y motor eléctrico. |
| **OBD-II** | Puerto/protocolo estándar de diagnóstico a bordo presente en todo auto de pasajeros vendido en EE. UU. desde 1996. |
| **Bus CAN** | Red interna de comunicación del auto que escucha el registrador. |
| **OEM** | Fabricante original del equipo (la marca del auto); las "señales personalizadas OEM" son señales no estándar específicas del fabricante. |
| **GPS** | Sistema de posicionamiento global. |
| **MAF** | Flujo másico de aire (g/s). |
| **RPM** | Revoluciones por minuto (régimen del motor). |
| **Carga absoluta** | Medida OBD-II de la carga del motor. |
| **Ajuste de combustible (STFT / LTFT)** | Corrección de corto / largo plazo de la cantidad de combustible por parte de la unidad de control del motor (%). |
| **OAT** | Temperatura del aire exterior. |
| **Batería HV** | Batería de tracción de alto voltaje de híbridos y eléctricos. |
| **SOC** | Estado de carga de la batería (%). |
| **HVAC** | Calefacción, ventilación y aire acondicionado. |
| **Frenado regenerativo** | Recuperación de energía cinética hacia la batería al desacelerar (energía negativa / corriente de batería positiva). |
| **MPG / MPGe** | Millas por galón / millas por galón equivalente (autos eléctricos). |
| **Map matching** | Ajustar puntos GPS ruidosos a la red de calles. |
| **HMM** | Modelo oculto de Markov, el método estadístico usado en el map matching. |
| **OSM** | OpenStreetMap, la base de datos abierta de mapas. |
| **QGIS** | Sistema de información geográfica de código abierto usado para cruzar mapas y viajes. |
| **Punto de interés (focus point)** | Elemento del camino que puede cambiar la velocidad de un auto (semáforo, paso peatonal, señal de pare...). |
| **Gradiente / pendiente** | Inclinación del camino (subida sobre recorrido). |
| **Viaje (trip)** | Una sesión continua de registro de un vehículo. |
| **IQR** | Rango intercuartílico (del percentil 25 al 75). |

---

## 12. Cómo citar, licencias y créditos

### Referencias

**Quienes utilicen estos datos deben citar los trabajos originales.** Los autores de eVED piden citar cualquiera de sus dos papers ([2] o [3]); como eVED se construye sobre los registros de VED, corresponde citar también el paper de VED [1].

**[1]** G. S. Oh, D. J. LeBlanc y H. Peng, "Vehicle Energy Dataset (VED), a large-scale dataset for vehicle energy consumption research," *IEEE Transactions on Intelligent Transportation Systems*, 2020. doi: [10.1109/TITS.2020.3035596](https://doi.org/10.1109/TITS.2020.3035596) · preprint: [arXiv:1905.02081](https://arxiv.org/abs/1905.02081)

**[2]** S. Zhang, D. Fatih, F. Abdulqadir, T. Schwarz y X. Ma, "Extended Vehicle Energy Dataset (eVED): An Enhanced Large-Scale Dataset for Vehicle Energy Consumption Analysis," en *2025 IEEE 101st Vehicular Technology Conference (VTC2025-Spring)*, Oslo, Noruega, 2025, pp. 1–7. doi: [10.1109/VTC2025-Spring65109.2025.11174415](https://doi.org/10.1109/VTC2025-Spring65109.2025.11174415)

**[3]** S. Zhang, D. Fatih, F. Abdulqadir, T. Schwarz y X. Ma, "Extended vehicle energy dataset (eVED): an enhanced large-scale dataset for deep learning on vehicle trip energy consumption," arXiv preprint arXiv:2203.08630, 2022. [arxiv.org/abs/2203.08630](https://arxiv.org/abs/2203.08630)

Los títulos de [2] y [3] son distintos; los autores de eVED indican ambos como forma de citar su trabajo.

**BibTeX de [1]**, tal como se publica en arXiv (para [2] y [3], se utilizan las citas anteriores):

```bibtex
@misc{oh2019vehicleenergydatasetved,
      title={Vehicle Energy Dataset (VED), A Large-scale Dataset for Vehicle Energy Consumption Research},
      author={G. S. Oh and David J. Leblanc and Huei Peng},
      year={2019},
      eprint={1905.02081},
      archivePrefix={arXiv},
      primaryClass={physics.soc-ph},
      url={https://arxiv.org/abs/1905.02081},
}

```

**Repositorios originales:** VED — <https://github.com/gsoh/VED> · eVED — <https://github.com/zhangsl2013/eVED> (datos y código: `git clone https://Datarepo@bitbucket.org/datarepo/eved_dataset.git`).

### Licencias y créditos

**Licencias y términos.** El repositorio de VED (copiado en [`VED/`](VED/)) está bajo la **Licencia Apache 2.0** ([`VED/LICENSE`](VED/LICENSE)). Las columnas de eVED se derivan de fuentes de terceros: colaboradores de **OpenStreetMap** (límites de velocidad, intersecciones, puntos de interés, red de calles), la **API de Elevación de Google Maps** (elevación) y el catálogo de datos abiertos de la **ciudad de Ann Arbor** (paraderos de bus). No hemos revisado sus términos de redistribución ni de publicación de obras derivadas; deben verificarse antes de publicar cualquier resultado que incluya esas columnas.

**Créditos.** VED: Universidad de Michigan (G. S. Oh, D. J. LeBlanc, H. Peng), University of Michigan Transportation Research Institute, Argonne National Laboratory e Idaho National Laboratory, financiado por el Departamento de Energía de EE. UU. eVED: Universidad Tecnológica de Chalmers, Universidad de Gotemburgo y Universidad Tecnológica de Xi'an. Preparamos esta edición procesada y documentada para una hackatón; no cuenta con el respaldo de los autores originales.
