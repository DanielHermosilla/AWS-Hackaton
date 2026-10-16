# F05 · edición de ubicaciones y direcciones

## Encargo del agente

Implementar la edición de ubicaciones confirmada mediante formulario y mapa.
Leer MASTER-CONTEXT, ORCHESTRATION, README y API; aplicar skills `zmd-map-ui`,
`zmd-contract`, `zmd-apple-design`, pruebas y QA. Mantener el solver de Daniel intacto.
La madre investiga autocomplete y transmitirá la decisión; avanzar mientras tanto
en el editor que funciona sin credenciales ni conexión de geocodificación.

## Alcance y arquitectura

Editar depósito, visita o cargador del borrador antes de calcular. Conservar ID y
tipo; permitir coordenadas mediante formulario y ajuste de marcador, con Confirmar
y Cancelar. El borrador no debe mutar el resultado ni el original hasta confirmar.
El formulario debe funcionar con teclado y aunque no cargue el mapa base.

CSV y caso sintético: reutilizar los nodos normalizados y `/prepare` existente.
Tras confirmar cambios, invalidar preparación/resultado y volver a obtener una
instancia en el backend, con confirmación explícita del alcance no vial. Nunca
construir arcos, estimaciones energéticas ni un solver alternativo en JavaScript.

**Instancia nativa con grafo:** cambiar coordenadas no reconstruye energía/arcos.
No sobrescribirla o degradarla silenciosamente a haversine. Conservar el bloqueo
de resolución hasta disponer de una red preparada para la nueva ubicación.
Implementar una interacción explícita y útil sin fingir esa capacidad: la
instancia nativa puede inspeccionarse, y debe explicar qué preparación de Daniel
falta para editarla/recalcularla con seguridad. Si se propone una conversión
voluntaria a otro borrador, acordar antes con la madre qué datos se conservarían.

Responsabilidad: `webapp/run-panel.js`, `webapp/run-panel.css`, nuevos
`webapp/location-editor.js`, `webapp/location-editor.css`,
`webapp/shared/location-draft.js` y pruebas propias.
`webapp/map.js` solo si una extensión acotada es necesaria; preferir el renderizador
MapLibre ya distribuido y separar el mapa del borrador de los resultados.
No tocar `boot.js`, `plan.js`, adaptador, solver, cliente/entrada compartidos ni
backend sin coordinación previa.

## Secuencia y aceptación

- [ ] Pruebas de borrador independiente, confirmar/cancelar, rangos finitos,
  coordenadas cero, IDs opacos y prohibición de resolver una red nativa obsoleta.
- [ ] Integrar edición en la revisión de entrada con selección/lista y formulario.
- [ ] Añadir mapa de edición y confirmación, manteniendo teclado y fallo de mapa.
- [ ] Invalidar datos preparados y respuesta vieja; conservar presupuesto,
  metadatos y parámetros no editados.
- [ ] No resolver mientras haya edición no confirmada o coordenadas inválidas.
  Cancelar no modifica la instancia original ni invalida una corrida innecesariamente.
- [ ] Probar preparación → edición → nueva preparación → cálculo → exportación;
  comprobar que coordenadas/IDs del JSON corresponden a lo confirmado.
- [ ] Probar respuesta de cálculo anterior tardía, archivo sustituido,
  doble apertura, mapa fallido, móviles, foco/Escape y entrada nativa protegida.
- [ ] `node --test webapp/tests/*.test.mjs`, pruebas afectadas y `git diff --check`.
- [ ] Incorporar únicamente autocomplete compatible con la decisión de la madre;
  no usar Nominatim público como autocompletado ni invocar APIs pagas.
- [ ] Commit y entrega con comandos, capturas y límites.

## Entrega

Informar SHA base/final, archivos, flujo terminado, red nativa bloqueada de forma
honesta, comportamiento con geocodificación no disponible, pruebas reales/simuladas,
capturas y dependencias de Daniel. La madre controla registro e integración.
