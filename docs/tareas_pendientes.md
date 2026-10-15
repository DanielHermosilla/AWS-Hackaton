# Tareas pendientes

Estado al 15-10-2026. Las ramas `exp/*` ya están integradas en `main`.

## Oleada 2: lanzar con autorización

Máximo 4 agentes a la vez, cada uno en su propio worktree y rama `exp/<area>`. Se hacen en dos tandas.

**Tanda 1: IA generativa**

Implementar todas las ideas y medir cuánto aporta cada una.

| Rama | Idea | Medición |
|---|---|---|
| `exp/ia-asistente` | A. Asistente conversacional con uso de herramientas: el motor es la herramienta y opera "agrega / quita / qué pasa si" | Tasa de éxito de tareas, turnos, latencia, tokens |
| `exp/ia-ingesta` | B. Pedidos en texto, correo o imagen → nodos, con geocodificación (evaluar Amazon Location) | Precisión de la extracción, % de direcciones geocodificadas |
| `exp/ia-explicacion` | C. Explicación de rutas, cargas y riesgos de batería | Fidelidad frente al JSON (sin datos inventados), legibilidad |
| `exp/ia-contexto` | D. Contexto (clima, tráfico) → ajuste de parámetros dentro de la lista blanca | Error del consumo frente a eVED según temperatura |

**Tanda 2: ajuste del solver y elevación**

| Rama | Tarea | Medición |
|---|---|---|
| `exp/ia-tuning` | E. Ajuste del solver estilo LLM4MIP: perfil del modelo → parámetros de HiGHS validados | Tiempo y gap con el mismo presupuesto, comparados en la arena |
| `exp/elev-copernicus` | Copernicus DEM 30 m (AWS Open Data) | Error de energía frente a eVED, tiempo de preparación, dependencias |
| `exp/elev-usgs` | USGS 3DEP 10 m | Igual que la anterior |
| `exp/elev-eved` | Elevación de eVED proyectada sobre los nodos OSM | Igual que la anterior |

## Arena

- Repetir `ev_routing` con su `movement_limit` por defecto (30) y con valores mayores. La primera corrida usó H=10.
- Acordar con el autor de `ev_routing` los supuestos (en especial `max_snap_distance_m`; la arena usó 500 m) y recibir su JSON de escenario.
- Exportar su modelo Pyomo a MPS para la competencia de solvers.
- Habilitar CBC: `pulp` 4.0.1 no trae el ejecutable.
- Hacer más de 1 repetición por caso para medir la variabilidad.
- El validador neutral reutiliza primitivas de `evrp` (datos, red, energía). Para que sea independiente de verdad, reimplementar la simulación sin importar `evrp`.

## Motor

- Cachear el grafo cargado y vectorizar el ajuste a la calle. Hoy toma ~3 s y es el piso de tiempo.
- Desde 40 clientes: probar ALNS, romper simetría entre vehículos idénticos y llevar cortes de conectividad a la formulación compacta.
- Interfaz (Streamlit) sobre `evrp.resolver`.

## Otros

Ver `docs/evaluaciones_pendientes.md`: servicios AWS del evento, versiones de Python, Gurobi, robustez y regeneración.
