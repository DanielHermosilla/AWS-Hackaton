# Integración del mapa

Lee solo la parte pertinente y comprueba la versión instalada antes de copiar APIs. Las opciones vigentes y pendientes del proyecto están en `docs/MAPA-Y-BASE.md`.

## Datos y estado

En GeoJSON, representa ubicaciones como `[longitud, latitud]` en WGS84. Valida antes de generar geometría; no intercambies ejes automáticamente para que un punto “parezca correcto”. Conserva el ID original y la procedencia de una geometría: vial calculada, recibida del motor o esquemática. Evita presentar distancia de un segmento recto como distancia por carretera.

Una selección compartida por ID suele bastar para enlazar lista, capa y detalle. Define quién la mantiene y qué sucede al cambiar escenario o desaparecer ese ID. Evita ciclos de eventos que muevan la cámara o disparen selecciones repetidamente. Respuestas asíncronas se asocian con la solicitud vigente; cancelar ayuda a ahorrar trabajo, pero también hay que rechazar resultados obsoletos.

## Ciclo de vida y rendimiento

Instancia el mapa cuando su contenedor exista; espera el estado requerido por la biblioteca para añadir fuentes y capas. No recrees el mapa en cada render. Libera listeners, observadores, animaciones y la instancia al desmontar. Un cambio de estilo puede eliminar capas y fuentes personalizadas; repón las necesarias según su ciclo de vida.

Actualiza datos existentes cuando corresponda. Un cambio de tamaño del contenedor por un panel puede requerir notificar al mapa; verifica el encuadre con el espacio realmente visible. Mide rendimiento con la carga esperada antes de cambiar arquitectura. Para pocos nodos, marcadores DOM pueden bastar; las capas de una fuente común ayudan cuando crece la cantidad. No hay un umbral universal que obligue a clustering o workers propios.

Si usas React, el wrapper es una opción, no un requisito. Mantén claros los límites entre estado declarativo y métodos imperativos. No adoptes Next.js, Motion, deck.gl o una biblioteca de estado por aparecer en un ejemplo.

## Cartografía y proveedores

Renderizador libre no significa tiles, geocodificación o routing gratuitos e ilimitados. Identifica proveedor, atribución, credenciales permitidas en cliente, restricciones de origen y condiciones de caché/offline. No uses un secreto de servidor en el frontend ni desactives atribución para limpiar el diseño.

Fallo de tiles, falta de WebGL o geometría no disponible requieren un mensaje útil y acceso textual a los datos. Reintentar o cambiar proveedor no debe alterar silenciosamente los resultados. No envíes datos locales a una API por el solo hecho de abrir el mapa.

## Fuentes oficiales por necesidad

Consultadas el 14-10-2026; documentación viva, no versiones fijadas del producto:

- [GeoJSON RFC 7946, coordenadas](https://www.rfc-editor.org/rfc/rfc7946#section-3.1.1).
- [MapLibre GL JS](https://maplibre.org/maplibre-gl-js/docs/) y [API Map](https://maplibre.org/maplibre-gl-js/docs/API/classes/Map/): ciclo de vida, fuentes/capas, encuadre y tamaño.
- [react-map-gl](https://visgl.github.io/react-map-gl/): integración declarativa opcional.
- [Mapbox GL JS](https://docs.mapbox.com/mapbox-gl-js/guides/): alternativa de SDK y ecosistema; revisar condiciones del proveedor.
- [Leaflet](https://leafletjs.com/reference.html): alternativa 2D sencilla; sus métodos `LatLng` no adoptan por defecto el orden de GeoJSON.
- [Amazon Location: mapas](https://docs.aws.amazon.com/location/latest/developerguide/maps.html) y [rutas](https://docs.aws.amazon.com/location/latest/developerguide/routes.html): servicios distintos; permisos de la cuenta deben comprobarse.
- [OpenStreetMap: política de tiles](https://operations.osmfoundation.org/policies/tiles/): el servidor público no es un backend sin límites ni un paquete offline.
- [W3C: teclado](https://www.w3.org/WAI/WCAG22/Understanding/keyboard.html) y [animación de interacciones](https://www.w3.org/WAI/WCAG22/Understanding/animation-from-interactions.html): acceso alternativo y movimiento.
