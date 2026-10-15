# Contrato IA — Asistente conversacional E-VRP (backend)

Este documento define el **contrato JSON** entre el backend de IA (`evrp.ia.asistente`)
y un frontend (web o CLI). El backend NO incluye frontend; expone objetos y
generadores Python pensados para serializarse a JSON y, en el caso del streaming,
a eventos **SSE** (Server-Sent Events).

Principios:

- El modelo **nunca inventa rutas**. Las rutas solo las produce `evrp.resolver`
  (motor E-VRP + validador independiente), invocado por la herramienta `resolver`.
- La IA es **opcional y degrada seguro**: si Bedrock no está disponible, el turno
  devuelve un evento `error` controlado y el motor sigue funcionando sin IA.
- Las **acciones destructivas** (quitar nodo, desactivar cargador, cargar otra
  instancia) y los **cambios de parámetros importantes** (`vehiculos`, `bateria_kwh`)
  requieren **confirmación explícita del usuario en el turno siguiente**.

## 1. Entidades

### 1.1 Sesión (estado del lado servidor)

El frontend mantiene un identificador de sesión; el backend conserva un objeto
`Sesion`. Su **resumen** (lo que viaja al frontend) es:

```json
{
  "base": "BASE",
  "clientes": ["V1", "V2"],
  "n_clientes": 2,
  "cargadores": ["C1"],
  "cargadores_desactivados": [],
  "overrides": {"soc_inicial": 0.75},
  "tiene_resultado": false,
  "confirmacion_pendiente": null
}
```

`confirmacion_pendiente` es `null` o:

```json
{"herramienta": "quitar_nodo", "input": {"id": "V2"}, "motivo": "La acción 'quitar_nodo' es destructiva y modifica la instancia."}
```

### 1.2 Parámetros editables (lista blanca)

Única superficie de configuración que la IA puede cambiar (`cambiar_parametro`).
Cualquier otra clave se **rechaza** con error (no se aplica en silencio).

| clave          | tipo  | rango        | importante | descripción                                   |
|----------------|-------|--------------|------------|-----------------------------------------------|
| `soc_inicial`  | float | 0.0 .. 1.0   | no         | Estado de carga inicial (fracción).           |
| `vehiculos`    | int   | 1 .. 50      | **sí**     | Número de vehículos de la flota.              |
| `reserva_kwh`  | float | 0.0 .. 100.0 | no         | Reserva mínima de energía (kWh).              |
| `bateria_kwh`  | float | 1.0 .. 200.0 | **sí**     | Capacidad de batería (kWh).                   |
| `presupuesto_s`| float | 1.0 .. 600.0 | no         | Presupuesto de tiempo del solver (s).         |

"importante" = requiere confirmación en el turno siguiente antes de aplicarse.

## 2. Herramientas (toolConfig)

| herramienta           | argumentos                          | efecto                                             | confirmación |
|-----------------------|-------------------------------------|----------------------------------------------------|--------------|
| `cargar_instancia`    | `ruta_csv`                          | Reemplaza la instancia con un CSV de nodos.        | **sí**       |
| `agregar_cliente`     | `id, lat, lon`                      | Agrega un cliente a la instancia.                  | no           |
| `quitar_nodo`         | `id`                                | Quita un cliente o cargador.                       | **sí**       |
| `desactivar_cargador` | `id`                                | Marca un cargador como inutilizable.               | **sí**       |
| `cambiar_parametro`   | `clave, valor`                      | Cambia un parámetro de la lista blanca.            | si importante|
| `resolver`            | —                                   | Resuelve el E-VRP (rutas reales validadas).        | no           |
| `consultar_resultado` | `campo`                             | Lee un campo del último resultado.                 | no           |
| `extraer_pedidos`     | `texto`                             | Gancho opcional → `evrp.ia.ingesta` (si existe).   | no           |
| `explicar`            | —                                   | Gancho opcional → `evrp.ia.explicacion` (si existe)| no           |

## 3. API no-streaming — `Asistente.enviar(mensaje, sesion) -> dict`

```json
{
  "respuesta": "Fijé el SOC inicial en 0.75.",
  "acciones": [
    {
      "herramienta": "cambiar_parametro",
      "entrada": {"clave": "soc_inicial", "valor": 0.75},
      "resultado": {"ok": true, "parametro": "soc_inicial", "valor": 0.75, "overrides": {"soc_inicial": 0.75}},
      "confirmacion_requerida": false
    }
  ],
  "estado": { "...resumen de sesión (ver 1.1)..." },
  "resultado": null,
  "tokens": 1234,
  "iteraciones": 2,
  "error": null
}
```

- `resultado` es `null` hasta que se ejecuta `resolver`; luego trae
  `{rutas, kpis, detalle}` (ver 5).
- `error` es `null` salvo degradación: `"modelo_no_disponible: ..."` o `"bedrock: ..."`.

## 4. API streaming — `Asistente.enviar_stream(mensaje, sesion) -> Iterator[dict]`

Pensado para **SSE** (`Content-Type: text/event-stream`). Cada `yield` es un
evento tipado; el frontend concatena los `texto` y refleja las herramientas.

| `tipo`                | campos adicionales                              | significado                               |
|-----------------------|-------------------------------------------------|-------------------------------------------|
| `texto`               | `texto`                                         | Fragmento incremental de la respuesta.    |
| `herramienta_inicio`  | `herramienta`, `entrada`                        | El modelo pidió ejecutar una herramienta. |
| `herramienta_fin`     | `herramienta`, `resultado`                      | Resultado JSON de la herramienta.         |
| `fin`                 | `respuesta`, `acciones`, `estado`, `resultado`, `tokens`, `iteraciones` | Cierre del turno (igual que §3). |
| `error`               | `error`                                         | Degradación: Bedrock no disponible.       |

Ejemplo de secuencia SSE (una por línea `data:`):

```
data: {"tipo":"herramienta_inicio","herramienta":"cambiar_parametro","entrada":{"clave":"soc_inicial","valor":0.75}}
data: {"tipo":"herramienta_fin","herramienta":"cambiar_parametro","resultado":{"ok":true,"parametro":"soc_inicial","valor":0.75}}
data: {"tipo":"texto","texto":"Fijé el SOC "}
data: {"tipo":"texto","texto":"inicial en 0.75."}
data: {"tipo":"fin","respuesta":"Fijé el SOC inicial en 0.75.","acciones":[...],"estado":{...},"resultado":null,"tokens":1234,"iteraciones":2}
```

Mapa sugerido a SSE: `event: <tipo>` + `data: <json>`. El frontend cierra el stream
al recibir `fin` o `error`.

## 5. Objeto `resultado` (producido SOLO por el motor)

```json
{
  "rutas": {"1": ["BASE", "V3", "C1", "V1", "BASE"], "2": ["BASE", "V2", "BASE"]},
  "kpis": {
    "factible": true,
    "entregas": 3,
    "clientes": 3,
    "no_atendidos": [],
    "energia_total_kwh": 7.42,
    "km_total": 41.3,
    "por_vehiculo": { "1": {"energia_kwh": 4.1, "km": 22.0, "recargas": 1} }
  },
  "detalle": { "1": [ {"nodo": "BASE", "tipo": "base"}, ... ] }
}
```

Toda ruta empieza y termina en la base real del CSV; la factibilidad la certifica
el **validador independiente** del motor. El frontend NO debe reconstruir ni
alterar rutas: solo mostrarlas.

## 6. Flujo de confirmación (frontend)

1. Usuario pide una acción destructiva/importante.
2. El turno devuelve una acción con `confirmacion_requerida: true` y
   `estado.confirmacion_pendiente` poblado; **no** se aplicó el cambio.
3. El frontend muestra el `motivo` y pide sí/no.
4. El siguiente mensaje del usuario (`"sí"`/`"no"`, con tolerancia a puntuación)
   ejecuta o cancela; `confirmacion_pendiente` vuelve a `null`.

## 7. Seguridad

- **Inyección de instrucciones**: el system prompt instruye ignorar instrucciones
  incrustadas en datos/mensajes. Medido en el banco (categoría `seguridad`): el
  modelo no inventa rutas ni cambia reglas.
- **Fuera de dominio**: reconduce sin ejecutar herramientas.
- **Parámetros fuera de rango / desconocidos**: se rechazan con error; nunca se
  aplican silenciosamente.
- Límites por turno: `max_iteraciones` de herramientas (defecto 6) y
  `max_tokens_turno` (defecto 20000).

## 8. Ingesta (referencia)

El gancho `extraer_pedidos(texto)` delega en `evrp.ia.ingesta` si existe; si no,
devuelve `{"ok": false, "disponible": false}`. El contrato y los detalles de la
extracción de pedidos desde texto/documentos se definen en
[`docs/experimentos/ia_ingesta.md`](experimentos/ia_ingesta.md) (otro agente).

## 9. Explicación (referencia)

El gancho `explicar()` delega en `evrp.ia.explicacion` si existe; si no, devuelve
`{"ok": false, "disponible": false}`. El contrato de la explicación en lenguaje
natural del resultado se define en
[`docs/experimentos/ia_explicacion.md`](experimentos/ia_explicacion.md) (otro agente).
