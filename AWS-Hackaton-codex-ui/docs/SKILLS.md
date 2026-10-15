# Siete skills a medida para ZMD Mobility

**Nombres aclarados por Diego, 14-10-2026:** ZMD Mobility es nuestra consultora; CASE es la empresa de electromovilidad del desafío. Los nombres `case-*` usados en ensayos anteriores corresponden ahora a `zmd-*`, con la misma función.

**14-10-2026. Selección ajustada por petición de Diego.** El catálogo anterior contenía 13 repositorios/guías evaluados, no 13 skills instaladas. La nueva búsqueda con tres agentes añade **solo logos y mapas** a las cinco capacidades existentes. [Evaluación y descartes](SKILLS-PREPARACION.md). Sin hooks, memoria automática ni elección obligatoria de stack.

| Skill | Cuándo importa | Ejemplo de encargo |
|---|---|---|
| [zmd-project-context](../.agents/skills/zmd-project-context/SKILL.md) | Hechos, fase, acuerdos y fuentes; coordinación breve si realmente se delega | «Recupera qué está confirmado y prepara el encargo para integrar UI y motor». |
| [zmd-contract](../.agents/skills/zmd-contract/SKILL.md) | Definir o cambiar datos entre el motor de Daniel/Lucas y la interfaz de Diego | «Acordemos campos, unidades, estados y un ejemplo de salida; marca lo que falta confirmar». |
| [zmd-code-review](../.agents/skills/zmd-code-review/SKILL.md) | Fallos y complejidad en un cambio sustantivo; simplificación si está pedida | «Revisa este cambio; señala errores y abstracciones que sobren con evidencia». |
| [zmd-apple-design](../.agents/skills/zmd-apple-design/SKILL.md) | Composición, tipografía, jerarquía y feedback de pantallas ZMD Mobility | «Mejora esta pantalla para que la jefa de flota entienda el resultado y su siguiente acción». |
| [zmd-ui-qa](../.agents/skills/zmd-ui-qa/SKILL.md) | Probar el flujo visible, errores, datos difíciles e integración | «Comprueba este recorrido; separa lo observado de lo que falta probar». |
| [zmd-logo-creator](../.agents/skills/zmd-logo-creator/SKILL.md) | Crear o refinar identidad gráfica, SVG editable y exportaciones útiles | «Trabaja el logo y comprueba cómo se lee en la cabecera y la presentación». |
| [zmd-map-ui](../.agents/skills/zmd-map-ui/SKILL.md) | Integrar mapa, capas, selección, cámara y lista operable | «Conecta las paradas y rutas con el mapa sin inventar geometría vial ni disponibilidad». |

`zmd-apple-design` es la **adaptación local de Apple Design de Emil Kowalski**, contrastada con Apple HIG. No es una publicación oficial de Apple ni una obligación de copiar su apariencia. El nombre específico evita reemplazar la skill global `apple-design`.

## Uso flexible

No se cargan las siete por cada petición. Contexto se consulta una vez; luego se aplica la capacidad que responda a la tarea. Un ajuste de espaciado no necesita reabrir contrato, ejecutar tres revisores ni crear un plan nuevo.

Las skills combinan ideas útiles de ECC y guías existentes con el contexto ZMD Mobility. No prescriben framework, solver, API, microservicios, cobertura del 80%, número de agentes, tamaño de funciones o una estética obligatoria. Las restricciones firmes conservan datos, acuerdos y honestidad de resultados.

En una integración importante, el recorrido natural puede ser **contrato → trabajo acotado → revisión → comprobación visible**. Es una orientación por necesidad, no una cadena automática. Un revisor puede terminar con cero hallazgos; un fallo no resuelto sigue identificado.

Apple Design favorece claridad, tipografía legible, espacio consistente y acentos útiles. Materiales, densidad y movimiento se deciden por la tarea. Una interfaz opaca, sin animaciones y con fuente del sistema puede ser la mejor solución.

## Lo que salió del repertorio activo

Se fusionaron revisión y simplificación; coordinación quedó en contexto. Las pautas útiles de Emil, Vercel, Google, W3C y break-ui se incorporaron selectivamente. No añadimos workflows completos de Superpowers, Impeccable, generadores de frontend ni runtimes de ECC.

React, Motion, Playwright, Supabase u otras herramientas se evalúan cuando el producto y stack los necesiten; no son dependencias elegidas. Las instalaciones globales existentes se conservaron para otros proyectos. Para ZMD Mobility se prioriza esta selección, sin sumar automáticamente sus equivalentes globales.

[Comparación de las cinco candidatas de ECC y Apple Design](SKILLS-COMPARACION.md). La investigación amplia y sus enlaces permanecen como archivo consultable, no como instrucciones por defecto. [Auditoría original ECC](REVISION-ECC.md).

## Ensayos posteriores y especialistas

El [ensayo anterior del 14-10](SKILLS-ENSAYOS.md) comparó originales/adaptadas en cinco encargos y probó siete candidatas encontradas con `find-skills`, instalada como buscador global. Se conserva ese núcleo de cinco. Apple incorpora una referencia condicional de continuidad de movimiento; `animate`, `review-animations`, Impeccable y depuración sistemática siguen disponibles como especialistas existentes. Vercel React queda condicionado al stack. No cargar este repertorio completo para trabajar una pantalla.

La [revisión posterior de preparación](SKILLS-PREPARACION.md) incorpora `zmd-logo-creator` y `zmd-map-ui` por necesidades explícitas, con referencias técnicas selectivas. Son instrucciones originales del proyecto; no se instalaron suites de logos, GIS o motion. Ninguna skill garantiza por sí sola calidad de producto.

## Instalación y mantenimiento

Hay copias de estas siete skills en `.agents/skills`, `.claude/skills` y `.kiro/skills`. `skill-manifest.json` registra hashes. La fuente mantenida en el workspace de investigación es `skillset/skills/`; los cambios se sincronizan desde allí. No editar cada copia de forma independiente.

Los archivos quedan disponibles para descubrimiento por el cliente; esto no demuestra que una conversación abierta haya recargado el catálogo. En una sesión nueva, comprobar la selección por nombre.

Solo ampliar o dividir una skill si una necesidad concreta o un uso real muestra que falta contexto o se mezclan responsabilidades. Mantener decisiones cambiantes en [CONTEXTO.md](CONTEXTO.md), no duplicarlas en las skills. El proyecto prepara su desarrollo; [mapa y base técnica](MAPA-Y-BASE.md) permanecen como propuesta.

## Comprobación de disponibilidad en esta etapa

Se verificaron las siete skills y los 63 archivos de sus copias `.agents/.claude/.kiro` contra `docs/skill-manifest.json`: 63 hashes coincidentes, sin conflictos. No se añadieron skills globales ni nuevos frameworks. La guía de entrada de Claude/Kiro se actualizó al estado real tras el pull; las skills de origen se conservaron.
