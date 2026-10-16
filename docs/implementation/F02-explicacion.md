# F02 · entender cada cargador

**Qué hace.** «Cargadores» reúne todas las estaciones, incluso las no utilizadas
o sin coordenadas. Cada ficha muestra dirección, red, conectores, puertos y potencia.

**Cómo se agregó.** Completamos el panel existente. «0» significa cero;
«Sin informar» significa que falta el dato. Si un vehículo pasa varias veces,
puedes revisar la batería y recarga de cada paso.

**Límite.** No confirma disponibilidad ni la potencia que aceptará el vehículo.

**Para Daniel — implementación.** El adaptador conserva los puertos; un módulo
alimenta lista y ficha. Las recargas se leen por vehículo y posición, sin cambiar
KPIs ni solver. La selección se conserva entre Inicio y Plan.
