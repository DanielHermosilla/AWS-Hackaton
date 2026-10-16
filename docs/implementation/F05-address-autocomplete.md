# Direcciones: decisión y siguiente integración

Investigación de fuentes oficiales: **16-10-2026**. No se hicieron llamadas
pagas ni se verificó acceso a una cuenta de geocodificación.

## Qué recibe el usuario en esta entrega

El editor permite buscar entre los puntos cargados, corregir su dirección,
introducir coordenadas y ajustar un marcador antes de confirmar. Escribir una
dirección **no determina sus coordenadas**: ambas se revisan explícitamente.
Este flujo funciona sin contratar un buscador de direcciones.

El autocomplete externo queda **analizado, no implementado**. La recomendación
para la siguiente etapa es probar Amazon Location en la cuenta asignada, sujeto
a permisos, cobertura y presupuesto. Es una decisión de implementación propuesta,
no una exigencia oficial del concurso ni evidencia de acceso mediante sus créditos.

## Opciones y ajuste al producto

| Opción | Qué ofrece | Restricción relevante | Decisión |
|---|---|---|---|
| Edición y búsqueda local | Corregir y localizar nodos ya cargados | No descubre ni verifica direcciones nuevas | Base de F05; sin dependencia de geocodificación |
| Amazon Location Places | `Autocomplete` para texto; `Geocode` para coordenadas | Autocomplete no devuelve coordenadas ni POI. Los datos que se guardan requieren una operación compatible con `IntendedUse=Storage` y su tarifa. [1–3] | Candidato preferido por encaje con AWS y exportación de instancias; falta prueba en cuenta y zona |
| Mapbox Search Box | Sugerencias y recuperación de coordenadas | La documentación limita el uso de datos a temporal; guardar posiciones requiere contactar a ventas. Declara cobertura de EE. UU., Canadá y Europa. [4] | No adoptarlo como proveedor general del producto exportable sin resolver almacenamiento y cobertura |
| Nominatim público | Búsqueda puntual sobre OSM | Su política prohíbe autocomplete y limita el servicio a 1 petición/s; esto se refiere al servidor público, no a instalaciones de terceros. [5] | Descartado para autocomplete |

No se afirma cuál encuentra mejor las direcciones del escenario sin comparar una
muestra autorizada. Tener teselas OpenFreeMap no incluye un servicio de búsqueda.

## Plan de implementación para Daniel

1. **Habilitar una prueba acotada.** Confirmar región, permisos de Amazon Location,
   operación de almacenamiento, cobertura de las entradas y costo por consulta.
   No reutilizar credenciales de Bedrock como prueba de permisos del buscador.
2. **Añadir dos operaciones al backend existente.** Una devuelve sugerencias
   transitorias; la otra geocodifica la selección con `IntendedUse=Storage` cuando
   sus datos vayan a guardarse o exportarse. El frontend no recibe claves AWS.
   Conservar solo los campos necesarios de la respuesta final, su procedencia y
   la confirmación del operador; no persistir respuestas de Autocomplete. [1–3]
3. **Conectar el campo de dirección.** Propuesta inicial: consultar desde tres
   caracteres, esperar 300 ms entre cambios y mostrar hasta cinco alternativas
   con comuna/ciudad. Descartar respuestas atrasadas; soportar flechas, Enter,
   Escape y fallo del servicio. Estos límites son decisiones del producto.
4. **Confirmar la ubicación.** Seleccionar una sugerencia abre el punto obtenido
   en el mapa. Una calle o localidad sin precisión suficiente no se acepta
   silenciosamente como puerta de entrega. El usuario puede ajustar y confirmar;
   editar el texto después invalida la selección geocodificada.
5. **Repreparar antes de resolver.** La ubicación confirmada actualiza el borrador
   y vuelve a `/prepare` en el flujo sintético. En una instancia vial nativa,
   Daniel debe reconstruir o validar su red y perfiles: geocodificar un punto
   no actualiza los arcos ni sus consumos. Conservar el bloqueo actual hasta
   contar con ese contrato.

Aceptación futura: direcciones ambiguas, cero resultados, timeout/cuota, teclado,
respuesta vieja, coordenadas cero, exportación permitida y nueva preparación.
Medir tasa de selección correcta y tiempo hasta confirmar sobre la misma muestra;
no prometer ahorro de cómputo, energía o entregas por incorporar autocomplete.

## Fuentes oficiales consultadas

1. [Amazon Location: Autocomplete](https://docs.aws.amazon.com/location/latest/developerguide/autocomplete.html).
2. [Amazon Location: Geocode](https://docs.aws.amazon.com/location/latest/APIReference/API_geoplaces_Geocode.html).
3. [Amazon Location: IntendedUse](https://docs.aws.amazon.com/location/latest/developerguide/places-intended-use.html).
4. [Mapbox: Search Box API, cobertura y límites](https://docs.mapbox.com/api/search/search-box/).
5. [OSMF: política del servicio público Nominatim](https://operations.osmfoundation.org/policies/nominatim/).
