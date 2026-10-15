# Evaluaciones pendientes

Ideas que se postergaron hasta que el proyecto esté más avanzado. Cada una indica qué aportaría y cómo verificarla.

## Servicios AWS del evento (Workshop Studio, us-east-1)

La documentación del evento los menciona, pero **no se han verificado los permisos efectivos**. Antes de usar cualquiera, comprobarlo con el perfil `hackathon`.

| Servicio | Aporte posible | Verificación mínima |
|---|---|---|
| Bedrock Runtime (Converse) | Asesor, asistente, ingesta y explicación. **En uso.** | `converse` funciona con Claude Sonnet 4.6 (us. y global.) |
| Bedrock AgentCore / Agents | Asistente conversacional con herramientas gestionadas: el motor como herramienta | Crear un agente de prueba y llamar a una herramienta |
| Amazon Location Service | Geocodificar direcciones (ingesta B) y mapas base para la interfaz | `aws location search-place-index-for-text` |
| Lambda + API Gateway | Exponer el motor como API, en un contenedor por el peso de HiGHS y OSMnx | Desplegar `evrp solve` en una imagen de Lambda y medir el arranque en frío |
| S3 | Instancias, resultados, mapa vial y DEM | `aws s3 ls` y `put-object` en un bucket propio |
| DynamoDB | Historial de corridas y escenarios de la interfaz | Crear una tabla bajo demanda |
| Step Functions | Orquestar preparar → resolver → validar → explicar | Flujo de 3 pasos con Lambda |
| AWS Open Data (Copernicus DEM) | Elevación para el modelo de pendiente | Leer un tile COG de `s3://copernicus-dem-30m/` sin credenciales |

## Técnicas

- **Versiones de Python:** CPython 3.13 (JIT y variante free-threaded) o PyPy. Casi todo el tiempo lo consume HiGHS (C++), así que se esperan ganancias acotadas en el preprocesamiento. Probar en una rama por versión, con el mismo benchmark de la arena.
- **Gurobi:** queda fuera por ahora. La licencia de pip limita el tamaño del modelo; hace falta la licencia académica.
- **Robustez energética:** reserva robusta o restricciones probabilísticas frente a la incertidumbre del consumo (p25–p75 de eVED: 0,117–0,180 kWh/km).
- **Regeneración:** con pendiente hay energías negativas por arco. Hoy la contracción usa un solo camino por par. Evaluar caminos alternativos Pareto en energía y pico de consumo.
