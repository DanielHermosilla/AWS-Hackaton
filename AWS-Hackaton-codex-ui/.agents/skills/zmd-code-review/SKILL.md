---
name: zmd-code-review
description: "Revisa un cambio sustantivo de ZMD Mobility buscando fallos y complejidad innecesaria, o simplifica código cuando el encargo lo pide. Úsala sobre un diff o área concreta; no dispara una auditoría completa por cada edición."
---

# Revisión y simplicidad para ZMD Mobility

Usa los acuerdos vigentes de `docs/CONTEXTO.md` y el contrato afectado; no reformules el motor ni elijas stack durante una revisión.

Interpreta el encargo antes de actuar:

- **Revisar:** inspecciona y entrega hallazgos; no edites por haber encontrado algo.
- **Corregir o simplificar:** modifica el alcance autorizado y comprueba el comportamiento afectado. “Revisa y corrige” ya incluye ambos; no exige otra aprobación rutinaria. Si corriges lo revisado, declara esa intervención; tu comprobación no es una revisión independiente de tu propio arreglo.

Identifica la base del diff, cambios locales y archivos nuevos pertinentes. Lee su contexto y sigue los flujos afectados. Prioriza errores de comportamiento, unidades/IDs/estados, incompatibilidades, pérdida de datos y exposición de secretos. Evalúa permisos, concurrencia o rendimiento cuando esa superficie exista.

Para simplificar, busca duplicación o indirección que dificulten una tarea real: lógica del motor repetida en UI, helpers que ocultan algo sencillo, dependencias o generalizaciones sin consumidor actual. Conserva límites que sí separan responsabilidades. Menos líneas no bastan para justificar un cambio; tampoco impongas un máximo de líneas, inmutabilidad universal o patrones de arquitectura.

Antes de construir otra solución, revisa lo que ya usa el proyecto. Optimiza una lentitud medida; no añadas cachés, memoización ni servicios por anticipación.

Examina si las pruebas fallarían ante el defecto relevante. Distingue mocks de integración real y comprobaciones omitidas de aprobadas. Elige verificaciones proporcionales; una cuota de cobertura o un grep no certifican corrección o seguridad.

Cada hallazgo debe explicar **disparador → esperado/observado → impacto → archivo/evidencia → arreglo mínimo**. Cero hallazgos es válido. Separa preferencias opcionales de defectos. Tras corregir, revisa lo afectado; si dos rondas no resuelven una discrepancia, entrégala al responsable con evidencia y sin darla por aprobada.

Fuentes de contraste, 14-10-2026: [ECC code-reviewer](https://github.com/affaan-m/ECC/blob/b92f181b3b748d1abbc2afd94af6aa7d8c8fca29/agents/code-reviewer.md), [code-simplifier](https://github.com/affaan-m/ECC/blob/b92f181b3b748d1abbc2afd94af6aa7d8c8fca29/agents/code-simplifier.md) y [Google Engineering Practices](https://google.github.io/eng-practices/review/reviewer/standard.html). Adaptación propia, sin sus workflows obligatorios.
