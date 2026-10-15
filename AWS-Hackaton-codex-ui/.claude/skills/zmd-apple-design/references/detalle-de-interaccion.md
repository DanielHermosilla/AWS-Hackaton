# Detalle de interacción

Consultar al implementar o revisar movimiento, no para cada decisión visual. Ampliación motivada por el ensayo comparativo del 14-10-2026: cancelar una animación conservaba su posición, pero reiniciaba su opacidad. No se midió cuánto percibiría una persona ese salto.

## Continuidad y control

Antes de cancelar o redirigir, captura el estado **visible actual de todas las propiedades animadas**, no solo el destino lógico o la posición. Si animas transform y opacity, conserva ambas. Después cambia el destino; no vuelvas a los valores iniciales de una animación nueva. Un callback de la transición cancelada tampoco debe ocultar un panel que acaba de reabrirse.

Comprueba apertura → cierre antes de terminar y cambio rápido de destino, cuando el control permita esas acciones. Inspeccionar `cancel()` en el código no demuestra continuidad: comprueba valores intermedios o fotogramas. Separa continuidad numérica, observación visual y valoración humana del tacto.

El foco y la acción deben seguir siendo correctos al interrumpir o eliminar el movimiento. Prueba la alternativa reducida activada. El feedback estático de presión, selección y foco también comunica; el teclado conserva respuesta aunque no se use desplazamiento.

## Elegir la técnica

Una transición sencilla puede resolverse con CSS o Web Animations. Elige propiedades, curva y duración por su propósito y frecuencia. Un intervalo breve, como 100–200 ms, es un punto de partida para feedback pequeño, no una regla para todos los componentes.

Si un encargo requiere arrastre, conserva el punto donde se tomó el elemento, el seguimiento del puntero y su cancelación. Si además requiere inercia, consulta el original para entrega de velocidad y proyección del destino; reutiliza una implementación fiable existente antes de construir física propia. No añadir gestos, springs o dependencias por tener esta referencia.

Fuente: [Apple Design de Emil, versión consultada](https://github.com/emilkowalski/skills/blob/2d228630ba1446365f614a108cb8252f1feda202/skills/apple-design/SKILL.md), especialmente continuidad, velocidad y movimiento reducido. Se mantiene su licencia en la carpeta de la skill. Los valores y técnicas son recursos condicionados por el encargo, no un estilo obligatorio.
