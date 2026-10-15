# eVED — Extended Vehicle Energy Dataset (processed edition)

🇬🇧 English · [🇪🇸 Español](README.es.md)

Real-world driving records of **384 cars** (gasoline, hybrid, plug-in hybrid and electric) driven by their owners in everyday use in **Ann Arbor, Michigan (USA)** between **November 2017 and November 2018**, enriched with road information taken from maps: elevation, slope, speed limit, intersections, bus stops, traffic signals and more.

This edition is our preprocessing (data cleaning and error correction) of two published datasets: **VED**, by Oh, LeBlanc & Peng [[1]](#references), and **eVED**, by Zhang, Fatih, Abdulqadir, Schwarz & Ma [[2]](#references) [[3]](#references). Both contain the records of the same vehicles over the same time window, with complementary information that we merged in this edition. Throughout this document, *the VED paper* means [1] and *the eVED paper* means [2] / [3]. Full references and BibTeX are in [section 12](#12-citing-licenses-and-credits).

This document is written for someone who has **never seen the data**. It explains where the data comes from, how it was recorded, what every column means, what we did to it, and what to keep in mind when using it. If only one section is read before modelling, it should be **[9. Considerations](#9-considerations-about-the-data-before-modelling)**.

---

## Contents

1. [Summary](#1-summary)
2. [Where the data comes from](#2-where-the-data-comes-from)
3. [Dataset overview](#3-dataset-overview)
4. [Repository layout](#4-repository-layout)
5. [How to read the files](#5-how-to-read-the-files)
6. [Column dictionary](#6-column-dictionary)
7. [Missing values](#7-missing-values)
8. [What we changed with respect to the original eVED files](#8-what-we-changed-with-respect-to-the-original-eved-files)
9. [Considerations about the data before modelling](#9-considerations-about-the-data-before-modelling)
10. [Reproducing our processing](#10-reproducing-our-processing)
11. [Glossary](#11-glossary)
12. [Citing, licenses and credits](#12-citing-licenses-and-credits)

---

## 1. Summary

- **What it is:** 22.4 million time-stamped samples (rows) from 32,552 trips of 384 real cars. Each row is one instant of a trip: GPS position, speed, engine or battery signals, and information about the road the car was on.
- **Starting point:** the folder [`data/processed/`](data/processed/), which contains three CSV files split by powertrain plus a table describing each vehicle.

| File | Vehicles | Trips | Rows | Columns | Size |
|---|---|---|---|---|---|
| `eVED_ICE.csv` | 264 gasoline/diesel cars (ICE) | 18,936 | 13,129,462 | 26 | 2.9 GB |
| `eVED_PHEV_HEV.csv` | 93 hybrids (HEV) + 24 plug-in hybrids (PHEV) | 13,112 | 8,830,937 | 32 | 2.2 GB |
| `eVED_EV.csv` | 3 electric cars (EV) | 504 | 476,308 | 24 | 0.1 GB |
| `vehicle_types.csv` | all 384 vehicles: type, engine, weight... | — | 384 | 7 | 14 KB |

- **How they link:** every row has a `VehId` (anonymous vehicle id) and a `Trip` id. The pair `(VehId, Trip)` identifies one trip uniquely. `VehId` joins to `vehicle_types.csv`.
- **Missing data:** missing values are written as `nan`. Many are *structural* (an electric car has no engine RPM) or come from sensors that a given car does not report. **We did not impute any measurement**; how to handle them is left to each participant (see [7](#7-missing-values)).
- **Minimal usage example:**

```python
import pandas as pd

veh = pd.read_csv("data/processed/vehicle_types.csv")                       # vehicle information by id
ev  = pd.read_csv("data/processed/eVED_EV.csv", parse_dates=["Timestamp"])   # 0.1 GB, the 3 electric cars

trip = ev[(ev["VehId"] == 455) & (ev["Trip"] == 1720)]                       # one trip = one (VehId, Trip)
print(trip[["Timestamp", "Vehicle Speed[km/h]", "HV Battery SOC[%]", "HV Battery Current[A]"]].head())
```

- **Large files:** `eVED_ICE.csv` and `eVED_PHEV_HEV.csv` are 2–3 GB. It is advisable to read only the necessary columns (`usecols=[...]`) or to process them in chunks (`chunksize=2_000_000`).
- **Worked example:** [`preprocess.ipynb`](preprocess.ipynb) includes the cleaning code, figures for every main variable and a detailed analysis of one trip.

---

## 2. Where the data comes from

### 2.1 The lineage in one picture

```
 Cars with OBD-II loggers ──►  VED (raw driving records)  ──►  eVED (adds map information)  ──►  this repository
 (Ann Arbor, 2017-2018)        University of Michigan          Chalmers / Univ. of Gothenburg      cleaned, documented and
                               weekly CSV files                weekly CSV files, +13 columns       split by powertrain type
                               static vehicle tables           (map matching, elevation,           (preprocess.ipynb)
                                                               speed limit, intersections...)
```

Three layers, produced by three different groups:

1. **VED (Vehicle Energy Dataset)** [[1]](#references) — the raw driving records. Made by the University of Michigan.
2. **eVED (Extended VED)** [[2]](#references) [[3]](#references) — the same records with corrected GPS positions and road attributes obtained from map services. Made by researchers at Chalmers University of Technology, the University of Gothenburg and Xi'an University of Technology.
3. **This edition** — our cleaned and documented version of eVED, prepared for a hackathon. It is **not** an official release of either project. The original, unmodified eVED files are kept in [`data/eVED/`](data/eVED/).

### 2.2 VED: how the raw driving records were obtained

*Source: [[1]](#references) Oh, LeBlanc & Peng, "Vehicle Energy Dataset (VED), a large-scale dataset for vehicle energy consumption research", IEEE Trans. on Intelligent Transportation Systems, 2020 ([doi](https://doi.org/10.1109/TITS.2020.3035596) · [arXiv:1905.02081](https://arxiv.org/abs/1905.02081)).*

- **Who and why.** The University of Michigan, the Argonne National Laboratory and the Idaho National Laboratory studied how human drivers use energy and how much could be saved with eco-driving technologies. The work was funded by the U.S. Department of Energy.
- **Participants.** Owners of personal cars who lived or worked in Ann Arbor, Michigan, were recruited. Because hybrid, plug-in and electric cars were rare in 2017, the researchers made a special effort to recruit owners of those.
- **The logger.** With the owners' consent, an **OBD-II data logger** was installed in each car. OBD-II is the standard diagnostic port present in every passenger car sold in the USA since 1996; it gives access to the car's internal network (CAN bus) and to a standard set of signals. The loggers sent their data in real time to a database over the cellular network, **for about a year**.
- **Signals recorded.** Three groups:
  - GPS: latitude and longitude.
  - *Standard* OBD-II signals: vehicle speed, engine speed, air flow, engine load, fuel trims and outside air temperature.
  - *OEM-customized* signals (manufacturer specific): high-voltage battery current, voltage and state of charge, and the power used by the air conditioning and by the electric heater. These exist only for plug-in and electric cars.
- **Period.** From 1 November 2017 to 9 November 2018 according to the paper (the files we have run until 10 November 2018).
- **Fleet:**

| Type | Vehicles | Notes |
|---|---|---|
| ICE (internal combustion engine) | 264 | 249 with fuel signals, 15 without |
| HEV (hybrid, not plug-in) | 93 | 91 with fuel signals, 2 without |
| PHEV (plug-in hybrid) | 24 | 4 models |
| EV (battery electric) | 3 | all three are 2013 Nissan Leaf, 24 kWh advertised battery |
| **Total** | **384** | |

  The vehicles and the fuel signals (the car reports `MAF` or `Absolute Load`) are counted in the files; the models and the battery come from the VED paper.
- **Trips.** According to the VED paper, trips average 11.4 miles (median 9.4 miles). The paper reports 32,940 trips; the files we have contain 32,552 distinct `(VehId, Trip)` pairs.
- **Variety.** Passenger cars (coupes, hatchbacks, sedans, convertibles, crossovers, luxury cars) and light trucks (pickups, SUVs, minivans, wagons). According to the VED paper, the 264 ICE cars are 107 different models from 26 manufacturers and the HEVs are 18 models from 10 manufacturers. Trips range from highways to the dense downtown area, in every season of the year.
- **Privacy: the data was de-identified.** Because trip start/end points could reveal where someone lives or works, the authors applied three steps before publishing (their parameters are not disclosed):
  1. *Random fogging:* the GPS samples at the beginning and at the end of each trip were removed following randomly generated shapes.
  2. *Geo-fencing:* only data inside a rectangle around the city of Ann Arbor was kept.
  3. *Major-intersection bounding:* each trip was cut to the part between its first and its last **major intersection**.

  Vehicle make, model, year, trim and exact weight were removed or generalized (weight is given in steps of 500 lb). General powertrain information (engine type, transmission) was kept. **Implication for use:** trips do not start or end at the driver's home or workplace; they start and end near major intersections, and there are no records outside Ann Arbor.
- **Two components.** VED has *static data* (one row per vehicle, `vehicle_types.csv` here) and *dynamic data* (the time series, one row per sample).

### 2.3 eVED: what was added on top of VED

*Source: [[2]](#references) Zhang, Fatih, Abdulqadir, Schwarz & Ma, "Extended Vehicle Energy Dataset (eVED): An Enhanced Large-Scale Dataset for Vehicle Energy Consumption Analysis", IEEE VTC2025-Spring, 2025 ([doi](https://doi.org/10.1109/VTC2025-Spring65109.2025.11174415)), and its earlier preprint [[3]](#references) ([arXiv:2203.08630](https://arxiv.org/abs/2203.08630)). The technical details below follow the preprint [3]; repository: <https://github.com/zhangsl2013/eVED>.*

The GPS positions in VED are noisy (the logger is in a vibrating, moving car), so many recorded points fall outside the road the car was really on. That makes it impossible to join the data with map information. The eVED authors therefore first **fixed the positions** and then **attached road attributes**:

| Step | What they did | Columns it produces |
|---|---|---|
| **Map matching** | Each trip's GPS trace was snapped to the most likely sequence of roads with a *Hidden Markov Model* (Valhalla / Meili library, Viterbi algorithm, OpenStreetMap roads). This is preferable to assigning the nearest road, which can select a wrong parallel street. Over 99 % of the records were matched. | `Matched Latitude[deg]`, `Matched Longitude[deg]`, `Match Type` |
| **Speed limit** | Downloaded the drivable roads and the `maxspeed` tags from OpenStreetMap (Overpass Turbo) and attached them with QGIS. Added a *class* of speed limit and the limit *in the direction of travel* (found by comparing the bearing of the road segment with the bearing of the trip). | `Class of Speed Limit`, `Speed Limit with Direction[km/h]` |
| **Elevation** | Queried the Google Maps Elevation API for each position. Because GPS points repeat over several rows, the raw elevation shows a stepwise profile, so a 5-point moving average (2 samples before, the sample itself, 2 after) was added. | `Elevation Raw[m]`, `Elevation Smoothed[m]` |
| **Road gradient** | Computed from the smoothed elevation and the geodesic distance between consecutive points (see [`Gradient`](#63-road-and-map-context)). | `Gradient` |
| **Intersections** | Extracted all intersection coordinates of Ann Arbor from OpenStreetMap with QGIS and flagged the records that fall on one. | `Intersection` |
| **Bus stops** | Bus stop locations from the City of Ann Arbor open-data catalog. A 10 m radius was drawn around each stop and the records inside are flagged. | `Bus Stops` |
| **Focus points** | 16 kinds of road elements likely to change a car's speed (traffic signals, pedestrian crossings, stop signs...) taken from OpenStreetMap. A record inside a 3 m radius is tagged with the kind of element. | `Focus Points` |
| **Energy** | A per-sample energy value computed from the signals (this is implemented in the authors' notebook [`code/EnergyConsumptionCalculation.ipynb`](code/EnergyConsumptionCalculation.ipynb); the paper does not describe it). | `Energy_Consumption` |

The eVED authors' notebooks for these steps are in [`code/`](code/) (`map-matching`, `spatial-join`, `EnergyConsumptionCalculation`, `export-processed-data`, `visualize-osm-data`).

### 2.4 This edition: what we did

We read the 54 weekly eVED CSV files (35 columns each), classified each vehicle as ICE/HEV/PHEV/EV using the static tables, fixed typos and duplicated columns, merged the two time columns into one `Timestamp`, turned impossible sensor readings into `nan`, dropped columns that are empty for a given powertrain, and wrote three CSV files. **We did not fill in missing measurements.** The complete list, with counts, is in [8](#8-what-we-changed-with-respect-to-the-original-eved-files).

---

## 3. Dataset overview

| Powertrain | Vehicles | Trips | Rows (samples) | Driving time |
|---|---|---|---|---|
| ICE | 264 | 18,936 | 13,129,462 | ≈ 2,743 h |
| HEV | 93 | 9,507 | 5,587,565 | ≈ 1,412 h |
| PHEV | 24 | 3,605 | 3,243,372 | ≈ 615 h |
| EV | 3 | 504 | 476,308 | ≈ 80 h |
| **Total** | **384** | **32,552** | **22,436,707** | **≈ 4,850 h** |

- **Period:** 2017-11-01 to 2018-11-10 (54 weekly files).
- **Area:** Ann Arbor, Michigan (latitude ≈ 42.22–42.33, longitude ≈ −83.80 to −83.67), elevations 227–324 m.
- **Balance:** the data is heavily unbalanced. Electric cars are 3 vehicles (2 % of the rows), so any conclusion about EVs rests on very few vehicles.

---

## 4. Repository layout

```
eved-dataset/
├── README.md · README.es.md      this document (English / Spanish)
├── preprocess.ipynb              our full pipeline: cleaning, three CSVs, figures, one-trip walkthrough
├── data/
│   ├── eVED/                     54 ORIGINAL weekly CSVs from the eVED authors (35 columns, ≈ 5.8 GB)
│   └── processed/                ◄── processed data
│       ├── eVED_ICE.csv
│       ├── eVED_PHEV_HEV.csv
│       ├── eVED_EV.csv
│       └── vehicle_types.csv
├── VED/                          the original VED repository (Apache 2.0)
│   └── Data/                     static vehicle tables (.xlsx) and the original dynamic data (.7z)
├── code/                         notebooks by the eVED authors (map matching, spatial join, energy...)
└── figures/                      journal-style figures (PDF vector + 300 dpi PNG) made by preprocess.ipynb
```

- The processed data is in `data/processed/`. `data/eVED/` is the raw data, which we keep for reference and for reproducibility.
- All CSV files are plain UTF-8, comma-separated, with a header line and Windows (`\r\n`) line endings, like the original files.

---

## 5. How to read the files

### 5.1 One row = one sample of one vehicle

Each row is an instantaneous record of a vehicle at one moment of one trip: its position, its speed, the state of its engine or battery, and the type of road it was on. Rows of a trip are stored consecutively and in time order.

### 5.2 Vehicles and trips

- `VehId`: an anonymous integer (2 to 630, not consecutive). It has no meaning by itself; it is used to join with `vehicle_types.csv`.
- `Trip`: an integer that identifies a trip of that vehicle.
- **`(VehId, Trip)` is unique:** it identifies exactly one trip, and a trip never spans two weekly files. Trips can be obtained with `groupby(["VehId", "Trip"])`.
- Trips are **not** guaranteed to be numbered in chronological order. For example, in vehicles 269, 356, 535 and 592 (week of 2018-04-25) the trip with the higher `Trip` id happened *immediately before* the lower one. When strict chronology is required, sort by `["VehId", "Timestamp"]` (not by `Trip`).

### 5.3 Time

- The column `Timestamp` (text `YYYY-MM-DD HH:MM:SS.mmm`, millisecond precision) is the moment of the sample. It can be parsed with `parse_dates=["Timestamp"]`.
- **It replaces two original columns.** In the original files, `DayNum` was "elapsed days since a reference date" (`DayNum` 1 = 2017-11-01 00:00:00, 1.5 = 2017-11-01 12:00:00) and is **constant within a trip**; `Timestamp(ms)` was the offset in milliseconds of each sample from that reference. We combined them: `Timestamp` = reference + offset.
- **Time zone:** neither paper says which one; the timestamps should be interpreted as the logger's local clock, without time-zone information.
- **Rows are not evenly spaced.** Measured on 14 of the 54 weeks: the time between consecutive rows of a trip has median ≈ 0.6 s, 90th percentile ≈ 1.4 s and 99th percentile ≈ 2.8 s, with occasional gaps of minutes (the largest is about 1.75 hours inside one trip). A fixed step must not be assumed; the timestamps should be used.
- **Signals are recorded at different rates** (nominal sampling times published in the VED paper):

| Signal | Nominal update |
|---|---|
| Vehicle speed, battery current | 1 s |
| Engine speed (RPM), mass air flow | 2 s |
| GPS latitude/longitude | 3 s |
| Fuel rate, absolute load, short-term fuel trims, battery voltage | 5 s |
| Long-term fuel trims | 30 s |
| Outside air temperature, battery SOC, air-conditioning and heater power | 60 s |

- **Repeated values are normal, not duplicates.** The logger merged signals of different rates into a single table, so a slow signal repeats its last value on the rows in between. The eVED paper states this for GPS ("part of the recorded GPS coordinates are duplicated across several consecutive records"); we saw the same in the other columns (for example, the state of charge changes about once a minute and forms a stepwise profile).

### 5.4 Vehicle types

Each vehicle belongs to one powertrain type, given by `EngineType` in `vehicle_types.csv`:

| `EngineType` | Meaning | Has fuel/engine signals | Has battery signals |
|---|---|---|---|
| `ICE` | Internal combustion engine (gasoline; a few diesel) | yes (most) | no |
| `HEV` | Hybrid electric vehicle. Engine + electric motor, **cannot** be plugged in | yes | practically no (only 1 of 93) |
| `PHEV` | Plug-in hybrid. Engine + motor, battery charged from the grid | yes (some) | yes |
| `EV` | Battery electric vehicle, no engine | no | yes |

The file `eVED_PHEV_HEV.csv` mixes HEV and PHEV rows intentionally (they share most columns). **To tell them apart, join with `vehicle_types.csv`:**

```python
df = pd.read_csv("data/processed/eVED_PHEV_HEV.csv", usecols=["VehId", "Trip", "Timestamp", "HV Battery SOC[%]"])
df = df.merge(veh[["VehId", "EngineType"]], on="VehId")
phev = df[df["EngineType"] == "PHEV"]
```

### 5.5 Coordinates: recorded vs matched

- `Latitude[deg]`, `Longitude[deg]` are what the GPS logged (7 decimals, noisy, updated about every 3 s).
- `Matched Latitude[deg]`, `Matched Longitude[deg]` are the corrected position on the road network. They are recommended when joining the data with maps.
- `Match Type` indicates how the matched position was obtained (see [6.3](#63-road-and-map-context)).

### 5.6 Missing values in the CSV

- A missing value is written as the text **`nan`**. `pandas.read_csv` reads it as `NaN` automatically; in other tools, `nan` must be declared as the missing-value marker.
- `Focus Points` uses the ordinary text `none` (lowercase) for "no focus point". It is **not** a missing value.

### 5.7 Loading recommendations

```python
# Read only the necessary columns
cols = ["Timestamp", "VehId", "Trip", "Vehicle Speed[km/h]", "Energy_Consumption"]
ice = pd.read_csv("data/processed/eVED_ICE.csv", usecols=cols, parse_dates=["Timestamp"])

# Read a large file in chunks
for chunk in pd.read_csv("data/processed/eVED_PHEV_HEV.csv", chunksize=2_000_000):
    ...

# Seconds since the start of each trip
t0 = ice.groupby(["VehId", "Trip"])["Timestamp"].transform("min")
ice["t_s"] = (ice["Timestamp"] - t0).dt.total_seconds()
```

---

## 6. Column dictionary

Every file follows the **same column order**. Below, *Origin* says where the value comes from: **logger** = recorded by the car's OBD-II logger; **eVED** = added by the eVED authors from maps or by calculation; **ours** = created or changed in this edition.

### 6.1 Which columns are in which file

| Column | `ICE` | `PHEV_HEV` | `EV` |
|---|:-:|:-:|:-:|
| Timestamp, VehId, Trip | ✓ | ✓ | ✓ |
| Latitude, Longitude, Vehicle Speed | ✓ | ✓ | ✓ |
| MAF, Engine RPM, Absolute Load | ✓ | ✓ | — |
| OAT | ✓ | ✓ | ✓ |
| Fuel Rate | — (see [7](#7-missing-values)) | ✓ | — |
| Air Conditioning Power, Heater Power | — | ✓ | ✓ |
| HV Battery Current, SOC, Voltage | — | ✓ | ✓ |
| Short/Long Term Fuel Trims (banks 1 and 2) | ✓ | ✓ | — |
| Elevation Raw/Smoothed, Gradient, Energy_Consumption | ✓ | ✓ | ✓ |
| Matched Latitude/Longitude, Match Type | ✓ | ✓ | ✓ |
| Class of Speed Limit, Speed Limit with Direction | ✓ | ✓ | ✓ |
| Intersection, Bus Stops, Focus Points | ✓ | ✓ | ✓ |

We leave a column out of a file only when it is (almost) empty for that powertrain.

### 6.2 Time, vehicle and signals recorded by the car

| Column | Unit / type | What it is | Origin |
|---|---|---|---|
| `Timestamp` | text `YYYY-MM-DD HH:MM:SS.mmm` | Moment of the sample (see [5.3](#53-time)). | ours (from `DayNum` + `Timestamp(ms)`) |
| `VehId` | integer | Anonymous vehicle id. | logger |
| `Trip` | integer | Trip id; `(VehId, Trip)` is unique. | logger |
| `Latitude[deg]`, `Longitude[deg]` | degrees | GPS position as recorded (noisy). | logger |
| `Vehicle Speed[km/h]` | km/h | Speed reported by the car (resolution 1 km/h; some PHEV/EV report decimals). About 5–15 % of the samples are 0 (stopped). | logger |
| `MAF[g/sec]` | g/s | *Mass air flow*: mass of air entering the engine. Together with the fuel trims it allows fuel use to be estimated (VED paper, Algorithm 1). | logger |
| `Engine RPM[RPM]` | rev/min | Engine speed. `0` means the engine is off (common in hybrids: 29 % of HEV and 73 % of PHEV samples). | logger |
| `Absolute Load[%]` | % | OBD-II *absolute load value*: how much air the engine takes relative to its capacity. Normally 0–100 %, it can exceed 100 % in some engines. We turned values above 300 % into `nan`. | logger, ours (impossible values) |
| `OAT[DegC]` | °C | *Outside air temperature*, from the car's own sensor. Some sensors read higher than the true value (solar radiation, engine heat) or show the placeholder −40 °C. We turned values outside −30…45 °C into `nan`. | logger, ours (impossible values) |
| `Fuel Rate[L/hr]` | L/h | Fuel consumption **reported by the manufacturer's electronics**. Only some PHEVs report it (see [7](#7-missing-values)). This is the only *direct* fuel measurement in the data. | logger |
| `Air Conditioning Power[Watts]` | W | Power used by the air-conditioning compressor. In the original files some cars used kW and others W in two separate columns; we unified them in W. | logger, ours (unit merge) |
| `Heater Power[Watts]` | W | Power used by the electric cabin heater. | logger |
| `HV Battery Current[A]` | A | Current at the terminal of the high-voltage traction battery. **Positive = charging** (for example regenerative braking), **negative = discharging** (driving). | logger |
| `HV Battery SOC[%]` | % | *State of charge*: how full the high-voltage battery is (0–100 %). It changes about once a minute, so it shows a stepwise profile. | logger |
| `HV Battery Voltage[V]` | V | Voltage of the high-voltage battery. We turned values of 0 V (sensor without reading) into `nan`. | logger, ours (impossible values) |
| `Short Term Fuel Trim Bank 1[%]`, `... Bank 2[%]` | % | Instant correction the engine control unit applies to the amount of fuel (range −100…99.2 %). A *bank* is a row of cylinders; bank 2 exists only in engines with two banks (for example V6, V8), otherwise it is `nan`. | logger |
| `Long Term Fuel Trim Bank 1[%]`, `... Bank 2[%]` | % | Slow, accumulated version of the same correction. | logger |

### 6.3 Road and map context

| Column | Unit / type | What it is | Origin |
|---|---|---|---|
| `Elevation Raw[m]` | m | Height above sea level at the position, from the Google Elevation API. It shows a stepwise profile because positions repeat over consecutive rows. | eVED |
| `Elevation Smoothed[m]` | m | Moving average of the raw elevation over 5 points (2 before, the point, 2 after). This one is recommended for slopes. | eVED |
| `Gradient` | ratio (rise / run) | Road slope: `0.05` is a 5 % uphill, `−0.05` a 5 % downhill. Computed from consecutive points (cases in the table below). Most values are exactly 0 (about 81 % in a sample of four weeks). | eVED |
| `Energy_Consumption` | kWh **per row** | Energy of the sample, defined by the eVED authors ([6.5](#65-how-energy_consumption-is-computed)). **Consult [9](#9-considerations-about-the-data-before-modelling), item 1, before using it.** | eVED |
| `Matched Latitude[deg]`, `Matched Longitude[deg]` | degrees | Position snapped to the road by map matching. (The original files had the typo `Matchted Latitude[deg]`; we fixed it.) | eVED, ours (typo) |
| `Match Type` | 0 / 1 / 2 | How the matched position was obtained (table below). | eVED |
| `Class of Speed Limit` | −1, 0, 1, 2, 3 | Where the speed limit comes from (table below). | eVED |
| `Speed Limit with Direction[km/h]` | km/h | Speed limit **for the direction the car was driving**. The values are US limits in mph converted to km/h (40 = 25 mph, 48 = 30, 56 = 35, 72 = 45, 89 = 55, 113 = 70). | eVED |
| `Intersection` | 0 / 1 | 1 if the position is at an intersection (from OpenStreetMap). | eVED, ours (empty → 0) |
| `Bus Stops` | 0 / 1 | 1 if the position is within 10 m of a bus stop. | eVED, ours (empty → 0) |
| `Focus Points` | text | Kind of road element within 3 m, or `none`. The 16 kinds: `crossing`, `traffic_signals`, `stop`, `give_way`, `roundabout`, `mini_roundabout`, `turning_loop`, `turning_circle`, `motorway_junction`, `level_crossing`, `hump`, `bump`, `gate`, `lift_gate`, `swing_gate`, `bollard` (OpenStreetMap terms). Ten rows carry the combined value `gate;lift_gate`. | eVED, ours (empty → `none`) |

**`Match Type`** (share of the rows of the files):

| Code | Label | Meaning | Share of rows |
|---|---|---|---|
| `0` | matched | A new GPS fix, matched to a road. 99 % of these rows differ from the previous row's coordinates. | 15–20 % |
| `1` | interpolated | The raw coordinate repeats the previous row's (98.6 %), so the matched point is the same one. | 80–87 % |
| `2` | unmatched | No road found; the matched position equals the raw one. | less than 1 % |

The papers name the three labels but not their numeric codes; we checked the codes in the table against the data (on the first million rows of `eVED_EV.csv`).

**`Gradient`** (computed from consecutive points):

| Situation | Value |
|---|---|
| The elevation values of the two points are equal | `0` |
| The elevation values differ | (height difference) / (geodesic distance between the two points) |
| The vehicle has not moved between the two rows | `nan`. In 99.7 % of the `nan` rows the GPS coordinate equals the previous row's, consistent with a division by zero |

**`Class of Speed Limit`** (share of the raw records, from the eVED paper):

| Class | Meaning | Share |
|---|---|---|
| `0` | Legal maximum speed limit posted on the road (`maxspeed`) | 81.7 % |
| `1` | No explicit sign: Michigan **default** limits apply (motorway 70 mph, trunk/primary/unclassified 55, secondary 45, tertiary 35, residential/service 25) | 14.4 % |
| `-1` | The limit is different in each direction of travel (`maxspeed:forward/backward`); `Speed Limit with Direction` gives the one that applies | 0.57 % |
| `2` | Advisory speed (not legally binding) | 0.93 % |
| `3` | Practical/realistic average speed when there is no legal limit | 0.03 % |

Counts of `Focus Points` in the whole eVED (paper, Table 4): crossing 312,196 · traffic signal 195,856 · stop 29,397 · turning loop 5,848 · level crossing 4,053 · turning circle 3,554 · motorway junction 2,938 · gate 1,105 · give way 985 · hump 223 · mini roundabout 195 · bump 108 · lift gate 96 · roundabout 81 · bollard 1 · swing gate 4.

### 6.4 The vehicle table `vehicle_types.csv`

One row per vehicle (384 rows). Source: the two static tables of VED (`VED/Data/VED_Static_Data_*.xlsx`), which we unified.

| Column | What it is | Completeness |
|---|---|---|
| `VehId` | Vehicle id (joins with the CSVs). | 384 / 384 |
| `EngineType` | `ICE` (264), `HEV` (93), `PHEV` (24) or `EV` (3). *The two source tables named this column differently (`Vehicle Type`, `EngineType`).* | 384 / 384 |
| `Vehicle Class` | `Car` or `SUV`. | only 32 vehicles (all PHEV and EV, 5 others) |
| `Engine Configuration & Displacement` | Text such as `4-FI 2.4L` (4 cylinders, fuel injection, 2.4 litres), `4-GAS/ELECTRIC 1.8L` (hybrid), `8-DSL 6.7L T/C` (8 cylinders, diesel, turbocharged; our reading of `DSL` and `T/C`) or `ELECTRIC`. | 384 / 384 |
| `Transmission` | For example `CVT`, `5-SP AUTOMATIC`, `5-SP MANUAL` (upper-cased by us). | 95 / 384 (ICE 79, HEV 4, PHEV 12) |
| `Drive Wheels` | `FWD` (front-wheel drive). | only PHEV and EV (27) |
| `Generalized_Weight` | Weight in **pounds**, deliberately rounded to 500 lb steps (2,000–6,500) for privacy. | 368 / 384 |

The source tables used the text `NO DATA` for unknown values; we turned it into an empty cell.

### 6.5 How `Energy_Consumption` is computed

Defined by the eVED authors and implemented in [`code/EnergyConsumptionCalculation.ipynb`](code/EnergyConsumptionCalculation.ipynb) (the paper does not describe it). The unit is **kWh per row**. The authors assumed in their code that **each row lasts exactly 1 second** (hence the `/3600` divisors in the formulas; they justify it because speed and current are sampled every 1 s) and did not use the timestamps. Since the real energy of a row is `Energy_Consumption × Δt` (Δt = seconds between rows), to add values over a trip the `Timestamp` must be used (see [9](#9-considerations-about-the-data-before-modelling), item 1).

| | PHEV and EV | ICE and HEV |
|---|---|---|
| Formula per row | `−current × voltage / 3.6·10⁶` | `(speed/3600)/100 × (MAF × 3.78541) × (1 + ShortTermTrim1/100 + LongTermTrim1/100) / 14.08`, then converted to kWh with 1 kWh = 0.1123 L of gasoline |
| Comes from | measured electrical power | a formula based on air flow |
| Sign | positive = the battery is discharging (consumption); negative = regeneration | fuel burnt, expressed as energy |
| Car stopped | the formula does not use speed | **exactly 0**, even if the engine is idling and burning fuel, because the formula multiplies by the distance covered in the sample (in ICE rows with speed 0 and MAF present it is 0 or `nan`, with no other values) |
| `nan` when | current or voltage is missing | `MAF` or a bank-1 fuel trim is missing |

The ICE/HEV formula is different from the fuel-rate estimate of the VED paper (Algorithm 1: `MAF × (1 + STFT/100 + LTFT/100) / AFR`, AFR = 14.08 for E10 fuel, averaging the trims of both banks when bank 2 exists). To obtain fuel flow, it must be computed from `MAF[g/sec]` and the trims. Electric and combustion values are not directly comparable.

---

## 7. Missing values

### 7.1 Why values are missing

1. **The car does not have the sensor.** An EV has no engine, so it has no RPM or MAF; an ICE car has no battery. We remove those columns from the file of that powertrain.
2. **The car has the sensor but the logger did not capture it.** For a given vehicle, a signal is usually either present in almost every row or absent altogether: a car does not report MAF for some rows and not for others. For example 15 ICE and 2 HEV vehicles report no fuel signals at all (VED paper, Table I).
3. **Missing for whole trips.** In the weeks we inspected, *no* `nan` cell of the sensor columns had a valid reading within 30 seconds inside its own trip. Missing data comes as whole trips or whole vehicles, not as short gaps. Interpolating inside a trip therefore fills almost nothing.
4. **`Gradient` is `nan` when the car did not move** between consecutive rows (see [6.3](#63-road-and-map-context)).
5. **The speed-limit columns** (`Class of Speed Limit`, `Speed Limit with Direction[km/h]`) **are `nan`** where the map join attached no speed limit (the papers do not document why; most likely positions that are not on the mapped road network).
6. **Impossible readings that we blanked** (`OAT`, `Absolute Load`, `HV Battery Voltage`): see [8](#8-what-we-changed-with-respect-to-the-original-eved-files).
7. **`Energy_Consumption` is derived** from other columns, so it is `nan` whenever its inputs are (for ICE/HEV: MAF or a bank-1 fuel trim missing; see [6.5](#65-how-energy_consumption-is-computed)).

### 7.2 How much is missing (percent of the rows of each file)

| Column | `ICE` | `PHEV_HEV` | `EV` |
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

Notes: in `PHEV_HEV` the battery columns are 63.2 % empty because the file mixes PHEVs (which report them) with HEVs (only 1 of 93 does). The percentages are per file, so they mix vehicles that report a signal with vehicles that never do: they should be reviewed **per vehicle** before deciding how to treat a column.

### 7.3 What we did about them

**Nothing beyond blanking impossible readings.** We deliberately did **not** impute or interpolate any measurement (`OAT`, `Gradient`, `MAF`, fuel trims, battery signals...). Participants are free to handle them with the method they consider appropriate (dropping, per-vehicle or per-trip statistics, model-based imputation, models that accept `nan`...). Two facts that may help: the ambient temperature is essentially the same for the whole city at a given time, so the `OAT` of other vehicles at the same hour carries information; and `Gradient` is derived from `Elevation Smoothed[m]` and the positions, so it can be recomputed.

The only fills we made are not statistical: the `Air Conditioning Power` unit merge, and the "no event" flags (`Intersection`, `Bus Stops` → 0; `Focus Points` → `none`).

---

## 8. What we changed with respect to the original eVED files

The original files are in [`data/eVED/`](data/eVED/). Everything below is implemented in [`preprocess.ipynb`](preprocess.ipynb), and the counts can be seen in its execution log.

| # | Problem in the original | What we did | Effect |
|---|---|---|---|
| 1 | Header typo `Matchted Latitude[deg]` | We renamed it to `Matched Latitude[deg]` | all files |
| 2 | Header typo `Focus Points;` (with a semicolon, in week 180124 only), and values ending in `;` in that week (`crossing;`) | We renamed it to `Focus Points` and removed the trailing `;` | 1 week |
| 3 | The vehicle type column is called `Vehicle Type` in one static table and `EngineType` in the other | We unified it as `EngineType` | `vehicle_types.csv` |
| 4 | Air conditioning power in two columns (`[kW]` for some cars, `[Watts]` for others; no car has both) | We merged them into `Air Conditioning Power[Watts]` (kW × 1000) | ≈ 0.9 M values converted |
| 5 | `Speed Limit[km/h]` duplicates `Speed Limit with Direction[km/h]`, with mixed text/number values such as `40-48` | We dropped it. The direction-dependent case remains flagged by `Class of Speed Limit = -1` | 1 column removed |
| 6 | The same instant of a vehicle (same `VehId`, `DayNum` and `Timestamp(ms)`) appeared in **two different trips** (4 trips of week 180425, all ICE) | We kept the copy of the trip with the lower `Trip` id and removed the other. The removed copies matched in sensors and position and differed at most in map-derived columns | **101 rows removed** |
| 7 | Impossible readings | We set them to `nan`: `OAT` outside −30…45 °C (32,368 values), `Absolute Load` above 300 % (340), `HV Battery Voltage` equal to 0 V (5). Also checked, with no case found: speed outside 0–200 km/h, fuel trims outside the OBD-II range −100…99.2 % | 32,713 values |
| 8 | Empty `Intersection`, `Bus Stops`, `Focus Points` really mean "no event" | We filled them with `0`, `0`, `none` | 3 columns |
| 9 | Two time columns (`DayNum` + `Timestamp(ms)`) | We merged them into one `Timestamp` (millisecond integer arithmetic, verified independently). In 4 trips the `Timestamp(ms)` offset was negative; it is valid and ends up with the right `Timestamp` (see [5.2](#52-vehicles-and-trips)) | 2 columns → 1 |
| 10 | `VehId`, `Trip`, `Match Type` stored as decimals (`8.0`) | We stored them as integers | — |
| 11 | Columns that are empty for a powertrain | We removed them from that powertrain's file when ≥ 99 % empty | see 6.1 |
| 12 | One big table of mixed powertrains | We split it into `ICE`, `PHEV_HEV`, `EV` and kept the row order (chronological by week, then by trip) | 3 files |

**What we did *not* do:** no imputation or interpolation; no resampling to a fixed rate; no unit conversion except the air-conditioning merge; no removal of rows other than the 101 repeated ones; no normalization or scaling; no change to the map-matched positions, the speed limits or the energy values.

**Checks.** The notebook stops if any of these fails.

- *On the original weekly files:* time is ordered within every trip; there is a single `DayNum` per trip; each `(VehId, Trip)` appears in one week only; every `VehId` has a type; the weekly files have identical columns.
- *On the three final files:* the expected header and number of rows; only vehicles of their own type; strictly increasing time within each trip; no vehicle with overlapping trips; no duplicated columns.
- *In addition,* we compared the output row by row with the original files for several weeks (including the two anomalous ones), and confirmed that only the columns listed above changed.

**Original dataset and this edition:**

| | Original dataset (VED/eVED files) | This edition |
|---|---|---|
| Vehicles | 384 | 384 |
| HEVs | 93 | 93 |
| Trips | 32,552 | 32,552 |
| Last day | 2018-11-10 | 2018-11-10 |
| Rows | 22,436,808 | 22,436,707 |

---

## 9. Considerations about the data before modelling

1. **`Energy_Consumption` needs care, especially when summed.** Definition and formulas: [6.5](#65-how-energy_consumption-is-computed).
   - **To obtain the energy of a trip, integrate with the timestamps (`Energy_Consumption × Δt`); the rows should not be added up directly.** The column is in **kWh per row** and the eVED authors computed each value as if the row lasted exactly 1 second, but rows are on average ≈ 0.6 s apart and irregular. That is why the direct sum overestimates the energy: for the 329 EV trips longer than 5 min with a relevant net energy, it was about **2.1 times** (quartiles 2.03–2.17) the energy obtained by integrating battery power over the real time, and a separate check across PHEV and EV gave a median of about 1.5. With the data of this repository:

     ```python
     dt = df.groupby(["VehId", "Trip"])["Timestamp"].diff().dt.total_seconds().fillna(0)   # seconds between rows
     trip_kwh = (df["Energy_Consumption"] * dt).groupby([df["VehId"], df["Trip"]]).sum()
     ```

     We checked that this matches integrating battery power over the real time in all 504 EV trips (difference of the order of 1e-13 kWh), and recomputing the ICE formula with the real Δt on 911,541 ICE rows.
   - **For ICE and HEV it is exactly 0 whenever the car is stopped, even if the engine is idling and burning fuel.** To obtain fuel flow, it must be computed from `MAF[g/sec]` and the trims.
   - Electric and combustion values are not directly comparable: one comes from measured electrical power, the other from a formula based on air flow.
2. **The `Timestamp` should be used to differentiate and integrate.** Rows are not equally spaced (median ≈ 0.6 s) and values repeat. Rates (`diff` per second) and integrals should be computed with the timestamps, not with row counts. Consecutive identical values are the normal effect of signals recorded at different rates ([5.3](#53-time)).
3. **Beware of information leakage when splitting the data.** Rows of one trip are extremely similar to each other, and so are trips of one car. If the rows are spread at random between training and test, information leaks from one set to the other. Splitting in whole blocks is recommended: by vehicle (it measures generalization to new cars) or by date range (it measures generalization to later dates); see also item 11.
4. **Very few EVs (3) and few PHEVs (24).** Average results for these types can depend on a single car. All three EVs are the same model (2013 Nissan Leaf).
5. **Different vehicles have different sensors.** Availability changes per vehicle, not just per type (see [7](#7-missing-values)). Coverage per vehicle should be checked before using a column.
6. **Only 1 of 93 HEVs has battery signals.** Battery analyses are in practice PHEV + EV.
7. **`Fuel Rate[L/hr]` is scarce.** It exists for about half of the PHEVs. In ICE cars only vehicle 119 (an 8-cylinder 6.7 L turbo diesel, 5 trips, 1,822 rows) reports it, and because it is 99.99 % empty for the ICE population we **removed it from `eVED_ICE.csv`**. It is still in the original files in `data/eVED/`.
8. **GPS and map columns.** Raw GPS is noisy: for map work, the matched coordinates are recommended. About 80 % of the rows repeat the previous position (`Match Type = 1`). The speed limits are those of OpenStreetMap at the time of the eVED work.
9. **Time zone unknown** (see [5.3](#53-time)). Time-of-day analyses assume local time.
10. **Weather and other context are not in the data.** Only outside air temperature is included, and for many cars it is missing.
11. **The number of vehicles recording changes along the year.** Vehicles drop out of the study: for example, ICE cars with at least one trip fall from 222 (84 % of the ICE fleet) in November 2017 to 126 (48 %) in October 2018, and ICE trips per month from 2,318 to 1,090. The trips *per active vehicle* stay roughly constant (ICE and HEV: about 8–12 per month), so the selected time period changes both the amount of data and *which* cars are observed. This should be considered when defining training and validation periods.

---

## 10. Reproducing our processing

Everything that produced `data/processed/` and `figures/` is in [`preprocess.ipynb`](preprocess.ipynb):

1. Loads the static tables and classifies each vehicle.
2. Cleans each weekly file ([8](#8-what-we-changed-with-respect-to-the-original-eved-files)) and stores it temporarily as Parquet.
3. Decides which columns to drop per powertrain and writes the three CSV files.
4. Verifies the files.
5. Draws the figures (sections 8 and 9 of the notebook) and saves them in `figures/` as vector PDF and 300-dpi PNG.

To run it: Python ≥ 3.10 with `pandas` (≥ 2), `numpy`, `pyarrow`, `openpyxl`, `matplotlib` and Jupyter. The notebook should be opened from the repository root and run in full. On a 16 GB machine the processing takes a few minutes; about 10 GB of free disk are required for the outputs. For a quick trial run, set `MAX_WEEKS = 2` in the configuration cell.

Section 9 of the notebook shows one trip in detail (`TRIP_ID = (455, 1720)`, an electric car; it can be replaced by another trip): speed, elevation, state of charge, voltage, current, energy per sample, the route on a map and cumulative energy.

---

## 11. Glossary

| Term | Meaning |
|---|---|
| **ICE** | Internal combustion engine vehicle (gasoline or diesel). |
| **HEV** | Hybrid electric vehicle: engine + electric motor, recharges its battery without an external connection, cannot be plugged in. |
| **PHEV** | Plug-in hybrid electric vehicle: like HEV but its battery can be charged from the grid; drives in "EV mode" or "hybrid mode". |
| **EV / BEV** | (Battery) electric vehicle: only a battery and electric motor. |
| **OBD-II** | Standard on-board diagnostic port/protocol present in every passenger car sold in the USA since 1996. |
| **CAN bus** | The car's internal communication network that the logger listens to. |
| **OEM** | Original equipment manufacturer (the carmaker); "OEM-customized signals" are manufacturer-specific, non-standard signals. |
| **GPS** | Global positioning system. |
| **MAF** | Mass air flow (g/s). |
| **RPM** | Revolutions per minute (engine speed). |
| **Absolute load** | OBD-II measure of engine load. |
| **Fuel trim (STFT / LTFT)** | Short-term / long-term correction of the fuel quantity by the engine controller (%). |
| **OAT** | Outside air temperature. |
| **HV battery** | High-voltage traction battery of hybrids and electric cars. |
| **SOC** | State of charge of the battery (%). |
| **HVAC** | Heating, ventilation and air conditioning. |
| **Regenerative braking** | Recovery of kinetic energy into the battery when decelerating (negative energy / positive battery current). |
| **MPG / MPGe** | Miles per gallon / miles per gallon equivalent (electric cars). |
| **Map matching** | Snapping noisy GPS points to the road network. |
| **HMM** | Hidden Markov Model, the statistical method used for map matching. |
| **OSM** | OpenStreetMap, the open map database. |
| **QGIS** | Open-source geographic information system used to join maps and trips. |
| **Focus point** | Road element that may change the speed of a car (signal, crossing, stop sign...). |
| **Grade / gradient** | Road slope (rise over run). |
| **Trip** | One continuous recording session of a vehicle. |
| **IQR** | Interquartile range (25th to 75th percentile). |

---

## 12. Citing, licenses and credits

### References

**Users of this data should cite the original works.** The eVED authors ask to cite either of their two papers ([2] or [3]); since eVED is built on VED's recordings, the VED paper [1] should be cited as well.

**[1]** G. S. Oh, D. J. LeBlanc and H. Peng, "Vehicle Energy Dataset (VED), a large-scale dataset for vehicle energy consumption research," *IEEE Transactions on Intelligent Transportation Systems*, 2020. doi: [10.1109/TITS.2020.3035596](https://doi.org/10.1109/TITS.2020.3035596) · preprint: [arXiv:1905.02081](https://arxiv.org/abs/1905.02081)

**[2]** S. Zhang, D. Fatih, F. Abdulqadir, T. Schwarz and X. Ma, "Extended Vehicle Energy Dataset (eVED): An Enhanced Large-Scale Dataset for Vehicle Energy Consumption Analysis," in *2025 IEEE 101st Vehicular Technology Conference (VTC2025-Spring)*, Oslo, Norway, 2025, pp. 1–7. doi: [10.1109/VTC2025-Spring65109.2025.11174415](https://doi.org/10.1109/VTC2025-Spring65109.2025.11174415)

**[3]** S. Zhang, D. Fatih, F. Abdulqadir, T. Schwarz and X. Ma, "Extended vehicle energy dataset (eVED): an enhanced large-scale dataset for deep learning on vehicle trip energy consumption," arXiv preprint arXiv:2203.08630, 2022. [arxiv.org/abs/2203.08630](https://arxiv.org/abs/2203.08630)

The titles of [2] and [3] differ; the eVED authors list both as the way to cite their work.

**BibTeX of [1]**, exactly as published on arXiv (for [2] and [3], use the citations above):

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

**Original repositories:** VED — <https://github.com/gsoh/VED> · eVED — <https://github.com/zhangsl2013/eVED> (data and code: `git clone https://Datarepo@bitbucket.org/datarepo/eved_dataset.git`).

### Licenses and credits

**Licenses and terms.** The VED repository (copied in [`VED/`](VED/)) is under the **Apache License 2.0** ([`VED/LICENSE`](VED/LICENSE)). The eVED columns are derived from third-party sources: **OpenStreetMap** contributors (speed limits, intersections, focus points, road network), the **Google Maps Elevation API** (elevation) and the **City of Ann Arbor** open-data catalog (bus stops). We have not checked their terms for redistribution or publication of derived work; verify them before publishing anything that includes these columns.

**Credits.** VED: University of Michigan (G. S. Oh, D. J. LeBlanc, H. Peng), University of Michigan Transportation Research Institute, Argonne National Laboratory and Idaho National Laboratory, funded by the U.S. Department of Energy. eVED: Chalmers University of Technology, University of Gothenburg and Xi'an University of Technology. We prepared this processed and documented edition for a hackathon; it is not endorsed by the original authors.
