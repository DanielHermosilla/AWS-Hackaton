# IA · Ideas C y D — Explicación de rutas y Contexto→parámetros

Autor: agente `ia_explicacion` · rama `exp/ia-explicacion` · región `us-east-1`, perfil `hackathon`.

Este informe cubre dos capacidades de IA **opcionales** sobre el motor E-VRP. Ambas
degradan con seguridad: si no hay credenciales/red o el LLM falla, el resultado se
produce igual sin IA. El motor nunca depende de estas piezas.

Toda cifra viene de un comando reproducible; los scripts están en
`experimentos/ia_explicacion/` y `experimentos/ia_contexto/`.

---

## C) Explicación de rutas (`src/evrp/ia/explicacion/`)

### Qué hace

`explicar(resultado, estilo='operador'|'gerencia', idioma='es', cliente=None)` convierte
un `evrp.Resultado` (o su dict) en una explicación en lenguaje natural para la jefa de
flota. **Requisito duro: cero cifras inventadas.** Para garantizarlo:

1. `extraer_hechos(resultado)` arma la única fuente de verdad: todos los números e IDs
   citables (KPIs, por vehículo, nodos de ruta).
2. El LLM recibe un resumen compacto (solo hechos citables) y redacta.
3. `verificar_texto` extrae **todos** los números e IDs del texto y comprueba que
   existan en los hechos, con tolerancia de redondeo (abs 0.05, rel 1 %, y casado por
   redondeo a los decimales citados).
4. Si falla, se **reintenta una vez** pasándole la lista exacta de errores.
5. Si vuelve a fallar, se devuelve la **plantilla determinista** (`explicar_plantilla`),
   que por construcción pasa el verificador.

La plantilla pura es además la **línea base** sin LLM.

Módulos: `hechos.py` (extracción + resumen), `verificador.py` (anti-alucinación),
`plantilla.py` (línea base/fallback), `explicador.py` (orquestador).

### Contrato JSON

```jsonc
explicar(resultado, estilo, idioma, cliente=None) -> {
  "texto": "string",                       // explicación; SIEMPRE pasa el verificador
  "hechos_citados": [                       // hechos efectivamente usados en el texto
    {"campo": "kpis.energia_total_kwh", "valor": 11.2203},
    {"campo": "rutas.1.nodo", "valor": "C9"}
  ],
  "advertencias": ["string"],               // p. ej. "LLM no superó verificación; plantilla"
  "uso": {
    "origen": "llm" | "plantilla",
    "intentos": 0,                           // 0 = sin LLM; 1 = al primer intento; 2 = con reintento
    "modelo": "us.anthropic.claude-...|null",
    "tokens_entrada": 0, "tokens_salida": 0, "tokens_total": 0,
    "latencia_s": 0.0,
    "verificado": true                       // invariante: siempre true en el texto devuelto
  }
}
```

Garantía invariante: **el `texto` devuelto siempre pasa el verificador** (lo prueban los
tests y la evaluación: fidelidad 1.0 en todos los escenarios y modelos).

### Evidencia

Escenarios reales generados con `evrp.resolver` (haversine): competición, evaluación,
2 sintéticas de 40 clientes (2 y 3 vehículos) y 2 casos de batería pequeña (uno con 4
clientes no atendidos). Dos estilos × 6 escenarios = 12 explicaciones por configuración.

Comando: `uv run python experimentos/ia_explicacion/evaluar.py [--llm <modelo>]`

| Configuración | Fidelidad | Cobertura media | Chars | Palabras | Latencia media | Tokens tot | % LLM |
|---|---|---|---|---|---|---|---|
| Plantilla (sin LLM) | **1.000** | 0.80 | 227 | 39 | 0.002 s | 0 | 0 % |
| Haiku 4.5 (LLM) | **1.000** | **0.98** | 942 | 157 | 3.84 s | 11 265 | 100 % |
| Sonnet 4.6 (LLM) | **1.000** | 0.95 | 1 023 | 176 | 5.94 s | 14 105 | 92 % (11/12) |

Rúbrica de cobertura (promedio de 5 ítems: menciona entregas, energía, recargas y por
qué, margen mínimo de batería, pendientes). La plantilla de `gerencia` baja a 0.6 **por
diseño** (resumen ejecutivo sin detalle de recargas/batería); el estilo `operador`
alcanza 1.0. El LLM sube la cobertura global a 0.95–0.98 cubriendo esos ítems también
en gerencia.

Detalle por escenario (Haiku 4.5), de `experimentos/ia_explicacion/evaluacion_haiku.json`:

| Escenario | Estilo | Origen | Intentos | Fiel | Chars | Lat (s) | Cob | No atend. |
|---|---|---|---|---|---|---|---|---|
| competition | operador | llm | 1 | ✓ | 660 | 3.67 | 1.00 | 0 |
| competition | gerencia | llm | 1 | ✓ | 895 | 3.64 | 1.00 | 0 |
| evaluation | operador | llm | 1 | ✓ | 860 | 3.00 | 1.00 | 0 |
| evaluation | gerencia | llm | 1 | ✓ | 835 | 3.09 | 1.00 | 0 |
| sintetica40_v2 | operador | llm | 1 | ✓ | 1123 | 4.04 | 1.00 | 0 |
| sintetica40_v2 | gerencia | llm | **2** | ✓ | 1044 | 7.33 | 1.00 | 0 |
| sintetica40_v3 | operador | llm | 1 | ✓ | 986 | 3.65 | 1.00 | 0 |
| sintetica40_v3 | gerencia | llm | 1 | ✓ | 1074 | 3.73 | 1.00 | 0 |
| no_atendidos_B1.0 | operador | llm | 1 | ✓ | 711 | 3.02 | 1.00 | **4** |
| no_atendidos_B1.0 | gerencia | llm | 1 | ✓ | 1120 | 4.06 | 1.00 | **4** |
| no_atendidos_B1.5 | operador | llm | 1 | ✓ | 1030 | 3.38 | 0.80 | 0 |
| no_atendidos_B1.5 | gerencia | llm | 1 | ✓ | 970 | 3.43 | 1.00 | 0 |

Observaciones medidas:
- El **reintento se activó en producción** (sintetica40_v2/gerencia, `intentos=2`) y el
  segundo intento pasó el verificador: el mecanismo de corrección funciona con datos reales.
- El caso `no_atendidos_B1.0` produjo 4 clientes sin atender (V2, V7, V9, V19) y la
  explicación los nombra correctamente sin inventar.
- En una corrida de Sonnet, 2 llamadas tuvieron error de conexión transitorio y
  **degradaron a la plantilla** sin romper la fidelidad (prueba de la degradación segura).

Fidelidad del verificador frente a invenciones (tests `test_ia_explicacion.py`): rechaza
números fuera de tolerancia (`999.9 kWh`) e IDs inexistentes (`V99`), y acepta citas
redondeadas (`11.22` por `11.2203`, `72 km` por `71.925`).

---

## D) Contexto→parámetros (`src/evrp/ia/contexto/`)

### Qué hace

Dos capas separadas, para que el LLM nunca invente números de física:

1. **Calibración (sin LLM, `calibracion.py`).** Desde `data/eVED_EV.csv` estima el
   consumo (kWh/km) por **banda de temperatura** (y por banda de velocidad), integrando
   energía con el Δt real (README §9.1) y agregando **por viaje** `(VehId, Trip)`.
2. **Ajuste (`ajustador.py`).** `ajustar(contexto_texto)` donde el LLM **solo extrae
   variables** de una **lista blanca** (temperatura °C, precipitación seco/lluvia/nieve,
   tráfico bajo/medio/alto, carga 0–1). El `consumo_factor` lo calcula **nuestra función
   calibrada** con rangos acotados (factor ∈ [0.7, 2.0]). Sin cliente, un extractor de
   reglas determinista reemplaza al LLM.

### Contrato JSON

```jsonc
ajustar(contexto_texto, calibracion=None, cliente=None) -> {
  "ajustes": {                              // claves que el motor acepta
    "consumo_factor": 1.69,                  // multiplicador sobre consumo_kwh_km
    "reserva_kwh": 1.5                       // opcional: colchón en frío/nieve
  },
  "justificacion": "Factor de consumo 1.69×. Temperatura <0 °C (×1.4). ...",
  "supuestos": ["Sin tráfico explícito: se asume bajo.", ...],
  "variables": {"temperatura_c": -5.0, "precipitacion": "nieve", ...},  // tras lista blanca
  "componentes": {"banda_temperatura": "<0", "factor_temperatura": 1.4, ...},
  "uso": {"origen": "llm"|"reglas", "modelo": "...|null",
          "tokens_entrada": 0, "tokens_salida": 0, "tokens_total": 0, "latencia_s": 0.0}
}
```

El LLM nunca escribe `consumo_factor`: aunque lo "sugiera", se descarta (probado en
`test_ajustar_llm_ignora_variables_fuera_de_lista_blanca`).

### Calibración por temperatura (datos reales)

Comando: `uv run python experimentos/ia_contexto/calibrar.py`
(salida en `experimentos/ia_contexto/calibracion_temp.json`). 379 viajes > 2 km.

| Banda (°C) | Viajes | km | Consumo kWh/km | p25–p75 | Factor vs 20–30 |
|---|---|---|---|---|---|
| < 0 | 53 | 303.6 | 0.2357 | 0.196–0.261 | **1.80** (tope) |
| 0–10 | 127 | 719.6 | 0.1631 | 0.133–0.186 | 1.28 |
| 10–20 | 77 | 424.7 | 0.1326 | 0.108–0.156 | 1.04 |
| 20–30 (ref) | 103 | 603.3 | 0.1274 | 0.101–0.146 | 1.00 |
| > 30 | 19 | 144.5 | 0.1395 | 0.107–0.158 | 1.10 |

Consumo global: 0.1559 kWh/km (coincide con el 0.156 de `base_conocimiento.md`). La
señal térmica es nítida: el frío severo casi **duplica** el consumo (calefacción). Por
velocidad: 20–40 km/h = 0.179, 40–60 = 0.146, >60 = 0.142 kWh/km (urbano consume más).

### Evaluación: error de consumo predicho vs eVED, por viaje

Validación **por fechas** (no por filas): fit con fechas < 2018-06-09 (237 viajes),
test con las restantes (142 viajes). Métrica: MAE/RMSE del consumo por viaje.

Comando: `uv run python experimentos/ia_contexto/evaluar.py`

| Método | MAE (kWh/km) | RMSE | Mejora MAE vs (i) |
|---|---|---|---|
| (i) sin ajuste (consumo global) | 0.0428 | 0.0514 | — |
| (ii) fórmula por temperatura (sin LLM) | **0.0310** | 0.0400 | **−27.6 %** |
| (iii) LLM + fórmula | 0.0308 | 0.0398 | −28.0 % |

La fórmula por temperatura reduce el error de predicción de consumo **~28 %** sobre un
holdout temporal. (iii) iguala a (ii): como estaba diseñado, el LLM solo aporta la
extracción de variables desde texto libre; el valor numérico lo pone la fórmula
calibrada. El beneficio del LLM es de **usabilidad** (entender "está nevando y hay
congestión") no de precisión adicional.

### Verificación en Bedrock real (ambos modelos)

`test_ia_contexto.py::test_ajustar_bedrock_real_extrae_variables` y
`test_ia_explicacion.py::test_explicar_bedrock_real_es_fiel` pasan con Haiku 4.5
(perfil `hackathon`). Comando:
`$env:AWS_PROFILE='hackathon'; uv run pytest -q -m bedrock tests/test_ia_explicacion.py tests/test_ia_contexto.py`
→ `2 passed, 26 deselected in 8.24s`.

---

## Pruebas

- Sin red (dobles): `uv run pytest -q -m "not bedrock" tests/test_ia_explicacion.py tests/test_ia_contexto.py`
  → **26 passed, 2 deselected**.
- Suite completa sin red: `uv run pytest -q -m "not bedrock"` → **81 passed, 3 deselected** (sin regresiones).
- Bedrock real (1 por idea): **2 passed**.

Consumo de tokens Bedrock de este agente (medido): evaluación C Haiku 11 265 + Sonnet
~14 105 + corrida parcial Sonnet ~9 851 + 2 tests reales ≈ **≤ 36 k tokens**, muy por
debajo del presupuesto de 150 k. No se imprimieron ni registraron credenciales.

---

## Valor para el usuario final (jefa de flota)

- **Explicación (C):** convierte el JSON del motor en un parte legible por estilo
  (operador: qué hace cada vehículo, dónde y por qué recarga, margen de batería,
  pendientes; gerencia: resumen ejecutivo). La **garantía de cero cifras inventadas** es
  lo que hace la herramienta usable sin desconfianza: cada número del texto existe en la
  solución verificada.
- **Contexto (D):** la jefa escribe "mañana nieva y hay −5 °C con tráfico" y el sistema
  ajusta el consumo esperado con un factor **respaldado por datos** (frío ≈ +40–80 %),
  sin que un modelo invente física. Mejora ~28 % la predicción de consumo frente a usar
  un valor fijo, lo que se traduce en planes más robustos (menos riesgo de quedarse sin
  batería en invierno).

## Valor para el jurado

- **Innovación/factibilidad:** verificador anti-alucinación con reintento y fallback
  determinista; separación estricta "LLM extrae / fórmula decide". Patrón reutilizable y
  defendible ante un jurado técnico.
- **Impacto medible:** fidelidad 1.0, cobertura 0.95–0.98, −28 % de error de consumo con
  validación temporal honesta.
- **Escalabilidad/robustez:** todo es opcional y degrada; el motor pasa sus 81 tests sin
  IA. Funciona en competición, evaluación y sintéticas de 40 clientes.

## Limitaciones

- La rúbrica de cobertura es heurística (búsqueda de términos); mide presencia, no
  calidad redaccional. La `gerencia` por plantilla puntúa bajo a propósito.
- La calibración por **velocidad** quedó informativa (no entra al factor) porque el
  contexto operativo rara vez trae velocidad media fiable; la señal térmica es la fuerte.
- Los recargos por lluvia/tráfico/carga son valores de ingeniería acotados (no
  calibrados con eVED, que no trae esas etiquetas por viaje). Solo la **temperatura**
  está calibrada contra datos.
- (iii) usa el extractor de reglas como proxy del LLM en la evaluación offline (para no
  gastar tokens en 142 viajes); el aporte del LLM real se verifica aparte con el test
  `@pytest.mark.bedrock`.
- Una llamada a Sonnet 4.6 tuvo error de conexión transitorio; degradó a plantilla. No
  es un fallo de la lógica sino de red.

## Cambios solicitados (a otros dueños de archivos)

Ninguno imprescindible. Dos **opcionales** para integrar estas piezas en el pipeline sin
romper la frontera de propiedad:

1. En `src/evrp/asesor.py` (dueño: IA base), el `AsesorBedrock.explicar` podría delegar
   en `evrp.ia.explicacion.explicar` para heredar la verificación anti-alucinación.
2. En `src/evrp/pipeline.py` / `config.py` (dueño: motor), aceptar `consumo_factor` y
   `reserva_kwh` provenientes de `evrp.ia.contexto.ajustar` como sobrescritura de
   `tipos_vehiculo` antes de construir la instancia (hoy ya se puede pasar a mano vía
   `config`; sería un atajo de UX).

No se editó ningún archivo fuera de mi worktree asignado.

## Próximos pasos

- Calibrar recargos de lluvia/tráfico/carga si aparecen datasets etiquetados.
- Añadir un modo "explicación comparativa" (por qué esta solución y no otra) usando la
  bitácora del solver.
- Exponer `ajustar` + `explicar` en el CLI (`evrp explicar`, `evrp contexto`).
- Internacionalización real de la plantilla (hoy el contrato acepta `idioma` pero la
  plantilla solo redacta en español; el LLM sí respeta el idioma).
