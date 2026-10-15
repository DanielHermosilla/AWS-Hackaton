# Tuning futuro, no integrado en esta rama

- No conectar AWS, cargar credenciales ni hacer llamadas a un LLM en esta fase.
- `tuning.py` define dónde preparar el perfil y solicitar una propuesta futura.
- La integración futura deberá usar Bedrock de la cuenta AWS asignada y
  reutilizar material de LLM4MIP con licencia/procedencia documentadas.
- Mantener inalterados la instancia, formulación, presupuesto y certificación.
- Una futura respuesta será JSON validado contra opciones reales del solver.
  Nunca ejecutar código generado ni aplicar parámetros desconocidos.
