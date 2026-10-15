# Planificación de entregas para vehículos eléctricos

Proyecto para la hackatón AWS Breaking Barriers Chile 2026 y el desafío de CASE,
Centro de Aceleración Sostenible de Electromovilidad de la FCFM de la Universidad
de Chile. El escenario oficial considera dos Nissan Leaf 2013 al 60 % inicial.
El objetivo es maximizar entregas factibles y después minimizar energía neta de
batería, con regreso al depósito y reserva suficiente.

Esta rama conecta la **webapp HTML/CSS/JavaScript** con el solver de
**Daniel Hermosilla**, importado desde `modelamiento@6242035`.
Usa SCIP/PySCIPOpt, formulación por rutas sin H, contratos nativos y comprobador
independiente. Se excluye el preprocesamiento que adapta trabajo de Lucas Zulueta
y se retira el anterior proveedor `evrp`. Los cambios quedan locales para revisión
y merge posterior.

## Ejecutar la webapp

Con Python 3.12 o 3.13 y `uv`, desde la raíz:

```sh
uv sync --locked
uv run --locked python -m backend.local_server --port 4294
```

Abrir `http://127.0.0.1:4294/` y pulsar **Cargar y calcular**. Se puede cargar una
instancia JSON nativa o preparar un CSV con parámetros explícitos. La preparación
geodésica desde CSV es sintética y debe confirmarse; no acredita una red vial.
Inicio y Plan comparten la ejecución, rutas, batería, resultados y descargas.

[Guía de integración](docs/integration-beta.md) ·
[Contrato HTTP](backend/API_CONTRACT.md) ·
[Guía del frontend](webapp/README.md)

## CLI y verificación

La CLI usa el mismo `ProblemInstance` y pipeline que la web:

```sh
uv run --locked ev-routing run \
  --instance examples/toy_recharge.json \
  --time-limit-seconds 30 \
  --output artifacts/toy-result.json

uv run --locked pytest -q
node --test webapp/tests/*.test.mjs
```

El caso de recarga espera dos entregas, 14 kWh netos de batería y 9 kWh recargados.
Los ejemplos son sintéticos; no constituyen resultados del concurso.
Los datos reales, credenciales, entornos y artefactos permanecen fuera de Git.

## Modelo y contratos

El [PDF de Daniel](modelamiento.pdf) contiene la formulación vigente sin H,
ecuaciones (25)–(29), y la referencia posicional Pyomo, ecuaciones (1)–(24).
[docs/model.md](docs/model.md) explica el alcance de esta importación.
La batería, recargas parciales, regeneración, compatibilidad, retorno y servicios
se conservan en el motor original.

La comunicación usa [contratos versionados](docs/contracts.md).
Cambios internos del solver se adaptan en el puente; no se trasladan sus detalles
a la UI. Se conserva el resultado nativo completo, con estados y certificados
por fase. Sin evidencia no se inventan optimalidad, ahorros ni emisiones.
El [registro de procedencia](docs/solver-source.json) permite contrastar una
actualización futura con el commit importado.

La ejecución web es local, sin autenticación ni base de datos. La política
estándar no llama a AWS. El código de Bedrock de Daniel se conserva con su
[procedencia LLM4MIP](docs/llm4mip-adaptation.md); esta entrega no acredita acceso
a la cuenta AWS ni una mejora de tuning.

Las reglas de trabajo están en [AGENTS.md](AGENTS.md), y el diccionario de los
históricos eVED permanece en [diccionario.md](diccionario.md).
