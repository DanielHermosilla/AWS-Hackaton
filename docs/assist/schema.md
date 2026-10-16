# Contrato `GET /assist/schema` — fin de los números mágicos del frontend

> Instruido por **Ateuluz** — fuente de verdad única de parámetros.

## Objetivo

Que el frontend NO cablee `min`/`max`/`value` de los controles de configuración.
En su lugar, pide este esquema al backend al cargar y rellena los inputs de
forma dinámica. Si un rango cambia en el solver/`assist`, la UI se actualiza
sola, sin tocar JS.

## Origen de los datos

`ev_routing.assist.tools.parametros_schema()` serializa la lista blanca
(`PARAMETROS`) — ya implementado y testeado (`tests/test_assist.py`). Es la única
fuente de verdad de tipos y rangos editables por IA/usuario.

## Forma de la respuesta

```json
{
  "schema_version": "1.0",
  "parametros": {
    "vehiculos": {
      "tipo": "int", "min": 1, "max": 20,
      "seccion": "instancia", "destino": "vehicle_count",
      "importante": true,
      "descripcion": "Numero de vehiculos de la flota (1..20)."
    },
    "tiempo_limite_s": {
      "tipo": "float", "min": 1.0, "max": 600.0,
      "seccion": "solver", "destino": "time_limit_seconds",
      "importante": false,
      "descripcion": "Presupuesto de tiempo del solver en segundos."
    }
    // ... soc_inicial, reserva_final_soc, margen_energia, gap_energia, max_ruta_s
  }
}
```

- `importante: true` → la UI debe pedir confirmación antes de aplicar (igual que
  hace el asistente en el chat).
- `destino` y `seccion` indican a qué contrato del núcleo pertenece el campo;
  el frontend normalmente no los necesita, pero sirven para trazabilidad.

## Cómo lo serviría el backend (pendiente de implementar)

En `backend/service.py`, una ruta nueva:

```python
from ev_routing.assist.tools import parametros_schema

def handle_assist_schema():
    return json_response(200, parametros_schema())
```

Registrarla como `GET /assist/schema`, mismo origen que el resto de la API.
No requiere boto3 ni Bedrock: es estático, solo lee la lista blanca.

## Cómo lo consumiría el frontend (pendiente de implementar)

En `webapp/run-panel.js`, al construir el formulario, reemplazar los literales
por valores del esquema:

```js
const schema = await fetch('/assist/schema').then(r => r.json());
const v = schema.parametros.vehiculos;
runCount.min = v.min; runCount.max = v.max;   // en vez de max="20" fijo
```

Mapa control → clave del esquema:

| Control (`run-panel.js`) | Clave de `parametros` |
|---|---|
| `#run-count` | `vehiculos` |
| `#run-seconds` | `tiempo_limite_s` |
| `#run-soc` | `soc_inicial` (fracción; la UI muestra %) |
| tolerancia energética | `gap_energia` |

## Compatibilidad

> Instruido por **Ateuluz**.

- `schema_version` permite evolucionar el contrato sin romper clientes viejos.
- No elimina claves existentes sin subir la versión.
- El backend puede fusionar los defaults del solver (`SolverConfig()`,
  `Operations()`) en el `value` inicial de cada control; los rangos siempre
  vienen de este esquema.
