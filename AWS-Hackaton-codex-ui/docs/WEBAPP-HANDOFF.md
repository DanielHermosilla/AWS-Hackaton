# ZMD Mobility · base elegida y dashboard

Fuente: decisión explícita de Diego, **15-10-2026**, America/Santiago. ZMD Mobility es la consultora; CASE plantea el desafío.

## Decisión aprobada

**Estética de Cristal + distribución y tamaños de botones de Esencial.** Implementar una única base y seguir desarrollándola. No volver a presentar cuatro direcciones ni pedir que Diego elija otra vez.

La pantalla de partida es [`explorations/webapp/plan.html`](../explorations/webapp/plan.html), servida en `http://127.0.0.1:4173/webapp/plan.html`. Conserva el layout y los controles compactos de Esencial; `material.css` aporta la apariencia elegida. Las carpetas `round-2` y `round-3` son referencias históricas que no deben alterarse para construir el dashboard.

Contrato visual de partida:

- Computador primero. Mapa dominante y panel de vehículos de 352 px; 310 px en el ancho intermedio de Esencial.
- Barra superior de 64 px. Tarjetas compactas, automóvil pequeño en la cabecera, batería y métricas alineadas. Los controles mantienen sus dimensiones de Esencial.
- En móvil secundario el mapa recibe 550 px de altura para separar detalle, leyenda y atribución; etiquetas de resumen de 10 px. Seleccionar desde la lista encuadra el pin en espacio libre; pulsarlo directamente conserva la cámara salvo que la tarjeta lo cubra.
- Tipografía del sistema, neutros fríos, azules y violeta reservados para identificar rutas. Radios suaves, bordes claros y sombras discretas de Cristal.
- Vidrio en controles o navegación sobre contenido. Los números y las listas importantes conservan una superficie estable y legible. No hacer transparente cada tarjeta.
- Animación breve para orientar, interrumpible, sin retrasar acciones. La reducción de movimiento/transparencia y el contraste deben seguir funcionando.

La marca continúa como texto **ZMD Mobility**. Las 40 propuestas del chat `logo` están terminadas pero Diego no eligió identidad. No seleccionar una por cuenta propia.

## Encargo autorizado para el nuevo chat

Construir autónomamente la base de la webapp con **Inicio/dashboard**, navegación lateral discreta y un **círculo de iniciales abajo** que abra un menú hacia arriba o al lado, según el espacio disponible. El menú debe ofrecer ajustes y una salida apropiada al estado real de la aplicación. Diego pidió avanzar sin preguntas rutinarias: resolver composición, espaciado e interacción con criterio y evidencia.

El inicio debe orientar hacia el escenario y el plan, con jerarquía clara, pocas métricas útiles y acciones que hagan algo real. La barra de navegación de aplicación y el panel de vehículos son responsabilidades distintas; evitar dos columnas anchas que ahoguen el mapa. Mantener el plan elegido reconocible al entrar desde Inicio y al volver.

Usar los datos y estados disponibles. No llenar el dashboard con ingresos, ahorros, emisiones, viajes históricos, telemetría en vivo o supuesta actividad de usuarios. Una tarjeta vacía bien explicada vale más que datos inventados. Los valores del plan actual son de demostración.

El menú de perfil está autorizado como interfaz; todavía no existe servicio de autenticación. No fingir una sesión autenticada. Se puede ofrecer una salida local de la demostración con nombre y efecto claros, ajustes reales de presentación y un camino de regreso, sin montar infraestructura de cuentas. La decisión concreta queda al implementador y auditor.

## Trabajo entre modelos

**Opus 5.5 mediante Kiro: diseñador e implementador principal. Astra 6: auditor, crítico y depurador.**

1. Astra recupera el contexto y prepara un encargo acotado que conserve la dirección aprobada.
2. Opus propone e implementa un incremento concreto. Darle archivos, alcance y criterios observables; evitar un único prompt enorme para toda la plataforma.
3. Astra inspecciona el diff y el navegador, comunica defectos reproducibles y pide correcciones concretas a Opus. Puede depurar e integrar los ajustes necesarios.
4. Cerrar cada incremento con evidencia visible y atribución real. No llamar «implementado por Opus» a un archivo creado por otro modelo.

Puente privado existente: `/Users/caballero/.codex/zmd-collaboration/HANDOFF.md`; runner `tools/acp_runner.py`. Modelo exacto `claude-opus-5.5`, esfuerzo `max`, ACP V3. Crear estado exclusivo del dashboard; no reutilizar sesiones de logo, de Nobu o del híbrido. Consultar [KIRO-Y-AGENTES.md](KIRO-Y-AGENTES.md), sin copiar secretos ni registros privados al repositorio.

**Limitación comprobada antes de este encargo:** varias tareas creativas de Opus terminaron abortadas sin contenido útil, aunque modelo/configuración y una respuesta corta sí se verificaron. La galería de logos terminó con autoría Astra; el intento de Opus no produjo diseños. El intento concreto del híbrido se registra en el cierre de esta base. Configuración no equivale a participación. Ante un timeout, reconciliar antes de reenviar; no repetir ciegamente prompts ni atribuir una respuesta inexistente. Un fallo del proveedor no debe convertirse en una espera indefinida ni en una nueva pregunta de diseño a Diego.

## Investigación y skills

Diego pidió explícitamente **find-skills / skillfinder en el nuevo chat** para buscar criterios de buenos dashboards. Leer `/Users/caballero/.codex/skills/find-skills/SKILL.md`, buscar y revisar fuentes, y elegir las que sirvan a esta aplicación. El chat de origen leyó la skill y consultó el catálogo `skills.sh`; queda hacer la selección concreta para dashboard en el nuevo chat.

Priorizar las skills de proyecto:

- `.agents/skills/zmd-project-context/SKILL.md`: recuperar acuerdos y fuentes.
- `.agents/skills/zmd-apple-design/SKILL.md`: jerarquía y dirección aprobada.
- `.agents/skills/zmd-map-ui/SKILL.md`: mapa, listas y cámara.
- `.agents/skills/zmd-ui-qa/SKILL.md`: prueba visible del recorrido.
- `.agents/skills/zmd-code-review/SKILL.md`: revisión de un cambio sustantivo.

Las rutas anteriores son relativas a `/Users/caballero/Documents/ChatGPT/AWS`, no al checkout de UI. Para movimiento, consultar `motion` o el detalle de interacción cuando se necesite; no cargar todos los workflows equivalentes. No instalar una librería o framework porque lo recomiende una skill genérica. Revisar guías primarias pertinentes de Apple, W3C y diseño de dashboards; registrar qué criterio se aplica, con fuente y fecha.

## Archivos, datos y aislamiento

Checkout: `/Users/caballero/Documents/ChatGPT/AWS/AWS-Hackaton-ui`, rama `codex/ui`. El checkout `AWS-Hackaton/main` y el motor de Dani/Lucas quedan fuera del encargo.

El nuevo chat será propietario de `explorations/webapp/` después del cierre de esta base y de su documentación de dashboard. No editar variantes históricas ni la galería `explorations/logo-40/`. Esta última y `docs/LOGO-40-HANDOFF.md` son trabajo terminado de otro chat, aún sin commit al inicio de este encargo. No hacer stage global ni incluirlas por accidente.

Esta implementación continúa en HTML/CSS/JS. No introduce React ni decide la integración final con Streamlit. Puede progresar como frontend funcional sin rehacer el motor ni abrir una discusión técnica de arquitectura que no cambie el incremento pedido.

`plan.js` consume `round-3/shared/{data,icons,motion}.js` y el módulo local `webapp/map.js`. Este último conserva el mapa previo y añade selección en espacio libre (`focusPoint`) para que el detalle no tape el pin; no se modificó el shared histórico. Los JSON locales están ignorados por Git; `round-3/shared/prepare-local-fixture.py` reproduce el ejemplo desde los CSV públicos locales. No versionar datos originales ni telemetría.

Datos visibles: dos vehículos, veinte entregas, sesenta estaciones registradas, dos recargas de ejemplo. Rutas sobre calles OSRM preparadas para el diseño; **consumo y batería ilustrativos, sin validación del motor**. Desconocidos como tiempo de cómputo continúan desconocidos. Un cargador registrado no equivale a disponible. No añadir variables del motor mientras faltan las respuestas del equipo.

## Aceptación del siguiente incremento

- Inicio y plan comparten la dirección elegida y permiten ir y volver sin perder el contexto necesario.
- Sidebar discreta con estados activos claros; navegación operable con teclado y nombres accesibles.
- Avatar inferior abre/cierra el menú; Escape, clic externo y retorno de foco funcionan. El menú cabe en el viewport y sus acciones tienen efecto honesto.
- Ajustes guardan una preferencia real y toleran almacenamiento local no disponible.
- Mapa, lista, vehículo y parada siguen sincronizados. BASE de salida y regreso siguen siendo ocurrencias distintas.
- Revisar el estado sin resultados, la demostración y los fallos que realmente soporte el incremento. No simular progreso del solver.
- Inspección real de escritorio y móvil secundario, sin desbordamientos; foco, contraste, movimiento/transparencia reducidos y superposiciones sobre mapa.
- Entrega visible, evidencia breve, límites y autoría comprobada. Una revisión independiente al cerrar el incremento, sin cadena infinita de auditorías.

## Estado del traspaso

Base híbrida implementada. La revisión principal pasó 23 comprobaciones: geometría de Esencial, material, cinco anchos, selección, teclado, preferencias de accesibilidad, procedencia y hashes originales. [Evidencia y capturas](../explorations/webapp/qa/README.md). La revisión independiente cerró 18 casos de cámara y 12 de foco/scroll móvil, sin hallazgos abiertos dentro de ese alcance. Seleccionar una parada desde la lista móvil lleva el mapa a la vista; cerrar devuelve foco y scroll a la fila correcta.

El intento del híbrido con Opus 5.5/max no produjo texto ni CSS; fue cancelado tras 255 s y reconciliado como abortado, sin runner activo. El acabado y los arreglos de esta base fueron integrados por Codex. El nuevo chat conserva el encargo de Opus como diseñador/implementador y Astra como auditor, con verificación de cada aporte.

Tras el checkpoint del chat de origen, el nuevo chat recibe propiedad de `explorations/webapp/` para continuar el inicio/dashboard. No hace falta otra aprobación visual ni una respuesta de Diego para empezar.
