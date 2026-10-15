---
name: zmd-apple-design
description: "Diseña o mejora pantallas ZMD Mobility con claridad, tipografía y feedback inspirados en Apple, adaptados a la jefa de flota. Úsala para composición e interacción; una auditoría del flujo existente corresponde a zmd-ui-qa."
---

# Apple Design para ZMD Mobility

Adaptación del `apple-design` de Emil Kowalski, no una skill oficial de Apple. Para ZMD Mobility utiliza esta síntesis; el original queda como referencia especializada, sin sumar ambos workflows por defecto.

Recupera `docs/CONTEXTO.md` y el recorrido acordado si faltan en el encargo. La referencia es una jefa de flota: debe reconocer el escenario, entender el resultado y encontrar su siguiente acción. Presenta detalle técnico cuando ayude, sin inventar funcionalidades para completar una pantalla.

Favorece la preferencia de Diego por claridad y sobriedad:

- Jerarquía mediante tamaño, peso, alineación y espacio. Usa pocos estilos reutilizables; el contenido decide la densidad.
- Tipografía legible; la fuente del sistema es una opción suficiente. Conserva zoom y ampliación de texto; no traduzcas tamaños nativos de Apple a píxeles web como reglas.
- Acentos de color con significado, acompañados de texto o iconos comprensibles. Unidades cerca de las cifras y números estables al comparar resultados.
- Acción principal reconocible y controles familiares. Prioriza componentes existentes o nativos antes de inventar gestos.
- Estados de espera, vacío, error o resultado parcial solo cuando correspondan al flujo. El progreso mostrado debe provenir de información real.

Apple es referencia de criterio, no obligación de apariencia: superficies opacas, bordes o una composición distinta son válidos. No exigir vidrio, blur, degradados, modo oscuro, springs ni una biblioteca concreta.

Da feedback inmediato sin ejecutar acciones sensibles antes de confirmar el gesto. Añade movimiento si explica un cambio o conserva orientación; debe poder interrumpirse y tener alternativa reducida. Evita retrasar tareas frecuentes o animar cifras de manera que parezcan resultados distintos.

Al implementar o afinar una transición o gesto, consulta [detalle de interacción](references/detalle-de-interaccion.md). Conserva las técnicas pertinentes del original sin cargar sus recetas para una pantalla estática.

Los estados y valores siguen el contrato: cargador registrado no significa disponible; una línea entre coordenadas no prueba ruta vial. Identifica datos de ejemplo. Mantén teclado, foco y significado independiente del color.

Entrega la propuesta o cambio pedido con una justificación breve. Cuando exista una pantalla ejecutable, inspecciona el resultado visible; no conviertas cada ajuste tipográfico en una auditoría general.

Fuentes, 14-10-2026: [Emil apple-design](https://github.com/emilkowalski/skills/blob/2d228630ba1446365f614a108cb8252f1feda202/skills/apple-design/SKILL.md), [Apple Typography](https://developer.apple.com/design/human-interface-guidelines/typography) y [Apple Motion](https://developer.apple.com/design/human-interface-guidelines/motion). Consulta detalle solo si la interacción lo requiere.
