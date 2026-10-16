# Consumo por calle e históricos

Encargo del 16-10-2026. Base: `5773074`, integración local del motor terminado
de `main` y las mejoras del panel. Los históricos son una entrada adicional:
no son archivos de destinos ni sustituyen el modelo matemático.

## Flujo acordado

1. Adjuntar CSV/JSON histórico por una carga separada, limitada a 256 MiB.
   Conservarlo temporalmente en el servidor, con hash y un identificador opaco.
2. Reconocer eVED por sus columnas. Para otros formatos, Bedrock propone un
   mapeo de columnas, unidades y señales, mediante JSON validado y razonamiento
   alto compatible con el modelo configurado. No ejecuta código del archivo.
3. Integrar energía con intervalos reales, separando viajes y vehículos.
   Los huecos y las muestras no utilizables se cuentan y explican.
4. Estimar consumo por calle dirigida únicamente donde la trayectoria y su
   soporte sean suficientes. Informar cobertura y evaluación por viajes
   reservados. Conservar consumo supuesto donde falte evidencia.
5. Aplicar energía antes de preparar caminos y perfiles de batería. Cambiar el
   histórico invalida la preparación; la comprobación independiente sigue
   usando la red con esa misma energía.

Los datos observados, las estimaciones de consumo futuro y las propuestas de
supuestos se presentan separados. La IA puede interpretar estadísticas
verificables, pero no acredita capacidad útil, reserva, potencia de cargadores
ni tiempos de entrega que el archivo no mida. No se modifican esos parámetros
por una conjetura. La velocidad histórica describe el histórico; no es tráfico
en vivo. HVAC ya incluido en corriente y voltaje no se suma por segunda vez.

## Frontera de la aplicación

- `/history/upload`: bytes del archivo, `X-History-Filename`, mismo origen.
- `/history?profile_id=...`: resumen y disponibilidad del histórico temporal.
- `/history/analyze`: reintenta la interpretación con la conexión AWS vigente.
- `/history/remove`: retira el histórico temporal.
- `/prepare`: admite `energy_profile_id`; devuelve cobertura y procedencia
  en `preparation.energy_profile`. Una instancia JSON nativa ya contiene sus
  energías y no recibe una sustitución implícita.
- `/bedrock/session`: consultar o conectar con perfil local/cadena AWS o
  credenciales temporales. Una llamada Converse acotada comprueba el modelo.
- `/bedrock/disconnect`: invalida la sesión para futuras llamadas.

La conexión usa una sesión SDK en memoria compartida por interpretación de
históricos y política del solver. Las credenciales no van a archivos,
variables de entorno, contratos del problema, resultados, logs ni almacenamiento
del navegador. El historial adjunto no se envía íntegro a AWS: se envían
columnas, muestras limitadas y estadísticas identificadas como tales.

## Verificación prevista

Casos con energía distinta por calle; intervalos irregulares, regeneración,
GPS repetido y dirección contraria; falta de cobertura y datos ambiguos;
separación por viajes; invalidación de caché; fallos/JSON inválido de IA;
expiración y desconexión de credenciales; recorrido del panel y resultado
real con el eVED local. Las pruebas simuladas de AWS no prueban acceso real.

La revisión final registra pruebas ejecutadas, límites y reproducción.

## Evidencia integrada

Prueba con el original local `data/raw/eVED_EV.csv`, sin modificarlo:

| Comprobación | Resultado |
|---|---|
| Carga e integración | 476.308 filas, 504 viajes, 3 vehículos; 2,58 s de carga/análisis local. |
| Calibración espacial | 5.349 de 211.593 arcos elegibles; 173,73 km dirigidos. Cobertura: 2,53 % de arcos / 3,58 % de distancia de toda la red. |
| Evaluación temporal | 403 viajes de entrenamiento y 100 reservados; 97 con porciones cubiertas. MAE 0,136 kWh por porción cubierta de viaje, no error de una ruta completa. |
| Preparación completa | 141,46 s en esta máquina; 607 nodos y 6.345 conexiones tras preparar recursos. Cambiar capacidad/SoC reutiliza la calibración sobre la misma red. |
| Resolución | 20/20 entregas; 11,534 kWh del modelo; verificación independiente de calles, retorno y batería aprobada. 4,37 s de motor / 10,25 s de petición de resolución. |
| Navegador real | Recuperación del histórico, preparación, resolución y resultados en escritorio/móvil; cero errores de página. |
| AWS | Sesión, payload HIGH, evidencias, unidades, expiración y desconexión probados con dobles. No se ejecutó una llamada real con credenciales del usuario. |

La mayor parte de la red de la ciudad sigue usando respaldo manual: el
histórico no acredita consumo individual de todas sus calles. Los valores
energéticos de esta corrida no se comparan como una mejora contra el modelo
anterior, pues cambió el estimador. La recuperación estando detenido no se
aprende como regeneración vial. Las calles mixtas conservan descarga y
recuperación separadas con el orden supuesto visible.

La revisión independiente encontró y corrigió: recarga estacionaria atribuida
a calle; histórico anterior recuperado al navegar; unidades de potencia con
prefijos confundidos; código Match Type incompatible entre contratos; mezcla
EV/HEV aceptada desde una muestra parcial. Hay regresiones para cada caso.
La suite final completa pasó **874 pruebas Python**, con 10 omisiones por
componentes opcionales, y **155 pruebas JavaScript**. Los dos recorridos
de históricos y la regresión del panel pasaron; además se recorrió la
instancia histórica real desde el navegador. La revisión independiente cerró
sin hallazgos pendientes dentro de este alcance.

Evidencia local ignorada: `.local/historical-energy-2026-10-16/`, incluyendo
`real-history-report.json`, `real-history-result.json`,
`real-browser-report.json` y capturas. Reproducción: iniciar la web según su
README con la red GraphML, cargar la instancia de ubicaciones, adjuntar el
eVED EV en «Consumo con históricos» y calcular. Usar política estándar permite
reproducir la física sin acceso a AWS.

Guías breves:
[Consumo por calle](GUIA-CONSUMO-HISTORICO.md) ·
[Interpretación y conexión AWS](GUIA-HISTORICOS-BEDROCK.md).
