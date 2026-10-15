# Integración beta UI–evrp

Esta rama conecta Inicio y Plan con una ejecución real del proveedor `evrp`.
Conserva la interfaz publicada de `codex/webapp` (`bb08a4a`) y adapta explícitamente
el motor de `codex/optimizacion-contraida`
(`f88d0120c0b80087d718224b46b2613735cee69c`). No integra las historias de ambas
ramas ni modifica el motor. El proveedor utiliza HiGHS directamente; esta beta no
demuestra equivalencia con la formulación Pyomo de `modelamiento.pdf`.

## Ejecución local

Se necesita un checkout limpio del proveedor en ese SHA y su entorno:

```sh
# En un checkout separado y verificado de codex/optimizacion-contraida:
uv sync --locked --group dev

# Desde la raíz de esta rama, usando el Python de aquel entorno:
/ruta/al/proveedor/.venv/bin/python -m backend.local_server --port 8000
```

Abrir `http://127.0.0.1:8000/`. El servidor sirve exclusivamente el frontend y la API
local. Verifica SHA, cambios del proveedor y versión HiGHS `1.11.0`. No requiere
otro lockfile, instalación de paquetes JavaScript, AWS, autenticación ni una base
de datos. El comando estático de `webapp/README.md` sigue sirviendo el ejemplo,
pero no ejecuta el motor.

1. Pulsar **Cargar y calcular**; seleccionar CSV de nodos, preparada
   `evrp.instancia_preparada/1` o una instancia/resultado descargado de la beta.
2. Revisar el resumen y configurar capacidad útil, reserva y consumo.
   Dos vehículos al 60 % es el perfil oficial; los demás valores son supuestos.
3. Confirmar el alcance y calcular. **Usar caso sintético pequeño** completa un
   caso de prueba expresamente identificado; también se resuelve con HiGHS real.
4. Consultar el mismo `run_id` en Inicio y Plan, vehículos, paradas y pendientes.
5. Descargar instancia o resultado completo. Ante error HTTP se puede descargar
   el intento fallido con su entrada y error, sin inventar un resultado.

La entrada CSV no trae calles. En esta beta se admite como referencia explícita
`haversine`, plana y sin conectividad vial certificada. Una preparada conserva su
red declarada y geometrías guardadas. Sin geometría, las paradas siguen disponibles.
No se descarga una red ni se transforma un fallo del motor en un ejemplo.

## Contrato y estado compartido

La definición HTTP está en [backend/API_CONTRACT.md](../backend/API_CONTRACT.md).
Reutiliza `/health`, `/solve` y el envoltorio `api_version/result` del servicio
`deploy-aws` (`9f1389c`), con versión nueva **`2.0-beta.1`**. Su contrato antiguo
`ev_routing`, el de `modelamiento` y el `Resultado` nativo de `evrp` son distintos.
Las opciones antiguas `movement_limit` y `network` se rechazan; no se ignoran.

El adapter recibe preparada + configuración efectiva + resultado + metadatos.
Los IDs originales permanecen en la presentación; una tabla reversible registra
los IDs internos usados para evitar colisiones upstream con `|` y `#fin`.
El servicio añade el origen que omite el detalle nativo y convierte geometría
`[lat,lon]` a GeoJSON `[lon,lat]`. JavaScript convierte kWh a porcentaje por
capacidad, comprueba la estructura y presenta servicio explícito; no estima energía.

El servidor conserva como máximo cuatro corridas y 32 MiB en memoria. Las
referencias expiran con el reinicio o reemplazo. `sessionStorage` guarda únicamente
el ID, revisión y estado mínimo de la ejecución; no almacena preparadas ni respuestas.
No es persistencia de una organización ni aislamiento entre usuarios.

Editar marca **Cambios sin calcular** y mantiene identificado el resultado anterior.
Una respuesta tardía no puede reemplazar la revisión vigente. La selección del
Plan depende del `run_id` y de la ocurrencia de la parada. El regreso por BFCache
comprueba si cambió la ejecución. **Dejar de esperar** aborta la espera del navegador;
no promete cancelar el solver. Un 422 sin incumbente no significa infactibilidad.

## Energía, alcance y límites

El proveedor tiene una discrepancia reproducida entre su política de recarga del
detalle y la simulación de consumo efectivo de KPIs. En el caso regenerativo
sintético, inicial 6 + recarga 5 − final 8 = 3 kWh, mientras el KPI dice −1 kWh.
Se conservan ambas fuentes en `raw`, se deja consumo efectivo `null` y se retira
la afirmación de factibilidad cuando esos datos se contradicen. No se corrige con
una matemática alternativa en JavaScript.

El detalle upstream redondea la batería a cuatro decimales. Si ese redondeo cruza
capacidad o reserva dentro de su precisión conocida, la lectura de presentación
y la factibilidad se dejan sin certificar, con advertencia y valor original en
`raw`. No se recorta silenciosamente una lectura a sus límites.

La factibilidad `true` significa comprobación del proveedor con el alcance
descrito en la respuesta; no garantiza consumo real ni valida externamente la red.
Las cotas, gap y optimalidad no se publican como certificados porque el proveedor
no ofrece evidencia homogénea suficiente. `phases` queda vacío y la traza original
se descarga. Los valores desconocidos se muestran como `—`, no como cero.

`runtime_seconds.solver` mide `resolver_preparada` completo, incluida construcción,
heurística, MILP y validación del proveedor. La interfaz lo denomina **Resolución
(incluye modelo y validación)**. `total` mide el servicio completo; no se suman
intervalos contenidos ni se presenta como tiempo puro HiGHS. El presupuesto
solicitado limita la búsqueda, no toda la latencia de preparación/serialización.

Límites locales: una flota homogénea de 1–20 vehículos, hasta 200 nodos, petición
de 8 MiB y presupuesto solver de 1–120 s. No son reglas del concurso. Esta beta
no incorpora auth, DB, geocodificación, tuning AWS, despliegue ni integración de
las ramas exploratorias de login.

## Comprobación

```sh
node --test webapp/tests/*.test.mjs
/ruta/al/proveedor/.venv/bin/python -m unittest discover -s tests -p test_web_bridge.py -v
git diff --check
```

Las pruebas Python reales necesitan el entorno fijado. Sus omisiones se reportan
como `skip`; una corrida sin ese entorno no demuestra conexión MILP.
`backend/fixtures/tiny-request.json` y `tiny-response.json` son un caso sintético
realmente ejecutado y su salida completa; sus tiempos no son un benchmark.

La evidencia local de esta entrega queda en `.local/integration-beta/`: baseline
de la UI publicada, revisión independiente, capturas del recorrido HTTP/MILP y
matriz visual. No se versionan screenshots, datos de CASE, entornos ni cachés.
La rama se entrega con commits locales revisables; no se fusiona, publica ni
despliega automáticamente.

## Pendientes del proveedor

Para Daniel/Lucas, sin modificar su rama:

- Unificar detalle, política de recarga y energía efectiva; ofrecer una única
  contabilidad verificable, incluyendo regeneración saturada.
- Hacer segura la serialización de pares con IDs opacos y el depósito `#fin`.
- Validar todas las referencias, exclusiones y números finitos de preparadas.
- Comprobar todos los parámetros/tipos energéticos antes de reusar preparación.
- Ofrecer estados estables con/sin incumbente y certificados por fase completos.
- Documentar equivalencia o diferencias entre modelo contraído y PDF vial base.

La aceptación AWS y una prueba con red vial de procedencia verificada siguen
pendientes; las pruebas locales de esta entrega no las simulan.
