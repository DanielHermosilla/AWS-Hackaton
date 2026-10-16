# Motor y archivos · implementado

Ahora la app usa el solver completo de main junto con las features existentes.
Acepta CSV de ubicaciones y JSON con la instancia y sus parámetros. Los históricos
eVED se rechazan porque contienen mediciones, no un plan de entregas.
El ejemplo sintético ya no intenta conectarse a calles de otra ciudad.

**Para Daniel:** API 3.0 y pipeline nativo conservados. El puente valida gap y
semilla, permite los CPU disponibles y distingue geometría sintética de vial.
Importación 256 MiB; petición 64 MiB; resultados temporales 256 MiB. La matemática
no cambió. El CSV completo pasó con 20/20 entregas y validación vial independiente.
