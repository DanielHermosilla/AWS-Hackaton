# Pruebas

- Unit tests deterministas sin red, AWS ni datos privados obligatorios.
- Marcar pruebas de solver con `solver`; verificar Gurobi y SCIP cuando estén.
- Casos esperados independientes: pequeños óptimos conocidos, enumeración
  exhaustiva, transiciones de batería calculadas a mano y resultados alterados.
- Probar tránsito sin entrega, recarga repetida, saturación, déficit intermedio,
  retorno intermedio al depósito, vehículo inactivo, H y estados sin incumbente.
- Los datos locales se prueban aparte con `real_data`; los ejemplos sintéticos
  nunca se describen como datos reales ni como certificado de la instancia total.
