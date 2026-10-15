# Skills necesarias antes de comenzar el software

**Revisión del 14-10-2026 solicitada por Diego.** Resultado: conservar las cinco skills propias y añadir **dos capacidades acotadas: logo y mapa operativo**. No encontramos una carencia que justifique otra skill genérica de código, diseño o motion antes de decidir el stack.

Las skills orientan el trabajo; **no garantizan un estándar máximo**. El siguiente avance importante será probar una primera integración real, con código revisado y una interfaz usable. Acumular instrucciones no reemplaza esa evidencia.

## Cómo se hizo la selección

Tres agentes repartieron código/calidad, diseño/motion/logo y mapas. Usaron `find-skills` con **12 búsquedas CLI**, además de revisar documentación primaria y lo ya instalado. Se inspeccionaron **15 SKILL.md completos y dos parcialmente**; un resultado adicional de Leaflet no estaba en el árbol actual del repositorio indicado por el buscador. No se afirma haber probado todas las coincidencias.

Se compararon instrucciones, dependencias, licencias y cambios respecto a los ensayos anteriores. Las estrellas y las instalaciones sirvieron para descubrir, no para aprobar. No se ejecutaron scripts de proveedores externos ni se añadieron hooks, runtimes, bibliotecas del producto o servicios.

## Qué queda disponible

| Necesidad | Repertorio seleccionado | Decisión |
|---|---|---|
| Contexto y coordinación proporcional | `zmd-project-context` | Conservar; los acuerdos viven en documentos, no repetidos en cada skill |
| Integración con el motor | `zmd-contract` | Conservar; IDs, unidades, estados, errores y ejecuciones |
| Código comprensible y correcto | `zmd-code-review` | Conservar; sin arquitectura por plantilla ni cuotas artificiales |
| Diseño y detalle de interacción | `zmd-apple-design` | Conservar; Apple/Emil/Impeccable siguen como especialistas existentes |
| Movimiento | Referencia de Apple adaptada, `animate` y `review-animations` existentes | No añadir otra suite; usar solo cuando haya una interacción que lo necesite |
| QA visible y accesibilidad | `zmd-ui-qa` | Conservar; comprobar ejecución real y distinguirla de inspección |
| Identidad visual | **`zmd-logo-creator` nueva** | Crear/refinar SVG editable y comprobar usos concretos, sin APIs obligatorias ni paquetes de decenas de variantes |
| Operación geográfica | **`zmd-map-ui` nueva** | Capas, coordenadas, mapa/lista, cámara, estados, atribución y ciclo de vida; separada del solver |

Las dos nuevas son redacción original del proyecto, con referencias oficiales consultables cuando hacen falta. No convierten un estilo, un proveedor ni una secuencia de trabajo en obligación. [Guía de uso de las siete skills](SKILLS.md).

## Candidatas que no instalamos

| Candidata | Conclusión para ZMD |
|---|---|
| [Vercel React Best Practices](https://github.com/vercel-labs/agent-skills/blob/063bee94c3f4df8453406c830b0a7df0f2860278/skills/react-best-practices/SKILL.md) | **Reservar si elegimos React.** El commit sigue igual al ensayado anteriormente. No justifica por sí sola Next.js, nuevas cachés ni dependencias. |
| [Software Design Philosophy](https://github.com/wondelai/skills/blob/c172996495bed0fcd26896a9416b2093fd7073f0/software-design-philosophy/SKILL.md) | Buen criterio sobre abstracciones; proceso de puntuación 10/10 y cuotas de tiempo innecesarios frente a nuestra revisión. |
| [TDD de Matt Pocock](https://github.com/mattpocock/skills/blob/49dd158d1076134a641b33efb035946536778336/skills/engineering/tdd/SKILL.md) | Pruebas de comportamiento útiles, pero otro workflow con aprobaciones y dependencias de skills. No duplicarlo. |
| [Frontend Security](https://github.com/schalkneethling/webdev-agent-skills/blob/85710096f476abb8910033f53667f153fa8062ff/frontend-security/SKILL.md) | Dos fallos reproducidos en ejemplos de validación; no copiar estas recetas. Consultar OWASP y el framework elegido. |
| [ReScienceLab logo-creator](https://github.com/ReScienceLab/opc-skills/blob/d1949b21c4ce7fc115bed6cb88f932332d352bcb/skills/logo-creator/SKILL.md) | Tres APIs, otra skill y lotes de 20 imágenes por defecto; coste de proceso sin necesidad actual. |
| [rknall SVG Logo Designer](https://github.com/rknall/claude-skills/blob/ca7fbd0e07f824b119030f323da3409bc779f9bc/svg-logo-designer/SKILL.md) | Paquete habitual de 30–75 archivos y licencia abierta no identificada. |
| [kbravh SVG logo creator](https://github.com/kbravh/skills/blob/9e35f9ecb6edff654c4f5541ee6ace567f8c2d09/logo-design/skills/svg-logo-creator/SKILL.md) | Referencia ligera y MIT, pero variantes y medidas obligatorias. Se prefirió una skill propia proporcional al encargo. |
| [LottieFiles motion-design](https://github.com/LottieFiles/motion-design-skill/blob/f9a8a041b85185ee4881b3471d3415e939aac772/skills/motion-design/SKILL.md) | Duplica especialistas y prescribe movimiento ambiental como regla general; mal ajuste como norma del mapa operativo. |
| [MapLibre agent skills](https://github.com/maplibre/maplibre-agent-skills/tree/ca1eae70deddff697a7c392f8735e37d64cb61ea/skills) | Cartografía y conexión de fuentes aportan referencias. No instalar toda la familia ni convertir umbrales de rendimiento en leyes. |
| [Mapbox agent skills](https://github.com/mapbox/mapbox-agent-skills/tree/f71cd72b8d8937b06db440538bd65559eb792c49/skills) | Consultar piezas pertinentes si se elige Mapbox. Evitar procedimientos que requieren MCP ausentes y recetas sin prueba sobre nuestra carga. |
| [OpenMapStack](https://github.com/jaakla/openmapstack-skills/blob/861ed60dfba5c0893b75789ef68aaf1d8b800957/skills/open-map-stack/SKILL.md) | Demasiada infraestructura GIS para los 81 nodos del caso público. No instalar por anticipación. |

Son juicios de encaje y de las instrucciones inspeccionadas, no una descalificación de cada repositorio completo. Más detalles y pines en los informes conservados en el workspace de investigación.

## Qué comprobamos y qué no

- **Código:** un ensayo sintético de seis casos reprodujo dos defectos en los ejemplos de seguridad (decimal parcialmente numérico y escape a carpeta hermana con prefijo común), con cuatro controles correctos. No prueba una vulnerabilidad del producto, que todavía no existe.
- **Logo:** aplicación de la skill a la marca ficticia NODO; SVG editable y vista en Chrome con instancias de 24 y 200 px, claro/oscuro, nombre accesible y teclado. No es el logo ZMD, una prueba con usuarios ni una búsqueda de exclusividad.
- **Mapa:** 11 pruebas Node de datos/estado distinguen una miniintegración deliberadamente defectuosa de su corrección. Utilizan un puerto simulado; **no prueban MapLibre, navegador, rendimiento ni factibilidad de rutas**.
- **Revisión:** otro agente leyó ambas skills y contrastó sus límites y fuentes. Los ensayos logo/mapa fueron escritos por agentes que participaron en la investigación; no son una comparación ciega ni demuestran mejora causal.

Las pruebas históricas de movimiento, contrato y UI se conservaron; no se repitieron sin cambios que lo justificaran. Los resultados completos, salidas de búsqueda, capturas, código sintético y hashes están en `memoria-hackaton/10-planificacion/skill-readiness-20261014/` del workspace de investigación.

## Qué sigue

El repertorio ya permite comenzar a acordar la base y el primer recorrido. La propuesta es **TypeScript + React + Vite**, con **MapLibre** como primera opción y Leaflet como alternativa suficiente si buscamos un mapa 2D más sencillo. Proveedor cartográfico, geometría vial, integración y motor permanecen abiertos. [Comparación, repositorios y decisiones](MAPA-Y-BASE.md).

No falta otra skill general por instalar para empezar. Reabrir la búsqueda cuando una tecnología elegida o un problema real revele una necesidad específica.
