# Guía de trabajo del proyecto

## 1. Propósito y fuentes de verdad

Construimos un planificador de entregas para vehículos eléctricos para la hackatón AWS Breaking Barriers Chile 2026. El beneficiario del desafío es CASE, Centro de Aceleración Sostenible de Electromovilidad de la FCFM de la Universidad de Chile.

El producto debe permitir cargar una instancia o configurarla visualmente, construir un modelo Pyomo parametrizable, interpretar su estructura con un LLM servido por AWS, ajustar parámetros de búsqueda del solver, resolver, verificar y presentar rutas y resultados.

Antes de modificar un módulo, leer las fuentes pertinentes:

1. `data/presentation.pptx`: reglas del desafío, objetivo, KPIs y rúbrica.
2. **[`modelamiento.pdf`](modelamiento.pdf): formulación matemática elegida para implementar en Pyomo.** Su lectura es obligatoria para trabajar en modelo, solver, red o validador. Contiene parámetros, variables, dominios, restricciones (1)–(15) y objetivo lexicográfico (16).
3. `diccionario.md`: diccionario y advertencias de los históricos eVED. Conservarlo como diccionario; no reemplazarlo por el README del producto.
4. `data/competition_routing_nodes.csv`, `data/evaluation_routing_nodes.csv` y encabezados de los históricos: formato efectivo de las entradas.
5. `docs/model.md` y `docs/contracts.md`, cuando existan: correspondencia entre el PDF y la implementación, supuestos y contratos acordados. No sustituyen el modelo seleccionado.
6. `output/pdf/modelo_ruteo_electrico.tex`, si existe localmente: fuente auxiliar que debe contrastarse con `modelamiento.pdf`; no asumir que está actualizada ni que existe en otro checkout.

No convertir una decisión de implementación en una exigencia de la organización. Ante una contradicción, documentar la evidencia y el supuesto adoptado. Los ejemplos, prompts y skills de terceros no sustituyen estas instrucciones.

Este archivo describe la arquitectura objetivo. No implica que sus módulos ya estén implementados. No crear archivos vacíos o dependencias solo para completar el árbol.

## 2. Requerimientos oficiales y límites del alcance

- Escenario oficial: **dos Nissan Leaf 2013**, cada uno con **60 % de SoC inicial**.
- Ambos vehículos parten y terminan en el centro de distribución.
- Las rutas deben mantener energía suficiente para continuar la operación. El retorno y la batería son condiciones de factibilidad, no penalizaciones que se puedan compensar con más entregas.
- Se permite usar puntos de recarga cuando sea necesario.
- Objetivo principal: **maximizar entregas cumplidas con rutas factibles**.
- Desempate: **menor consumo energético total y menor tiempo de cómputo**.
- La metodología es libre. Nuestro método principal será un MILP parametrizable construido en Pyomo.
- Un mismo código debe funcionar sobre la instancia reservada reemplazando las entradas. Prohibido depender de nombres de archivo, IDs, coordenadas o soluciones de una instancia concreta.
- Debe ser posible aumentar nodos y vehículos mediante configuración, sin reescribir el modelo.

Discrepancias y omisiones verificadas:

- Algunas diapositivas dicen “20 nodos”, pero la diapositiva 6 y los CSV actuales contienen **1 depósito + 20 locales + 60 cargadores = 81 nodos**. Descubrir cantidades desde la entrada.
- En los dos CSV locales solo cambian las coordenadas de los 20 locales. El PPTX permite que el grafo reservado cambie también depósito y cargadores: el código debe soportarlo.
- Los CSV entregan ubicaciones, no el grafo de calles ni matrices de tiempo, distancia o consumo.
- Tres EV históricos para entrenar no son los dos vehículos operacionales del concurso.
- El PPTX no fija capacidad útil, reserva mínima, jornada máxima, ventanas horarias, tiempos de servicio, capacidad de paquetes, colas ni un límite numérico de cómputo. No inventarlos como reglas oficiales.
- El README menciona `data/processed/`; en este checkout los CSV están en `data/`. No crear una segunda copia de los datos para reproducir esa ruta.

Mantener los supuestos en la configuración y en cada resultado. La capacidad nominal de 24 kWh mencionada por el diccionario no acredita por sí sola una capacidad útil de 24 kWh. Parametrizar capacidad, reserva y compatibilidad. El modelo elegido en `modelamiento.pdf` supone que el depósito no ofrece recarga y permite dejar un vehículo inactivo mediante el arco artificial `(0, 0)`; conservar esos supuestos en la versión base.

## 3. Producto y flujo único de ejecución

Las dos entradas de usuario deben converger al mismo contrato `ProblemInstance`:

1. **Archivo**: cargar un CSV de nodos con el formato existente y completar parámetros que ese archivo no contiene.
2. **Interfaz gráfica**: configurar depósito, destinos, cargadores, direcciones/coordenadas y parámetros de flota. Validar y confirmar resultados ambiguos de geocodificación. Permitir exportar la instancia.

Flujo común:

```text
CSV o formulario
  -> normalización y validación de instancia
  -> red vial y estimaciones de energía
  -> modelo Pyomo
  -> perfil estructural y propuesta de tuning mediante AWS
  -> validación de parámetros del solver
  -> resolución lexicográfica
  -> comprobación independiente de factibilidad
  -> JSON de resultados y visualización
```

CLI e interfaz usan el mismo pipeline. La UI no construye restricciones, modifica parámetros del solver directamente ni calcula una versión alternativa de los KPIs.

El modelo es una plantilla de nuestra familia de problemas. **El LLM no genera un modelo nuevo por consulta ni cambia su significado.**

## 4. Arquitectura simple y modular

Priorizar **código simple, legible y suficiente para el caso real**. Evitar overkill y no recrear la rueda.

- Un solo proyecto Python y un backend organizado por responsabilidades.
- Pyomo para modelar. Usar una integración existente con el solver, no implementar branch-and-bound, presolve o un protocolo propio.
- Para el MVP, usar **Streamlit** como interfaz y un mapa integrado con una biblioteca existente. El backend debe poder ejecutarse sin Streamlit.
- **HiGHS es el backend inicial propuesto** cuando no se haya confirmado otra elección y su licencia. Si el equipo decide usar COPT/Gurobi para acercarse al entorno de LLM4MIP, documentar licencia, disponibilidad, integración Pyomo y decisión antes de implementar el adaptador. Mantener un solo backend funcional en el MVP.
- Usar `boto3` para AWS y estructuras validadas, preferentemente Pydantic, para los contratos. Usar bibliotecas existentes para CSV, grafos y mapas.
- No agregar microservicios, colas, Kubernetes, una base de datos, un framework de agentes, varias capas de repositorios o interfaces genéricas sin una necesidad demostrada.
- Preferir funciones pequeñas y tipos explícitos. Extraer una abstracción cuando exista reutilización real, no por anticipación.
- Mantener dependencias y versiones en `pyproject.toml` y un único lockfile. No mezclar gestores ni replicar entornos.
- Usar nombres en inglés para código y campos de contratos; documentación y UI principal en español. Unidades explícitas en nombres, por ejemplo `energy_kwh` y `runtime_seconds`.

Estructura objetivo:

```text
AGENTS.md
README.md                         # instalación, ejecución y demo del producto
diccionario.md                      # diccionario original de datos
presentation.pptx                 # enunciado original
modelamiento.pdf                  # formulación matemática que se implementará
pyproject.toml
.env.example                      # nombres de variables; nunca secretos
config/
  default.json                    # escenario, presupuestos y opciones documentadas
src/ev_routing/
  contracts.py                    # esquemas compartidos y sus validaciones
  config.py                       # configuración del problema, solver y AWS
  inputs.py                       # CSV/formulario -> ProblemInstance
  network.py                      # geocodificación, red dirigida y caché
  energy.py                       # integración, estimación y perfiles energéticos
  model.py                        # construcción de la plantilla Pyomo
  solve.py                        # adaptador del solver y fases lexicográficas
  validation.py                   # comprobador independiente de la solución
  metrics.py                      # KPIs y comparaciones con referencias
  pipeline.py                     # coordinación de los módulos
  cli.py                          # ejecución reproducible sin interfaz
  llm/
    bedrock.py                    # cliente AWS, límites, errores y uso de tokens
    tuning.py                     # perfil -> propuesta -> opciones validadas
ui/
  app.py                          # formulario, carga, mapa y resultados
tests/
  fixtures/                       # instancias sintéticas pequeñas
docs/
  model.md                        # correspondencia PDF/Pyomo y alcance de certificados
  contracts.md                    # contratos y ejemplos mínimos
  llm4mip-adaptation.md            # procedencia y adaptación del upstream
data/                             # datos originales locales, ignorados por Git
artifacts/                        # resultados/cachés locales, ignorados por Git
```

Crear módulos adicionales solo cuando el tamaño o la responsabilidad lo justifiquen. No publicar datos, credenciales, cachés, binarios de solver ni resultados masivos en Git. No modificar ni borrar originales al preprocesar.

## 5. Contratos y datos

El archivo `contracts.py` y su documentación son responsabilidad compartida coordinada. Acordar contratos mínimos antes de que UI, modelo y LLM implementen sus partes en paralelo.

Contratos mínimos:

- `ProblemInstance`: versión, nodos, flota, parámetros, red/perfiles y procedencia.
- `SolverConfig`: backend, presupuesto, recursos, semilla y opciones aprobadas.
- `TuningRequest`: resumen estructural, capacidades del solver, parámetros permitidos y presupuesto.
- `TuningProposal`: opciones propuestas, explicación breve y advertencias; sin código ejecutable.
- `RunResult`: estados, rutas, validación, certificados, KPIs, tiempos y trazabilidad.

Separar `problem_config` de `solver_config`. Capacidad, reserva, objetivos, grafo y límite de movimientos pertenecen al problema. No son parámetros que el LLM pueda modificar para aparentar una mejora.

Formato actual de nodos, CSV UTF-8 con posible BOM:

```text
node_id,node_type,latitude,longitude,address,network,total_ports,dc_fast_ports,level2_ports,connector_types,max_power_kw
```

- `node_id`: string opaco, único y no vacío. No asumir numeración consecutiva.
- `node_type`: `base`, `visit` o `charger`; el MVP requiere exactamente una base.
- Coordenadas finitas y dentro de rangos geográficos válidos.
- Campos de cargadores vacíos en bases/locales son legítimos.
- Puertos: enteros no negativos; informar inconsistencias entre total, DC y nivel 2.
- Conectores: separar por `;` y normalizar espacios.
- `max_power_kw`: máximo reportado para la estación. No equivale a potencia por conector ni potencia aceptada por el vehículo.
- Validar IDs duplicados, referencias inexistentes, parámetros imposibles y problemas de cobertura. Devolver errores accionables, sin correcciones silenciosas.

Construir una red vial dirigida con procedencia y cobertura documentadas. Las coordenadas y las trayectorias históricas no equivalen a conectividad completa. La distancia en línea recta puede ser una referencia exploratoria, pero no debe presentarse como una ruta vial validada.

Reglas para eVED:

- Identificar viajes con `(VehId, Trip)`, ordenar por tiempo y calcular intervalos dentro de cada viaje.
- Integrar energía con tiempo real: `sum(-current_a * voltage_v * delta_t_seconds / 3.6e6)`. La columna `Energy_Consumption` también debe multiplicarse por `delta_t_seconds`.
- No sumar directamente las filas de `Energy_Consumption`.
- Conservar regeneración y limitar lo efectivamente almacenado por la batería. No convertir todos los valores negativos o faltantes a cero.
- Tratar huecos temporales grandes mediante una política explícita y registrada.
- Entrenar energía EV con señales adecuadas de EV; no equiparar consumo ICE/HEV con consumo del Leaf.
- Separar entrenamiento/validación por viajes, vehículos o períodos. No dividir aleatoriamente filas correlacionadas.
- Corriente, voltaje y consumo observado sirven para construir etiquetas; no están disponibles para una ruta futura. Otras variables futuras requieren predicciones o escenarios explícitos.
- No ajustar modelos ni escoger configuraciones mirando desempeño en `evaluation`. El código puede leer la instancia de evaluación para resolverla, pero no aprender de sus resultados de evaluación.
- Cargar solo columnas/datos necesarios. Reutilizar cachés identificadas por contenido y configuración; no reprocesar los históricos completos en cada clic.

## 6. Modelo Pyomo, factibilidad y certificados

**Implementar la formulación de [`modelamiento.pdf`](modelamiento.pdf), manteniendo sus parámetros, variables, dominios y restricciones.** No sustituirla silenciosamente por otra formulación de TSP/VRP ni por una aproximación que cambie las rutas factibles.

Mantener una única plantilla Pyomo parametrizable. Documentar en `docs/model.md` la correspondencia entre las ecuaciones del PDF y los componentes de Pyomo. Toda extensión o reducción del modelo debe explicar su efecto y distinguirse de la versión base.

- El PDF modela un grafo vial dirigido `G = (V, A)` con intersecciones y tramos elementales. Los 81 puntos de los CSV son ubicaciones de servicio, no toda la red vial `V`.
- Las variables `z_ikr` indican ubicación, `x_ijkr` seleccionan calles, `a_ikr` indican entregas y `y_i` contabiliza clientes atendidos. Mantener la separación entre desplazamiento y servicio.
- `H` es el máximo de movimientos por vehículo y corresponde a `movement_limit`. El índice de posición no sincroniza los relojes de los vehículos.
- Prioridad lexicográfica: maximizar entregas; después minimizar energía manteniendo el cumplimiento alcanzado.
- Cada entrega se cuenta como máximo una vez entre todos los vehículos. Pasar físicamente por una ubicación no debe implicar automáticamente atender una entrega.
- Las rutas son continuas y regresan al depósito. Calles y cargadores pueden repetirse cuando la representación lo requiera.
- El PDF permite retornos intermedios al depósito y volver a salir. No añadir una restricción de permanencia obligatoria después del primer retorno.
- Batería inicial `0.6 * B` en el escenario oficial; recarga solo donde esté habilitada y sea compatible.
- Respetar capacidad y reserva durante el recorrido completo. Un balance energético correcto en el destino no prueba factibilidad de los segmentos intermedios.
- Modelar la saturación de regeneración. Si se agregan caminos en arcos, conservar la información necesaria para reproducir su perfil energético y verificarlo. Justificar que la agregación preserva las opciones de recorrido del PDF; fijar caminos entre puntos de servicio puede restringirlas y no es automáticamente una reformulación equivalente.
- Distinguir energía neta efectiva de batería, energía incorporada a batería y electricidad comprada a la red.
- Usar nombres distintos para `movement_limit` y `time_horizon_seconds`. El primero restringe la representación de rutas; no es una jornada oficial.
- Indicar el alcance de la optimalidad: depende de la red, caminos disponibles, modelo energético y límites de representación. No extrapolar un certificado a un problema más amplio.
- La versión base no permite cargar en el depósito y no incorpora tiempos de servicio, ocupación ni jornada. Cualquier variante debe identificarse como extensión y actualizar su documentación.

En la primera fase, registrar mejor solución y cota de entregas. Si se agota el tiempo sin probar el máximo, la segunda fase puede mejorar energía fijando las entregas encontradas, pero debe declararse **mejora condicionada a ese cumplimiento**, no óptimo lexicográfico demostrado.

Guardar por fase: sentido del objetivo, incumbente, cota, gap reportado, estado de terminación y tiempo. No construir un único “gap óptimo” combinando fases incompatibles. No llamar óptima a una solución por haber terminado la ejecución.

Si el solver alcanza su límite con una solución factible, conservarla y validarla. Distinguir: óptimo probado, factible sin prueba de optimalidad, sin solución encontrada, infactibilidad probada y error de ejecución.

`validation.py` debe comprobar el resultado independientemente de las restricciones de Pyomo: continuidad, arcos permitidos, retorno, entregas únicas, SoC inicial, cargadores, capacidad/reserva en segmentos y balance energético. La UI solo presenta una ruta como factible cuando pasa esta comprobación. La factibilidad se refiere al modelo energético utilizado, no a una garantía sobre consumos reales inciertos.

Las metaheurísticas pueden servir después como referencia o para producir incumbentes compatibles, si hay evidencia de necesidad. No reemplazan el flujo principal Pyomo + solver solicitado ni justifican implementar otro solver desde cero.

## 7. LLM obligatorio mediante AWS y adaptación de LLM4MIP

**El LLM del producto debe invocarse mediante la API de los servicios y modelos habilitados para la cuenta, región y plan/créditos AWS de la hackatón.** La integración inicial será **Amazon Bedrock Runtime, API Converse, mediante `boto3`** para un modelo compatible.

- Configurar región e identificador de modelo o perfil de inferencia. No fijar un modelo arbitrario ni asumir que está habilitado, cubierto por créditos o disponible gratuitamente.
- Verificar disponibilidad, permisos, condiciones de acceso, cuotas y presupuesto en el entorno asignado antes de elegir el modelo definitivo.
- La llamada es `boto3.client("bedrock-runtime").converse(...)` y requiere `bedrock:InvokeModel`. Resolver requisitos adicionales del proveedor/cuenta con el responsable del entorno; consultar documentación no demuestra acceso real.
- Usar la cadena estándar de credenciales AWS: rol de ejecución, perfil/SSO local o credenciales temporales del entorno. No incrustar claves ni registrarlas en Git, prompts o logs.
- Convención de configuración: `BEDROCK_MODEL_ID`, `AWS_DEFAULT_REGION` y `AWS_PROFILE` opcional. Mapear explícitamente cualquier variable propia de región a `region_name`. No confundir perfil de credenciales con perfil de inferencia.
- No sustituir esta integración por APIs directas de OpenAI, Anthropic u otros proveedores, ni por un modelo local. Un modelo de esos proveedores servido a través de Bedrock sí puede ser válido si está habilitado para la cuenta.
- Centralizar AWS en `llm/bedrock.py`; el resto del código no maneja credenciales.
- Configurar timeout, límites de entrada/salida, cantidad máxima de llamadas y reintentos acotados. Registrar tokens y costos estimados cuando exista una tarifa verificada.
- Los tests habituales usan dobles del cliente. La aceptación de la integración requiere una prueba real en la cuenta AWS asignada; un mock no demuestra conectividad.

Referencia solicitada: https://llm4mip.github.io/

Repositorio público inspeccionado:
https://github.com/LLM4MIP/llm4mip.github.io

Commit de referencia inspeccionado: `9335a69f446244f28d5b406eb66ddf13afa1d2e9`.

**Reutilizar y adaptar material existente de LLM4MIP. No reconstruir desde cero su trabajo de diagnóstico y diseño de experimentos.** El material público incluye workflows, prompts, referencias y scripts auxiliares; no proporciona una integración lista de Pyomo, Bedrock y autotuning.

Componentes concretos a revisar:

- `data/skill-study/packages/primal-current/`: instrucciones y referencias para analizar estructura y mejorar soluciones.
- `data/skill-study/packages/primal-current/scripts/summarize_runs.py`: resumen de registros; no es un validador de rutas.
- `data/skill-study/packages/dual-current/`: criterios sobre cotas y su validez. No adoptar cortes o transformaciones fuera del alcance sin demostrar que preservan el problema.
- `downloads/milp-structure-research-copt/scripts/profile_mip_structure.py`: perfil estructural basado en COPT. Reutilizar lo pertinente adaptando su dependencia al backend elegido; no añadir COPT solo para obtener estadísticas que Pyomo/nuestro solver ya exponen.
- `downloads/milp-structure-research-copt/references/output-templates.md`: formatos de diagnóstico e hipótesis.

Los materiales usan Gurobi/COPT y el sitio describe un trabajo más amplio que tuning de parámetros. Nuestro MVP adapta su análisis estructural y experimentación al ajuste del solver. **No afirmar una reproducción literal de sus resultados o infraestructura** sin haberla implementado y medido.

Registrar en `docs/llm4mip-adaptation.md`: URL y commit de origen, archivos/prompts reutilizados, cambios, licencia MIT y partes no reproducidas. Conservar avisos de licencia/copyright en material incorporado. No copiar íntegramente el sitio ni asumir acceso a repositorios no públicos referenciados por él.

### Contrato de tuning

El LLM recibe un perfil compacto: número y tipo de variables, restricciones, estructura del ruteo y batería, escalas numéricas, fase de optimización, estadísticas relevantes, solver/versión, opciones admitidas y presupuesto. No necesita los históricos completos, credenciales ni direcciones exactas de clientes.

Debe devolver JSON validable, por ejemplo:

```json
{
  "schema_version": "1.0",
  "solver": "backend_configurado",
  "parameters": {},
  "rationale": "Hipótesis de ajuste basada en la estructura observada",
  "warnings": []
}
```

Reglas obligatorias:

1. Mantener una lista de parámetros permitidos con tipos, rangos y versión del solver. Solo aceptar opciones realmente soportadas.
2. Heurísticas, branching, cortes, presolve u otras estrategias solo pueden proponerse si el backend las expone y están aprobadas. No inventar equivalencias entre opciones de COPT, Gurobi y HiGHS.
3. El LLM no modifica datos, restricciones, dominios, objetivos, capacidad, reserva, límite de movimientos, tolerancias de factibilidad/integralidad ni criterios de certificación.
4. Presupuestos, recursos y metas de gap los fija el protocolo/configuración del usuario. No dejarlos variar para aparentar aceleración.
5. No usar `eval`, `exec`, shell o archivos Python generados por el LLM para aplicar tuning.
6. Ante respuesta inválida, parámetros desconocidos, fallo de AWS o presupuesto agotado, usar la configuración estándar y marcar `fallback`. No ocultar que el LLM no se utilizó.
7. Comparar baseline y configuración propuesta con la misma instancia, formulación, fase, recursos y presupuesto. Registrar propuestas aceptadas/rechazadas y resultados. No prometer una mejora antes de medirla.
8. Empezar con una propuesta y un experimento acotado; no crear un bucle autónomo indefinido. Separar presupuesto de tuning del de resolución.
9. Medir tiempo de solver y tiempo total, incluyendo llamadas al LLM y experimentos. El costo del tuning forma parte del costo de uso del producto.

## 8. JSON de salida, KPIs y experiencia de usuario

`RunResult` se serializa como JSON versionado, incluso cuando no hay solución. Usar `null` más un motivo para datos no disponibles; no `NaN`, infinitos ni ceros ficticios.

Campos mínimos:

- Identidad: `schema_version`, `run_id`, hashes de entradas/configuración/red, versión del código y del modelo energético.
- Escenario: flota, capacidad, reserva, SoC inicial, límites y supuestos.
- Ejecución: solver/versión, semilla, presupuesto, parámetros solicitados/efectivos y estado.
- `phases`: objetivo, incumbente, cota, gap, terminación y tiempo de cada fase.
- `tuning`: estado, modelo/región AWS, propuesta, validación, fallback, tokens y costo cuando estén disponibles.
- `routes`: vehículo, pasos en orden, clientes atendidos, geometría/arcos, batería de llegada/salida, recarga y energía por tramo.
- `unserved_visit_ids`, validación independiente y sus violaciones.
- `kpis`: valores, unidades, definición y calidad de la información.
- `runtime_seconds`: carga/preparación, modelo, LLM, experimentos, solver, validación y total. Definir intervalos para no sumar dos veces etapas incluidas en otras.
- Advertencias y procedencia de los datos usados para impactos estimados.

No guardar “todas las estadísticas posibles” como un volcado indiscriminado. Conservar las estadísticas útiles y soportadas para diagnosticar, comparar y reproducir, con logs detallados en artefactos separados.

KPIs oficiales:

| Prioridad | Métrica | Tratamiento |
|---|---|---|
| Factibilidad | Retorno al depósito y batería suficiente de ambos vehículos | Condición obligatoria, mostrar validación |
| Principal | Entregas cumplidas | Maximizar; mostrar cumplidas/total |
| Desempate | Consumo energético total, kWh | Minimizar, indicando la definición energética |
| Desempate | Tiempo de cómputo, segundos | Medir solver y ejecución total |
| Escalabilidad | Mismo código con más nodos/vehículos | Evaluar calidad, factibilidad y tiempo |

La rúbrica del jurado es distinta: innovación técnica 25 %, impacto social 25 %, factibilidad y sustentabilidad 20 %, escalabilidad 15 %, presentación 15 %. **No convertir esos porcentajes en pesos de la función objetivo.**

Mostrar además, cuando se puedan calcular: kilómetros, tiempo operacional, paradas de carga, energía recargada, mínima reserva, clientes pendientes y estado/gap por fase.

Para ahorro de tiempo y emisiones:

- Indicar qué se compara: tiempo de cómputo contra baseline, duración operacional contra una ruta de referencia o emisiones contra una alternativa de transporte.
- Usar la misma demanda/alcance para comparar, o advertir diferencias de entregas. Conservar resultados negativos si la propuesta empeora la referencia.
- No inferir tiempo operacional a partir de tiempo de cómputo.
- CO2e evitado requiere referencia, consumo, factores de emisión, unidades, fuente/fecha y alcance de la estimación. No presentar emisiones de escape como emisiones de ciclo de vida.
- No equiparar consumo neto de batería con electricidad comprada sin modelar pérdidas y condiciones de comparación.
- Sin referencia o factores válidos, devolver `null` y explicar qué falta. No inventar ahorros ni presentar estimaciones como mediciones.

UI pensada para un operador de CASE/FCFM:

- Carga de archivo y edición gráfica/formulario con errores claros.
- Mapa vial con depósito, entregas, cargadores y colores por vehículo.
- Primero factibilidad y entregas; después energía, tiempos y estado de optimalidad.
- Detalle por ruta con secuencia, batería y recargas; supuestos visibles cuando afectan decisiones.
- Comparación estándar/tuning, cuando exista una comparación medida.
- Descarga del JSON y de la instancia normalizada.
- Estados comprensibles: validando, preparando, ajustando, resolviendo, comprobando, completado/error. No mostrar resultados antiguos como si correspondieran a parámetros recién editados.

## 9. Trabajo paralelo, branches y worktrees

**Actualización UI de Diego, 14-10-2026:** concentrar el trabajo de interfaz en **`codex/ui`**, o ramas basadas en ella, con destino **`main`**. Worktree de UI: `AWS-Hackaton-ui`; el checkout original del motor permanece en `AWS-Hackaton`/`main`. La guía inicial proponía establecer `master`; esa migración no se ejecutó y no debe hacerse como efecto secundario del trabajo de UI. Conservar historia y coordinar cualquier cambio futuro de integración.

**Actualización de Diego, 15-10-2026:** la elección visual ya ocurrió: estética de Cristal, tamaños de botones y distribución de Esencial. Implementar esa base y continuar autónomamente en un nuevo chat con inicio/dashboard, sidebar discreta y menú de perfil. Opus 5.5 por Kiro diseña e implementa; Astra audita, critica y depura, acreditando aportes reales. Investigar guías con find-skills. No volver a pedir la elección entre las cuatro variantes. La identidad sigue pendiente. Se autorizan frontend funcional y fixtures identificadas sin modificar el motor. Streamlit sigue como previsión de integración; no asumir React aprobado. Estado y reparto en `docs/WEBAPP-HANDOFF.md` y `docs/ESTADO-Y-HANDOFF.md`.

- Una tarea/agente por rama `codex/<area>-<tarea>` y worktree o workspace designado.
- Antes de editar: identificar rama, directorio, estado de Git, alcance y propietario de los archivos.
- No trabajar varios agentes en el mismo checkout mutable ni cambiar la rama bajo otro agente.
- No usar `reset --hard`, limpieza masiva, force push o descarte de cambios ajenos para resolver conflictos.
- No integrar directamente trabajo incompleto en la rama de integración. Usar commits/PRs pequeños y revisables.
- El integrador coordina cambios transversales, revisa merges y resuelve conflictos preservando los contratos y objetivos.
- No automatizar el stage de todo el repositorio. Incluir solo cambios correspondientes a la tarea.

Reparto inicial:

| Área | Responsabilidad principal | Coordinación necesaria |
|---|---|---|
| Integración | contratos, configuración, pipeline, dependencias y merges | acuerda contratos antes de trabajo paralelo |
| Datos/energía | inputs, red, perfiles y estimador | entrega instancias normalizadas al modelo |
| Optimización | Pyomo, solver, fases y certificados | consume contratos; no depende de UI/AWS |
| LLM/AWS | Bedrock, adaptación LLM4MIP y tuning | usa capacidades reales del adaptador |
| UI/UX | formulario, mapa y resultados | consume pipeline/RunResult, sin duplicar lógica |
| Validación/métricas | comprobador, KPIs y comparaciones | independiente de construcción Pyomo |

Una persona puede cubrir varias áreas. La tabla asigna responsabilidades, no exige crear más equipos o capas. Coordinar antes de editar simultáneamente `contracts.py`, `config.py`, `pyproject.toml`, el lockfile o este archivo.

## 10. Entregas y verificaciones necesarias

Construir incrementos ejecutables:

1. Contratos, configuración y un ejemplo sintético pequeño.
2. Flujo CLI con Pyomo, solver estándar, validador y JSON.
3. Datos/red/energía reales con sus supuestos y cachés.
4. Bedrock y tuning validado con material reutilizado de LLM4MIP.
5. Interfaz conectada al mismo pipeline.
6. Comparación reproducible, prueba con entradas reemplazables y demo para el jurado.

UI y AWS pueden avanzar en paralelo usando fixtures acordadas, sin presentar fixtures como resultados reales.

Pruebas mínimas con valor:

- Lectura CSV con BOM, campos opcionales y errores de esquema.
- Integración energética en tiempos irregulares y separación entre viajes.
- Instancia pequeña con óptimo conocido; caso donde solo parte de las entregas es factible.
- Recarga repetida y regeneración con saturación y déficit intermedio.
- Retorno, reserva y unicidad de entregas comprobados independientemente.
- Timeout con/sin incumbente y reportes correctos de las fases lexicográficas.
- Respuestas LLM inválidas, opciones no permitidas y fallback.
- CLI y UI consumen el mismo contrato y toleran reemplazar la instancia.

No escribir tests que solo repitan la implementación ni benchmarks costosos para cambios documentales. Las pruebas unitarias no llaman a AWS ni descargan mapas. Separar explícitamente pruebas de integración con red y su presupuesto.

Cada entrega debe informar qué cambió, validación ejecutada, limitaciones y cómo reproducirla. No afirmar mejoras de tiempo, energía, gap o emisiones sin comparación verificable.

Fuentes técnicas de la integración AWS:

- https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html
- https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html
