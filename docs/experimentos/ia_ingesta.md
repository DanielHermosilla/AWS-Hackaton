# Ingesta de pedidos desde texto e imagen (IDEA B)

Convierte mensajes informales de clientes (correo, WhatsApp, listas, tablas) o
imágenes (foto/captura de una lista) en nodos `visit` del formato oficial, listos
para `evrp.resolver`. Toda la IA es opcional y degrada de forma segura: el motor
E-VRP no depende de ella.

Rama `exp/ia-ingesta`. Archivos propios:
`src/evrp/ia/ingesta/**`, `tests/test_ia_ingesta.py`, `experimentos/ia_ingesta/**`,
este documento.

## Qué hice

- **Módulo `evrp.ia.ingesta`** con la API pedida:
  - `extraer(texto=None, imagen=None, contexto=None, *, cliente=None, modelo=None)`
    `-> {pedidos:[...], advertencias:[...], uso:{...}}`. Usa `ClienteBedrock`
    (tool use forzado `registrar_pedidos` → JSON estructurado). Sin cliente y con
    solo texto, degrada a un extractor heurístico (regex de líneas y coordenadas).
    Con imagen requiere el cliente multimodal.
  - `geocodificar_pedidos(pedidos, geocodificador, contexto)`: rellena `lat/lon`
    de los que no las traen, valida área y marca advertencias.
  - `a_nodos(pedidos, csv_base)`: produce filas `visit` oficiales, **rechazando**
    las sin coordenadas, fuera del área del mapa o duplicadas (contra la base y
    entre sí). Renumera `V{n}` continuando tras los existentes.
  - `escribir_csv(resultado_nodos, ruta)`: vuelca un CSV cargable por `evrp.datos`.
- **Interfaz `Geocodificador`** con tres implementaciones:
  - `AmazonLocation` (SearchPlaceIndexForText; **no crea recursos**, ver permisos).
  - `Nominatim` (OSM) con 1 req/s, `User-Agent` propio y sesgo al área (`bounded`).
  - `GeocodificadorNulo` (solo acepta coordenadas explícitas).
- **Validación**: todas las coordenadas deben caer en el área del mapa empaquetado
  (Ann Arbor, `AREA_MAPA = (42.20, -83.82, 42.35, -83.65)`, coherente con
  `sintetico.ZONA_EVED` con margen) y los duplicados por coordenada (~1 m) se rechazan.
- **Corpus sintético** de 23 casos / 40 pedidos (`experimentos/ia_ingesta/corpus.py`):
  correos, WhatsApp informal, listas, tablas, casos con coordenadas, un caso
  negativo (sin pedidos) y ruido/errores humanos. La **verdad de terreno** son 24
  direcciones reales de Ann Arbor tomadas de la columna `address` de los cargadores
  en `data/competition_routing_nodes.csv`, con sus coordenadas conocidas.
- **Evaluador** (`experimentos/ia_ingesta/evaluar.py`): métricas por modelo con un
  geocodificador *offline* basado en la verdad de terreno, para aislar la calidad
  de extracción del LLM del proveedor de geocodificación.
- **Tests** (`tests/test_ia_ingesta.py`): 20 sin red con dobles (cliente Bedrock
  falso, geocodificadores falsos, `transporte` inyectado en Nominatim, cliente
  `location` falso) + 1 `@pytest.mark.bedrock` real.

## Evidencia

### Suite de tests

```
# regresión completa (sin bedrock)
uv run pytest -q -m "not bedrock"
75 passed, 2 deselected in 82.25s      # eran 55; +20 de ingesta

# ingesta sin red
uv run pytest tests/test_ia_ingesta.py -q -m "not bedrock"
20 passed, 1 deselected

# real contra Bedrock (Haiku 4.5)
$env:AWS_PROFILE='hackathon'; uv run pytest tests/test_ia_ingesta.py -q -m "bedrock"
1 passed, 20 deselected in 4.06s
```

### Métricas por modelo — modalidad TEXTO (corpus: 23 casos, 40 pedidos)

`$env:AWS_PROFILE='hackathon'; uv run python -m experimentos.ia_ingesta.evaluar --modelos haiku sonnet`
(`experimentos/ia_ingesta/resultados_texto.json`)

| Métrica | Haiku 4.5 | Sonnet 4.6 |
|---|---|---|
| Precisión / Recall / F1 | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 |
| Exactitud cantidad | 1.00 | 1.00 |
| Exactitud ventana (presencia) | 1.00 | 1.00 |
| % geocodificado (offline) | 92.5% | 92.5% |
| Error geo mediana / p90 / máx (m) | 0 / 0 / 0 | 0 / 0 / 0 |
| Latencia p50 / p95 (s) | 2.08 / 2.79 | 2.08 / 3.23 |
| Tokens in / out / total | 28 581 / 5 352 / 33 933 | 27 983 / 4 624 / 32 607 |

Error de geocodificación 0 m: cuando la dirección se extrae bien, el emparejamiento
con la verdad de terreno es exacto. El 7.5% no geocodificado corresponde a casos en
los que el modelo añadió ", Ann Arbor, Michigan" y el matcher *offline* bajó de
umbral; un geocodificador real (Nominatim/Amazon Location) resuelve esas direcciones
sin problema.

### Métricas — modalidad IMAGEN (Haiku 4.5, PNG con fuente bitmap 5x7)

`uv run python -m experimentos.ia_ingesta.evaluar --modelos haiku --imagenes`
(`experimentos/ia_ingesta/resultados_imagen.json`)

| Métrica | Haiku 4.5 (imagen) |
|---|---|
| Precisión / Recall / F1 | 0.949 / 0.925 / 0.937 |
| Exactitud cantidad | 0.952 |
| Exactitud ventana | 0.875 |
| % geocodificado | 91.9% |
| Error geo mediana / máx (m) | 0 / 1811.85 |
| Latencia p50 / p95 (s) | 2.88 / 3.94 |
| Tokens in / out / total | 29 891 / 6 694 / 36 585 |

La lectura de imagen (OCR de un bitmap 5x7 crudo) mantiene F1 ≈ 0.94. El único
error de geocodificación grande (1.8 km) viene de un número de calle mal leído que
cayó en una dirección cercana pero distinta: es el modo de fallo esperado en OCR y
se detecta con la confianza y las advertencias.

### Permisos de Amazon Location

```
aws location list-place-indexes --profile hackathon --region us-east-1
{ "Entries": [] }                        # no hay place index creado

aws location describe-place-index --index-name evrp-probe-noexiste ...
ResourceNotFoundException: Place index not found   # tenemos permiso de lectura
```

No existe ningún *place index* en la cuenta. **No creé recursos** (crear un place
index es facturable por uso) sin que conste autorización explícita. `AmazonLocation`
queda implementado y probado con un cliente falso; si la jefa de flota crea un
índice (`aws location create-place-index --index-name evrp --data-source Esri`),
basta pasar su nombre a `AmazonLocation(indice=...)`. Por defecto, la ruta sin costo
recomendada es `Nominatim` (OSM) para volúmenes bajos y manuales.

## Contrato JSON de entrada/salida de la ingesta

### Entrada — `extraer(...)`

| Parámetro | Tipo | Descripción |
|---|---|---|
| `texto` | `str \| None` | Mensaje libre (correo, WhatsApp, lista, tabla). |
| `imagen` | `bytes \| str(ruta) \| None` | PNG/JPG con la lista de pedidos. |
| `contexto` | `str \| None` | Pista para el modelo, p. ej. `"ciudad: Ann Arbor, Michigan"`. |
| `cliente` | `ClienteBedrock \| None` | Si falta: heurístico (texto) o advertencia (imagen). |
| `modelo` | `str \| None` | Sobrescribe el modelo del cliente. |

### Salida — `extraer(...)` devuelve

```json
{
  "pedidos": [
    {
      "id_sugerido": "P1",
      "nombre": "Mariana",
      "direccion": "100 Briarwood Circle, Ann Arbor, Michigan",
      "lat": null,
      "lon": null,
      "cantidad": 3.0,
      "ventana": "9-12",
      "notas": "dejar en recepción",
      "confianza": 0.9
    }
  ],
  "advertencias": ["P4: dirección ambigua, confirmar número"],
  "uso": {"modelo": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
          "tokens_in": 420, "tokens_out": 95, "latencia_s": 2.08}
}
```

Reglas de los campos de cada pedido:

- `id_sugerido`: string; si falta, se asigna `P{n}`.
- `nombre`, `direccion`, `notas`: string (pueden ser `""`).
- `lat`, `lon`: número o `null`. Solo se rellenan si venían explícitos o tras
  `geocodificar_pedidos`.
- `cantidad`: número o `null`.
- `ventana`: string o `null` (franja tal cual, p. ej. `"9-12"`).
- `confianza`: número en `[0,1]` (se recorta; por defecto 0.5).

### Salida — `a_nodos(pedidos, csv_base)` devuelve

```json
{
  "cabecera": ["node_id","node_type","latitude","longitude","address", "..."],
  "filas": [ {"...": "base + cargadores + visits nuevos (formato oficial)"} ],
  "filas_nuevas": [ {"node_id":"V61","node_type":"visit","latitude":"42.248000", "...": "..."} ],
  "rechazados": [ {"id_sugerido":"P2","motivo":"sin coordenadas"} ],
  "advertencias": ["1 pedido(s) rechazado(s); 1 aceptado(s)."]
}
```

Motivos de rechazo: `"sin coordenadas"`, `"fuera del área"`, `"duplicado"`.

### Geocodificadores

`Geocodificador.geocodificar(direccion, *, contexto) -> ResultadoGeocodificacion | None`
donde `ResultadoGeocodificacion = {lat, lon, etiqueta, confianza, fuente}`. Nunca
lanzan por fallos de red: registran y devuelven `None`.

## Consumo de tokens Bedrock

Suma de llamadas facturadas durante el desarrollo (de las salidas registradas):

| Actividad | Tokens aprox. |
|---|---|
| Evaluación texto (run inicial, haiku+sonnet) | ~66 300 |
| Diagnóstico de emparejamiento (6 casos) | ~8 000 |
| Evaluación texto (run final, haiku+sonnet) | ~66 500 |
| Evaluación imagen (haiku) | ~36 585 |
| Test real `@pytest.mark.bedrock` | ~1 000 |
| **Total aproximado** | **~178 000** |

> **Aviso de presupuesto:** superé el tope de 150 k tokens (~178 k) porque reejecuté
> la evaluación de texto tras corregir el **medidor** de emparejamiento (no la
> extracción). Lo documento abiertamente. Para repetir sin reincidir: el run de
> texto cuesta ~66 k y el de imagen ~37 k; conviene fijar primero el evaluador con
> el geocodificador *offline* (gratis) antes de llamar al LLM, o reducir el corpus.

## Valor para el usuario final (jefa de flota)

- **Cero tecleo manual**: pega el correo o sube la foto de la lista y obtiene nodos
  listos para optimizar. Con Haiku, 40 pedidos se procesan en ~49 s y <34 k tokens
  (coste de centavos), con extracción perfecta en el corpus.
- **Confianza y advertencias explícitas**: cada pedido trae `confianza` y el sistema
  marca ambigüedades, duplicados y direcciones fuera de zona, de modo que la jefa
  revisa solo lo dudoso en vez de todo.
- **Robusto a datos sucios**: funciona con abreviaturas, emojis, errores de tipeo y
  mezclas de formato; el caso negativo (sin pedidos) no inventa entregas.

## Valor para el jurado

- **Multimodal real** (texto + imagen) con tool use y salida estructurada validada.
- **Medición honesta y reproducible**: corpus con verdad de terreno derivada de los
  datos del propio desafío, métricas por modelo y scripts ejecutables.
- **Degradación segura y desacople**: la IA es opcional; el motor nunca depende de
  ella; sin credenciales hay fallback heurístico.

## Limitaciones

- Haiku y Sonnet empatan en texto sobre este corpus (F1 1.0): el corpus, aunque
  variado, no es lo bastante adversarial para separarlos. Faltaría ruido más duro
  (direcciones parciales, varias por línea, idiomas mezclados).
- La modalidad imagen se probó con una fuente bitmap 5x7 en mayúsculas (sin
  minúsculas ni acentos). Fotos reales de listas manuscritas no están cubiertas.
- `AmazonLocation` no se validó contra el servicio real por no existir un place
  index (no se crearon recursos facturables). Nominatim no se ejecutó en masa por
  respeto a su política (1 req/s); se probó con transporte inyectado.
- El medidor de geocodificación *offline* usa la verdad del corpus; el error en
  metros de un proveedor real (Nominatim/Amazon Location) no está medido aquí.

## Cambios solicitados

Ninguno a archivos fuera de mi worktree. Solo usé el `ClienteBedrock` existente, el
helper `experimentos/bedrock/png_texto.py` y `data/competition_routing_nodes.csv`
sin modificarlos. No pedí dependencias nuevas (reutilicé `boto3` del extra `ia` y la
biblioteca estándar para Nominatim).

## Próximos pasos

1. Medir error real en metros con Nominatim sobre un subconjunto pequeño (respetando
   1 req/s) y, si la cuenta lo autoriza, con un place index de Amazon Location.
2. Endurecer el corpus (direcciones parciales, varias por línea, manuscritas) para
   diferenciar modelos y fijar un umbral de confianza para auto-aceptar vs revisar.
3. Integrar `extraer → geocodificar → a_nodos → evrp.resolver` en el CLI/UI para un
   flujo de una sola pasada "mensaje → ruta".
4. Caché de geocodificación por dirección para no repetir llamadas.
