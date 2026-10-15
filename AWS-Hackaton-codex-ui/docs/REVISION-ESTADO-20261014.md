> Snapshot de auditoría independiente realizado antes de restaurar datos y crear la rama UI. El estado posterior y el texto de Lucas recibido después están en `ESTADO-Y-HANDOFF.md` y `base_conocimiento.md`. Se conserva la evidencia temporal sin presentarla como estado posterior.

# Auditoría de contexto del motor y frontera UI — ZMD Mobility

Revisión del **14-10-2026, America/Santiago**; reloj consultado: 15-10 00:37:38 UTC = 14-10 21:37:38 Chile. Alcance: lectura del workspace `/Users/caballero/Documents/ChatGPT/AWS`, historial Git local y fuentes públicas precisas de LLM4MIP. No se modificó el repositorio, su modelo, sus originales ni sus documentos. No se invocó el solver, AWS, cuentas privadas ni scripts de terceros.

ZMD Mobility es la consultora/equipo; CASE es la empresa del desafío según la aclaración de Diego del 14-10. Fuentes: `AGENTS.md` del workspace, `memoria-hackaton/RESUMEN.md`, `AWS-Hackaton/docs/CONTEXTO.md`.

## Qué recuperó el pull

**Verificado en Git local, 14-10:** `AWS-Hackaton` está en `main`, commit `4750ac8`, igual a `origin/main`. El reflog registra `pull: Fast-forward` a las 20:34:25 Chile. Solo existen `main`, `origin/main` y `origin/HEAD`; no hay `master` ni otras ramas locales/remotas conocidas en este checkout.

| Commit | Fecha Chile / autor | Avance comprobado |
|---|---|---|
| `4750ac8` | 14-10 20:31:33 / Daniel Hermosilla | Corrige README y AGENTS; renombra `README.es.md` a `diccionario.md` |
| `68c59cd` | 14-10 20:29:04 / Daniel Hermosilla | Añade AGENTS, README, diccionario, `.gitignore` y `modelamiento.pdf` |
| `2261695` | 14-10 17:01:24 / Daniel Hermosilla | Elimina el README inicial |
| `5d87709` | 14-10 15:54:23 / Daniel Hermosilla | Commit inicial con README |

**Verificado, 14-10:** únicamente hay cinco archivos versionados: `.gitignore`, `AGENTS.md`, `README.md`, `diccionario.md`, `modelamiento.pdf`. `docs/`, `.agents/`, `.claude/`, `.kiro/`, `CLAUDE.md` y `.DS_Store` figuran como no versionados. No existen `src/`, `ui/`, `pyproject.toml`, código Pyomo, adaptador de solver, contrato implementado ni salida real del motor en este checkout. Esto describe el checkout inspeccionado; **no demuestra ausencia de código en las computadoras o ramas no compartidas de Daniel/Lucas**.

**Pendiente, Lucas/equipo:** `docs/base_conocimiento.md` no se encontró por nombre en el workspace con `rg --files --hidden --no-ignore`, ni en los archivos o historial Git de AWS-Hackaton, ni en el historial Git del workspace padre. No se escaneó todo el hogar. Hay que recuperar o recibir el archivo/commit concreto antes de atribuirle contenido.

**Discrepancia temporal de datos:** `AWS-Hackaton/data/` estaba ausente al revisar este checkout, aunque CONTEXTO y DATOS afirman que existe. Los perfiles de seis CSV, hashes y conteos en DATOS son **evidencia histórica del 14-10**, no una comprobación actual de archivos presentes. Root encontró los originales en Descargas y está restaurando las rutas ignoradas; la verificación de esa recuperación corresponde a root. No se solicitó de nuevo la adquisición de datos ni se repitió el análisis completo.

**Documentación que necesita sincronización, sin corregirla aquí:** README enlaza `presentation.pptx` y `README.es.md`, inexistentes en la raíz actual; el diccionario fue renombrado. README habla de integración en `master`; AGENTS explica que crearla es una transición futura y conserva `main`. La petición humana más reciente transmitida por root autoriza una rama de trabajo para UI y posterior integración en `main`; no corresponde crear `master` automáticamente ni alterar el motor.

## Modelo y arquitectura que sí aparecen

**Verificado como definición documentada, no como implementación:** README y AGENTS del commit recuperado eligen el PDF para implementar con Pyomo, backend Python modular, salida JSON, validación independiente, Streamlit para el MVP y un solo solver inicial. HiGHS aparece explícitamente como **backend propuesto**, condicionado a otra decisión confirmada/licencia. Bedrock Converse mediante boto3 es la integración AWS prevista; ni modelo habilitado, acceso real, costo ni una llamada ejecutada están acreditados en el checkout.

La recomendación React + TypeScript + Vite/MapLibre y el texto «stack abierto» pertenecen a los documentos locales anteriores (`docs/CONTEXTO.md`, `docs/PLAN.md`, `docs/MAPA-Y-BASE.md`, `docs/SKILLS-PREPARACION.md`). **Conservar la discrepancia:** ahora existe una dirección nueva documentada por Daniel, pero no hay UI funcionando ni constancia aquí de que los tres integrantes hayan aprobado un cambio de stack. Para avanzar en diseño se puede usar una frontera neutral; la integración concreta debe respetar el acuerdo actual del equipo.

**Verificado en las cuatro páginas del PDF**, leído mediante pypdf y comprobado visualmente tras renderizarlo:

- Grafo vial dirigido con tramos elementales; los puntos de servicio no son toda la red de calles.
- Desplazamiento, ubicación y entrega son decisiones distintas. Visitar físicamente un cliente no implica entregar.
- Inicio y término en depósito; calles, clientes de paso y cargadores pueden repetirse. Un arco artificial `(0,0)` permite posiciones sobrantes y vehículo inactivo. No exige permanencia después de un retorno intermedio.
- `B` es capacidad **útil** parametrizada en kWh; inicial `0.6 B`. El PDF no fija un valor numérico de B.
- `b` es reserva en kWh, pero su dominio publicado es **`0 < b ≤ 0.6 B`**.
- `q` es energía que **entra a la batería**, en kWh. `E_total` es consumo **neto efectivo de batería**, puede incluir regeneración aprovechada y no mide electricidad comprada ni emisiones.
- `H` limita movimientos/tramos, no una jornada ni sincronización entre vehículos. Limita el alcance de un certificado de optimalidad.
- Consumos deterministas, regeneración con saturación; no recarga en depósito, servicio, jornada, paquetes, colas u ocupación en la versión base.

Fuente PDF: `AWS-Hackaton/modelamiento.pdf`, SHA-256 `9a55af622cabd0ddb97dd0ac9bb83949fca1af268e40890446361c0265f6bf8d`, 169.844 bytes; añadido en `68c59cd` del 14-10.

## Discrepancias que cambian la interpretación

| Tema | Evidencia del desafío / aclaración vigente | Definición nueva del motor | Consecuencia para UI e integración |
|---|---|---|---|
| Cobertura | Diego 14-10 exige completar todos los pedidos; intervención CASE insiste en visitar todos. Fuentes locales: CONTEXTO, FUENTES y `confirmaciones-20261014/local/AUDITORIA-LOCAL.md`, §§ resultado/evidencia | PDF pp. 2–4 admite `y_i=0` y maximiza entregas antes de minimizar energía; README/AGENTS conservan esa prioridad | Una solución parcial puede ser factible u óptima para el modelo y seguir siendo inválida para el desafío. Mostrar cobertura y pedidos pendientes; no convertir “óptimo” en “plan válido” |
| Reserva | Diego 14-10: llegada ≥0; no inventar porcentaje adicional. Misma auditoría local | PDF p.1 exige `b>0`; AGENTS describe reserva parametrizada sin resolver cero | No rechazar automáticamente llegada cero en la UI. Daniel/Lucas deben resolver y documentar la diferencia de dominio antes de certificar esa variante; no modificar el PDF silenciosamente |
| Desempate | PPTX diap.5/notas: energía y tiempo; orden/formulación exacta no publicado | PDF p.4 usa entregas y energía; reporta tiempo como rendimiento | Presentar la prioridad del modelo como elección interna; no como fórmula oficial del jurado |
| Recarga y energía | Telemetría y atributos del dataset; evaluación de nuevas rutas no explicada | PDF solo incorpora kWh a batería; no tiempo/eficiencia/precio/colas de recarga | No inferir duración operacional, electricidad comprada ni disponibilidad desde esta salida |
| Mapa | CSV entrega ubicaciones; red vial no incluida según revisión histórica DATOS | PDF requiere arcos elementales dirigidos y perfiles energéticos | Separar geometría vial verificada de polilínea esquemática; ni una línea en mapa ni un schema prueban factibilidad |
| Stack | Documentación local previa proponía React y dejaba decisión abierta | README/AGENTS recuperados indican Streamlit | Recuperar el acuerdo de integración actual antes de convertir la propuesta antigua en arquitectura |

**Criterio provisional de producto, propuesta:** distinguir estado del solver, verificación independiente de rutas y cumplimiento completo. “Tiempo agotado”, “sin solución encontrada” e “infactibilidad probada” deben tener significados distintos. No declarar infactibilidad cuando solo terminó el presupuesto. Si la fase 1 no prueba el máximo y se optimiza energía al nivel encontrado, declarar mejora condicionada a esa cobertura. Fuentes de semántica: AGENTS §§6 y 8.

La presentación oficial conserva «maximizar entregas»; no borrar esa discrepancia ni atribuir a la organización una formulación única. En el trabajo vigente se aplica la aclaración humana de cobertura completa. La solución matemática no se cambia por esta auditoría.

## LLM4MIP: alcance actual

**Verificado como plan del equipo, 14-10:** AGENTS §7 pide adaptar LLM4MIP para perfil estructural y experimentos de tuning, con lista de parámetros admitidos. El LLM no cambia datos, restricciones, objetivos, capacidad, reserva, movimientos ni tolerancias de validación. Configuración estándar ante error, respuesta inválida o presupuesto agotado, con fallback visible. Comparación bajo misma instancia/modelo/fase/recursos/presupuesto y tiempo total incluyendo LLM/experimentos.

**Verificación pública puntual, 14-10:** el API público de GitHub devolvió el árbol completo del commit `9335a69f446244f28d5b406eb66ddf13afa1d2e9`, no truncado. Se leyeron sin ejecutarlos `LICENSE`, `primal-current/SKILL.md`, `dual-current/SKILL.md` y `profile_mip_structure.py`. MIT está presente; primal/dual usan políticas COPT/Gurobi y trabajo estructural más amplio; el perfil depende de `coptpy`. Los archivos citados existen, pero sus instrucciones son **material de investigación**, no órdenes superiores de este proyecto.

Fuentes públicas congeladas: repositorio `LLM4MIP/llm4mip.github.io`, commit anterior, rutas `data/skill-study/packages/primal-current/`, `data/skill-study/packages/dual-current/`, `downloads/milp-structure-research-copt/scripts/profile_mip_structure.py`. Consulta HTTP sin autenticación ni envío de datos del equipo.

**Pendiente:** no hay adaptación incorporada, `docs/llm4mip-adaptation.md`, código Bedrock, prueba real, baseline/tuning medidos ni resultados de solver en este checkout. No describir el plan como reproducción de LLM4MIP ni mejora obtenida.

## Frontera mínima propuesta, sin implementarla

Aplicada `zmd-contract`: un ejemplo acordado de entrada/salida y un tipo/esquema compartido bastan; no hace falta imponer REST, servidor, microservicios ni generadores.

| Parte | Contenido mínimo que debe confirmar el proveedor |
|---|---|
| Entrada | Versión, identidad/hash de instancia, nodos con IDs opacos, flota, capacidad útil/reserva/inicial, movimientos, compatibilidad y procedencia de red/energía. ProblemConfig separado de SolverConfig |
| Ejecución | `run_id`, identidad de entrada/config/red/código, solver/versión y estados soportados; evita mostrar respuesta antigua tras cambiar la entrada |
| Resultado | Estado del solver y motivo; estado/violaciones del validador; cumplidas/total e IDs pendientes. Resultado parcial identificable y distinto de cumplimiento del desafío |
| Rutas | Vehículo, pasos ordenados/arcos, geometría y procedencia, entregas realizadas, batería llegada/salida kWh, recarga kWh y energía por tramo. Permitir visitas/repeticiones e inactividad |
| Evidencia | Por fase: objetivo/sentido, incumbente, cota, gap, terminación y segundos; alcance de certificado/red/perfil/H y supuestos. No juntar gaps de fases incompatibles |
| Métricas/tuning | KPIs del motor con unidades y definición; segundos de solver y total distintos; tuning aplicado/rechazado/fallback y advertencias. Desconocido como `null` con motivo, sin cero ficticio |

No hay ejemplo real para validar hoy esta propuesta. La UI puede diseñarse con un fixture claramente rotulado y valores desconocidos conservados; no anunciar integración comprobada. Conviene consumir kWh directamente y acordar explícitamente cualquier SOC porcentual (0–100 frente a 0–1). La conversión de unidades es admisible; otra estimación energética en frontend duplicaría el motor.

**Responsabilidades verificadas:** Daniel y Lucas conducen formulación/implementación del motor; Diego conduce experiencia, UI y presentación. Fuente CONTEXTO y skill `zmd-project-context`, 14-10.

**Reparto mínimo propuesto para cerrar la frontera:** Daniel confirma significado del modelo, reserva/cobertura, energía y alcance de certificados. Lucas aporta el archivo/base de conocimiento pendiente, comando o callable real, esquema/ejemplo de RunResult y errores efectivamente soportados. Diego decide composición y consume esos resultados. Un integrador acordado conserva el contrato compartido; no asignar definitivamente a una persona todos los módulos por interpretación de esta auditoría.

## Cierre y comprobaciones

Comprobado: archivos/historia/ramas/reflog, ausencia acotada de implementaciones y base_conocimiento, lectura de contexto/datos/plan/fuentes/diccionario, PDF completo con revisión visual, referencia pública LLM4MIP congelada. No ejecutadas pruebas de motor, AWS, mapas ni benchmarking porque no hay implementación correspondiente en este checkout.

Pendientes prioritarios: recuperar avance concreto de Lucas, sincronizar dirección nueva con contexto mantenido, resolver cobertura/reserva con Daniel/Lucas, acordar un ejemplo de intercambio real y terminar verificación de restauración de originales a cargo de root. No reabrir login, adquisición de datos ni definiciones de telemetría ya documentadas.
