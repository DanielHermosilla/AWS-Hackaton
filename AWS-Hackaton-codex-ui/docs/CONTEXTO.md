# ZMD Mobility — contexto vigente

**Decisión vigente de Diego, 15-10-2026:** implementar la **estética de Cristal con los tamaños de botones y la distribución de Esencial**. Es la dirección visual aprobada; ya no hay que volver a elegir entre variantes. Base en `explorations/webapp/plan.html`, conservando intactas las exploraciones anteriores. Diego también autorizó un nuevo chat para construir autónomamente el inicio/dashboard, una barra lateral discreta y un avatar de iniciales abajo con menú de ajustes/sesión. Opus 5.5 mediante Kiro como diseñador e implementador principal; Astra como auditor, crítico y depurador, con autoría comprobada. Investigar guías/skills de dashboard mediante find-skills. [Traspaso de la webapp](WEBAPP-HANDOFF.md). La identidad sigue pendiente; no añadir variables del motor antes de las respuestas del equipo.

**Trabajo paralelo autorizado:** chat **logo** (`01a13dc0-6ef2-7893-aa59-cc691b35901d`, Astra 6) para 40 ideas nuevas en HTML interactivo, incluyendo minimalismo, vínculos con electromovilidad/eficiencia/IA y tipografía. Uso real de Opus 5.5 mediante Kiro sujeto a evidencia de sus respuestas. Escrituras aisladas en `explorations/logo-40/` y `docs/LOGO-40-HANDOFF.md`; no mezcla automática de trabajo en curso.

## Antecedentes conservados

**Feedback posterior, 15-10-2026:** Diego rechazó las cuatro interfaces y las treinta identidades: «no tienen nada que ver con el tema». Ninguna está seleccionada. Nueva ronda en `explorations/round-2/`, centrada en vehículos eléctricos, batería, entregas y recargas; la identidad vuelve a partir de ZMD y elementos eléctricos reconocibles. Se conserva lo anterior como historial descartado.


Actualizado el **14-10-2026, America/Santiago**. Este archivo es la entrada breve para personas y agentes. El detalle se consulta por necesidad.

## Identidad del equipo y empresa del desafío

**Confirmado por Diego el 14-10-2026:** nuestra consultora se llama **ZMD Mobility**. **CASE** es la empresa de electromovilidad que plantea el desafío; no es el nombre de nuestra consultora.

Usar ZMD Mobility para identificar al equipo, sus documentos y sus skills (`zmd-*`). Conservar CASE al citar la empresa, su presentación, datos, requisitos y fuentes. Los ensayos históricos con nombres `case-*` conservan la nomenclatura de su ejecución.

## Fase y equipo

**Encargo inicial de Diego, 14-10, superado por la selección visual del 15-10:** recuperar primero el contexto actualizado, investigar mapas/Kiro, consultar preferencias y presentar **cuatro alternativas interactivas de interfaz y seis conceptos de logo**. Diego elige y puede pedir refinamientos antes de implementar la interfaz definitiva. **Refinamiento posterior del brief de marca:** pidió muchas más opciones, minimalistas y vinculadas a electromovilidad, eficiencia, ahorro y/o IA. Se amplía a 24 conceptos nuevos, conservando los seis anteriores; ninguna identidad elegida. El mapa será central. Se autoriza exploración funcional con datos sintéticos identificados; no autoriza sustituir el motor de Daniel/Lucas.

**Cambio recuperado tras el pull:** `main` está en `4750ac8` (Daniel, 14-10 20:31 Chile). `README.md`, `AGENTS.md` y `modelamiento.pdf` fijan una formulación MILP vial dirigida, Pyomo, tuning por Bedrock y Streamlit como UI prevista; HiGHS sigue propuesto. Esto reemplaza la afirmación anterior de que no existía ninguna elección del motor. Solo hay cinco archivos versionados y no hay `src/`, `ui/`, `pyproject.toml`, API ni resultados ejecutables en este checkout. No implica que no existan avances en los equipos de Daniel/Lucas.

**Discrepancia de frontend abierta:** Streamlit está escrito en la nueva guía del repositorio; React/TypeScript/Vite y MapLibre eran recomendaciones locales anteriores. Los prototipos de diseño no eligen todavía el stack definitivo. Ver [handoff y discrepancias](ESTADO-Y-HANDOFF.md).

Diego Caballero conduce diseño, UI/UX, experiencia del software y presentación mediante agentes. Daniel Hermosilla y Lucas Zulueta conducen investigación, formulación e implementación del motor. El reparto de integración se acuerda cuando exista el contrato.

Preferencia de Diego, reconfirmada en esta sesión: **web para computador; móvil secundario**, interfaz limpia y clara, tipografía cuidada, colores sobrios con acentos útiles, referencia Apple/Notion y buena integración con el motor. Delegó el alcance funcional al criterio del equipo; disponibilidad de tokens no implica añadir funciones sin utilidad. Evitar complejidad, dependencias y código sin necesidad concreta. Auditorías independientes en hitos, con hallazgos comprobables y un cierre definido.

**Usuario de referencia confirmado en la presentación, diap. 3:** una jefa de flota de reparto (Carla es ilustrativa) que decide qué vehículo visita cada local y necesita confianza en el retorno con energía. Diego pidió orientar el diseño desde esa presentación. **Propuesta derivada:** vista principal de operación con detalle técnico accesible; no tomar al investigador como usuario principal por defecto.

## Hechos del desafío

**Verificado en presentación CASE del 14-10:** dos Nissan Leaf 2013, SOC inicial de 60%, 20 locales y 60 cargadores en la instancia pública; ambos vehículos deben regresar al centro. Recarga permitida. También se consideran energía, tiempo de cómputo, escalabilidad y adaptación a cambios de la red.

**Aclaración de Diego, 14-10, vigente para el trabajo:** atender **todos** los clientes y completar **todos** los pedidos. Dejar pedidos sin completar o quedarse sin batería invalida la solución. Reserva mínima a la llegada **mayor o igual a cero**; no inventar un margen obligatorio adicional ni rechazar la llegada exactamente en cero por ese solo hecho. Diego indica que el consumo lo mide el auto y la recarga depende del dataset. El relato de sala respalda la cobertura completa; se conserva como antecedente que las diapositivas usaban «maximizar entregas». Un resultado parcial sirve de diagnóstico y no satisface el objetivo de producto de Diego. **Discrepancia explícita tras el pull:** el PDF permite entregas parciales y maximiza cobertura antes de energía; además establece reserva estrictamente positiva (`0 < b ≤ 0.6B`, p.1). No afirmar que el PDF ya permite reserva cero, ni atribuir la cobertura total obligatoria a toda la regla oficial. La UI distinguirá cobertura, factibilidad del modelo y criterio de aceptación de Diego. Daniel/Lucas deben resolver la reserva en la formulación; no se modifica desde UI. [Contraste de fuentes](FUENTES.md).

Se evaluará el mismo código cambiando archivos de entrada. El **programa reproducible** forma parte del resultado técnico; los detalles de empaquetado siguen pendientes. Una interfaz y una demo son propuestas de producto/presentación, sin formato oficial verificado. [Fuentes y entrega](FUENTES.md).

**Verificado localmente, 14-10:** el ZIP recibido contiene seis CSV. Datos y ZIP están en `AWS-Hackaton/data/`, ignorados por Git. En esta sesión faltaba el directorio y se restauró desde originales existentes en Descargas con hash SHA-256 coincidente; no se repitió el perfil de 22 millones de filas. El worktree UI no duplica la telemetría. Hay nodos y telemetría; el ZIP no incluye una matriz de distancias/tiempos.

**Nueva fuente recibida por AWS y recuperada el 14-10:** `Diccionario.zip`, correo «FW: Readme CASE» de Carla Catalano, 15:02 hora de Chile. Define unidades, códigos, faltantes, procesamiento y `Energy_Consumption`: valor eléctrico derivado de corriente/voltaje bajo un supuesto de un segundo; para acumularlo debe usarse el tiempo real entre registros. Ya no están pendientes esas definiciones. La medición histórica del vehículo no documenta por sí sola cómo evaluarán una ruta nueva. [Inventario, comprobaciones y límites](DATOS.md).

AWS/Kiro ya iniciados según Diego. No repetir preparación de cuentas como requisito para planificar. Esto no demuestra permiso para cada servicio ni presupuesto ilimitado.

Workshop Studio, leído con la sesión existente el 14-10, fija región `us-east-1` y ofrece VS Code y Kiro como opciones de IDE. Eso resuelve que Kiro IDE no es el único editor presentado, sin establecer el uso mínimo evaluado de IA o asistentes. El directorio público ya registra ZMD MOBILITY y sus tres integrantes en C-1. [Fuentes](FUENTES.md).

## Pendientes que sí cambian decisiones

- Qué capacidad de batería se debe usar en el ejercicio: el diccionario cita 24 kWh anunciados, sin fijarlos como capacidad utilizable del evaluador.
- Cómo se comprobará consumo/batería en rutas nuevas y qué simplificaciones de recarga acepta la evaluación, más allá de los campos que sí trae el dataset.
- Papel del CSV `evaluation`, red vial de referencia y protocolo de la instancia reservada.
- Formato de salida, comando/entorno, límites de cómputo y conectividad; desempate exacto entre energía y tiempo.
- Formato/canal de entrega, corte definitivo, duración de presentación y uso funcional mínimo de AWS/GenAI o evidencia exigida de asistentes.

Antes de trasladar un pendiente al equipo, consultar el análisis de datos, el diccionario y las fuentes pertinentes; preguntar solo la parte no resuelta. Las elecciones de solver, imputación, arquitectura e interfaz corresponden al equipo, salvo una restricción oficial encontrada.

Agenda publicada: cierre del desarrollo **16-10 a las 10:15**, preevaluación 12:00 y pitch de finalistas 15:00. La información histórica de cierre al mediodía sigue como discrepancia; confirmar con organización. [Evidencia](FUENTES.md).

## Recuperar solo lo necesario

[Plan abierto](PLAN.md) · [Mapa y base técnica propuesta](MAPA-Y-BASE.md) · [Fuentes](FUENTES.md) · [Datos](DATOS.md) · [Glosario](GLOSARIO.md) · [Skills y guías](SKILLS.md).

No hay resultados del solver ni ahorros medidos en el checkout inspeccionado. El archivo previo `docs/base_conocimiento.md` no apareció en el checkout ni su historia. **Diego aportó después el texto completo enviado por Lucas**, preservado con procedencia y revisión en [base_conocimiento.md](base_conocimiento.md). Ya no hace falta volver a pedir su contenido. Los ~16 kWh útiles, 0,156 kWh/km y 33 km/h siguen como estimaciones atribuidas, sin análisis reproducible recibido. El conteo de 54 estaciones con algún conector CHAdeMO/J1772 sí se corroboró en el CSV restaurado; no demuestra 54 estaciones operables. La reserva 10–15 % propuesta por Lucas no se adoptó.

**Trabajo actual:** worktree `../AWS-Hackaton-ui`, rama `codex/ui`, creado desde `4750ac8`; conserva el checkout original en `main`. Sigue la petición previa de Diego de concentrar UI en una rama destinada a `main`; la migración histórica propuesta a `master` no se ejecutó. Los cambios de producto y memoria de esta etapa se mantienen aquí. [Estado, siguiente paso y recuperación](ESTADO-Y-HANDOFF.md).
