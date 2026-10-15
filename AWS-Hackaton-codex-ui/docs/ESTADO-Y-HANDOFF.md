# ZMD Mobility — estado y continuidad

**Decisión vigente de Diego, 15-10-2026:** implementar la **estética de Cristal con los tamaños de botones y la distribución de Esencial**. Es la dirección visual aprobada; ya no hay que volver a elegir entre variantes. Base en `explorations/webapp/plan.html`, conservando intactas las exploraciones anteriores. Diego también autorizó un nuevo chat para construir autónomamente el inicio/dashboard, una barra lateral discreta y un avatar de iniciales abajo con menú de ajustes/sesión. Opus 5.5 mediante Kiro como diseñador e implementador principal; Astra como auditor, crítico y depurador, con autoría comprobada. Investigar guías/skills de dashboard mediante find-skills. [Traspaso de la webapp](WEBAPP-HANDOFF.md). La identidad sigue pendiente; no añadir variables del motor antes de las respuestas del equipo.

**Trabajo paralelo autorizado:** chat **logo** (`01a13dc0-6ef2-7893-aa59-cc691b35901d`, Astra 6) para 40 ideas nuevas en HTML interactivo, incluyendo minimalismo, vínculos con electromovilidad/eficiencia/IA y tipografía. Uso real de Opus 5.5 mediante Kiro sujeto a evidencia de sus respuestas. Escrituras aisladas en `explorations/logo-40/` y `docs/LOGO-40-HANDOFF.md`; no mezcla automática de trabajo en curso.

## Antecedentes conservados

**Feedback posterior, 15-10-2026:** Diego rechazó las cuatro interfaces y las treinta identidades: «no tienen nada que ver con el tema». Ninguna está seleccionada. Nueva ronda en `explorations/round-2/`, centrada en vehículos eléctricos, batería, entregas y recargas; la identidad vuelve a partir de ZMD y elementos eléctricos reconocibles. Se conserva lo anterior como historial descartado.


Actualización: **14-10-2026, America/Santiago** (la sesión transcurre el 15-10 UTC). Fuentes principales: encargo y respuestas de Diego de esta sesión; Git local; README/AGENTS/modelamiento de Daniel; mensaje de Lucas conservado en [base_conocimiento](base_conocimiento.md). Los estados de herramientas se documentan con pruebas, no con sus propias afirmaciones.

## Encargo y decisiones del usuario

ZMD Mobility es la consultora; CASE plantea el desafío. Daniel Hermosilla y Lucas Zulueta llevan el motor/backend. Diego Caballero conduce producto, UI, mapa e integración visual.

Diego autorizó dirección autónoma, investigación y agentes. Pidió explícitamente usar Kiro Opus 5.5 Max y Sonnet 5.5 Max cuando estuvieran realmente disponibles, además de Astra y Sol. La prioridad es calidad con arquitectura simple, sin maximizar cantidad de código.

Confirmó:

- Web para computador; móvil secundario.
- Interfaz limpia, con claridad, distribución y cuidado de Apple/Notion como referencias.
- Mapa central, datos intercambiables, carga → ejecución → comprensión de resultados.
- Cuatro alternativas de interfaz; seis logos iniciales y, tras su feedback, **24 conceptos nuevos** vinculados a electromovilidad, eficiencia, ahorro e IA, priorizando minimalismo. Las seis anteriores se conservan. **La elección final es de Diego.**
- Alcance funcional delegado al criterio del equipo. Muchos tokens disponibles no justifican más funcionalidades o infraestructura.
- Continuidad y memoria en documentos del proyecto. Datos simulados siempre identificados.

En la etapa anterior no había dirección aprobada. La decisión vigente selecciona Mapa de flota como base para refinar, sin elegir variante definitiva, logo ni reemplazo de Streamlit por React. No confundir la existencia de prototipos HTML con esa elección.

## Ronda 2, antecedente de la selección actual

Las nuevas propuestas están en `explorations/round-2/`: **Mapa de flota**, **Mesa de despacho**, **Control de batería** y **Recorrido por paradas**. La galería de marca de esa ronda contiene doce conceptos nuevos con ZMD, enchufes, baterías, vehículos y recorridos. Prototipos para comparar, todavía sin elección de Diego.

El mapa ahora usa MapLibre 6.14 y OpenFreeMap; las dos geometrías OSRM tienen secuencias manuales de demostración. Los valores energéticos son ilustrativos, aunque mantienen coherencia aritmética interna. Datos originales y respuestas se conservan en JSON locales ignorados por Git; el README de la ronda explica cómo reconstruirlos. No se calculó una optimización, no se consumieron recursos AWS ni se cambió el motor.

**Siguiente paso:** recibir el feedback de Diego sobre esta ronda. Refinar la dirección que él elija antes de integrar el frontend definitivo. El stack y contrato definitivo siguen pendientes; la nueva cartografía no los aprueba.

## Repositorio y datos

Base inspeccionada: `/Users/caballero/Documents/ChatGPT/AWS/AWS-Hackaton`, `main`, `4750ac8`, remoto DanielHermosilla/AWS-Hackaton. Pull registrado el 14-10 a las 20:34 Chile. La base tiene cinco archivos versionados: `.gitignore`, `AGENTS.md`, `README.md`, `diccionario.md`, `modelamiento.pdf`. La documentación/skills recuperadas estaban locales y no versionadas.

Trabajo UI aislado: `/Users/caballero/Documents/ChatGPT/AWS/AWS-Hackaton-ui`, rama **`codex/ui`**, creada desde esa base. El checkout del motor permanece en `main`. Esto recupera la petición anterior de Diego —interrumpida antes de crear la rama— de concentrar el UI en una rama con destino `main`. La propuesta histórica de migrar a `master` no se ejecutó.

`AWS-Hackaton/data/` faltaba al inicio. Se restauró desde Descargas mediante copias de los seis CSV, dos ZIP y diccionarios; hashes origen/destino iguales, ZIP coincidentes con la evidencia histórica. Datos ignorados por Git, sin publicación. Evidencia local: `data/manifest-restored-20261014.json`. No se repitió el perfil completo ni se recuperaron los antiguos `data/analysis/`. El worktree UI no necesita duplicar telemetría.

Comprobación nueva acotada: CSV público = 81 nodos (1 base, 20 visitas, 60 estaciones); 54 estaciones tienen algún conector CHAdeMO/J1772. Ese conteo **no prueba operabilidad ni disponibilidad**.

## Lo que hicieron Daniel y Lucas

**Daniel, verificado en commits:** incorporó y corrigió README/AGENTS, conservó el diccionario y añadió una formulación MILP en `modelamiento.pdf`. La arquitectura descrita es Python/Pyomo, comprobador independiente, JSON, tuning por Bedrock/LLM4MIP y UI Streamlit. HiGHS está propuesto. No hay implementación ni ejecución del motor visible en este checkout.

**Lucas, texto recibido de Diego:** resume enunciado, flujo y parámetros; propone IDs del CSV, cobertura primero y energía después; aporta estimaciones de capacidad/consumo/velocidad y un ensayo con distancias rectas. El texto exacto recibido y su clasificación están en [base_conocimiento](base_conocimiento.md). Ya no hace falta pedirlo de nuevo. Falta su archivo/commit o notebook original para reproducir las cifras.

No se tocó la formulación, ni se escribió otro solver, estimador energético o backend. Una ausencia en este checkout no demuestra ausencia de avances en sus equipos.

## Discrepancias preservadas

| Tema | Evidencia y tratamiento |
|---|---|
| Cobertura | PPT/README/PDF y Lucas maximizan entregas; Diego quiere todas. Separar factibilidad del modelo, cobertura completa y aceptación operativa. Un parcial no se presenta como plan completo. |
| Reserva | Diego admite llegada ≥0; Lucas propone 10–15 %; PDF p.1 exige `b>0`. No elegir un margen desde UI ni modificar PDF. Daniel/Lucas deben resolver la variante. |
| Capacidad y energía | 24 kWh nominales en diccionario; ~16 útiles y 0,156 kWh/km atribuidos a Lucas, todavía sin método reproducible recibido. No fijarlos como verdad en UI. |
| Red vial | PDF usa arcos dirigidos elementales; líneas rectas o rutas elegidas a posteriori por otro servicio no son equivalentes. Presentar geometría exacta del motor cuando exista. |
| Frontend | Streamlit está en nuevos README/AGENTS; React/Vite/MapLibre era propuesta previa. Elegir después de ver las cuatro direcciones y acordar integración. |
| Tiempo | Tiempo de cómputo y duración de la operación son distintos. No inferir duración de carga/ruta sin datos. |
| Disponibilidad | Sesión AWS iniciada no prueba presupuesto ni permisos de Location/Bedrock; conectores registrados no prueban estación libre o utilizable. |

## Propuesta de producto y frontera

Un flujo pequeño: cargar CSV, revisar errores y flota, ejecutar, inspeccionar resultado en mapa/lista, exportar JSON. Edición de coordenadas/nodos puede añadirse cuando resuelva una tarea real; no es necesaria para empezar. Sin autenticación, base de datos, colas, microservicios, seguimiento en vivo ni optimizador alternativo.

Mientras falta el motor, usar **fixtures explícitas y un adaptador en la frontera de presentación**, no un “solver simulado” que haga pasar una heurística nueva por resultado. El primer prototipo solo usa datos sintéticos. La futura UI deberá recibir la misma identidad de escenario/ejecución en todas sus vistas, conservar desconocidos como `null`, invalidar resultados al cambiar entradas y respetar unidades/estados del motor.

La propuesta mínima de intercambio está en [contracts.md](contracts.md); no es un contrato acordado con Daniel/Lucas. No se creó una API ni se implementaron los contratos Python por anticipación.

## Exploraciones y validación

`explorations/` contiene propuestas de diseño separadas del producto. Sirven localmente con:

```sh
cd /Users/caballero/Documents/ChatGPT/AWS/AWS-Hackaton-ui
python3 -m http.server 4173 --bind 127.0.0.1 --directory explorations
```

Abrir `http://127.0.0.1:4173/`. No se necesitan cuentas, secretos o dependencias de aplicación. Los esquemas locales no descargan cartografía y no son mapas viales. Las cifras no se presentan como optimización real. El README de exploración registra interacción y pruebas concretas.

Direcciones previstas: Atlas (mapa continuo), Cuaderno (documento operativo), Secuencia (flujo guiado), Balance (comparación por vehículo). Las identidades se eligen por separado. El estado de cada entrega y las recomendaciones se cierran tras la inspección visual.

## Siguiente acción vigente · 15-10

1. Cerrar la base Cristal + Esencial con verificación visible y cederla al nuevo chat de dashboard.
2. En ese chat: investigar guías/skills, construir Inicio, sidebar discreta y perfil/ajustes según [WEBAPP-HANDOFF.md](WEBAPP-HANDOFF.md), con Opus como diseñador/implementador y Astra como auditor. Avanzar sin preguntas rutinarias.
3. Con Daniel/Lucas: recibir ejemplo real de entrada/salida y ejecución; confirmar reserva, cobertura, energía y geometrías. No hace falta volver a pedir el diccionario ni repetir login.
4. Integrar el frontend elegido con el motor cuando exista esa frontera, conservando procedencia, errores y estados reales.

La elección visual ya está resuelta. La integración completa y la identidad siguen pendientes; terminar una base visual no termina el proyecto entero.

## Hito de exploración preparado

- Cuatro prototipos locales ejecutables: Atlas, Cuaderno, Secuencia y Balance; [galería](../explorations/index.html).
- Identidad ampliada según feedback: [24 conceptos nuevos](../explorations/identity-lab/index.html), más [seis originales](../explorations/identity/index.html). 90 SVG entre símbolos y firmas claras/oscuras. No hay elección de marca todavía.
- MapLibre es el renderizador recomendado; Amazon Location es proveedor candidato condicionado a permisos/presupuesto. No se crearon recursos AWS ni se envió el CSV a routing. Geometría exacta del motor como fuente del recorrido; [investigación](MAPA-Y-BASE.md).
- Kiro CLI/ACP y modelos Opus/Sonnet 5.5 con `max` fueron verificados mediante respuestas reales. La creación larga falló; Atlas/Secuencia fueron implementados por Sol, con aportes textuales de Sonnet, sin atribuirlos falsamente a Opus. Limitaciones y continuidad privada: [KIRO-Y-AGENTES](KIRO-Y-AGENTES.md).
- Recomendación de composición: Atlas por centralidad del mapa y detalles con claridad de Cuaderno. Esperar selección/refinamiento de Diego.

El navegador local usa puerto 4173 y la galería principal enlaza todas las propuestas. Si el proceso no sigue activo, usar el comando anterior. No hay deploy público ni integración efectiva con el motor.
