# Implementación de esta rama

- Seguir `modelamiento.pdf`: red vial elemental y entregas separadas del tránsito.
- Comentar ecuaciones Pyomo con su número (1)–(16), unidades y significado.
- Gurobi es la primera opción. Si falta o su licencia no permite resolver,
  intentar SCIP y registrar el motivo. No sustituir SCIP por otro backend.
- El LLM queda desconectado: el esqueleto de tuning no hace llamadas de red.
- Contratos compartidos en `contracts.py`; coordinar cambios antes de editarlo.
- El validador no usa restricciones ni valores auxiliares de Pyomo para decidir
  factibilidad: reproduce la física desde la instancia y el resultado.
- Nunca presentar fixtures, distancias geodésicas o red recortada como una
  solución validada del grafo vial completo.
