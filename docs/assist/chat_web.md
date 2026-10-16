# Chat web del asistente

> Instruido por **Ateuluz**. Referencia para quien mantenga o integre el chat.

## Qué hace

Un chat en Inicio y Plan (botón **Asistente** en la barra de acciones) que reemplaza
el formulario para quien prefiere conversar:

- Un saludo abre la conversación; no pide datos.
- El único dato que se pide es el **archivo de nodos** (clip 📎), y solo al querer calcular.
  Si se pidió calcular sin datos, el pedido queda pendiente y se ejecuta al adjuntar.
- Lo no mencionado usa el **estándar del escenario** (`tools.PARAMETROS[*].estandar`):
  2 Nissan Leaf 2013 al 60 %, 24 kWh, reserva 2 kWh, 0,18 kWh/km, calles del servidor,
  10 s, búsqueda GPT. Se cambia hablando ("que sean 3 autos", "al 70 %", "sin GPT").
- El chat arma `/prepare` + `/solve`, publica el resultado en el `RunStore` y la página
  Plan lo abre por `run_id`. El historial del chat sobrevive a la recarga.
- Con un plan ya en pantalla, recalcula sin re-adjuntar: recupera nodos y supuestos de
  la preparación original (contexto vial del servidor, incluidos `scenario` y
  `energy_profile_id`) o los reconstruye del resultado.

## Piezas

| Archivo | Rol |
|---|---|
| `webapp/assist-panel.js`, `.css` | Cliente delgado: mensajes, clip, abrir el plan |
| `backend/assist_service.py` | Sesiones, fuentes de datos, resolutor `/prepare`+`/solve` |
| `backend/local_server.py` | `POST /assist/chat`, `GET /assist/schema` |
| `src/ev_routing/assist/` | Sesión, asistente (tool use), intérprete local, lista blanca |

## Reglas de seguridad y compatibilidad

> Instruido por **Ateuluz**.

1. Las rutas solo salen del motor (`Sesion.resolver` → `/prepare` + `/solve`). El LLM
   nunca escribe resultados; cada cambio pasa por `validar_parametro`.
2. `/assist/chat` **no** toma el candado global del servidor: lo toma el resolutor solo
   mientras calcula (sin bloquear). Si se mueve el chat detrás del candado de `do_POST`,
   todo cálculo desde el chat responderá "cálculo en curso".
3. El chat usa la conexión Bedrock del servidor (`runtime.bedrock`, la misma de
   `/bedrock/session`), con su modelo y región. Se apoya en `BedrockSession._client` y
   `_epoch` (API interna): si cambian, ajustar `_cliente_bedrock`.
4. Sin Bedrock (o si falla), un intérprete local determinista responde y la UI marca
   "respuesta sin IA". El chat nunca rompe el flujo del motor.
5. Igual que el resto del servidor beta: solo local (mismo origen), sin autenticación.
   No exponer en red sin agregar acceso controlado.

## Verificación

- `pytest tests/test_assist.py tests/test_assist_backend.py` (29 tests; los `solver`
  corren el motor real con red geodésica o instancia nativa).
- E2E por HTTP sobre `local_server`: saludo → adjuntar instancia → "calcula con 1 auto
  sin gpt" → plan publicado y recuperable por `GET /solve?run_id=…`. Verificado en modo
  local y con Bedrock real (`us.openai.gpt-5.6-luna`, tool use).

## Pendiente / ideas

- Casos precargados con nombre amigable en `tools.CASOS`: «corre el caso CASE» (dataset competition) o «CASE-evaluacion» (evaluation); los nombres internos y la herramienta `usar_caso_hackaton` siguen aceptándose por compatibilidad.
- Explicación por ruta (eje C) junto al mapa, no solo en el chat.
