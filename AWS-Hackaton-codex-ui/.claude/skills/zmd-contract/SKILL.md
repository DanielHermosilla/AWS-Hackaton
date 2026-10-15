---
name: zmd-contract
description: "Define o revisa el intercambio de datos entre el motor y la interfaz ZMD Mobility: entradas, resultados, unidades, estados y errores. Úsala cuando esa frontera cambie o las partes deban integrarse; no escoge solver ni arquitectura."
---

# Contrato UI–motor de ZMD Mobility

Consulta `docs/CONTEXTO.md` si no conoces la fase y los acuerdos vigentes. En el workspace de investigación, `memoria-hackaton/RESUMEN.md` indica el repositorio. Trabaja con la frontera existente y lo que Daniel/Lucas hayan confirmado.

Empieza por la tarea que la interfaz necesita resolver y un ejemplo real de entrada/salida, si existe. Aclara con sus responsables lo que cambie el significado:

- Identificadores, campos requeridos, opcionales y diferencia entre ausente, vacío y cero.
- Unidades, escala del SOC y precisión de presentación. Una conversión de unidades no es una nueva estimación energética.
- Escenario y ejecución a los que pertenece el resultado; cómo reconocer una respuesta antigua.
- Estados y errores realmente soportados. Un tiempo agotado o una búsqueda sin resultado no demuestran inviabilidad.
- Datos medidos, calculados, supuestos o simulados, con su procedencia.

Mantén una única definición comprobable, reutilizando tipos, esquema o formato existente. Un archivo o tipo compartido puede bastar; incorpora generadores o una API solo si resuelven una necesidad actual. La interfaz presenta el resultado del motor sin inventar una segunda matemática.

En planificación, basta proponer la frontera y señalar preguntas abiertas. Un ejemplo sintético rotulado permite avanzar diseño sin fingir integración. No rellenes parámetros energéticos desconocidos para cerrar el documento.

Cuando haya implementación, contrasta tanto la salida real del proveedor como el consumo de la interfaz con el mismo acuerdo. Cubre un caso normal y las alternativas relevantes al cambio: ausencia, error, parcial o rechazo. La validez de un esquema no prueba la factibilidad de una ruta.

Entrega el acuerdo o cambio concreto, un ejemplo y lo comprobado o pendiente. No crees otro documento si el repositorio ya tiene una fuente adecuada.

Origen: adaptación de [ECC contract-first](https://github.com/affaan-m/ECC/blob/b92f181b3b748d1abbc2afd94af6aa7d8c8fca29/skills/contract-first/SKILL.md) y `test-collaboration`, contrastada el 14-10-2026. Referencias para consulta puntual, no carga automática.
