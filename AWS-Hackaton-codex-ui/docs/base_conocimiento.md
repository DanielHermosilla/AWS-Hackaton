# Aporte de Lucas — enunciado, flujo y parámetros

**Procedencia:** texto enviado por Lucas y pegado íntegramente por Diego en la conversación de trabajo el 14-10-2026, America/Santiago. Lucas refiere `DATA/bb-assets-c1-presentation.pptx` y un archivo previo `docs/base_conocimiento.md`; esos archivos de su checkout no se recibieron. Se conserva abajo su contenido, con formato Markdown normalizado. **Esta fuente mezcla interpretación del enunciado, estimaciones y propuestas; no convierte cada cifra en requisito oficial ni en parámetro aprobado.**

## Texto aportado

Revisé el PPT (`DATA/bb-assets-c1-presentation.pptx`) y agregué un resumen del enunciado oficial a `docs/base_conocimiento.md`. Abajo están el problema, el flujo del usuario y la lista de variables y parámetros.

### El problema en una frase

Una distribuidora tiene 2 Nissan Leaf 2013 que salen de un centro de distribución con 60 % de batería. El programa debe decidir qué locales visita cada auto, en qué orden y dónde recarga, para entregar al mayor número de locales posible. Ambos autos deben volver al centro sin quedarse nunca sin batería. Si dos soluciones entregan lo mismo, gana la que consume menos energía en total (kWh) y la que se calcula más rápido (segundos de cómputo).

### Flujo desde la perspectiva del usuario

1. **Carga los puntos.** Entrega un archivo con el mismo formato que `competition_routing_nodes.csv`: un centro de distribución, los locales a visitar y los cargadores disponibles.
2. **Indica la flota** (opcional). Cuántos autos hay y de qué modelo. Por defecto, 2 Leaf al 60 %.
3. **Ejecuta el programa.** No toca nada más. La organización hará exactamente esto con un grafo reservado que no conocemos, con otro centro, otros locales y otros cargadores.
4. **El programa prepara los datos.** Calcula distancias y energía entre puntos y descarta los cargadores que no sirven para el auto.
5. **El motor optimiza.** Primero intenta cubrir todos los locales; si no puede, cubre la mayor cantidad posible. Después reduce la energía total.
6. **El programa valida la solución.** Comprueba que cada auto vuelva al centro, que la batería nunca baje de la reserva y que ningún local se repita.
7. **El usuario recibe el resultado:**
   - Las rutas: `{"auto_1": ["BASE", "V3", "C6", "V7", "BASE"], "auto_2": [...]}`.
   - Un resumen: entregas cumplidas, locales no atendidos, kWh por auto y en total, batería en cada parada y tiempo de cómputo.

Recomiendo usar `node_id` (BASE, V3, C6) en vez del número de fila. En el grafo reservado los IDs cambian, y el número de fila depende del orden del archivo.

### Variables y parámetros

#### Entradas del usuario (archivo de nodos)

- `node_id`: identificador del nodo.
- `node_type`: base, local o cargador.
- `latitude`, `longitude`: ubicación.
- `connector_types`: conectores del cargador (CCS, CHAdeMO, NACS, J1772).
- `max_power_kw`, `dc_fast_ports`, `level2_ports`, `total_ports`: potencia y puertos.
- `address`, `network`: solo informativos.

#### Flota y vehículo

- Número de vehículos: 2.
- Modelo: Nissan Leaf 2013.
- Capacidad útil de batería: unos 16 kWh según los datos. La nominal es 24 kWh.
- Batería inicial: 60 % de la capacidad útil.
- Reserva mínima: no está definida. El enunciado solo dice "nivel insuficiente para continuar"; propongo entre 10 y 15 %.
- Conectores compatibles: CHAdeMO y J1772 (ficha técnica del Leaf, no está en los datos).
- Potencia máxima que acepta el auto: 6,6 kW en AC y unos 50 kW en DC.
- Capacidad de carga de mercadería: el enunciado no la menciona. Si no hay, no se modela.

#### Parámetros que calcula el programa

- Distancia entre cada par de nodos: en línea recta con un factor de corrección, o por calle con OpenStreetMap.
- Energía de cada tramo `e_ij`: unos 0,156 kWh/km según eVED. Se puede ajustar por pendiente.
- Tiempo de cada tramo: unos 33 km/h según eVED. Solo hace falta si se reporta el tiempo de ruta.
- Cargadores compatibles con cada auto: de los 60, quedan 54.
- Potencia efectiva de cada cargador: el mínimo entre la del cargador y la del auto.
- Tiempo de carga: energía cargada dividida por la potencia efectiva. Por ahora se desestima.

#### Configuración del motor

- Máximo de paradas o movimientos por auto (`H`).
- Cargadores preseleccionados: cuántos se consideran para no inflar el modelo.
- Límite de tiempo de cómputo.
- Pesos o prioridades del objetivo: primero entregas, después energía.

#### Variables de decisión (lo que elige el motor)

- `y_i`: si se entrega al local `i`.
- `z_ikr`: si el auto `k` está en el nodo `i` en la posición `r` de su ruta.
- `x_ijkr`: si el auto `k` va del nodo `i` al `j` en el paso `r`.
- `a_ikr`: si el auto `k` entrega en `i` en la posición `r`. Separa "pasar por un nodo" de "entregar" en él.
- `q_kr`: cuánta energía recarga el auto `k` en la posición `r`.

#### Variables de estado (se calculan a partir de las decisiones)

- `b_kr`: batería al llegar a la posición `r`.
- `b̄_kr`: batería al salir de la posición `r`, igual a `b_kr + q_kr`.
- `E_kr`: energía consumida en cada paso.
- `T_kr`: hora de llegada a cada parada. Solo existe si se modela el tiempo.

#### Salidas y KPIs

- Diccionario de rutas por auto.
- Entregas cumplidas y lista de locales no atendidos.
- Energía total (kWh), por auto y por tramo.
- Batería mínima alcanzada por cada auto. Prueba que nunca se quedó sin energía.
- Retorno al centro: sí o no, por auto.
- Tiempo de cómputo (s).
- Opcionales: kilómetros recorridos, número de recargas, tiempo estimado de ruta.

### Puntos del enunciado que conviene tener claros

- **El "tiempo" del desempate es tiempo de cómputo, no duración de la ruta.** Desestimar el tiempo de carga y la velocidad es coherente con el enunciado. El tiempo de ruta puede reportarse como valor agregado, pero no se evalúa.
- **El PPT dice "red de 20 nodos" en la portada, pero el archivo trae 81:** 1 base, 20 locales y 60 cargadores. La diapositiva 6 confirma que los 20 son locales.
- **No hay capacidad de carga ni demandas.** El único límite real es la batería. Con 2 autos y recargas libres, entregar a los 20 locales debería ser factible en el grafo público; lo comprobé solo con distancias en línea recta. La competencia real está en la energía y en el tiempo de cómputo.
- **El código debe funcionar con otro grafo sin cambios.** Nada puede quedar fijo en el código: ni IDs, ni la lista de cargadores compatibles, ni coordenadas. La compatibilidad debe calcularse leyendo `connector_types`.

## Integración crítica de la fuente, 14-10-2026

| Aporte | Estado al incorporarlo |
|---|---|
| “Ningún local se repita” | La unicidad corresponde a **entregas realizadas**, no a visitas físicas. El PDF permite volver a pasar por calles, nodos y cargadores, e incluso retornar al depósito y salir. |
| “Paradas o movimientos H” | El PDF define **movimientos/arcos**, no cantidad de clientes ni paradas de servicio. La configuración debe llamarse `movement_limit`; no confundirla con jornada o duración operacional. |
| Flujo de cargar → ejecutar → validar → presentar; IDs opacos | Coherente con README/AGENTS y base del producto. Los valores CSV efectivos son `base`, `visit`, `charger`; “local/cargador” arriba son etiquetas en español, no otros valores de schema. |
| Dos Leaf al 60 %, 81 nodos públicos | Corroborado por presentación y análisis local previo. Cantidades se descubren desde la entrada; no se fijan en el código. |
| Capacidad útil ~16 kWh; 0,156 kWh/km; 33 km/h | Estimaciones atribuidas a Lucas. Falta notebook, selección de viajes, integración temporal y tratamiento de huecos para reproducirlas. No se convierten en valores por defecto del motor ni en resultados certificados. |
| Reserva 10–15 % | Propuesta de Lucas. No adoptada: Diego pide llegada ≥0 y el PDF fija `b>0`. La discrepancia debe resolverse con los responsables del modelo. |
| CHAdeMO/J1772; 6,6 kW AC/~50 kW DC | Afirmaciones técnicas cuya ficha/configuración exacta no acompaña el mensaje. Deben documentarse por configuración del vehículo. Potencia máxima de estación no es potencia por conector. |
| 54 cargadores | **Conteo corroborado** en el CSV público restaurado: 54 de 60 estaciones tienen CHAdeMO o J1772 en el campo de conectores. Es coincidencia textual, no disponibilidad, compatibilidad completa o potencia efectiva. No etiquetar como 54 estaciones operables. |
| Distancia recta corregida | Aproximación exploratoria propuesta, distinta de la red dirigida elemental elegida en el PDF. No prueba camino conducible ni equivalencia de la solución. |
| Todos los locales deberían ser factibles | Hipótesis acompañada de un ensayo de líneas rectas no recibido. No hay prueba vial/energética reproducida en este checkout. |
| Batería mínima | Debe provenir de la comprobación del perfil completo; el mínimo solo en paradas de servicio no descarta déficit intermedio. |
| Cobertura máxima y menor energía/tiempo | Consistente con prioridades descritas. Mantener separados el objetivo lexicográfico del motor, cobertura completa deseada por Diego y criterios oficiales cuya regla exacta de desempate sigue pendiente. |

El texto de Lucas queda preservado; estas precisiones no reescriben su implementación ni sustituyen su análisis. Ver [CONTEXTO](CONTEXTO.md), [DATOS](DATOS.md) y [handoff](ESTADO-Y-HANDOFF.md).
