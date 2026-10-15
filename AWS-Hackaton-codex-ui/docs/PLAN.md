# Plan abierto de producto y desarrollo

**Estado actualizado, 15-10-2026:** Diego aprobó el híbrido Cristal (estética) + Esencial (distribución y tamaños de controles) y pidió implementarlo. Autorizó un nuevo chat autónomo para inicio/dashboard, sidebar discreta y perfil con ajustes/sesión, usando Opus 5.5 como diseñador/implementador y Astra como auditor. [Encargo concreto y continuidad](WEBAPP-HANDOFF.md). La integración con el motor y la identidad siguen pendientes; no reabrir la elección visual ni inventar nuevas métricas.

Equipo: **ZMD Mobility**, nuestra consultora. Empresa que plantea el desafío: **CASE**. Nombres aclarados por Diego el 14-10-2026.

14-10-2026. **Encargo autorizado de exploración y posterior desarrollo incremental.** Diego pidió recuperar el nuevo estado, investigar mapas y Kiro y presentar cuatro propuestas de interfaz y seis logos. La elección visual quedó resuelta el 15-10 con Cristal + Esencial; la frontera de integración sigue pendiente. El mapa es parte principal de la operación. La [base técnica propuesta](MAPA-Y-BASE.md) prepara esas decisiones sin anticipar las conclusiones del motor de Daniel/Lucas.

## Qué resultado preparar

El núcleo confirmado es un programa que produzca rutas evaluables con archivos intercambiables. [Reglas y pendientes](FUENTES.md). Proponemos acompañarlo con una experiencia comprensible y una presentación basada en evidencia. La forma de entrega, despliegue y duración del pitch se confirmarán con organización.

| Capa del resultado | Para qué sirve | Estado |
|---|---|---|
| Programa reproducible | Ejecutar otra instancia y comprobar resultados | Comportamiento anunciado por CASE; protocolo pendiente |
| Interfaz | Ayudar a una persona a entender y usar la salida del motor | Mapa operativo principal confirmado por Diego; perfil de jefa de flota; flujo concreto por acordar |
| Evidencia y explicación | Mostrar resultados, límites y valor al jurado | Propuesta; rúbrica y pitch sí publicados |

No confundimos un prototipo presentable con una operación comercial certificada. El nivel de producto que construyamos debe responder al tiempo y alcance acordados.

## Usuario y problema de la presentación CASE

**Verificado directamente en el PPTX, diapositiva 3 y notas, 14-10:** Carla representa a una jefa de flota de reparto. Decide qué vehículo visita cada local sin certeza de tener energía para regresar; esa incertidumbre puede hacer que acorte recorridos, deje entregas o vuelva al diésel. Es un caso ilustrativo, no una entrevista de usuario realizada por el equipo.

Diego pidió utilizar esa presentación para orientar la interfaz. Por ello, el usuario principal de referencia es **quien planifica la operación de la flota**. Daniel/Lucas y el jurado necesitan evidencia técnica, pero no desplazan esa tarea principal.

| KPI / condición CASE (diap. 5–7) | Pregunta de la persona | Traducción propuesta a la interfaz |
|---|---|---|
| Todos los pedidos completados — aclaración de Diego, 14-10 | ¿Quedaron atendidos todos los clientes? | Conteo sobre el total; un resultado parcial se identifica como incompleto, no como solución válida |
| Retorno de ambos vehículos sin quedar sin energía; llegada ≥ 0 — aclaración de Diego | ¿Pueden completar el recorrido y volver? | Estado por vehículo y evidencia energética disponible; no añadir una reserva obligatoria inventada |
| Energía total, kWh | ¿Cuánta energía consume este plan? | Métrica del motor con unidad; comparación solo si es válida |
| Tiempo de cómputo, segundos | ¿Cuánto tarda en obtener una respuesta útil? | Tiempo medido; distinguir espera, resultado y límite alcanzado |
| Escalabilidad y adaptación de red | ¿Funciona con otra instancia? | Identidad de entradas y resultados trazables al mismo programa |

No convertir “incertidumbre” o “replanificación en línea”, descritas como crecimiento, en features obligatorias antes de acordarlas con Daniel. La forma visual de mostrar estos resultados sigue abierta.

El diccionario remitido por AWS el 14-10 ya define las variables y el tratamiento temporal de la columna de energía; revisar [DATOS](DATOS.md) antes de pedir esas definiciones a Daniel. El equipo todavía debe definir cómo aplica los datos históricos a rutas nuevas; la documentación del dataset no elige su motor.

## Alternativas consideradas

| Dirección | Decisión que ayuda a tomar | Ventaja | Coste o límite |
|---|---|---|---|
| Consola de operación | Qué plan ejecutar y por qué | Flujo sencillo y relato claro | Puede ocultar detalle experimental si no se ofrece al desplegar |
| Laboratorio de escenarios | Cómo cambian resultados al variar entradas | Útil para Daniel/Lucas y análisis | Más controles, más estados y mayor carga de explicación |
| Consola con detalle técnico desplegable | Entender el plan y consultar su evidencia | Equilibra presentación y análisis | Requiere recortar cuidadosamente para no construir dos productos |

**Dirección propuesta a partir del enunciado:** consola de operación, con detalle técnico desplegable cuando el motor lo entregue. No crear funciones nuevas únicamente para llenar la interfaz. El laboratorio queda como alternativa secundaria si el equipo encuentra una necesidad concreta; no es necesario pedir de nuevo a Diego que identifique al usuario que ya describe CASE.

## Qué necesitamos de Daniel y Lucas

Una conversación corta y un ejemplo real de entrada/salida pueden bastar para empezar. Acordar:

1. Qué resuelve el motor, restricciones confirmadas y supuestos que mostrará.
2. Qué entra y qué sale: campos, IDs, unidades, estados y errores. Si todavía no existe API, un archivo de ejemplo puede definir la frontera.
3. Cómo se ejecuta y cuánto tarda en un caso medido; qué significa “sin solución”, “tiempo agotado” o “no certificable”.
4. Qué resultados puede mostrar la UI sin recalcular una matemática distinta.
5. Qué queda fuera del primer producto y quién integra cambios de la frontera.

No se exige JSON, REST, microservicios, contenedores ni una base de datos antes de conocer esa necesidad. Tampoco se elige un framework o solver por una skill.

## Diseño que Diego puede dirigir

**Brief propuesto:** una persona debe reconocer el escenario activo, entender el resultado y encontrar el siguiente paso. Debe poder diferenciar cálculo real, supuesto y ejemplo de diseño.

El encargo inicial comparó cuatro composiciones distintas; la ronda vigente refina únicamente Mapa de flota en cuatro variantes totales. Se conservan la original y tres variaciones cercanas. La exploración de identidad pasa a 40 ideas en otro chat autorizado. Se pueden combinar y refinar. No mantener los cuatro prototipos en producción ni tratar la recomendación del agente como selección aprobada.

Dirección visual solicitada: tipografía legible, jerarquía evidente, espacio consistente, superficies discretas y acentos de color con significado. Elegir pocos estilos reutilizables de texto, espaciado, color y controles. Evitar tarjetas, gráficos o animaciones que no respondan a una pregunta del usuario.

El mapa principal se acompaña de información textual operable; una línea entre coordenadas se rotula como esquema mientras no exista geometría vial verificada. Si hay SOC, mostrar unidad y criterio aplicado; un cargador registrado no aparece como “disponible” sin información que lo respalde. [Opciones de renderizador, proveedor y guías de integración](MAPA-Y-BASE.md).

Movimiento solo para explicar un cambio, conservar orientación o dar respuesta a una acción. Mantener teclado, foco visible, zoom y reducción de movimiento. Apple/Notion son referencias de claridad; no una obligación de copiar su apariencia. Guías: [Apple HIG](https://developer.apple.com/design/human-interface-guidelines), [W3C](https://www.w3.org/WAI/WCAG22/quickref/) y [Vercel](https://vercel.com/design/guidelines), consultadas el 14-10.

## Desarrollo cuando el alcance esté acordado

**Propuesta:** completar primero un recorrido pequeño que conecte entrada, motor y salida visible. Reutilizar patrones existentes y mantener separadas las responsabilidades que realmente cambien de forma independiente. Un módulo no necesita convertirse en un servicio.

Por cambio sustantivo, pedir al agente: propósito, archivos que tocará, resultado observable y comprobación adecuada. No exigir documentación ceremonial para cada ajuste de texto o estilo. Una abstracción nueva debe resolver repetición o una necesidad actual; una dependencia debe aportar más que su coste de integración.

Para el frontend, el contrato del motor será la referencia de cifras y estados. Para el motor, las reglas acordadas y pruebas independientes serán la referencia de validez. Ni el mapa valida energía ni una prueba unitaria del algoritmo demuestra que la interfaz sea utilizable.

## Revisores independientes con trabajo concreto

| Momento | Revisor | Evidencia que revisa | Condición de cierre |
|---|---|---|---|
| Alcance y primera integración | Contrato y simplicidad | Ejemplo real, unidades, recorrido y cambios propuestos | Frontera entendible; decisiones abiertas explícitas; complejidad justificada |
| Lógica relevante del motor | Daniel/Lucas con apoyo de agente independiente | Casos que cumplen y violan restricciones; cálculo comprobable | Sin violaciones conocidas de las restricciones acordadas; límites registrados |
| Primer flujo usable | UX y accesibilidad | Navegador real, teclado, zoom, errores y datos difíciles | Acción principal realizable; estados y cifras comprensibles |
| Cambio relevante de código | Revisor de código | Diff y ejecución de comprobaciones pertinentes | Sin fallo funcional importante ni complejidad innecesaria demostrada |
| Lentitud observada o cierre | Rendimiento e integración | Medición separada de motor, red y pantalla; recorrido completo | Se cumple un objetivo acordado, sin optimizaciones especulativas |
| Preparación de entrega | Reproductor independiente | Checkout/paquete, instrucciones, dependencias y otra entrada | Puede repetir el resultado y explicar sus límites |

El implementador y el revisor no deben ser el mismo agente cuando la independencia aporte valor. Un integrador mantiene coherente la frontera y los archivos compartidos; los revisores no los reescriben simultáneamente. Se pueden paralelizar revisiones de aspectos distintos.

**Evitar auditoría infinita:** un informe por hito, corrección de hallazgos relevantes y comprobación enfocada. Si persiste una discrepancia después de dos rondas, presentarla al responsable humano con evidencia en lugar de encadenar agentes. Los cambios cosméticos menores no reinician toda la auditoría.

Cada hallazgo: **pasos para reproducir → esperado/observado → impacto → archivo/evidencia → arreglo mínimo**. No aceptar “está perfecto” sin prueba ni refactorizar solo por gusto del revisor. [Criterios de Google](https://google.github.io/eng-practices/review/reviewer/looking-for.html), consulta 14-10.

## Qué probar, proporcional al cambio

- Motor/contrato: IDs y unidades, todos los pedidos, retorno y condiciones energéticas acordadas; rechazar pedido omitido o agotamiento que impida completar la ruta. Llegada exactamente en cero no falla por una reserva adicional inventada. Ajustar los casos al modelo de Daniel.
- Integración: mismo escenario en todas las vistas; cambio de entrada no deja resultados viejos como actuales; error o tiempo agotado se comunican.
- UI: flujo principal, vacíos/errores, etiquetas largas, teclado, zoom y tamaño de pantalla utilizado para presentar.
- Entrega: comando reproducible, dependencias fijadas, datos locales fuera de Git y métricas realmente medidas.

Si se elige un frontend web, Playwright es un candidato para probar comportamiento visible; no es una dependencia aprobada todavía. Las pruebas automáticas de accesibilidad se complementan con revisión manual. [Documentación Microsoft](https://playwright.dev/docs/accessibility-testing), consulta 14-10.

## Orden de trabajo vigente

1. Consolidar el pull, diccionario, formulación, discrepancias y responsabilidades; conservar originales.
2. Verificar Kiro y modelos mediante una ejecución real y decidir cartografía con fuentes primarias.
3. Consultar formato, profundidad de edición y preferencias visuales. Preparar cuatro prototipos. Tras seis logos iniciales, Diego pidió muchas más opciones mínimas vinculadas a electromovilidad, eficiencia, ahorro/IA: preparar 24 nuevos sin borrar los originales. Diego selecciona/refina.
4. Acordar frontend y frontera con el motor. Streamlit (guía del repo) y React (propuesta anterior) permanecen como discrepancia visible hasta resolverla.
5. Implementar un único flujo: cargar escenario → validar → ejecutar o ver ejemplo rotulado → inspeccionar rutas/energía → exportar resultado. Datos sintéticos no acreditan optimización ni integración real.
6. Probar mapa/lista, teclado, errores, respuesta obsoleta, coordenadas, cero legítimo y datos faltantes. Registrar evidencia y handoff.

MVP propuesto: una aplicación local sin autenticación ni base de datos, con el detalle técnico disponible a demanda. La edición gráfica de paradas se decidirá con Diego. No incluir seguimiento en vivo, predicción nueva de energía, optimizador alternativo, cuentas de usuario ni paneles empresariales por anticipación.

[Estado de ejecución y pendientes concretos](ESTADO-Y-HANDOFF.md).
