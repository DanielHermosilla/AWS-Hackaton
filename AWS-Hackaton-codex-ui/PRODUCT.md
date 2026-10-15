# ZMD Mobility

<!-- impeccable:product-schema 1 -->

Fuente: encargo y respuestas de Diego, 14–15 de octubre de 2026. Este resumen conserva acuerdos de producto; los hechos técnicos y sus discrepancias se mantienen en `docs/CONTEXTO.md`.

## Platform

web

Computador primero; móvil secundario, confirmado por Diego.

## Stack

Exploraciones reversibles en HTML, CSS, JavaScript y SVG. El stack definitivo está pendiente: Daniel documentó Streamlit; React y MapLibre son propuestas anteriores. La elección visual no decide esa frontera. Diego delegó las decisiones técnicas menores y exige evitar sobreingeniería.

## Users

Una jefa de flota debe organizar entregas con vehículos eléctricos, entender dónde recargar y revisar si cada vehículo puede regresar a base. El caso público tiene dos Nissan Leaf 2013, inicialmente al 60 %, veinte locales y sesenta estaciones registradas.

## Product Purpose

Cargar un escenario, ejecutar el motor de Daniel/Lucas y comprender las entregas, recorridos, batería, consumo y tiempo de cálculo. Diego exige atender todos los pedidos y retornar sin agotar la energía; la formulación actual admite cobertura parcial y una reserva positiva. La interfaz debe exponer la discrepancia, no resolverla silenciosamente.

## Operating Context

ZMD Mobility es la consultora; CASE es el cliente del desafío. La red pública está en Ann Arbor, Michigan. El programa debe aceptar archivos nuevos del mismo formato sin fijar cantidades, IDs o coordenadas. El mapa es central, con listas y detalle enlazados.

## Capabilities and Constraints

- Daniel y Lucas llevan motor y backend; este trabajo cubre producto, UI, mapa e integración.
- Aún no hay un motor ejecutable ni resultados recibidos en el checkout inspeccionado.
- Una geometría vial, una asignación de entregas y una validación energética son cosas distintas.
- Los ejemplos de diseño se identifican como tales. No hay ahorro medido, telemetría en vivo ni disponibilidad de estaciones verificada.
- Diego aprobó la estética de Cristal con los tamaños de botones y la distribución de Esencial. Implementar esa combinación y extenderla con inicio/dashboard, navegación discreta y menú de perfil. Identidad aún pendiente; no añadir variables del motor hasta las respuestas del equipo.
- No hacen falta autenticación ni plataforma empresarial para explorar el flujo inicial.

## Brand Commitments

Nombre: ZMD Mobility. Claridad y limpieza inspiradas en Apple y Notion, sin copiar sus marcas. Logos minimalistas que se relacionen de forma reconocible con electromovilidad, eficiencia, ahorro y/o IA.

**Feedback anterior, 15-10:** Diego rechazó las cuatro interfaces y las treinta identidades mostradas. Explicó que «no tienen nada que ver con el tema». Ninguna forma anterior es autoridad visual. Las siguientes propuestas deben hacer evidente la operación eléctrica y la relación de la marca con ella.

**Dirección vigente, 15-10:** Cristal + Esencial aprobadas como una sola base de webapp. Vidrio en superficies de control, cifras legibles, mapa dominante y tarjetas compactas. Inicio/dashboard y sidebar solicitados expresamente. Chat `logo` separado: 40 ideas nuevas, ninguna seleccionada.

## Evidence on Hand

`docs/base_conocimiento.md`, `modelamiento.pdf`, `diccionario.md`, investigación en `docs/MAPA-Y-BASE.md`. Los CSV originales están fuera de Git en el checkout base. Las propuestas anteriores permanecen en `explorations/` como historial rechazado.

## Product Principles

- La operación eléctrica debe reconocerse sin leer una explicación de diseño.
- Cada cifra lleva unidad, procedencia y estado; un ejemplo no es una prueba.
- Mapa, vehículo y paradas deben representar el mismo recorrido.
- Una versión pequeña y cuidada prima sobre cantidad de funciones.
- La revisión técnica no sustituye la elección de Diego.
