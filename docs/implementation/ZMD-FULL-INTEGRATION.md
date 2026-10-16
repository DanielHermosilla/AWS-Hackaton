# Integración y refinamiento ZMD — 16 de octubre de 2026

Solicitud: integrar `origin/main@9f03027` con F02 (cargadores), F03 (resumen) y F05 (editor), y completar el feedback de producto. Base previa recuperable: `codex/pre-main-refinement@d3e045a`. Sin push ni despliegue público.

La referencia vigente incluye preprocesamiento vial, SCIP sin H y Bedrock de main. La exclusión histórica del preprocesador quedó reemplazada por la autorización actual. Conservar validación independiente, física y prioridad de entregas. La preferencia de tema persistente reemplaza iniciar siempre en claro.

## Backlog de aceptación

| ID | Resultado esperado | Responsable | Estado / evidencia |
|---|---|---|---|
| I01 | Main fusionado con historia y F02/F03/F05 conservadas | Integración | Merge en curso; tres conflictos acotados |
| I02 | CSV completos de data/raw y JSON grandes válidos admitidos | Entrada/motor | Pendiente; distinguir nodos de históricos eVED |
| I03 | Tema oscuro se mantiene entre Inicio, Plan y resultados | Navegación | Pendiente |
| I04 | Caso sintético permite elegir clientes y cargadores | Panel + entrada | Pendiente |
| I05 | Botón del caso sintético rediseñado | Panel | Pendiente |
| I06 | Selector de archivo diseñado e identificable | Panel | Pendiente |
| I07 | Caso sintético no intenta encajar puntos ajenos a la red vial | Entrada/motor | Pendiente; reproducir error de acceso de 8516 km |
| I08 | Ayuda de formato con ? accesible por hover, foco y toque | Panel | Pendiente |
| I09 | Una tarjeta Flota y supuestos incluye red y explicación breve | Panel | Pendiente |
| I10 | Tarjeta Parámetros del motor: presupuesto, gap, búsqueda, semilla | Panel + motor | Pendiente; gap energético sin cambiar prioridad de entregas |
| I11 | Recursos CPU predeterminados disponibles, sin control en UI | Motor | Pendiente; verificar capacidades reales de SCIP |
| I12 | Datos y límites accesibles al terminar y al reabrir | Panel | Pendiente |
| I13 | Se retira checkbox de confirmación | Panel | Pendiente |
| I14 | Producto sin referencias a miembros del equipo | Presentación | Pendiente; conservar procedencia en exportaciones |
| I15 | Terminaciones de fases explicadas en lenguaje común | Presentación | Pendiente |
| I16 | Ruta sintética de dos clientes visible y rotulada como aproximada | Presentación + motor | Pendiente; sin fabricar una ruta vial |
| I17 | Etiquetas de paradas legibles, sin IDs técnicos como BASE#FIN | Presentación | Pendiente; IDs internos intactos |
| I18 | Se retira hash de la cabecera | Panel | Pendiente |
| I19 | Descargar pasa a Ver resultados | Panel | Pendiente |
| I20 | Importar JSON completa los parámetros presentes en el archivo | Panel + entrada | Pendiente; CSV solo contiene nodos |
| I21 | Calcular permanece disponible y explica faltantes en línea | Panel | Pendiente; evitar doble envío durante cálculo |
| I22 | Inicio permite scroll con Sobre estos indicadores abierto | Navegación | Pendiente |
| I23 | Sobre estos indicadores breve, sin frase de telemetría | Navegación | Pendiente |
| I24 | Revisión independiente y pruebas integradas de archivos/rutas/estado/UI | Auditoría | Pendiente |

## Límites de la verificación

Los históricos eVED contienen telemetría, no destinos. No convertir filas en clientes ni truncar un archivo silenciosamente. Una geometría sintética debe identificarse como aproximación por distancia. No relajar el umbral vial para esconder ubicaciones fuera de cobertura. No acreditar una invocación de AWS mediante mocks ni prometer mejora del LLM sin medición.

## Reproducción y cierre

Se completará con comandos, commits, capturas y límites observados al finalizar las pruebas sobre la versión integrada.
