# Planificación de rutas y recargas para vehículos eléctricos

Proyecto para la hackatón AWS Breaking Barriers Chile 2026 y el desafío de CASE, Centro de Aceleración Sostenible de Electromovilidad de la FCFM de la Universidad de Chile.

Queremos ayudar a un operador a planificar entregas sin quedarse sin batería: cargar un archivo de nodos o configurar destinos, cargadores y flota desde una interfaz, obtener rutas factibles y consultar sus resultados en un mapa y un JSON.

El escenario del desafío considera dos Nissan Leaf 2013 con un 60 % de carga inicial. Las entradas actuales contienen un depósito, 20 locales y 60 cargadores. El mismo código deberá aceptar nuevas instancias y flotas parametrizadas.

**Estado de la rama `modelamiento`:** flujo ejecutable por CLI, desde CSV y red vial hasta Pyomo, solver, verificación independiente y JSON. **Gurobi es la primera opción; SCIP es el respaldo si Gurobi no está disponible o su licencia no permite resolver la instancia.** El LLM y la UI corresponden a etapas posteriores.

## Nuestro modelamiento

**La formulación implementada está en [modelamiento.pdf](modelamiento.pdf).** Es un modelo de programación lineal entera mixta (MILP) sobre una **red vial dirigida**, cuyas decisiones incluyen las calles recorridas, las entregas realizadas y la energía recargada. [docs/model.md](docs/model.md) relaciona cada ecuación con su componente Pyomo.

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

Los nodos de los CSV no constituyen por sí solos la red de calles. El comando `prepare` utiliza un GraphML de OSMnx o descarga una red dirigida sin simplificar, solo cuando se solicita. Integra eVED con intervalos reales por vehículo/viaje y obtiene una referencia descriptiva de kWh/km. Este estimador inicial **no es un predictor validado del consumo futuro** y no produce regeneración en los arcos OSM; el modelo sí admite consumos firmados y saturación en instancias JSON.

## Ejecutar

Requiere Python 3.12 o 3.13 y `uv`. Las dependencias Python, incluida la interfaz Gurobi, están fijadas en `uv.lock`. La licencia Gurobi se configura fuera del repositorio. Para el respaldo, instalar el ejecutable SCIP con soporte de lectura `.nl` y dejarlo en `PATH`; instalar únicamente un paquete Python de SCIP no satisface esa integración.

```bash
uv sync --locked
uv run ev-routing run \
  --instance examples/toy_recharge.json \
  --output artifacts/toy_recharge.json
```

El ejemplo requiere dos entregas y una recarga: el óptimo consume 14 kWh netos e incorpora 9 kWh a la batería. `examples/toy_regeneration.json` tiene una entrega y óptimo de 2 kWh; comprueba que la regeneración excedente se pierde cuando la batería se llena. Son ejemplos sintéticos, no resultados del concurso.

Para fijar un backend, agregar `--solver gurobi` o `--solver scip`. El valor predeterminado `auto` habilita el respaldo. No se cambia de solver por timeout o infactibilidad. `--time-limit-seconds 60` limita el presupuesto compartido por las dos fases; es un límite blando. Los detalles de licencias, fases y certificados están en [docs/solvers.md](docs/solvers.md).

Preparar los datos locales, conservando los originales:

```bash
uv run ev-routing prepare \
  --nodes data/competition_routing_nodes.csv \
  --graphml artifacts/network/ann_arbor.graphml \
  --download-network \
  --eved data/eVED_EV.csv \
  --energy-cache artifacts/energy/eved-summary.json \
  --config config/default.json \
  --output artifacts/instances/competition.json

uv run ev-routing run \
  --instance artifacts/instances/competition.json \
  --config config/default.json \
  --output artifacts/results/competition.json
```

Si el GraphML ya existe, se reutiliza sin descargar ni reemplazarlo. Omitir `--download-network` exige una red local. `--energy-rate 0.16` permite usar un coeficiente explícitamente supuesto en lugar de `--eved`. `--visit-id ID`, repetible, y `--charger-id ID` o `--no-chargers` permiten ensayos con subconjuntos; esa selección queda registrada.

**Antes de interpretar una corrida real**, revisar `config/default.json`: 24 kWh útiles, reserva de 2.4 kWh y `movement_limit=30` son supuestos de ejemplo, no requisitos acreditados por la hackatón. En una red vial grande, 30 movimientos pueden excluir muchas entregas; aumentar `H` también aumenta el MILP. El grafo conserva intersecciones y tramos, y añade accesos bidireccionales cortos desde los servicios: su factibilidad vehicular es un supuesto registrado. El importador rechaza accesos mayores que `--max-snap-distance-m` (100 m por defecto) y registra servicios sin retorno vial.

`run` utiliza los parámetros físicos guardados en la instancia; de `--config` solo toma la sección `solver`. Así no cambia el problema después de prepararlo. La salida incluye rutas completas, energía, recargas, entregas pendientes, cotas/gaps por fase, tiempos, procedencia y comprobación de factibilidad. Sin referencia de comparación, los ahorros de tiempo y CO2e quedan en `null`.

## Pruebas

```bash
uv run pytest -q
uv run pytest --cov=ev_routing --cov-report=term-missing \
  --junitxml=artifacts/tests/results.xml
uv run ruff check src tests
```

Las pruebas habituales no descargan mapas ni llaman a AWS. Incluyen integración energética, errores de datos, calles dirigidas, oráculos que enumeran recorridos pequeños, dos solvers, fallos de licencia, timeouts, manipulación de rutas para probar el validador y CLI completa. Los casos con solver se omiten si ninguno está disponible; revisar los `skipped` antes de interpretar una ejecución como validación del MILP. Para pruebas sin solver: `uv run pytest -m "not solver"`.

Resultados medidos y alcance de los ensayos: [docs/validation.md](docs/validation.md).

## Próxima etapa: tuning mediante AWS

El flujo actual es **datos → instancia → Pyomo → Gurobi/SCIP → verificación → JSON**, sin llamadas a LLM. `llm/tuning.py` documenta el punto de integración y genera un perfil local; `propose_tuning` permanece desactivado.

Posteriormente adaptaremos el análisis estructural de [LLM4MIP](https://llm4mip.github.io/) para proponer opciones del solver mediante **Amazon Bedrock y un modelo habilitado para la cuenta, región y plan/créditos AWS de la hackatón**. El LLM no cambiará datos, restricciones, objetivos ni tolerancias. Las propuestas se validarán contra una lista de opciones permitidas y se compararán con la configuración estándar bajo iguales recursos y presupuesto. La futura UI en Streamlit consumirá el mismo backend.

Priorizamos código simple, modular y bibliotecas existentes. [STRUCTURE.md](STRUCTURE.md) explica brevemente cada archivo y sus funciones. Los equipos trabajan en ramas y worktrees separados; la integración objetivo del proyecto es `master`.

Documentos de referencia:

- [modelamiento.pdf](modelamiento.pdf): formulación matemática implementada.
- [data/presentation.pptx](data/presentation.pptx): enunciado, reglas y KPI de la hackatón, distribuido localmente.
- [diccionario.md](diccionario.md): diccionario de los históricos eVED.
- [AGENTS.md](AGENTS.md): arquitectura, contratos, reglas de implementación y trabajo en paralelo.
