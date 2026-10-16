# Features 2, 3 y 5 · entrega local

**16-10-2026.** Las tres funciones están implementadas, revisadas e integradas
en `codex/features-implementation`. Conservan el motor de Daniel y el diseño
vigente. La entrega es local, sin publicación ni despliegue.

Se mantiene el orden de la tabla original por impacto/factibilidad:

| Orden | Función | Estado y alcance | Explicación breve |
|---|---|---|---|
| **2** | Ficha de cargadores | **Implementada.** Todas las estaciones, metadatos y recargas por paso; datos desconocidos identificados. | [Qué hace y cómo se agregó](F02-explicacion.md) |
| **3** | Resumen e impresión | **Implementada.** Ejecución identificada, rutas, pendientes, comprobación y PDF; resultado anterior advertido. | [Qué hace y cómo se agregó](F03-explicacion.md) |
| **5** | Edición de ubicaciones | **Implementada para CSV y caso sintético.** Formulario/mapa, Confirmar/Cancelar y borrador conservado. JSON con red nativa protegido. Autocomplete externo: **analizado, pendiente de conectar**. | [Qué hace y cómo se agregó](F05-explicacion.md) |

Pruebas finales: **133 JavaScript**, **347 Python y 37 subpruebas**, más once
comprobaciones combinadas en navegador con cálculo real y exportación exacta.
Quedó omitida una prueba del ejecutable SCIP alternativo de Pyomo; PySCIPOpt,
usado por la aplicación, sí fue ejecutado. Revisión independiente sin hallazgos
pendientes. El PDF del caso operativo pequeño ocupa dos páginas A4; se verificó
en Chromium, sin impresión física ni certificación de cartografía externa.

Para probarlo, iniciar el servidor según [webapp/README.md](../../webapp/README.md).
En «Cargar y calcular», cargar un CSV o usar el caso sintético, editar ubicaciones,
confirmar los parámetros y calcular. Después abrir Cargadores o Ver resumen.

**Para Daniel.** F02 amplía la presentación de metadatos; F03 consume el mismo
resultado e incorpora impresión y control de vigencia; F05 modifica solo el
borrador y reutiliza `/prepare` y `/solve`. La siguiente dependencia real es
repreparar una red vial nativa al mover ubicaciones. El
[análisis de direcciones](F05-address-autocomplete.md) deja el plan de conexión
de Amazon Location sin asumir permisos ni cobertura.

[Contexto maestro](../ZMD-MASTER-CONTEXT.md) ·
[Ramas, commits, pruebas y decisiones](../ZMD-ORCHESTRATION.md)
