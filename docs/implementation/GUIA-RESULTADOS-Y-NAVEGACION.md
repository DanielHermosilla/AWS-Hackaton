# Resultados y navegación · implementado

Al terminar aparecen los resultados. «Ver resultados» permite volver a sus datos
y límites sin repetir la corrida. El modo oscuro se mantiene entre páginas.
Las paradas y los estados usan nombres comprensibles; el ejemplo muestra su ruta
como aproximación. Inicio vuelve a permitir desplazarse por los indicadores.

**Para Daniel:** se conserva el identificador de ejecución por pestaña y se recupera
el resultado desde la API. La presentación humaniza etiquetas sin alterar IDs,
KPIs ni el JSON nativo. Tema en localStorage. La exportación usa la entrada vigente,
incluso después de fallar un cálculo. Los resultados temporales expiran al reiniciar.
