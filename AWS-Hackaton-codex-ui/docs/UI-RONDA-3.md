# Mapa de flota — refinamiento elegido por Diego

**Elección posterior de Diego, 15-10-2026:** implementar estética de Cristal con tamaños de botones y distribución de Esencial. Esta comparativa se conserva como referencia histórica; la base elegida y el encargo de dashboard están en [WEBAPP-HANDOFF.md](WEBAPP-HANDOFF.md).

15-10-2026, America/Santiago. Fuente de decisiones: mensaje de Diego en este chat.

**Dirección confirmada:** opción 1 de la ronda 2, Mapa de flota. Conservarla exactamente. Comparar cuatro variantes totales: original, Batería integrada, Cristal y Esencial. Las otras tres direcciones anteriores se conservan como historial descartado.

**Límite confirmado:** no incorporar variables nuevas antes de las respuestas pendientes del equipo. Se presentan los mismos datos de ejemplo. Daniel y Lucas siguen a cargo del motor; no se eligió la variante final ni se cambió la arquitectura prevista por Daniel.

Comparador: `explorations/round-3/index.html`, servido en `/round-3/`. Alcance, reconstrucción del ejemplo, fuentes, dependencias y criterio de diseño en el [README de la ronda](../explorations/round-3/README.md).

## Autoría y evidencia

- Astra coordina la ronda y construye Esencial, el comparador, Motion y la integración.
- Los agentes de Codex construyen Batería integrada y Cristal en directorios separados.
- Kiro confirmó `claude-opus-5.5`, `effortLevel=max` y `autopilot=off` en una sesión propia nueva, `opus-ui-round3`. Se envió una sola consulta breve. El cliente agotó 180 segundos; el replay del servidor confirmó `aborted`, 179984 ms, sin texto útil y sin coste reportado. Se reconcilió y abandonó ese único prompt sin reenviarlo. No quedan runners de este intento activos; ninguna decisión ni código de esta ronda se atribuye a Opus. Evidencia privada: `/Users/caballero/.codex/zmd-collaboration/sessions/opus-ui-round3/attempt-evidence.json`.
- La revisión independiente se limita al flujo visible, fidelidad de valores y controles. No certifica motor ni accesibilidad global.

## Identidad en otro chat

Diego pidió separar el trabajo de marca. Se creó **logo**, con `openai.gpt-6-astra`, razonamiento `max`, ID `01a13dc0-6ef2-7893-aa59-cc691b35901d`.

Encargo: 40 ideas nuevas, minimalistas y variadas, con conexiones reconocibles con electromovilidad, eficiencia, ahorro o IA; incluir composiciones tipográficas. Mostrar el símbolo junto a ZMD Mobility en una galería HTML interactiva. Investigar fuentes primarias y usar la skill de marca, con prueba acotada de Opus 5.5 mediante Kiro y atribución real.

Ámbito exclusivo de ese chat: `explorations/logo-40/` y `docs/LOGO-40-HANDOFF.md`. No edita interfaz, motor ni documentos compartidos; no hace commit/push global mientras se comparte la rama. La identidad sigue sin aprobación.

## Continuación

Tras la comparación, Diego puede elegir una variante o combinar sus detalles. Incorporar las respuestas del equipo antes de ampliar variables; acordar después el intercambio real con el motor. La conservación del original se comprueba con `explorations/round-3/qa/baseline-sha256.json`.

## Cierre de verificación

Revisión independiente del 15-10: **PASS acotado para comparar las cuatro variantes**. Original: 18 archivos y dependencias idénticos. Se verificaron selección entre vehículos, recargas, salida/regreso del depósito, perfiles, teclado, foco, interrupciones de Motion, movimiento/transparencia reducidos y anchos de 319 a 1440 px. El comparador abre las cuatro vistas, devuelve el foco al cerrarse y no anida otra galería al volver desde una variante.

Las correcciones confirmadas y sus capturas están en el [informe independiente](../explorations/round-3/qa/independent-review.md). Es una revisión de diseño ejecutable en Chrome, sin motor conectado ni certificación global de accesibilidad. En la variante Batería queda documentada como límite secundario la posible cobertura del marcador seleccionado por el detalle en móvil; evaluar esa cámara al refinar la opción elegida.
