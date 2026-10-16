# Integración de correcciones de las sesiones ZMD

Fecha: 16 de octubre de 2026.

Base de comparación: `origin/main` recién actualizado, fijado en
`5d8745e3faa90b9ae4aca541ad90f665c6974b3a`.
Rama de integración: `codex/integrate-session-fixes`.

## Actualización posterior: rama de asistencia

Tras comprobar nuevamente que `origin/main` seguía en `5d8745e`, se recibió
la petición de incorporar la rama de asistencia recién publicada. Se encontró
`origin/feat/ia-asistente-mas-datos` en
`087bd3e52a686f763865d21589650d3d8d706e12`, que incluye la rama anterior
`feat/ia-asistente-explicacion`. Sus ocho commits se fusionaron en `4ebb66b`.

La rama añade el chat en Inicio y Plan, los endpoints `/assist/chat` y
`/assist/schema`, la carga y resolución desde el asistente y explicaciones
con tiempos, indicadores, gaps y certificados por fase. También restaura
intencionalmente el diseño anterior de Inicio/Plan: el caso de la hackatón
se precarga al abrir «Cargar y calcular». El mapa de preparación anterior
deja de ser la pantalla inicial.

Las correcciones de recuperación y concurrencia de la primera integración
se conservan. Las quince regresiones de cambios de entrada se adaptan a la
nueva apertura del diálogo; no se exige el selector del mapa que esta rama
retiró de la pantalla inicial.

La primera comprobación de la combinación dio **1.007 pruebas Python
aprobadas**, diez omitidas y una excluida por requerir datos reales, además
de **161 pruebas JavaScript aprobadas**. La revisión independiente también
reprodujo problemas que esas pruebas no cubrían: resultados sin solución
presentados como planes listos, repetición de efectos tras fallar Bedrock,
uso de una conexión ya desconectada y publicación de respuestas del chat
sobre un borrador distinto.

Se incorporaron tres correcciones con reproducción anterior y pruebas:

- `938861d`: un fallo posterior de Bedrock conserva las acciones realizadas
  y no vuelve a ejecutar el pedido. Cada llamada comprueba la sesión vigente,
  su caducidad y el bloqueo compartido; desconectar impide llamadas futuras.
- `c72a238`: sin solución validada, el chat conserva conteos desconocidos y
  muestra el diagnóstico, sin presentar un plan listo ni cero entregas
  ficticias. Una solución factible de cero entregas sigue mostrando cero.
  La explicación de esos estados usa el diagnóstico determinista.
- `63a8275`: un resultado del chat se publica con un estado limpio,
  correspondiente a ese cálculo. Si el usuario cambia la entrada mientras
  espera, la respuesta anterior no reemplaza el borrador ni abre otro plan.
  Incluye dos regresiones de navegador y adapta las quince anteriores.

Verificación final de la combinación en `a1bfea4`:

| Comprobación | Resultado |
| --- | --- |
| Python completo, sin red ni datos reales | **1.022 aprobadas, diez omitidas, una excluida y 37 subpruebas aprobadas**, cero fallos; 47,94 s. |
| JavaScript completo | **161 aprobadas**, cero fallos. |
| Navegador, cambios de fuente y estado del chat | **17 escenarios aprobados**. |
| HTTP del asistente → SCIP → resultado → explicación | **Aprobado**: dos entregas de dos, 14 kWh, validación independiente y explicación de tiempos/gaps de ambas fases desde el resultado publicado. |

Las diez omisiones son las condiciones de backend ya registradas en la
primera integración. La nueva exclusión requiere datos reales. Las pruebas
de Bedrock usan dobles; la aceptación HTTP desactiva Bedrock y bloquea
conexiones fuera de loopback. No se acredita acceso real a AWS.
La evidencia queda en `.local/session-integration/assist-087bd3e/`.
Se volvió a consultar el remoto al cerrar: la rama seguía en `087bd3e`.
No se modificaron el núcleo del solver, datos originales ni presentaciones.

Las secciones siguientes documentan la primera consolidación, anterior a
esta actualización del asistente.

La integración se preparó en un worktree independiente. Se revisaron los
cambios contra esta base y se reprodujeron los defectos antes de portarlos.
La rama `main` y los checkouts de las sesiones originales se conservaron.

## Sesiones y procedencia

| Sesión | Estado frente a la base | Tratamiento |
| --- | --- | --- |
| ZMD Features Implementation | `bc4609e` ya es antecesor de `5d8745e`; no tiene commits exclusivos ni cambios locales de producto. | Sus funciones ya están en `main`; no se duplicó su implementación. |
| ZMD Final A — QA y depuración | Dos commits exclusivos: `cf61b82` y `15ce5b7`. | Se portaron y adaptaron al nuevo mapa, los borradores y la carga diferida de eVED. |
| ZMD Final B — Integración y demo | Un commit exclusivo: `be228a4`. | Se portó la corrección del contrato de límites del histórico y su documentación. |

Esta identificación de las tres sesiones se comunicó como supuesto durante
el trabajo. También se inventariaron las propuestas de **ZMD Final D —
Producto y UX**: esa sesión no tenía código implementado que fusionar.

Commits adaptados: `c82f7fa` (recuperación de intentos), `447a1d7`
(concurrencia de entradas), `d7fe9f5` (límites del histórico) y `44dbfd4`
(regresión de pricing). Se fusionaron en esta rama conservando sus commits
y la procedencia de los parches originales.

No se incorporaron presentaciones, pitches, guiones, paquetes de demo,
resultados masivos, datos reales, credenciales ni recursos personales. Los
archivos de esas clases que ya pertenecían a la base no se eliminaron.

## Cambios de comportamiento respecto de la base

### 1. Recuperar un intento vial fallido

Antes, importar un intento exportado podía reutilizar un identificador de
instancia preparada que ya no existía en el servidor, o preferir una instancia
antigua sobre las entradas que permitían reconstruirla.

Ahora, si el intento contiene `prepare_request`, se recuperan esas entradas
para preparar de nuevo la red. Se conservan las opciones del solver y se
descartan el identificador temporal y la instancia preparada anteriores.
La validación de versión y de campos admitidos sigue activa.

Archivos: `webapp/shared/solver-input.js` y
`webapp/tests/native-input.test.mjs`. Procedencia: `cf61b82`.

### 2. Respetar la última entrada elegida

Un cálculo pendiente de cargar el escenario o su histórico ya no puede
ejecutarse después sobre otra entrada que el usuario acaba de seleccionar.
Cambiar a un archivo o un caso sintético retira el intento pendiente;
calcular esa nueva entrada requiere su propio clic.

Las respuestas y errores de escenarios antiguos ya no reemplazan mensajes
de la entrada vigente. El cierre de una petición antigua tampoco desbloquea
otra carga más reciente.

Archivos: `webapp/run-panel.js` y
`webapp/tests/source-switch.browser.mjs`. Procedencia: `15ce5b7`,
adaptado a los cambios de `5d8745e`.

### 3. Calcular una instancia nativa sin esperar un histórico ajeno

Una instancia JSON nativa ya contiene los datos necesarios para su cálculo.
La carga simultánea de un histórico para otra entrada no bloquea su envío.
Las entradas que sí necesitan el histórico mantienen la espera.

Archivos: `webapp/run-panel.js` y
`webapp/tests/source-switch.browser.mjs`.

### 4. Conservar decisiones tomadas durante la carga diferida de eVED

La revisión sobre el nuevo `main` encontró dos casos adicionales del mismo
problema de concurrencia. Mientras llegaba el histórico predeterminado, el
usuario podía elegir o quitar otro histórico, o confirmar una edición de
ubicaciones. La respuesta antigua podía reemplazar esa selección o mostrar
un error correspondiente al estado anterior.

Ahora esas decisiones retiran el cálculo pendiente. Una respuesta tardía,
tanto exitosa como fallida, no sobrescribe la elección confirmada ni inicia
automáticamente un cálculo. La adopción del histórico por la petición
vigente sigue funcionando y conserva la invalidación de resultados previos.

Archivos: `webapp/run-panel.js`, `webapp/shared/history-panel.js` y
`webapp/tests/source-switch.browser.mjs`. Es una adaptación adicional
reproducida contra la base, no una nueva función propuesta por Producto.

### 5. Informar los límites reales de carga del histórico

`GET /health` anunciaba un máximo único de 256 MiB aunque el servidor admite
CSV de hasta 4 GiB. Ahora informa el máximo global y los límites por formato:
CSV, 4 GiB; JSON, 256 MiB. Estos valores provienen de las constantes usadas
por el procesamiento del histórico.

El contrato documenta el campo adicional por formato y corrige a 256 MiB el
límite documentado de retención de resultados. La admisión efectiva de
archivos no cambia. Las pruebas comprueban el contrato y el rechazo HTTP
de tamaños declarados superiores al límite, sin crear archivos gigantes.

Archivos: `backend/service.py`, `backend/API_CONTRACT.md` y
`tests/test_historical_web.py`. Procedencia: `be228a4`.

### 6. Comprobar la interrupción del pricing en el callback vigente

La batería inicial detectó una prueba que sustituía un método del oráculo
antiguo y suponía que un presupuesto de 10 ms siempre interrumpiría el pricing.
Con el motor actual podía terminar el presupuesto antes de llegar al callback
o no activar el método sustituido.

Se conserva una prueba de presupuesto corto que comprueba la factibilidad
y, si el solver declara optimalidad lexicográfica, el óptimo manual de dos
entregas y 4 kWh. Se añaden
dos casos que agotan el plazo dentro del callback real, uno por fase.
Exigen conservar el incumbente factible, la cota analítica y la ausencia de
una certificación falsa de optimalidad o infactibilidad.

Un control negativo que simulaba una certificación falsa hizo fallar ambos
casos; el código vigente los supera. Solo cambia
`tests/test_route_solver.py`: no se modifican el solver, su formulación,
sus objetivos ni sus tolerancias.

## Verificación

La combinación de cambios quedó fusionada en `56126fc`. Las evidencias
detalladas, capturas e instancias sintéticas permanecen en
`.local/session-integration/`, ignorado por Git.

| Comprobación final | Resultado |
| --- | --- |
| Python completo sin marcadores `network` ni `real_data` | **965 aprobadas, 10 omitidas, 37 subpruebas aprobadas; cero fallos**, 85,26 s. |
| JavaScript completo | **161 aprobadas; cero fallos u omisiones**. |
| Navegador: concurrencia de entradas e históricos | **15 escenarios aprobados**; respuestas exitosas y fallidas controladas. |
| Navegador → servidor real → SCIP → validador → exportación | **Dos ejecuciones aprobadas**, cada una con dos entregas factibles; vista de escritorio y móvil, sin errores JavaScript. |
| Revisión independiente y `git diff --check` | Sin hallazgos pendientes dentro del parche; formato limpio. |

Las pruebas adicionales del mismo frontend, ejecutadas antes de fusionarlo,
aprobaron los flujos de mapa y escenarios, exportaciones y panel histórico.
El revisor independiente repitió los 15 escenarios y 35 pruebas de entrada,
cliente e históricos, también sin fallos.

De las diez omisiones de Python, nueve requieren un ejecutable externo
`scip` que no está instalado. La prueba restante de warm start se omite
según su comprobación de disponibilidad del backend: obtuvo un incumbente
factible sin demostrar el máximo de entregas. Estas omisiones también
estaban en la base. **PySCIPOpt 6.0.0 sí se ejecutó** en las pruebas nativas
y en la aceptación completa con el servidor real.

La base, antes de aplicar correcciones, dio:

- JavaScript: 160 pruebas aprobadas.
- Python sin marcadores `network` ni `real_data`: 956 aprobadas,
  10 omitidas, 37 subpruebas y cuatro fallos.
- Navegador: flujo de mapa y escenarios aprobado.

Tres de los cuatro fallos iniciales dependían de plazos reales muy breves:
dos pruebas esperaban aplicar propuestas LLM dentro de 10 ms y una esperaba
completar rutas dentro de 3 s. Las tres pasaron al repetirse de forma aislada.
En los casos LLM, la instrumentación observó que el hilo empezaba después
del plazo, por lo que el producto usaba correctamente el fallback. El cuarto
fallo correspondía a la prueba obsoleta de pricing corregida arriba.
Los tres casos sensibles a tiempos también aprobaron en la batería final
completa; siguen dependiendo de la carga de la máquina y no se modificaron
para esta integración.

### Reproducción

Desde la raíz del worktree, usando un entorno con las dependencias del
proyecto instaladas:

```sh
PYTHONPATH="$PWD/src:$PWD" OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 AWS_EC2_METADATA_DISABLED=true \
  python -m pytest -q -m 'not network and not real_data'
node --test webapp/tests/*.test.mjs
git diff --check 5d8745e
```

Para las regresiones de navegador, servir `webapp/` en un puerto local y
configurar `ZMD_QA_ORIGIN`. Si Playwright no se resuelve desde el proyecto,
`PLAYWRIGHT_MODULE` puede señalar su módulo instalado. Las pruebas usan
respuestas HTTP controladas y no requieren AWS ni datos privados:

```sh
ZMD_QA_ORIGIN=http://127.0.0.1:4396 \
  node webapp/tests/source-switch.browser.mjs
```

La aceptación con servidor real usa dos instancias sintéticas pequeñas:
una creada en la interfaz y otra desde
`backend/fixtures/native-operations-request.json`. Comprueba preparación,
SCIP, validador independiente, recuperación por `run_id`, valores visibles,
exportaciones completas y nativas, y vista móvil. Distinguir esta ejecución
real de las pruebas de concurrencia con HTTP simulado.

No se llamó a AWS, no se procesaron históricos privados ni se descargó una
red vial durante estas pruebas. No se midió una mejora de energía, velocidad
del solver o impacto operativo: las mejoras comprobadas son recuperación de
entradas, coherencia del estado y exactitud del contrato.

## Hallazgos y propuestas que siguen pendientes

Estos puntos no venían implementados en los commits de las sesiones y no se
presentan como correcciones integradas:

- Un error al recuperar un histórico guardado puede borrar su selección.
- Un candidato rechazado por el validador puede resultar inaccesible en la
  interfaz cuando el adaptador rechaza también sus valores físicos.
- Faltan rótulos específicos para `deterministic` y `partial_fallback`.
- El proveedor web de Bedrock no conserva las mismas trazas que otros caminos.
- El motivo de duración no disponible aún contiene una referencia heredada a H.
- Producto propuso resumir paradas operativas, acercar el estado AWS a la
  búsqueda, identificar mejor las ejecuciones, ampliar la comprobación
  previa y comparar exportaciones. Son propuestas, no funciones fusionadas.

La consolidación no equivale a una aceptación en la cuenta AWS del equipo,
un benchmark con los datos del concurso ni una garantía de ausencia de
defectos fuera de los flujos comprobados.
