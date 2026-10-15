# Construcción y entrega SVG

Consulta al implementar o exportar; no es un trámite previo a conversar sobre una idea.

- Define `viewBox` y límites que conserven todo el dibujo, incluidos trazos. Comprueba el recorte al escalar y exportar.
- Evita referencias externas y estilos globales que alteren la página. Si el SVG se inserta inline varias veces, los IDs de máscaras, gradientes y títulos deben resolver dentro de cada instancia sin colisiones. Un SVG autónomo no necesita por ello un generador de IDs.
- Mantén texto editable cuando sea útil. Si entregas letras convertidas a trazados, conserva la fuente editable y su procedencia/licencia cuando corresponda. No presupongas una tipografía instalada en el equipo receptor.
- Para una imagen funcional, el nombre accesible comunica su función: un enlace al inicio debe resultar comprensible. Evita repetir innecesariamente el nombre que ya aporta el texto adyacente. Un elemento puramente decorativo se excluye de la lectura asistida.
- Verifica estructura SVG y contenido; ni extensión, tamaño de archivo ni prefijo `<?xml` demuestran que sea un vector. Revisa imágenes incrustadas, recursos remotos y scripts antes de incorporar activos externos.
- Renderiza los usos incluidos en el encargo: por ejemplo, símbolo pequeño, cabecera y diapositiva. Fondos claro, oscuro o monocromo se prueban si forman parte de la entrega. Observa silueta, huecos, peso y alineación; exporta PNG solo si hace falta.

Informa qué se inspeccionó realmente. No atribuyas pruebas de navegador, pantalla pequeña o lectura asistida a una comprobación de XML. Los controles y textos del producto tienen obligaciones de contraste propias; la excepción WCAG de texto de logotipo no se extiende a toda la interfaz.

Fuentes primarias consultadas el 14-10-2026:

- [W3C: estructura de SVG](https://www.w3.org/TR/SVG2/struct.html).
- [W3C: imágenes funcionales](https://www.w3.org/WAI/tutorials/images/functional/).
- [W3C: contraste mínimo y excepción de logotipos](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html).
- [Apple: App Icon Design](https://developer.apple.com/videos/play/wwdc2017/822/), referencia de legibilidad a escala pequeña; no una norma universal de identidad.
