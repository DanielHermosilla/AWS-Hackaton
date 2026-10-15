# Implementación de esta rama

- Seguir `modelamiento.pdf`: red vial elemental y entregas separadas del tránsito.
- Comentar ecuaciones Pyomo con su número (1)–(16), unidades y significado.
- El flujo predeterminado es `scip-routes`, maestro por rutas sin H con
  PySCIPOpt. Preservar batería, carga continua, regeneración, tiempos y revisitas.
  Pyomo y GCG posicional siguen como referencia seleccionable explícitamente.
- Bedrock orquesta etapas mediante eventos y presupuestos explícitos, fuera de
  los callbacks. Conservar el oráculo exacto y no acreditar pricing completo
  después de interrumpirlo. Una cota del maestro restringido no es global.
- Contratos compartidos en `contracts.py`; coordinar cambios antes de editarlo.
- El validador no usa restricciones ni valores auxiliares de Pyomo para decidir
  factibilidad: reproduce la física desde la instancia y el resultado.
- Nunca presentar fixtures, distancias geodésicas o red recortada como una
  solución validada del grafo vial completo.
