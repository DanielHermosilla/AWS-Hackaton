# ZMD Mobility · Webapp

Interfaz estática de planificación eléctrica. Conserva el Plan con estética Cristal y distribución Esencial, la navegación compartida, el perfil local y cinco variantes de Inicio. No requiere instalar paquetes ni compilar.

Desde la raíz del repositorio:

```sh
python3 -m http.server 4173 --bind 127.0.0.1 --directory webapp
```

Abre `http://127.0.0.1:4173/plan.html` para el Plan o `http://127.0.0.1:4173/home/` para comparar los cinco inicios. Usa HTTP: los módulos JavaScript y el mapa no funcionan abriendo el HTML como archivo.

## Datos de demostración

- Un clon limpio usa `data/demo.synthetic.json`: puntos generados, líneas entre ellos y valores inventados. No son ubicaciones CASE ni rutas viales; no hay optimización, factibilidad energética ni ahorro medido.
- Si existe `data/fixture.local.json`, se usa el ejemplo local preparado con las ubicaciones públicas CASE y trazados OSRM. Este archivo es local e ignorado por Git; no se incluye con la interfaz. Sus baterías, recargas, orden y consumo siguen siendo ilustrativos.
- Solo un **404** del archivo local activa el ejemplo sintético. Un JSON corrupto o cualquier otro error muestra un fallo de carga, sin sustituir silenciosamente los datos.
- La cartografía de fondo necesita internet para acceder a OpenFreeMap. La lista de paradas continúa disponible si falla el mapa. Abrir la webapp no envía una consulta a OSRM.

El formato de estos ejemplos es interno de diseño, no el contrato definitivo del motor. No hay backend, autenticación, ejecución de solver ni importador genérico de CSV. El botón de salida cierra el contexto local de la demostración.

## Código

`plan.*` y `map.js` contienen la pantalla operativa. `app-shell.js`, `app.css`, `state.js` y `home-navigation.js` comparten navegación, preferencias y retorno al Inicio elegido. `home/` conserva las cinco propuestas actuales, incluida Consola adaptable con selector claro/oscuro. `shared/` contiene estilos, iconos, movimiento y lectura de datos.

La identidad elegida es **Batería en marcha**; sus SVG, favicons y estilos están en `assets/brand/`. La marca no representa el estado de batería.

## Dependencias y licencias

MapLibre GL JS 6.14.0 se distribuye en `vendor/maplibre/`, con su worker y licencia BSD. Motion 14.2.0 está en `vendor/motion/`, con licencia MIT. Las letras del logo Manrope están convertidas a curvas; se conserva su licencia SIL OFL en `assets/brand/licenses/Manrope-OFL.txt`. No se descarga una fuente de marca en ejecución.

El estilo cartográfico usa OpenFreeMap y datos OpenStreetMap; se conserva la atribución del mapa. No se incluyen teselas, credenciales, datos originales CASE ni cachés OSRM en el código publicable.
