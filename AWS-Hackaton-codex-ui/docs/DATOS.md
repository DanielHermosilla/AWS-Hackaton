# Electromovilidad.zip — datos locales y hallazgos

**14-10-2026. Revisión ampliada de todas las filas y columnas de los seis CSV, contrastada con el diccionario recibido por AWS.** No se eligió solver, calibró consumo ni ejecutó una planificación de rutas.

## Ubicación e integridad

El ZIP recibido en Descargas se copió a `data/archive/Electromovilidad.zip`. Sus seis CSV se extrajeron sin modificar a `data/raw/`. Se omitieron los metadatos de macOS `__MACOSX`, conservados dentro del ZIP. Las dos copias encontradas en Descargas tienen el mismo SHA-256:

```text
ad6ef73173bb893e3381375ec6efe92a03d6f2eb01126229a9b03255117bb9ab
```

Archivo comprimido: **656.394.335 bytes**. Los CSV ocupan aproximadamente **5,21 GB decimales**. `data/manifest.json` contiene nombres, tamaños y SHA-256 de los seis archivos. Scripts y agregados de esta exploración están en `data/analysis/`.

`/data/` está en `.gitignore` y no tiene archivos versionados. Originales, ZIP y derivados permanecen locales; no se añadieron a staging ni se enviaron a GitHub. La copia local se contrastó entre duplicados, no contra una segunda descarga del portal.

[Descarga publicada por el portal CASE](https://d78v2swml9yu2.cloudfront.net/api/challenges/c1/download?key=Electromovilidad.zip), identificada el 14-10. Su publicación no resuelve por sí sola las condiciones para redistribuir datos.

### Diccionario incorporado después del primer análisis

El correo **«FW: Readme CASE»**, remitido por Carla Catalano de AWS Professional Services el **14-10-2026 a las 15:02 de Chile**, contiene `Diccionario.zip`. Se recuperó mediante el acceso del correo y se guardó en `data/archive/Diccionario.zip`: **39.413 bytes**, SHA-256 `6151cb4d7b2e3c1efeae158e1cd0f16ecd1a12cd2aa6b93a16555ff6ec5f3931`.

Contiene únicamente `README.es.md` y `README.md`; copias sin modificar en `data/reference/diccionario-20261014/`, también fuera de Git. Se leyó completo el [diccionario en español](../../AWS-Hackaton/data/reference/diccionario-20261014/README.es.md) y se contrastaron sus definiciones con los archivos. Las rutas a notebooks, originales semanales y figuras que describe no forman parte de estos dos ZIP; no se ejecutaron ni se atribuyen como inspeccionadas.

## Inventario completo

Filas sin cabecera. En esta nueva pasada se recorrieron **todas las filas y columnas**, con bloques de 250.000 registros para la telemetría: faltantes, rangos, ceros/signos, categorías, cobertura por vehículo, IDs, viajes, cronología y fórmulas de energía. Perfil descriptivo completo no equivale a validación de cada significado físico ni a prueba del evaluador.

| Archivo | Filas | Columnas | Qué contiene / revisión |
|---|---:|---:|---|
| `competition_routing_nodes.csv` | 81 | 11 | Nodos; perfil completo de estructura, tipos y estaciones |
| `evaluation_routing_nodes.csv` | 81 | 11 | Nodos; comparación campo a campo con público |
| `vehicle_types.csv` | 384 | 7 | Catálogo; IDs únicos y tipos |
| `eVED_EV.csv` | 476.308 | 24 | 3 EV, 504 viajes; perfil completo y contraste de fórmula |
| `eVED_ICE.csv` | 13.129.462 | 26 | 264 ICE, 18.936 viajes; perfil completo y contraste de fórmula |
| `eVED_PHEV_HEV.csv` | 8.830.937 | 32 | 93 HEV + 24 PHEV, 13.112 viajes; perfil completo y contraste por tipo |

El catálogo tiene 264 ICE, 93 HEV, 24 PHEV y 3 EV. Total de telemetría: **22.436.707 registros, 384 vehículos y 32.552 viajes**. Cero IDs desconocidos, tipos inesperados o tiempos repetidos/decrecientes dentro del mismo viaje observados. HEV aporta 5.587.565 registros y PHEV 3.243.372.

Los seis SHA-256 coinciden con el manifiesto original; tamaño y fecha de modificación permanecen iguales. Se amplió la revisión anterior, que solo contaba filas/IDs en los archivos no EV. Evidencia local: [informe](../data/analysis/confirmaciones-20261014/README.md), [perfil de cada columna](../data/analysis/confirmaciones-20261014/profile.json), [script propio](../data/analysis/confirmaciones-20261014/profile_all.py) y [reconciliación](../data/analysis/confirmaciones-20261014/verification.json).

## Nodos y cargadores

Cabecera de ambos archivos, **UTF-8 con BOM**:

```text
node_id,node_type,latitude,longitude,address,network,
total_ports,dc_fast_ports,level2_ports,connector_types,max_power_kw
```

- Cada instancia tiene **1 base, 20 locales y 60 estaciones**. IDs únicos y coordenadas finitas, sin duplicados exactos. Atributos de estación vacíos en base/locales son campos no aplicables, no ceros inventados.
- `evaluation` cambia **solo las 40 celdas de latitud/longitud de los 20 locales**. BASE y los 60 cargadores son idénticos al público. Está confirmado qué cambia en estos archivos; solo queda aclarar su papel respecto de la instancia reservada anunciada.
- Potencia máxima declarada: **6,2–400 kW**; 12 estaciones ≥50 kW y 48 por debajo.
- **321 puertos:** 59 DC y 262 nivel 2. Conectores por estación: CCS 12, CHAdeMO 7, J1772 49, NACS 5; categorías superpuestas.
- La lista de conectores usa `;`. El total de puertos no es cantidad de puertos por conector. C7 mezcla 1 DC + 6 nivel 2 y declara máximo 80 kW; no significa que su J1772 entregue 80 kW.

No hay disponibilidad en vivo, horarios/colas, potencia por conector, tarifas, curva/eficiencia de carga o límite de potencia/capacidad útil del vehículo. El nuevo diccionario describe telemetría y catálogo, sin añadir reglas operativas de estos cargadores. Las siete estaciones con CHAdeMO **no equivalen a siete estaciones utilizables** sin verificar compatibilidad y condiciones.

**Aclarado por Diego, 14-10:** reserva a la llegada ≥ 0; todos los pedidos obligatorios, sin agotamiento que impida completar el recorrido. Su ausencia del CSV ya no deja esa regla pendiente. Las condiciones disponibles de recarga se toman del dataset; solo falta acordar qué simplificaciones admite la evaluación para los aspectos que no proporciona. No convertir horarios, colas, tarifas u otros campos ausentes en requisitos obligatorios.

El ZIP no incluye matriz de distancias/tiempos ni arcos de la instancia. Tampoco trae cantidades/pesos de pedidos, tiempos de servicio o ventanas horarias: no inventarlos como restricciones. Ubicaciones y trazas no certifican una ruta vial.

## Telemetría EV: detalles que cambian la interpretación

**476.308 registros, 3 vehículos y 504 pares `(VehId, Trip)`**. Hay solo 491 valores distintos de `Trip`: 13 se repiten entre vehículos. No usar ese campo solo para agrupar.

| Vehículo | Registros | Viajes |
|---|---:|---:|
| 10 | 167.257 | 201 |
| 455 | 303.824 | 293 |
| 541 | 5.227 | 10 |

No se observaron duplicados completos ni claves duplicadas `(VehId, Trip, Timestamp)`. Fechas literales: 2017-11-01 a 2018-11-09, sin zona horaria declarada.

El intervalo dentro de viaje varía: mediana **0,4 s**, mínimo **0,1 s**, máximo **1.318,2 s**. Hay **581 huecos >10 s en 157 viajes**. No es muestreo uniforme a 0,2 s ni a 1 s.

`Gradient` tiene 7.381 nulos; los dos campos de límite de velocidad, 6.619 cada uno. `Focus Points` contiene `none` en 462.374 filas: **el diccionario §5.6 confirma que significa «sin evento», no un faltante**. Ya están documentados códigos y unidades; pendiente es razón (0,05 = 5%), peso generalizado en libras y SOC en porcentaje.

### Hallazgo de `Energy_Consumption`

Las **476.308 filas** cumplen, con residuo absoluto máximo aproximado de 1,01×10⁻¹⁶:

```text
Energy_Consumption = −HV Battery Current[A] × HV Battery Voltage[V] / 3.600.000
```

Es una identidad verificada en el archivo local. El diccionario §§6.5 y 9 documenta esa misma fórmula para EV/PHEV y la atribuye al notebook de eVED. Se comprobó el resultado, no se inspeccionó aquel notebook.

**Definición ahora documentada:** cada valor se calculó como energía en kWh durante **un segundo**, aunque los intervalos reales sean distintos. El diccionario indica ponderar `Energy_Consumption` por `Δt` en segundos dentro de cada `(VehId, Trip)` al integrar un viaje. **No sumar filas directamente.** Los tiempos son variables y existen huecos; la regla de integración no recupera por sí sola lo sucedido durante un hueco ni garantiza precisión física.

Corriente positiva es entrada de energía a la batería y negativa es descarga; el signo de energía se invierte. El diccionario asocia energía negativa a regeneración, sin que una fila negativa demuestre una sesión de recarga en una estación. Las señales vienen del auto; `Energy_Consumption` es un cálculo derivado de ellas. Se respeta así la indicación de Diego sobre medición a bordo, distinguiéndola de una predicción para un recorrido todavía no realizado.

La fórmula documentada coincide en **16.574.904 filas con energía e insumos completos** de las tres tablas, residuo máximo ≈1,25×10⁻¹⁶: 476.308 EV, 8.268.462 ICE y 7.830.134 PHEV/HEV. Energía faltante: 37,024% de ICE, 11,333% de PHEV/HEV y 0% de EV. Para ICE/HEV se comprobó la fórmula de combustible del diccionario, distinta de la eléctrica; no compararlas como magnitudes equivalentes sin justificarlo.

**Excepciones y límites preservados:** cinco filas PHEV mantienen energía cero con voltaje faltante. Esto contradice la generalización «si falta voltaje, falta energía» y es coherente con limpiar los cinco voltajes cero sin recalcular energía; no afecta a EV. El diccionario también menciona «el primer millón de filas» de EV, aunque solo existen 476.308: errata de alcance. Los valores originales no se corrigieron. Detalle en el perfil local.

La definición de la columna dejó de ser una pregunta para Daniel/CASE. Su aplicación a rutas nuevas, manejo de huecos y elección de modelo corresponden a Daniel/Lucas; el diccionario permite a los participantes escoger el tratamiento de faltantes. No se calcularon kWh/km, autonomía, capacidad útil o ahorro en esta revisión.

## Procedencia eVED: corroboraciones y discrepancias

[VED original](https://github.com/gsoh/VED) y el diccionario entregado, §2.2, declaran tres Nissan Leaf 2013 con capacidad comercial anunciada de 24 kWh. **No fijan la capacidad utilizable del ejercicio.** El catálogo local dice EV, Car, ELECTRIC, FWD y peso generalizado 3500; su unidad, ausente del encabezado, queda confirmada como libras por §6.4.

VED describe 383 vehículos/92 HEV; la entrega local tiene **384/93 HEV**, corroborados por el diccionario. Este describe la unión de tablas, conversión de tiempo, 101 filas duplicadas eliminadas y otras limpiezas; no imputa ni remuestrea a un intervalo fijo. Se conserva la discrepancia con las cifras de publicaciones originales. No se reconstruyó el procesamiento desde los 54 CSV semanales.

[eVED de los autores](https://github.com/zhangsl2013/eVED) describe una extensión con correspondencia vial y atributos enriquecidos, y remite al [paper](https://arxiv.org/abs/2203.08630). Repositorios leídos el 14-10. La transformación de esta edición ya está documentada; las condiciones de redistribución del conjunto entregado no se deducen de la licencia de uno de sus componentes.

## Qué preguntar y qué puede hacer la UI

**Pendientes específicos después del análisis:** capacidad utilizable que acepta el ejercicio; si se exige un mapeo concreto entre los dos autos y los tres IDs históricos; simplificación de recarga y comprobación energética del evaluador para rutas nuevas; función de `evaluation`; red vial y protocolo/formato de salida. No hay evaluador, comando, entorno, conectividad ni límites de ejecución en los ZIP. [Búsqueda en información organizativa](FUENTES.md).

Propuesta UI: mostrar archivo/instancia activa, origen de cada cifra, conectores y potencia nominal bien rotulados. Diferenciar resultado calculado, supuesto y dato faltante. Al cambiar de archivo, no reutilizar resultados porque coincidan los IDs.

Esta información prepara el contrato con Daniel y Lucas; no selecciona tecnología ni demuestra factibilidad.

## Recuperación del directorio después del pull, 14-10 noche de Chile

El directorio `AWS-Hackaton/data/` no estaba presente al comenzar esta sesión. Los originales seguían en `~/Downloads/Electromovilidad/`, `Electromovilidad.zip` y `Diccionario.zip`. Se restauraron copias locales de los seis CSV a `data/raw/`, los dos ZIP a `data/archive/` y los dos README del diccionario a `data/reference/diccionario-20261014/`. Se preservaron las fuentes y se comprobó SHA-256 de origen y copia de cada archivo. Los ZIP coinciden con los hashes históricos indicados arriba. Evidencia nueva: `AWS-Hackaton/data/manifest-restored-20261014.json` (ignorado por Git).

Esta recuperación verifica integridad de la copia; no repite ni sustituye el perfil histórico completo. Los informes históricos `data/analysis/` y el manifiesto anterior no se encontraron en el checkout recuperado. Sus resultados siguen documentados como evidencia histórica, no como mediciones repetidas hoy. El nuevo worktree `AWS-Hackaton-ui` usa escenarios sintéticos en prototipos y no necesita duplicar 5,21 GB de telemetría. No se publicaron los datos.
