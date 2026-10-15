# Contrato de la API del backend de ruteo EV

**Versión:** 1.0 — estable. La UI (actual o futura) se integra contra este contrato.
El mismo contrato lo sirven: el servidor local (`backend.local_server`) y la
Lambda en AWS (`backend.lambda_handler`). Solo cambia la **URL base**.

## URL base

| Entorno | URL base |
|---|---|
| Local | `http://127.0.0.1:8000` |
| AWS (tras desplegar) | la que devuelva API Gateway, p. ej. `https://xxxx.execute-api.us-east-1.amazonaws.com` |

## Endpoints

### `GET /health`
Comprueba que el servicio responde.

**Respuesta 200:**
```json
{ "status": "ok", "api_version": "1.0" }
```

### `POST /solve`
Resuelve una instancia de ruteo.

**Cuerpo (JSON):**
```json
{
  "movement_limit": 6,
  "fleet": {
    "num_vehicles": 2,
    "battery_capacity_kwh": 24.0,
    "reserve_kwh": 2.4,
    "initial_soc": 0.6
  },
  "solver": {
    "time_limit_seconds": 120,
    "mip_gap": null
  },
  "nodes": [
    { "node_id": "BASE", "node_type": "base",    "latitude": 42.27, "longitude": -83.76 },
    { "node_id": "V1",   "node_type": "visit",   "latitude": 42.24, "longitude": -83.74 },
    { "node_id": "C1",   "node_type": "charger", "latitude": 42.30, "longitude": -83.69, "total_ports": 2 }
  ]
}
```

Campos:
- `nodes` (**obligatorio**): lista de nodos. Cada uno requiere `node_id`, `node_type`
  (`base` | `visit` | `charger`), `latitude`, `longitude`. Debe haber **exactamente un** `base`.
- `movement_limit` (opcional, def. 6): cota H de movimientos.
- `fleet` (opcional): parámetros de la flota (valores por defecto arriba).
- `solver` (opcional): `time_limit_seconds` (def. 120), `mip_gap`.
- `network` (opcional): si no se envía, el backend construye una red heurística
  por distancia (haversine). Para redes viales reales, enviar el objeto `network`.

**Respuesta 200:**
```json
{
  "api_version": "1.0",
  "result": {
    "served_count": 6,
    "unserved_visit_ids": ["V7", "V8"],
    "total_energy_kwh": 12.34,
    "validation": { "feasible": true, "violations": [] },
    "routes": [
      {
        "vehicle_index": 0,
        "served_visit_ids": ["V1", "V2"],
        "steps": [
          { "position": 0, "node_id": "BASE", "arrival_energy_kwh": 14.4, "charge_kwh": 0.0, "delivered_visit_ids": [] }
        ]
      }
    ],
    "phases": [ { "name": "...", "termination": "optimal" } ],
    "kpis": {}
  }
}
```

**Errores:**
- `400` — petición inválida (JSON mal formado o datos de nodos inválidos):
  `{ "error": "...", "detail": "..." }`
- `500` — error interno del solver.

## Notas de integración para la UI nueva

- Para dibujar el mapa: usa `latitude`/`longitude` de los nodos que enviaste y
  el orden de `steps[].node_id` por vehículo para trazar las rutas.
- Para KPIs: `result.served_count`, `result.total_energy_kwh`,
  `result.validation.feasible`.
- CORS está abierto (`*`), así que una web estática en otro dominio puede llamar
  la API sin configuración extra.
