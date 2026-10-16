# Consumo por calle

**Qué cambia.** Ahora puedes adjuntar un histórico eVED, CSV o JSON además del
archivo de destinos. Donde sus recorridos permitan estimar el consumo de una
calle, se usará esa estimación. Donde falten datos, seguirá tu consumo supuesto.

**Cómo se usa.** En «Flota y supuestos», abre «Consumo con históricos» y adjunta
el archivo. Verás las mediciones disponibles y, al calcular, la cobertura de
calles. «Qué aportan estos datos» explica observaciones y supuestos. Puedes
quitarlo para volver al valor manual. Se admiten hasta 256 MiB; el eVED EV local
entra en ese límite. Los datos de vehículos híbridos o de combustión no sirven
como consumo del eléctrico.

**Qué significa el resultado.** Son estimaciones para planificar, no mediciones
del viaje futuro. Se separan viajes, huecos y posibles recargas estacionarias.
No se cambia automáticamente la capacidad de batería, la reserva ni la flota.
El histórico temporal caduca al reiniciar el servidor.

**Para Daniel.** La normalización integra corriente y voltaje con Δt real.
Los bloques GPS se asocian a calles dirigidas; se exige soporte por viajes y se
reserva una parte para evaluar el error. La descarga y recuperación permanecen
separadas, con el orden interno supuesto declarado. Los costes se aplican antes
del preprocesador de recursos, regenerando hashes y caminos; el validador
reproduce la misma física. El formato nativo del solver conserva su autoridad.
