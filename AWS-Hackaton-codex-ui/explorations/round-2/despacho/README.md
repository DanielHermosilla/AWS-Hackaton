# Despacho eléctrico

Propuesta de interfaz del 15-10-2026: hoja operativa para una jefa de flota. Navegación compacta, lista de veinte locales o inspector de los dos Nissan Leaf 2013, y mapa de Ann Arbor a la derecha. La batería inicial, el regreso y las recargas tienen una posición visible en la operación.

Lee `PRODUCT.md` y consume los módulos compartidos de esta ronda sin modificarlos. Coordenadas, geometrías, procedencia y fixtures vienen de `../shared/`; esta vista no implementa un motor ni elige el stack final. No hubo participación de Kiro en esta propuesta.

Al entrar se muestran los puntos del escenario y la batería inicial al 60 %, sin resultados. **Ver plan de ejemplo** habilita las asignaciones, rutas y cifras ilustrativas. Los filtros muestran Todos, Auto 1, Auto 2 o Cargadores; una selección enlaza lista, mapa y detalle. La pestaña Flota muestra consumo y eventos de recarga de ejemplo. La potencia registrada de un cargador se distingue de su compatibilidad y disponibilidad, no verificadas.

Editar batería rechaza campos vacíos y valores fuera de 0–100 %. Un cero explícito es un parámetro válido; no equivale a una operación factible. Guardar cambios retira las asignaciones, geometrías, consumo, recargas y porcentajes de llegada del ejemplo. **Restaurar demostración al 60 %** repone el escenario y sus resultados ilustrativos. Los valores del plan se muestran redondeados a un decimal cuando corresponde.

Verificación en Chrome, 15-10-2026:

- **Aprobada:** veinte entregas, diez por vehículo al filtrar el ejemplo y sesenta estaciones registradas.
- **Aprobada:** selección en ambas direcciones; la selección del mapa se conserva sin reenmarcar por cada render.
- **Aprobada:** vacío rechazado, 101 % rechazado, cero explícito guardado, resultados retirados y restauración.
- **Aprobada:** pestañas con flechas, navegación de filas con flechas, selección con espacio y cierre del modal con Escape y devolución de foco.
- **Aprobada:** 1440 × 900, 900 × 900 y 390 × 844, sin desbordamiento horizontal. Capturas inspeccionadas.
- **Aprobada:** cero excepciones JavaScript y cero solicitudes fallidas durante ese recorrido.

Script, resultados y capturas de esa ejecución: `/tmp/zmd-dispatch-qa/`. No se verificaron optimización, factibilidad energética ni una conformidad completa de accesibilidad. El mapa comparte el fallback del renderizador y su atribución.
