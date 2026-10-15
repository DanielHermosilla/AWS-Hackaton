---
name: zmd-map-ui
description: "Diseña, integra o revisa el mapa operativo de ZMD Mobility: capas geográficas, rutas, selección con listas, cámara y estados visibles. Úsala al trabajar el mapa; no sustituye al solver, al modelo energético ni a una auditoría completa de la aplicación."
---

# Mapa operativo ZMD Mobility

Consulta los acuerdos vigentes y el contrato disponible. El mapa es parte principal de la operación. Empieza por la decisión que debe permitir y el dato que la respalda; una tarea de visualización no elige por sí sola proveedor, solver o infraestructura GIS.

Mantén separadas estas responsabilidades:

- El **renderizador** dibuja e interpreta gestos; el **proveedor cartográfico** entrega mapas base y sus condiciones de uso.
- La **geometría vial** representa un recorrido sobre calles. La **matriz** aporta costes entre ubicaciones y puede no incluir esa geometría.
- La **asignación logística** ordena y distribuye visitas. La **validación energética** determina si se satisfacen las restricciones acordadas.

Una línea directa entre nodos se presenta como esquema cuando no hay geometría vial; no la vendas como ruta conducible, distancia medida ni evidencia energética. Un cargador registrado no equivale a compatible, libre o disponible en vivo.

Reutiliza IDs de escenario, ejecución, vehículo y parada del contrato. Selección y resultado deben ser coherentes entre mapa, lista y detalle; una respuesta antigua no reemplaza la ejecución actual. Conserva IDs como datos, sin convertirlos arbitrariamente a números.

En la frontera geográfica, valida coordenadas finitas, significado y orden. GeoJSON usa **longitud, latitud**; otras APIs pueden recibir otro orden. No conviertas ausencias a cero ni filtres una coordenada cero por ser falsy. Los rangos válidos no detectan todos los intercambios de ejes: contrasta con el área esperada. No ocultes un cliente con coordenadas inválidas; conserva su registro y explica la limitación.

La cartografía de fondo debe permitir leer rutas, paradas y selección. Distingue categorías y estados con etiquetas, formas o trazos además del color. Ofrece lista o itinerario operable con teclado para acceder a la misma información y acciones; los píxeles del mapa no son la única interfaz.

Encuadra la información pertinente considerando paneles que la cubren. Conserva el control de cámara del usuario; actualizar datos no implica recentrar. Usa movimiento para orientar cuando aporte, respeta reducción de movimiento y evita representar telemetría en vivo con una animación ficticia.

Al implementar, consulta [integración y fuentes](references/integracion.md) según la biblioteca elegida. Reutiliza la instancia del mapa, limpia recursos al desmontar y actualiza datos/capas de forma controlada. No añadas clustering, un estado global, 3D o un servicio geoespacial sin necesidad demostrada.

Comprueba los riesgos afectados por el cambio con datos sintéticos o locales autorizados: orden de coordenadas, selección, respuesta antigua, nodos inválidos, errores del proveedor, paneles, teclado y movimiento reducido. Separa validación de datos, inspección estática y prueba real de navegador; ninguna demuestra que el motor complete los pedidos o vuelva con energía.

Entrega el cambio solicitado, su evidencia y limitaciones relevantes. Conserva atribución y condiciones del proveedor. Los fallos de mapa base o geometría deben tener un estado comprensible sin borrar resultados válidos del motor.

Instrucciones originales del proyecto, 14-10-2026; no fijan biblioteca. Fuentes primarias en la referencia.
