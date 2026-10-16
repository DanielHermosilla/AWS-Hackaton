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
