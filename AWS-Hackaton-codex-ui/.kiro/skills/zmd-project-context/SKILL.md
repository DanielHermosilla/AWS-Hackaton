---
name: zmd-project-context
description: "Recupera hechos, acuerdos y fuentes del proyecto de ZMD Mobility para CASE Electromovilidad eficiente, o prepara un encargo y su traspaso. Úsala al entrar al proyecto, resolver contexto o coordinar trabajo; no inicia desarrollo ni delegación por sí sola."
---

# Contexto ZMD Mobility

ZMD Mobility es nuestra consultora. CASE es la empresa de electromovilidad del desafío; no usar CASE como nombre de nuestra consultora. Nomenclatura confirmada por Diego el 14-10-2026.

Localiza `docs/CONTEXTO.md` en el repositorio de trabajo. En el workspace de investigación, `memoria-hackaton/RESUMEN.md` indica su ubicación. Lee el contexto una vez y recupera solo el tema necesario:

| Necesidad | Documento del repositorio |
|---|---|
| Reglas, entrega y enlaces oficiales | `docs/FUENTES.md` |
| Archivos, schema y límites de los datos | `docs/DATOS.md` |
| Términos y dónde preguntar | `docs/GLOSARIO.md` |
| Producto, diseño, integración y revisiones propuestas | `docs/PLAN.md` |
| Skills del proyecto y cuándo usar cada una | `docs/SKILLS.md` |
| Mapa operativo y alternativas de base técnica | `docs/MAPA-Y-BASE.md` |

Si falta un documento, declara la falta; no reconstruyas requisitos de memoria.

La fase vigente y las decisiones pertenecen a `CONTEXTO.md`, no a esta skill. Daniel y Lucas conducen formulación e implementación del motor; Diego conduce experiencia, interfaz y presentación. Respeta los acuerdos actuales antes de proponer tecnologías.

Distingue **verificado**, **propuesta**, **supuesto** y **pendiente**, con fuente/fecha para afirmaciones que cambian decisiones. Las propuestas históricas no son arquitectura aprobada. No deduzcas capacidad de batería, compatibilidad, disponibilidad, factibilidad ni ahorro sin evidencia. Ruta vial, asignación y validación energética son conceptos distintos.

Antes de preguntar por datos o reglas, consulta `DATOS.md`, el diccionario y las fuentes pertinentes de `FUENTES.md`; reutiliza el análisis comprobado y amplía solo lo que falte. Un campo ausente del CSV no prueba que falte en la documentación. Registra qué revisaste y pregunta únicamente lo no resuelto; no reabras aclaraciones del equipo ni conviertas decisiones internas en requisitos de la organización.

Aplica la capacidad que responda al encargo; no cargues todo el repertorio. Una tarea pequeña puede resolverse directamente. No elijas tecnologías ni reabras acuerdos para completar una plantilla.

Si el trabajo requiere y autoriza delegación, da a cada agente **objetivo, alcance, resultado esperado y comprobación**. Reparte tareas independientes; un integrador mantiene los archivos y contratos compartidos. El revisor busca defectos y evidencia, sin reescribir simultáneamente lo que revisa. No crear tableros, procesos permanentes ni nuevas skills por cada encargo.

Al cerrar un hito, registra solo decisión nueva, evidencia relevante y pendiente con responsable en el documento existente. Una revisión o un traspaso no necesita copiar la conversación.

Mantén los datos originales y derivados en `data/`, fuera de Git. No copies secretos ni cargues transcripciones o investigaciones completas por defecto. Al incorporar evidencia nueva, actualiza el contexto vigente y conserva la discrepancia relevante.
