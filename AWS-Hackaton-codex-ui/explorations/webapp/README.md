# Base elegida de ZMD Mobility

Decisión de Diego, 15-10-2026: **Cristal en la estética; Esencial en distribución y tamaños de controles**.

Abrir `http://127.0.0.1:4173/webapp/plan.html` con el servidor de `explorations/`. El siguiente chat ampliará esta base con Inicio/dashboard, navegación y perfil según [el traspaso](../../docs/WEBAPP-HANDOFF.md).

```sh
python3 -m http.server 4173 --bind 127.0.0.1 --directory explorations
```

- `plan.html` y `plan.js`: pantalla de reparto, vehículo/parada seleccionados, batería, diálogo de procedencia y teclado.
- `plan.css`: geometría de Esencial, con espacio adicional en móvil para detalle y atribución.
- `material.css`: acabado de Cristal sin cambiar las dimensiones de los controles.
- `map.js`: mapa derivado de la ronda anterior, con selección situada fuera de las tarjetas y controles superpuestos.
- `../round-3/shared/`: datos locales del ejemplo, iconos y Motion. Las rondas anteriores permanecen intactas.

La selección del mapa conserva la cámara al pulsar un pin visible. Si el detalle lo tapa, desplaza lo necesario para mostrarlo. Elegir una parada de la lista coloca el pin en la zona libre más próxima al centro. Se conserva la diferencia entre salida y regreso a BASE.

El escenario utiliza ubicaciones públicas de CASE y recorridos viales preparados para demostrar el diseño. Consumo, recarga y batería son ilustrativos. Esta base no ejecuta el motor, no valida energía, no demuestra ahorro ni acredita disponibilidad de cargadores.

Los JSON locales continúan ignorados por Git. El script `../round-3/shared/prepare-local-fixture.py` prepara el ejemplo a partir de los archivos locales del proyecto.

La evidencia y autoría del incremento están en [qa/README.md](qa/README.md) y en el traspaso: 23 comprobaciones principales, 18 de cámara y 12 de foco móvil aprobadas. Las preferencias elegidas quedan fijadas; no se necesita otra ronda de selección.
