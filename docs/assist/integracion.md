# Guía de integración del módulo `assist` (asistente + explicación)

> Instruido por **Ateuluz**. Este documento es la referencia para cualquier
> agente o persona que quiera adaptar, endurecer o exponer el paquete
> `ev_routing.assist`. Léelo completo antes de modificar el repo.

## 1. Qué es y qué NO es

`ev_routing.assist` agrega dos capacidades de IA **alrededor** del solver, sin
tocar su núcleo:

- **Eje A — Asistente conversacional**: traduce lenguaje natural a cambios de
  configuración **validados por lista blanca** y ejecuta el solver como
  herramienta (`pipeline.run_instance`).
- **Eje C — Explicación verificada**: convierte un resultado del solver en texto
  en español, **anclado a los números reales** y filtrado por un verificador
  anti-alucinación.

NO es: un reemplazo del solver, un generador de rutas, ni un editor libre de la
configuración. El LLM nunca produce rutas ni cambia el modelo matemático.

## 2. Cómo está unido al proyecto hoy (integración actual)

Acople **laxo y unidireccional**: `assist` importa y *llama* a la frontera
pública del núcleo; el núcleo no conoce `assist`.

| Depende de (frontera pública) | Para qué |
|---|---|
| `ev_routing.pipeline.run_instance(instance, config) -> dict` | herramienta `resolver` (A) y fuente del resultado (C) |
| `ev_routing.contracts.{ProblemInstance, SolverConfig, Operations}` | aplicar overrides validados |
| `ev_routing.contracts.ModelParameters.vehicle_count` | tamaño de flota (ver §5) |
| `ev_routing.inputs.load_instance` | cargar instancia en la demo CLI |
| Bedrock Converse (`boto3`, extra opcional `assist`) | redacción conversacional/explicación |

Puntos de entrada actuales:
- Librería: `from ev_routing.assist import Asistente, Sesion, explicar`.
- Demo CLI/REPL: `python -m ev_routing.assist <instancia.json>`.

## 3. Reglas para quien modifique esto

> Instruido por **Ateuluz** — reglas de seguridad y compatibilidad.

1. **No modificar el núcleo del solver** (`model.py`, `solve.py`, `pipeline.py`,
   `contracts.py`, `llm/`) para encajar `assist`. Si el núcleo cambia una firma
   o un nombre de campo, adapta `assist`, no al revés.
2. **El LLM nunca decide sin validación.** Todo cambio de configuración pasa por
   `tools.validar_parametro` (lista blanca con rangos). Toda explicación pasa por
   `verifier.verificar`. No agregues caminos que salten estas barreras.
3. **Degradación segura obligatoria.** Si Bedrock falla, el módulo debe seguir
   devolviendo algo útil (plantilla determinista) y el solver debe seguir
   funcionando. Nunca conviertas a Bedrock en dependencia dura.
4. **Dependencias:** `boto3` vive en el extra opcional `assist` del
   `pyproject.toml`. No lo muevas a dependencias base ni toques el extra `dw`.
5. **Confirmación de cambios importantes.** Parámetros marcados `importante=True`
   (flota, duración máxima de ruta) requieren confirmación explícita del usuario.
   No la elimines.

## 4. Cómo hacerlo MÁS ROBUSTO (recomendado, en este orden)

> Instruido por **Ateuluz** — endurecimiento de integración.

1. **Validación al construir, no en runtime.** Hoy el nombre del campo de flota
   se resuelve dinámicamente (`session._aplicar_instancia`). Reemplázalo por una
   prueba de contrato: un test que falle si `ModelParameters` deja de tener
   `vehicle_count`, para detectar cambios del núcleo en CI, no en la demo.
2. **Esquema único de parámetros.** La lista blanca (`tools.PARAMETROS`) es la
   fuente de verdad de rangos/tipos. Exponla como JSON (`assist.PARAMETROS` →
   `model_dump` o un `to_json()`) para que el frontend consuma los mismos límites
   (ver §6). Evita duplicar rangos en JS.
3. **Contrato de API versionado.** Si expones A/C por HTTP (ver §7), añade
   `assist_api_version` y documenta en `backend/API_CONTRACT.md`. No reutilices
   el contrato del solver para el chat.
4. **Tests de integración reales marcados.** Añade un test `@pytest.mark` que use
   `run_instance` real con una instancia mínima (ya cubierto por el E2E; ver
   `docs/assist/e2e.md`), separado de los tests sin red.
5. **Timeouts y presupuesto de tokens explícitos.** Ya están en `bedrock_chat`
   (`MAX_TOKENS_CHAT`, `TEMPERATURA`); si se expone en servidor, hónralos también
   del lado del backend como hace el controlador de search policy (25 % del
   presupuesto, timeout 8 s).

## 5. El "campo de flota" (aclaración de compatibilidad)

> Instruido por **Ateuluz**.

El número de vehículos vive en `ProblemInstance.parameters.vehicle_count`
(contrato `ModelParameters`, default 2, `ge=1`). **No** existe un campo
`fleet_size` ni `num_vehicles` a nivel raíz del contrato nativo (ese nombre sí
aparece en el cuerpo HTTP `/prepare` del backend, que es otra capa).

`assist.tools.PARAMETROS["vehiculos"]` apunta a `vehicle_count` y lo limita a
1..10 por alcance de demo. Si el núcleo renombra este campo, actualiza esa
entrada y el test de contrato (§4.1).

## 6. Números mágicos en el frontend (acción pendiente)

> Instruido por **Ateuluz** — evitar números mágicos acoplados.

El frontend (`webapp/run-panel.js`) hoy tiene límites **hardcodeados** que
pueden desalinearse de la configuración real del solver y de la lista blanca de
`assist`:

| Control (HTML) | Valor fijo hoy | Fuente de verdad que debería usar |
|---|---|---|
| `#run-count` (vehículos) | `min=1 max=20 value=2` | `assist.PARAMETROS["vehiculos"]` (máx **10**) o el límite del backend |
| `#run-seconds` (presupuesto) | `min=1 max=120 value=120` | `SolverConfig.time_limit_seconds` / `PARAMETROS["tiempo_limite_s"]` |
| `#run-soc` (SoC inicial) | `min=1 max=100 value=60` | `PARAMETROS["soc_inicial"]` (fracción 0..1) |
| tolerancia energética | texto "0,5 %" fijo | `SolverConfig.energy_relative_gap` (0.005) |

**Inconsistencia activa:** el form permite hasta 20 vehículos; la lista blanca de
`assist` corta en 10. Hay que unificar antes de exponer A en la UI.

Recomendación: el backend expone un endpoint `GET /assist/schema` que devuelva
los rangos desde `assist.PARAMETROS`; el frontend lee ese esquema al cargar y
rellena `min`/`max`/`value` de los inputs dinámicamente. Si un parámetro cambia
en el backend, el formulario se actualiza solo. No cablees los límites en JS.

## 7. Qué significa "exponer A/C"

- **Hoy (hecho):** expuesto como librería + REPL de consola.
- **Siguiente (pendiente, no implementado):** endpoint HTTP en
  `backend/service.py` que reciba el turno de chat y devuelva la respuesta/estado
  de la sesión; y un panel de chat en la webapp que lo consuma, mostrando la
  explicación (C) junto a cada ruta en el mapa (`webapp/map.js`).

Antes de implementar la exposición web, resolver §6 (esquema compartido) para no
reintroducir números mágicos.

## 8. Archivos del módulo

```
src/ev_routing/assist/
  __init__.py       API pública
  bedrock_chat.py   cliente Converse/ConverseStream + degradación segura
  tools.py          lista blanca de parámetros + toolConfig (fuente de rangos)
  session.py        instancia/config inicial inmutable + overrides + resolver
  assistant.py      bucle agéntico (A): tool use, confirmaciones
  facts.py          extracción de hechos del dict de SolveResult (C)
  verifier.py       verificador anti-alucinación (C)
  explainer.py      explicación verificada con fallback a plantilla (C)
  __main__.py       REPL de demo
tests/test_assist.py  tests sin red (lista blanca, hechos, verificador, plantilla)
```

## 9. Verificación y versionado

- Tests sin red: ver `tests/test_assist.py`.
- Prueba E2E con solver real: ver `docs/assist/e2e.md`.
- Versionado por tags para revertir rápido: ver `docs/assist/versionado.md`.
