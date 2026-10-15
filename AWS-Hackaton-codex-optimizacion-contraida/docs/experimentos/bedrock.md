# Experimento: integración Amazon Bedrock (agente bedrock)

Rama `exp/bedrock`. Worktree `C:\Users\lucas\evrp-lab-wt\bedrock`. Región `us-east-1`,
perfil CLI `hackathon`. Todas las cifras provienen de ejecuciones reales (ver comandos).

## Qué hice

### Objetivo 1 — cliente central y migración del asesor
- Nuevo subpaquete `src/evrp/ia/` con `bedrock.py` → `ClienteBedrock`, única puerta a
  `bedrock-runtime` Converse:
  - `boto3.Session(profile_name=...)` configurable (o cadena estándar de AWS).
  - `botocore.Config` con `connect_timeout`/`read_timeout` y reintentos acotados
    (`mode="standard"`, `max_attempts` configurable).
  - `conversar(...)`: system prompt, mensajes multi-turno, `toolConfig` (tool use con
    `toolChoice` forzado), imágenes (`content` image bytes). Registra latencia extremo a
    extremo y tokens (`usage`) en `RespuestaConverse`.
  - Ayudas: `preguntar` (texto+imágenes), `preguntar_json` (extrae y valida JSON) y
    `usar_herramienta` (fuerza una tool y devuelve sus argumentos).
  - Errores normalizados: `ModeloNoDisponible` (AccessDenied/Validation/ResourceNotFound)
    vs `ErrorBedrock`. Las credenciales nunca se imprimen ni registran.
- `src/evrp/asesor.py`: `AsesorBedrock` migrado para usar `ClienteBedrock` (acepta
  `cliente=` inyectable para pruebas). Se mantiene la interfaz `Asesor`, el `AsesorNulo`
  por defecto, el filtro de lista blanca y la config `asesor.perfil_aws` / `asesor.modelo`.
- Pruebas `tests/test_bedrock.py`: 14 sin red (cliente falso `FakeConverse`: tokens/latencia,
  JSON, imagen como bytes, tool use forzado, errores de disponibilidad, asesor filtra/tolera
  fallos) + 1 `@pytest.mark.bedrock` real que hace ping y se salta si no hay credenciales.

### Objetivo 2 — benchmark de modelos Anthropic
- `experimentos/bedrock/png_texto.py`: generador de PNG **sin dependencias** (zlib + fuente
  bitmap 5×7) para la prueba de visión (PIL/matplotlib no están instalados; verificado).
- `experimentos/bedrock/benchmark.py`: para cada candidato (ids directos y perfiles
  `us.`/`global.`) ejecuta 4 tareas × 3 repeticiones: (a) ping, (b) JSON
  `{nombre,direccion,lat,lon}`, (c) tool use `resolver_rutas(agregar_cliente, quitar_cargador)`,
  (d) imagen (leer direcciones del PNG). Mide latencia p50/p95, tokens in/out, éxito y errores.
  Tope de ~60k tokens.

## Evidencia

### Tests
```
uv run pytest -q -m "not bedrock"
35 passed, 1 deselected in 52.20s        # 21 base + 14 nuevos
uv run pytest tests/test_bedrock.py -q -m "bedrock" -rs
1 passed, 14 deselected in 2.94s         # llamada real a Sonnet 4.6
```

### Benchmark (reps=3; `experimentos/bedrock/resultados.json`)
```
uv run python experimentos/bedrock/benchmark.py --perfil hackathon --reps 3
# 17541 tokens totales, 108.8 s  (muy por debajo del tope de 60k)
```

Disponibilidad y latencia (p50/p95 en s, promedio sobre las 4 tareas; éxito = 12/12 tareas):

| Modelo / perfil | Disp. | ping p50 | json p50 | tool p50 | imagen p50 | peor p95 | JSON | tool | imagen |
|---|---|---|---|---|---|---|---|---|---|
| us.anthropic.claude-haiku-4-5 | sí | 0.79 | 0.86 | 0.96 | 1.32 | 1.43 | ✅ | ✅ | ✅ |
| us.anthropic.claude-sonnet-4-6 | sí | 0.87 | 1.02 | 0.96 | 1.69 | 1.91 | ✅ | ✅ | ✅ |
| global.anthropic.claude-sonnet-4-6 | sí | 0.81 | 0.97 | 0.97 | 1.90 | 2.08 | ✅ | ✅ | ✅ |
| us.anthropic.claude-opus-4-5 | sí | 1.88 | 1.99 | 1.74 | 3.28 | 3.43 | ✅ | ✅ | ✅ |
| us.anthropic.claude-sonnet-4-5 | sí | 1.60 | 1.95 | 2.27 | 3.36 | 4.19 | ✅ | ✅ | ✅ |
| us.anthropic.claude-opus-4-1 | **no** | — | — | — | — | — | AccessDenied |||
| us.anthropic.claude-3-haiku | **no** | — | — | — | — | — | ResourceNotFound |||
| us.anthropic.claude-3-sonnet | **no** | — | — | — | — | — | ResourceNotFound |||

Observaciones:
- **5 modelos invocables**, los 5 con 100 % de éxito en JSON estricto, tool use e imagen.
  La fuente bitmap propia resultó legible para todos (prueba de visión superada).
- **Más rápidos:** Haiku 4.5 y Sonnet 4.6 (perfiles `us.`/`global.` casi idénticos; `us.`
  ligeramente mejor en p95 para Sonnet 4.6). Opus 4.5 y Sonnet 4.5 ~2–4× más lentos.
- **No disponibles:** Opus 4.1 (AccessDenied) y los Claude 3 (ResourceNotFound: sólo existen
  como perfil de inferencia pero no habilitados para esta cuenta vía Converse directo).
- Modelos Anthropic listados pero NO probados (fuera de alcance/tiempo, se asumen tras el
  presupuesto): Opus 5/5.5, Opus 4.6/4.7/4.8, Sonnet 5/5.5, Haiku 5.5, Fable 5/5.1. Todos
  requieren INFERENCE_PROFILE; se pueden añadir a `CANDIDATOS` si se amplía el presupuesto.

## Recomendación por uso
- **Asistente conversacional / explicación de rutas:** `us.anthropic.claude-sonnet-4-6`
  (autorizado, buen equilibrio calidad/latencia; es el default de `asesor.modelo`).
- **Ingesta / extracción estructurada (JSON) y tool use de alto volumen:**
  `us.anthropic.claude-haiku-4-5` — el más rápido con JSON y tool use perfectos.
- **Ajuste de configuración / razonamiento más exigente:** `us.anthropic.claude-opus-4-5`
  si se prioriza calidad sobre latencia (coste/latencia mayores).
- **Visión (leer etiquetas/tablas de pedidos):** cualquiera de los 5; Haiku 4.5 y Sonnet 4.6
  por latencia.

## Limitaciones
- Benchmark con N=3 repeticiones: las latencias p95 tienen alta varianza (p. ej. Sonnet 4.5
  ping p95=3.68 s por un único outlier). Sirven para ordenar, no como SLA.
- No se midió coste monetario (no autorizado estimar precios); sólo tokens.
- La prueba de imagen usa una fuente bitmap simple en mayúsculas; no evalúa OCR de fotos reales.
- No se probaron los modelos Anthropic más nuevos (5.x, 4.6+) por el enfoque en los
  autorizados y el presupuesto de tokens.

## Cambios solicitados (archivos fuera de mi rol — NO modificados)
- `pyproject.toml`: el extra `ia` ya incluye `boto3==1.40.0`; el cliente usa `botocore.Config`
  (viene con boto3). **No requiere cambios.** Si se quisiera un test de imagen con render
  real, habría que añadir `pillow==<versión>` a un grupo opcional (no imprescindible: el
  generador propio no tiene dependencias).
- `src/evrp/config.py`: sin cambios; `asesor.modelo` por defecto ya es
  `us.anthropic.claude-sonnet-4-6`. Sugerencia opcional (no aplicada): documentar
  `us.anthropic.claude-haiku-4-5-20251001-v1:0` como alternativa rápida para ingesta.

## Próximos pasos
- Añadir a `CANDIDATOS` los modelos Anthropic recientes (Sonnet/Opus/Haiku 5.x) con mayor
  presupuesto para comparar calidad en JSON/tool use.
- Exponer selección de modelo por tarea en el asesor (p. ej. Haiku para `sugerir_config`,
  Sonnet para `explicar`).
- Reintentos específicos ante `ThrottlingException` con backoff (hoy delegado a botocore).
