# Adaptación de LLM4MIP

Origen: [LLM4MIP](https://llm4mip.github.io/) y
[repositorio público](https://github.com/LLM4MIP/llm4mip.github.io).
Commit inspeccionado: `9335a69f446244f28d5b406eb66ddf13afa1d2e9`.
La licencia MIT y su aviso de copyright se conservan en
[licenses/LLM4MIP.txt](licenses/LLM4MIP.txt).

Material público revisado para el controlador:

| Archivo del upstream | Adaptación |
|---|---|
| `downloads/milp-structure-research-copt/references/output-templates.md` | Perfil compacto de estructura y registro reproducible de experimentos |
| `data/skill-study/packages/primal-current/SKILL.md` | Separar observación, hipótesis y acción; distinguir factibilidad de calidad del incumbente |
| `data/skill-study/packages/dual-current/SKILL.md` | Diagnóstico de cotas y separación entre evidencia y afirmaciones de certificación |

`llm/bedrock.py::SYSTEM_PROMPT` adapta esas ideas al contrato cerrado de
`SearchPolicy`. `dw_bridge.py` obtiene la estructura de nuestro Pyomo/GCG;
no incorpora COPT ni reproduce su script de perfilado.
`search_policy.py` registra decisiones y `benchmark.py` crea el manifiesto y
las corridas comparables. Es una adaptación de sus criterios de análisis y
experimentos; no una copia de su infraestructura.

El flujo vigente sin H adapta esos mismos criterios en
`route_policy.py::ROUTE_PROMPT` y `RoutePolicy`: una decisión previa compartida
por ambas fases, catálogo de búsqueda de SCIP, presets, arranques, pricing,
cortes de ternas/DFJ, lotes y branching. La reducción exacta
la verifica el código y el LLM no puede autorizarla por sí mismo. No se consulta
Bedrock desde el pricing. La traducción GCG descrita arriba es la referencia
posicional anterior; ya no es el motor del benchmark.
La ampliación conserva observación/hipótesis/acción, pero los constructores por
inserción y las optimizaciones de dominancia son código propio del proyecto.

Cambios respecto del material de referencia:

- Invocación exclusivamente mediante Amazon Bedrock Converse.
- Familia fija de problemas y formulación Pyomo conservada.
- Motor GCG/SCIP y acciones que sus APIs admiten: descomposición antes de
  resolver, selección de cortes nativos y control de pricing.
- Propuestas JSON con tipos y rangos, sin ejecutar código generado.
- Pricing exacto, validación de rutas y certificados fuera del control del LLM.
- Llamadas acotadas, errores visibles y comparación pareada de tres políticas.

No se reproducen: sus resultados publicados, búsqueda autónoma abierta,
infraestructura interna, generación libre de algoritmos/cortes, experimentos
COPT ni resultados de repositorios no públicos. La integración no acredita
mejoras de rendimiento sin medirlas con nuestro benchmark.

En la integración web de `codex/webapp`, la política es `standard` y no se hacen
llamadas a Bedrock. `benchmark.py` y el preprocesador `service_graph.py` no se
importaron. Las referencias anteriores a benchmarks y GCG describen el trabajo
upstream; su ejecución no forma parte de la verificación de esta entrega.
