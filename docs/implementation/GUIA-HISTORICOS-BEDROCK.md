# Interpretación de históricos con AWS

**Para qué sirve.** Bedrock ayuda a identificar las columnas, unidades y datos
útiles de un archivo distinto de eVED. También puede explicar las observaciones
de un eVED. Se pide razonamiento **alto** a un modelo compatible.

**Cómo se usa.** «Conectar con AWS» abre una ventana para usar el perfil del
servidor o credenciales temporales: access key, secret key y session token.
También permite indicar región y modelo. Después puedes ampliar el análisis
del histórico. La conexión comprueba acceso al modelo, dura como máximo una
hora y se puede desconectar. Las credenciales quedan solo en memoria.

**Qué puede extraer.** Señales de consumo, velocidades, temperaturas y otros
datos realmente presentes. Una sugerencia de IA no se convierte automáticamente
en una regla del vehículo. Si faltan unidades o evidencia, se informa; si no
puede interpretar el archivo, puedes continuar con el consumo supuesto.

**Para Daniel.** El panel manda credenciales a un endpoint local dedicado.
Una sesión Boto3 efímera alimenta tanto la interpretación como el proveedor
de políticas del solver. La IA recibe un perfil acotado del archivo y devuelve
JSON: mapeos, observaciones y propuestas con evidencia. Python verifica unidades,
signos y referencias y calcula la energía; no ejecuta código generado.
Las pruebas automatizadas de AWS usan dobles. La conexión real requiere
credenciales vigentes con acceso al modelo elegido.
