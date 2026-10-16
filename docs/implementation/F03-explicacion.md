# F03 · leer e imprimir el plan

**Qué hace.** «Ver resumen» reúne entregas previstas, pendientes, batería,
recargas, energía, tiempos y límites. Puedes imprimirlo o guardarlo como PDF.

**Cómo se agregó.** Usa los mismos resultados que Inicio y Plan, ordenados por
vehículo. Identifica el cálculo y advierte si quedó desactualizado después de
editar. Las entregas previstas no se presentan como realizadas.

**Límite.** El resumen conserva datos desconocidos y estados incompletos; no
convierte una solución en óptima.

**Para Daniel — implementación.** Diálogo compartido desde `boot.js`, con estilos
de impresión. Consume el API sin recalcular KPIs y verifica vigencia al abrir e
imprimir. El detalle técnico completo permanece en la ejecución y su JSON.
