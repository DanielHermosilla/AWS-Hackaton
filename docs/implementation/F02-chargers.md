# F02 · información completa del cargador

## Encargo del agente

Implementar y probar la ficha de estación dentro del Plan aprobado. Lee primero
`docs/ZMD-MASTER-CONTEXT.md`, `docs/ZMD-ORCHESTRATION.md`, `webapp/README.md`,
`backend/API_CONTRACT.md` y las skills ZMD de contrato, diseño, mapa y QA pertinentes.
El usuario ya autorizó implementar; no abrir otra aprobación rutinaria.

## Alcance y arquitectura

Reutilizar el panel de parada y el resultado nativo. Conservar en el adaptador JS
dirección, red declarada, conectores, potencia y puertos totales/DC/nivel 2.
Presentar los atributos tanto si la estación participa en una ruta como si no.
La recarga de una ocurrencia debe seguir separada de la información estática.
Disponibilidad siempre sin verificar; valores ausentes se explican, cero no se
convierte en ausencia. No inferir potencia aceptada, compatibilidad real ni tiempos.

Responsabilidad exclusiva: `webapp/plan.js`, `webapp/shared/solver-adapter.js`,
`webapp/shared/charger-details.js`, `webapp/charger-details.css` y pruebas nuevas
`webapp/tests/charger-details.test.mjs`. Evitar cambios globales; cargar estilos
desde el módulo si hace falta. No editar solver, backend, boot o panel de cálculo.
Solicitar al integrador cualquier cambio fuera de esta lista.

## Secuencia y aceptación

- [ ] Añadir pruebas de metadatos completos, cero, vacíos y textos que requieran
  escape HTML; observar el fallo antes de cambiar la proyección.
- [ ] Completar proyección y renderización con controles/estilos existentes.
- [ ] Asegurar acceso con teclado a cargadores no usados y sin coordenadas,
  sin depender exclusivamente del mapa.
- [ ] Conservar detalle de recarga y selección por ocurrencia para una estación repetida.
- [ ] Ejecutar `node --test webapp/tests/*.test.mjs` y `git diff --check`.
- [ ] QA de estación usada/no usada, datos ausentes, ID/dirección largos,
  escritorio 1440×900, móvil 390×844, modo claro y cambio oscuro; mapa ausente.
- [ ] Commit acotado y entrega estructurada a la madre, con capturas locales.

Usar fixtures sintéticas; no publicar CSV originales ni invocar servicios pagados.
Las pruebas de esta ficha no certifican el solver ni la disponibilidad en terreno.

## Entrega

Reportar por colaboración: rama/worktree, base y commit final, archivos, flujo
visible, comandos con resultados, qué fue real/simulado, capturas, limitaciones
y cualquier cambio de integración necesario. No modificar el registro central.
