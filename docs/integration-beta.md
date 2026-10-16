# Integración local vigente en main

La importación parcial de `modelamiento@6242035` ha sido reemplazada por el merge
con historia de `codex/evrp-llm-search@ab67dc6` y `codex/webapp@a372d03`.
Se incluyen ahora preprocesamiento vial, caminos con recursos, búsqueda
especializada y GPT por Bedrock, conservando la UI, la validación y el resultado
nativo completo. La autorización actual reemplaza la exclusión anterior de
`service_graph.py` y los módulos que lo usan.

La guía de arranque, arquitectura, datos, credenciales, trazabilidad y límites
está en [webapp-integration.md](webapp-integration.md). El contrato HTTP aditivo
mantiene API 3.0; las instancias nativas pueden ser 1.0 o 1.1 según representación.
Ver [API_CONTRACT.md](../backend/API_CONTRACT.md) y
[solver-source.json](solver-source.json).

La aplicación sigue siendo local y sin autenticación. No se ha desplegado como
servicio público. Los ejemplos sintéticos siguen separados de las ejecuciones
reales y la cartografía de fondo requiere Internet.

