# ZMD Mobility — planificación de rutas y recargas

Proyecto para la hackatón AWS Breaking Barriers Chile 2026 y el desafío de CASE, Centro de Aceleración Sostenible de Electromovilidad de la FCFM de la Universidad de Chile.

Queremos ayudar a un operador a planificar entregas sin quedarse sin batería: cargar un archivo de nodos o configurar destinos, cargadores y flota desde una interfaz, obtener rutas factibles y consultar sus resultados en un mapa y un JSON.

El escenario del desafío considera dos Nissan Leaf 2013 con un 60 % de carga inicial. Las entradas actuales contienen un depósito, 20 locales y 60 cargadores. El mismo código deberá aceptar nuevas instancias y flotas parametrizadas.

**Estado del motor:** definición del proyecto y de su modelo matemático. La arquitectura e integraciones descritas abajo son el plan de implementación; este checkout no contiene todavía motor ejecutable.

**Producto/UI:** exploración autorizada por Diego el 14-10-2026. Cuatro propuestas interactivas y seis identidades en [explorations](explorations/README.md); la implementación definitiva espera su elección. [Contexto vigente](docs/CONTEXTO.md) · [handoff](docs/ESTADO-Y-HANDOFF.md) · [aporte de Lucas](docs/base_conocimiento.md) · [decisión cartográfica propuesta](docs/MAPA-Y-BASE.md).

## Nuestro modelamiento

**La formulación que implementaremos está en [modelamiento.pdf](modelamiento.pdf).** Es un modelo de programación lineal entera mixta (MILP) sobre una **red vial dirigida**, cuyas decisiones incluyen las calles recorridas, las entregas realizadas y la energía recargada.

Su objetivo es lexicográfico:

$$
\text{lexmin}\left(-\sum_{i\in C}y_i,\ E_{\mathrm{total}}\right).
$$

Primero se maximiza el número de entregas factibles. Después se minimiza el consumo neto efectivo de batería manteniendo ese cumplimiento. El tiempo de cómputo se mide como rendimiento del método.

El modelo:

- Exige salida y regreso al depósito, continuidad del recorrido y batería dentro de su capacidad y reserva.
- Permite repetir calles, intersecciones y cargadores, pero atender cada cliente como máximo una vez. Pasar por un cliente no implica realizar su entrega.
- Decide recargas parciales en estaciones compatibles y representa la regeneración, incluyendo la energía que no puede almacenarse cuando la batería está llena.
- Usa `H` como cota del número de movimientos, no como duración de jornada. Esa cota limita el alcance del certificado de optimalidad.
- Supone consumos deterministas y tramos viales elementales. La versión base no incluye carga en el depósito, jornada, tiempos de servicio, capacidad de paquetes ni colas.

Los nodos de los CSV no constituyen por sí solos la red de calles. Habrá que construir esa red y estimar su consumo usando eVED, integrando las señales con sus intervalos reales de tiempo.

## Enfoque de solución

1. **Entrada común.** Normalizar el CSV o los datos del formulario en una misma instancia validada.
2. **Modelo parametrizable.** Construir en Pyomo la formulación del PDF, con los parámetros de la instancia.
3. **Interpretación con un LLM.** Analizar la estructura del modelo y proponer ajustes de búsqueda para el solver, reutilizando y adaptando material de [LLM4MIP](https://llm4mip.github.io/).
4. **Tuning mediante AWS.** Invocar el LLM a través de **Amazon Bedrock**, usando un modelo habilitado para la cuenta, región y plan/créditos de la hackatón. Validar sus propuestas contra opciones realmente admitidas por el solver.
5. **Resolución y comprobación.** Resolver las dos prioridades y verificar las rutas con un comprobador independiente.
6. **Resultados.** Mostrar mapa, entregas, batería, recargas, energía, tiempos y estado/gap por fase; exportar un JSON reproducible.

**El LLM ajusta parámetros del solver; no cambia el modelo, sus restricciones ni sus objetivos.** Compararemos su configuración con una configuración estándar bajo condiciones equivalentes. LLM4MIP aporta procedimientos, prompts y herramientas auxiliares; la integración Pyomo–AWS–solver se desarrollará en este repositorio.

## Resultados y desarrollo

Los KPI principales son factibilidad, entregas cumplidas, consumo energético y tiempo de cómputo. También evaluaremos escalabilidad. Los ahorros de tiempo y emisiones se mostrarán únicamente con una referencia comparable y supuestos documentados.

Trabajaremos con un backend Python modular, Pyomo, un único solver inicial, una UI en Streamlit y un cliente AWS centralizado. Priorizamos código simple y bibliotecas existentes, sin overkill ni reinventar herramientas.

Los equipos de datos, optimización, UI/UX y LLM trabajarán con contratos compartidos y espacios aislados. El trabajo de UI está en `codex/ui`, basado en `4750ac8` y destinado a `main`, conforme petición de Diego. La migración a `master` prevista en la guía anterior no se ejecutó. El frontend final debe reconciliar la previsión Streamlit de esta base con la interacción que Diego elija; los prototipos HTML no cambian esa decisión por sí solos.

Documentos de referencia:

- [modelamiento.pdf](modelamiento.pdf): formulación matemática a implementar.
- [docs/FUENTES.md](docs/FUENTES.md): procedencia del enunciado, reglas y KPI; el PPTX es una fuente local del workspace de investigación, no un archivo versionado en esta raíz.
- [diccionario.md](diccionario.md): diccionario de los históricos eVED.
- [AGENTS.md](AGENTS.md): arquitectura, contratos, reglas de implementación y trabajo en paralelo.
