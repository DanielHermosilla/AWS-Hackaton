# Glosario de ZMD Mobility y fuentes del desafío CASE

Consulta: **14-10-2026, America/Santiago**. Este archivo sirve para ubicar conceptos y hacer preguntas. No selecciona tecnologías. [Evidencia de entrega](FUENTES.md) · [Datos recibidos](DATOS.md).

## Los enlaces de contexto

| Fuente | Qué aporta | Preguntas que ayuda a responder |
|---|---|---|
| [AWS Builder — espacio Breaking Barriers](https://builder.aws.com/connect/space/2ae550db-b363-308e-9727-97cc44928f76/breaking-barriers-chile-2026) | Publicaciones de organización y enlaces a registro, taller, desafíos y grabaciones | ¿Hay un anuncio posterior? ¿Cuál es el portal enlazado por AWS? |
| [Portal original que enviaste: Integra](https://d78v2swml9yu2.cloudfront.net/?inst=integra) | Recursos de las instituciones; ese parámetro abre Integra | ¿Dónde están los archivos de cada desafío? |
| [Vista correcta de CASE: U. de Chile → C-1](https://d78v2swml9yu2.cloudfront.net/?inst=uchile&challenge=c-1) | Electromovilidad.zip y presentación CASE | ¿Cuál es el enunciado y paquete del proyecto elegido? |
| [Taurus — página del evento](https://www.taurusmkt.com/breakingbarrierschile) | Agenda, rúbrica y descripción general | ¿Cuándo terminamos? ¿Qué evalúa el jurado? |
| [Grabaciones preparatorias](https://dxt5re7ypebh7.cloudfront.net/videos.html) | Servicios Core, Kiro IDE y AI-DLC | ¿Qué explicó el taller? Formación no equivale a base del concurso |
| [Registro de equipos](https://dxt5re7ypebh7.cloudfront.net/equipos.html) | Registro de integrantes/desafío | ¿Dónde se registra el equipo? No es el canal final de entrega |
| [Directorio público](https://dxt5re7ypebh7.cloudfront.net/equipos-publico.html) | Equipo, integrantes y desafío que utilizarán los jueces | Verificado: ZMD MOBILITY, tres integrantes, C-1 |
| Diccionario remitido por AWS: correo «FW: Readme CASE», 14-10 15:02 Chile | Definiciones, unidades, fórmulas y preparación de telemetría | [Copia local](../data/reference/diccionario-20261014/README.es.md), fuera de Git; consultar antes de repetir preguntas sobre variables |

Acceso verificado por navegador; el recuperador web no pudo leer tres de las cuatro URLs originales. No se enviaron formularios ni mensajes. Las páginas no aportaron una pauta completa de entrega.

## Datos, energía y evaluación

| Término | Significado útil aquí | Fuente / pregunta pendiente |
|---|---|---|
| ZMD Mobility | Nuestra consultora: Diego Caballero, Daniel Hermosilla y Lucas Zulueta | Nombre confirmado por Diego, 14-10-2026 |
| CASE | Centro de Aceleración Sostenible de Electromovilidad; empresa del desafío, distinta de nuestra consultora | [Descripción del evento](https://www.taurusmkt.com/breakingbarrierschile); distinción aclarada por Diego, 14-10-2026 |
| Instancia | Conjunto concreto de entradas con que se ejecuta el programa | Presentación CASE, diap. 6; ¿qué otros parámetros entrega el evaluador? |
| Nodo | Punto identificado: centro, local o estación | CSV: 81 nodos por archivo, no solo los 20 locales |
| Arco / matriz vial | Conexión dirigida / tabla de costes entre puntos | No vienen en el ZIP; ubicación no equivale a distancia de carretera |
| Grafo público / reservado | Instancia para desarrollo / anunciada para evaluación | ¿El CSV `evaluation` es ejemplo o examen final? |
| SOC / SoC | Estado de carga de batería; proporción o porcentaje según contrato | 60% inicial en CASE; no mezclar 60 con 0,6 |
| Capacidad útil | Energía realmente utilizable de la batería | Pendiente de CASE; no deducir de capacidad comercial nominal |
| SOH | Estado de salud de batería | Puede afectar capacidad; no está fijado en las entradas recibidas |
| kWh | Unidad de energía | Cantidad consumida o almacenada, no velocidad de carga |
| kW | Unidad de potencia | `max_power_kw` no prueba potencia recibida por el vehículo |
| Reserva | Energía mínima a la llegada | Diego confirmó ≥ 0 el 14-10; no imponer margen adicional |
| CHAdeMO, CCS, J1772, NACS | Etiquetas de conectores en los CSV de estaciones | Compatibilidad y potencia efectiva de la flota se confirman |
| Estación / puerto | Sitio de recarga / conexión reportada en ese sitio | Puertos registrados no son puertos libres en tiempo real |
| Factibilidad | Cumplir todas las restricciones del ejercicio | Todos los pedidos, retorno y energía; un resultado parcial no es solución válida. No equivale a certificación en carretera |
| Asignación | Qué vehículo atiende qué locales y en qué orden | Distinta del cálculo vial y de verificar energía |
| eVED | Extended Vehicle Energy Dataset: extensión de VED con datos viales enriquecidos | [Repositorio de los autores](https://github.com/zhangsl2013/eVED) |
| `VehId`, `Trip` | Identificadores de vehículo y viaje | Usar ambos al distinguir viajes; `Trip` se repite entre vehículos |
| `Energy_Consumption` | Columna derivada de señales del auto, calculada suponiendo un segundo por fila | Diccionario §§6.5 y 9: acumular con el intervalo real entre registros; [contraste completo](DATOS.md) |
| `nan` / `none` | Faltante / sin evento en `Focus Points` | Diccionario §5.6: no tratar ambos como datos perdidos |
| Schema / contrato | Nombres, tipos, unidades y significado de entradas/salidas | Acordarlo con Daniel/Lucas; no fijar API antes de necesitarla |
| KPI | Indicador medido del programa | Entregas, energía y cómputo; distinto de rúbrica general |
| Baseline | Método de comparación declarado | Comparar con misma instancia, cobertura y restricciones |
| Óptimo / mejor encontrado | Resultado probado mejor posible / mejor hallado por el método | No llamar óptimo a una heurística sin certificado |

Fuentes de este bloque: presentación CASE del 14-10, CSV recibidos, [VED original](https://github.com/gsoh/VED), [eVED](https://github.com/zhangsl2013/eVED) y análisis local documentado en DATOS.md. Las definiciones no resuelven parámetros que CASE no especificó.

## Producto, diseño y trabajo con agentes

| Término | Para qué sirve | Referencia |
|---|---|---|
| Prototipo / MVP | Primera versión de alcance reducido para probar una tarea | Propuesta de alcance en [PLAN](PLAN.md), no lista fija de features |
| Demo / pitch | Demostración del comportamiento / presentación de problema, valor y evidencia | Agenda pública; duración y soporte pendientes |
| UI / UX | Controles y presentación / experiencia completa de realizar una tarea | [Apple HIG](https://developer.apple.com/design/human-interface-guidelines) |
| Jerarquía visual | Hacer visible qué es principal, secundario y accionable | [Vercel](https://vercel.com/design/guidelines) |
| Tokens de diseño | Valores reutilizables de color, espacio y tipografía | Convención posible del equipo, no obligación de crear una librería |
| Divulgación progresiva | Mostrar detalle cuando se necesita | Propuesta para evitar saturación; evaluar en el flujo real |
| Accesibilidad | Poder usar la interfaz con diversas capacidades y formas de interacción | [WCAG 2.2](https://www.w3.org/TR/WCAG22/) |
| Foco / navegación por teclado | Saber y controlar qué elemento recibe la acción | [WAI-ARIA APG](https://www.w3.org/WAI/ARIA/apg/) |
| Reduced motion | Preferencia por reducir movimiento | [Motion](https://motion.dev/docs/react-accessibility); no obliga a esa biblioteca |
| Motion / Framer Motion | Biblioteca de animación; comprobar nombre/API según versión | [Repositorio](https://github.com/motiondivision/motion), candidata |
| Prueba E2E | Comprueba un recorrido completo desde la interacción | [Playwright](https://playwright.dev/docs/best-practices), candidato |
| Fixture | Entrada controlada para una prueba | Sintética y rotulada cuando corresponda |
| Regresión | Un cambio rompe algo que funcionaba | Verificación enfocada en comportamiento afectado |
| Overengineering | Complejidad adicional sin necesidad actual que la justifique | [Google code review](https://google.github.io/eng-practices/review/reviewer/looking-for.html) |
| Skill | Instrucciones y referencias que el agente carga para una tarea | [Agent Skills](https://agentskills.io/specification); no garantiza expertise |
| Revisor independiente | Agente/persona distinto que busca defectos con evidencia | [Plan de revisiones](PLAN.md), con alcance y cierre |
| `.gitignore` | Reglas que excluyen archivos sin seguimiento de la adición normal a Git | Verificación local: `data/` ignorado y no versionado; no borra historial |

Guías consultadas el 14-10-2026. Las referencias de diseño son recomendaciones técnicas, no reglas de la hackathon.

## Vocabulario histórico, solo si vuelve a hacer falta

Los talleres cubren AWS IAM (identidades/permisos), S3 (objetos), EC2 (cómputo), VPC (red), EBS (volúmenes), Bedrock (modelos), Kiro Vibe/Spec, steering, hooks y AI-DLC. Están en las [grabaciones](https://dxt5re7ypebh7.cloudfront.net/videos.html). El login ya iniciado no obliga a incorporar todos estos servicios ni a repetir su configuración.
