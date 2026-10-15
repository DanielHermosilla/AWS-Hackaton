# Control de búsqueda mediante Bedrock

- El usuario autorizó la política adaptativa de la variante Dantzig–Wolfe.
  Centralizar llamadas reales en `bedrock.py`, con credenciales estándar,
  timeout, presupuesto de llamadas y registro de uso sin secretos.
- La integración debe usar Bedrock de la cuenta AWS asignada y
  reutilizar material de LLM4MIP con licencia/procedencia documentadas.
- Mantener inalterados la instancia, formulación, presupuesto y certificación.
- Cada respuesta será JSON validado contra acciones implementadas del solver.
  Nunca ejecutar código generado ni aplicar parámetros desconocidos.
- En esta rama, el usuario autorizó la orquestación amplia por eventos:
  `before_search`, `after_seed` y `search_stagnation`. Usar `RoutePolicy`,
  límites explícitos de llamadas/inferencia y registros por decisión.
  Ninguna llamada remota por nodo, corte o ronda de pricing.
- El LLM puede elegir descomposiciones verificadas y políticas de cortes/pricing.
  No puede declarar infactibilidad, optimalidad ni ausencia de columnas.
- Los tests habituales usan dobles; identificar aparte la prueba real de AWS.
