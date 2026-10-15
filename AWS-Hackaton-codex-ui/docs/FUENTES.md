# Fuentes y producto que debemos entregar

Revisado el **14-10-2026, America/Santiago**, después de las aclaraciones de Diego. Se contrastaron páginas públicas, presentación/notas, transcripciones, correo de AWS, diccionario y CSV. Se consultó además Workshop Studio con la sesión existente. No se enviaron mensajes ni entregas. El [glosario](GLOSARIO.md) organiza los enlaces originales y conceptos.

## Qué sabemos del producto final

**Verificado:** CASE anuncia que ejecutará **el mismo código reemplazando los archivos de entrada**. El resultado técnico es un programa de planificación que pueda operar sobre otra instancia. Se consideran entregas factibles, retorno de ambos vehículos, energía, tiempo de cómputo y adaptación a cambios de red. Fuente: presentación CASE, diapositivas 5–7 y notas, recibida el 14-10; [presentación disponible en el portal](https://d78v2swml9yu2.cloudfront.net/api/challenges/c1/download?key=bb-assets-c1-presentation.pptx).

La comunicación general habla de prototipos que, en el caso de ganadores, se entregarán a las instituciones. La agenda incluye preevaluación técnica y pitch de finalistas. [Página del evento](https://www.taurusmkt.com/breakingbarrierschile), consulta 14-10.

| Elemento | Estado |
|---|---|
| Programa que funciona cambiando entradas | Anunciado por CASE; protocolo técnico pendiente |
| Prototipo de solución | Esperado en comunicación del evento |
| Presentación y preevaluación | Actividades publicadas; duración y soporte pendientes |
| Interfaz web, app móvil, chatbot o dashboard concreto | No se encontró obligación de una forma específica |
| Repositorio público/privado, ZIP, contenedor, video, diapositivas o URL desplegada | Formato/canal obligatorio no confirmado |
| AWS, IDE y GenAI | Workshop Studio fija región `us-east-1` y ofrece VS Code y Kiro como opciones de IDE; mínimo funcional evaluado de AWS/GenAI y uso exigido de asistentes siguen sin especificarse |
| Producto comercial completo | No aparece como exigencia; se habla de prototipos |

**Propuesta del equipo:** preparar programa reproducible, experiencia comprensible y demo con evidencia. La propuesta no convierte sus componentes en requisitos oficiales. [Plan abierto](PLAN.md).

## Condiciones CASE y dudas

**Problema/usuario (diap. 3):** una jefa de flota decide qué locales atiende cada vehículo con incertidumbre de energía para volver. Carla es un caso ilustrativo según las notas. Orienta la experiencia de operación, sin fijar pantallas ni stack. El 14-10 se releyeron directamente los XML de las diapositivas 3, 5, 6 y 7 y sus notas en el PPTX original; SHA-256 `76c955756fa77ca9a34ad6d2f4d119185110b500df2e70abb7530b9fa7d21502`.

Presentación del 14-10: dos Nissan Leaf 2013, 60% SOC inicial cada uno, retorno al centro de ambos, recarga permitida y metodología libre. Se consideran energía/cómputo entre resultados de igual cumplimiento. No se encontró orden o fórmula exacta de desempate ni capacidad utilizable fijada para la evaluación.

**Aclaración de Diego, 14-10:** todos los clientes y pedidos deben atenderse; incumplir pedidos o quedarse sin batería invalida. Reserva a la llegada **≥ 0**; no añadir un porcentaje obligatorio. Diego indica que el consumo lo mide el auto y las condiciones de recarga dependen del dataset. La intervención CASE recibida ya decía visitar todos los locales. Queda retirada la pregunta sobre admitir cobertura parcial; la redacción anterior de las diapositivas se conserva como antecedente, no como permiso para omitir pedidos. [Evidencia local contrastada](../../memoria-hackaton/10-planificacion/confirmaciones-20261014/local/AUDITORIA-LOCAL.md).

El archivo público contiene 1 centro, 20 locales y 60 estaciones; “20 nodos” en otra diapositiva no describe su tamaño total. `evaluation_routing_nodes.csv` cambia solo las coordenadas de los 20 clientes y conserva BASE y cargadores, a diferencia del grafo reservado descrito. Ese hecho está comprobado; su papel en el examen final sigue pendiente. [Auditoría de datos](DATOS.md).

## Respuestas recuperadas del diccionario de AWS

Carla Catalano (AWS Professional Services) remitió **«FW: Readme CASE» el 14-10 a las 15:02 de Chile**, con `Diccionario.zip`. Se descargó mediante el enlace del correo y se conservó en `data/`, fuera de Git, sin guardar códigos de acceso en la memoria. Contiene README en español e inglés; no contiene evaluador ni diccionario de los nodos de recarga.

- **Definición de energía resuelta:** se deriva de señales medidas por el auto. Para EV/PHEV, corriente y voltaje; la columna se calculó suponiendo un segundo por fila. Para obtener energía del viaje debe ponderarse por el tiempo real entre filas, agrupando por vehículo y viaje. El diccionario y los CSV concuerdan en la fórmula; [comprobaciones y excepciones](DATOS.md).
- **Unidades y códigos resueltos:** SOC en %, peso generalizado en libras, pendiente como razón, códigos de mapas y significado de `nan`/`none`.
- **Preprocesamiento documentado:** limpieza y separación por motorización, sin imputación estadística ni remuestreo uniforme. El diccionario deja a los participantes escoger cómo tratar faltantes; no es una regla pendiente que deba decidir CASE.
- **Límite:** medir consumo histórico no describe cómo comprobará el evaluador la energía de una ruta nueva. Tampoco fija capacidad útil, potencia aceptada por el vehículo o política de disponibilidad/colas. No añadir esas restricciones al ejercicio por defecto.

Fuente original local: [README.es.md, §§ 5–9](../data/reference/diccionario-20261014/README.es.md). Los notebooks y carpetas enlazados por ese README no están dentro de los ZIP recibidos; no afirmar que se ejecutaron.

## Fechas y rúbrica

La [agenda Taurus](https://www.taurusmkt.com/breakingbarrierschile) publica para el **viernes 16-10**: cierre del desarrollo **10:15**, preevaluación **12:00**, pitch finalistas **15:00**, cierre **16:30**, hora de Chile.

La [noticia UChile del 13-10](https://uchile.cl/noticias/245755/u-de-chile-sera-sede-de-la-hackaton-global-de-amazon-web-services) habla de cierre al mediodía. Verificada de nuevo el 14-10. **Propuesta:** planificar terminar antes de 10:15 y confirmar el corte; no interpretar la noticia como prórroga.

El correo Taurus del 13-10 a las 20:48 confirma que se mantiene la programación pese a las condiciones meteorológicas, pero no resuelve esa diferencia horaria. La duración de la cuenta temporal de Workshop Studio tampoco es el plazo de entrega.

Rúbrica publicada: innovación técnica 25%, impacto social 25%, factibilidad/sustentabilidad 20%, escalabilidad 15%, presentación 15%. No se publicó conversión matemática entre KPI del algoritmo y puntaje del jurado.

## Procedencia y acceso

| Fuente revisada | Hallazgo útil y límite |
|---|---|
| [AWS Builder](https://builder.aws.com/connect/space/2ae550db-b363-308e-9727-97cc44928f76/breaking-barriers-chile-2026) | Seis posts revisados el 14-10; agregan directorio para jueces y consejo de Kiro, sin pauta técnica de entrega |
| [Portal original Integra](https://d78v2swml9yu2.cloudfront.net/?inst=integra) | Se navegó a U. de Chile → C-1; el enlace inicial no es el desafío CASE |
| [Portal CASE](https://d78v2swml9yu2.cloudfront.net/?inst=uchile&challenge=c-1) | Lista ZIP (626,0 MB mostrados, modificado 13-10 16:36) y PPTX (671,1 KB, 14-10 11:30); zona de esos timestamps no etiquetada |
| [Taurus](https://www.taurusmkt.com/breakingbarrierschile) | Agenda, rúbrica y descripción del problema |
| [Videos](https://dxt5re7ypebh7.cloudfront.net/videos.html) | Core 5-oct, Kiro 6-oct, AI-DLC 8-oct; no se retranscribieron ni escucharon completos |
| [Registro](https://dxt5re7ypebh7.cloudfront.net/equipos.html) | Formulario de equipo/desafío, no entrega final; no se completó |
| [Directorio de equipos](https://dxt5re7ypebh7.cloudfront.net/equipos-publico.html) | ZMD MOBILITY figura en C-1 con Daniel, Diego y Lucas; coincide con nuestro equipo |
| Correo AWS «FW: Readme CASE», 14-10 15:02 Chile | Diccionario recuperado y leído; resuelve variables y preparación de telemetría |
| [Workshop Studio: Environment Setup](https://catalog.us-east-1.prod.workshops.aws/event/dashboard/en-US/workshop/20-environment-setup) | Leído por root con sesión existente: región `us-east-1`; no fija formato ni canal de entrega |
| [Workshop Studio: opción VS Code](https://catalog.us-east-1.prod.workshops.aws/event/dashboard/en-US/workshop/41-your-ide-vs-code-online) | VS Code en navegador con Kiro CLI; Q Developer figura opcional. El índice ofrece también Kiro IDE. No demuestra exclusividad obligatoria de Kiro IDE |

Builder, portal y videos fueron accesibles por navegador/HTTP aunque el recuperador web no pudo leerlos. No se deduce de ese fallo que estén caídos o requieran login.

El portal fue vinculado por [Challenge information](https://builder.aws.com/post/3KefC3hRQst1XHPJNDNlZsciVZF_p/challenge-information), publicado por un empleado AWS el 13-10. [Workshops recordings](https://builder.aws.com/post/3KdZi7ULtXGygb3EZKNclkhLP1s_p/workshops-recordings) acredita el enlace de videos. Consulta 14-10.

La presentación del portal se descargó de nuevo el 14-10: **idéntica byte a byte a la copia local**, 687.182 bytes, SHA-256 `76c955756fa77ca9a34ad6d2f4d119185110b500df2e70abb7530b9fa7d21502`. Se cierra la limitación anterior de haber comparado solo el nombre. El ZIP de datos y sus seis CSV se comprobaron por hash; [procedencia](DATOS.md).

El registro enlaza [Términos de Eventos AWS](https://aws.amazon.com/events/terms/). Hay condiciones generales sobre materiales presentados; no especifican el paquete técnico CASE ni prueban aceptación del equipo, obligación de abrir el repositorio o permiso para publicar los datos. [Revisión pública y límites](../../memoria-hackaton/10-planificacion/confirmaciones-20261014/fuentes/RESULTADOS.md).

## Pendientes después de revisar la evidencia

1. ¿Qué se entrega, por qué canal y a qué hora exacta?
2. ¿Qué comando/entorno correrán, con qué conectividad y límite de tiempo, y qué formato debe salir?
3. ¿`evaluation` es ensayo o examen final? ¿Cambian depósito, cargadores, cantidad de locales y vehículos?
4. Con todas las entregas y rutas válidas, ¿cómo desempatan energía y tiempo?
5. ¿Los 24 kWh nominales del Leaf son la capacidad a utilizar en el ejercicio? ¿Cómo comprobarán energía en rutas nuevas y qué simplificaciones de recarga esperan más allá de los campos disponibles?
6. ¿Qué red, distancias y tiempos usará el evaluador? No vienen arcos ni matriz en los ZIP.
7. ¿Qué uso funcional mínimo evaluarán de AWS/GenAI? ¿Exigen evidencia de uso de algún asistente, o restringen código/librerías previas? No preguntar si Kiro IDE es el único editor: Workshop Studio ya ofrece VS Code.
8. ¿Cuánto duran preevaluación/pitch/demo/preguntas y qué alcance técnico tiene el traspaso? La licencia del repositorio y publicación del dataset no quedaron especificadas.

Registrar la respuesta y su fuente/fecha. Cobertura, reserva, unidades y definición de `Energy_Consumption` dejaron de ser preguntas abiertas. Elección de solver, tratamiento de faltantes, API interna, stack y pantallas son decisiones del equipo, no obligaciones nuevas de CASE. No haber encontrado las otras instrucciones en las fuentes consultadas no demuestra que no existan en otra comunicación.
