# Tareas pendientes

Estado al 15-10-2026. Las ramas `exp/*` ya están integradas en `main`.

## Oleada 2: COMPLETADA (15-10-2026), integrada en `main`

Informes en `docs/experimentos/`: `ia_asistente`, `ia_ingesta`, `ia_explicacion` (C+D), `ia_tuning`, `elevacion_eved`, `elevacion_usgs`, `elevacion_copernicus` y `arena_scip`.

| Ítem | Resultado | Pendiente |
|---|---|---|
| A. Asistente | Streaming y uso de herramientas; Sonnet 4.6 resolvió 8/8 del set focalizado; primer texto en ≤ 1 s | Exponerlo por SSE (FastAPI/Lambda) |
| B. Ingesta | F1 = 1,0 en texto; 0,94 en imagen | Geocodificación real (Nominatim o Amazon Location; hoy no existe ningún índice de lugares) |
| C. Explicación | 100 % de fidelidad, verificada | — |
| D. Contexto | MAE −27,6 % solo con la fórmula de temperatura; el LLM no mejora la precisión, solo la usabilidad | — |
| E. Ajuste del solver | **Sin mejora** frente a la configuración base, con el mismo presupuesto | Reevaluar solo con ≥ 80 clientes |
| Elevación | +8,8 % de energía (USGS, eVED) y +12 % (Copernicus); no cambia el orden de las rutas; USGS frente a eVED: error medio absoluto 0,7 m | Elegir la fuente por defecto: USGS (cobertura del 100 %, sin dependencias) |
| Arena con SCIP | `ev_routing` con su propio flujo (SCIP) y H ∈ {30, 60, 100}: 0 entregas con 1–5 clientes (sin solución factible dentro del tiempo); `evrp`: 100 % con gap 0 | Acordar los supuestos con el autor |

Se excedió el tope de tokens en la ingesta: ~178 mil frente a los 150 mil asignados.

## Oleada 1 (referencia)

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

## Oleada 3: experimento controlado de la poda top-k (k-vecinos)

Se corre después de las oleadas de IA y de elevación, en paralelo por su cuenta. Queda configurable y **apagado por defecto** hasta tener evidencia. Hoy `escala.k_vecinos: auto` activa k = 10 sobre 25 clientes, y ese umbral no tiene respaldo en datos. Puede correr en otra máquina.

- **Pregunta:** ¿la poda empeora la energía frente a no podar (k = 0) con el mismo presupuesto total? ¿Desde cuántos clientes conviene?
- **Subconjunto que da indicios fuertes** (en vez del factorial completo de 5×5×5×2×3 = 750 corridas):
  - k ∈ {0, 10} como contraste principal, más k = 5 y k = 15 solo en 40 clientes.
  - Clientes: {30, 40, 60, 100}; 3 semillas; 2 vehículos; 2 repeticiones.
  - Total: ~64 corridas de ≤ 55 s, unos 60 min en serie o ~15 min con 4 procesos.
- **Medida directa del daño, que no depende del tiempo:** en instancias de 20 a 30 clientes con óptimo demostrado (k = 0, gap 0), contar cuántos arcos de la solución óptima tienen un rango de vecino mayor que k.
- **Referencia de calidad:** la mejor solución conocida con k = 0 y 600 s en el subconjunto de 40 y 60 clientes.
- **Análisis:** diferencia pareada por instancia y semilla (k = 10 contra k = 0), con promedio, intervalo de confianza y conteo de victorias y derrotas.
- **Cómputo:** cada corrida usa 1 núcleo (`solver.hilos: 1`) para poder paralelizar con procesos independientes, `uv run python -m experimentos.topk --worker i/N`. Necesita unos 2 GB de RAM por proceso (estimado; medirlo en la primera corrida). Se puede mover a otra máquina clonando `evrp-lab` y ejecutando `uv sync`. Los resultados se guardan en JSONL y se agregan al final.
- **Decisión:** si k = 10 no gana de forma consistente, `k_vecinos` vuelve a 0 por defecto.

## Separación preparar/resolver: HECHA (15-10-2026, commit 3e1614d)

- Comandos: `evrp preparar` (etapa 1: red → instancia preparada), `evrp resolver` (etapa 2: solver sobre la instancia preparada) y `evrp solve` (las dos etapas). Las firmas en Python están en el README.
- Resultados medidos: preparar ~5 s, archivo de 0,31 MB (0,88 MB con geometría); resolver ~1,3–2,3 s frente a ~7 s del flujo completo; rutas idénticas.
- **Pendiente:**
  - Probar en la arena el modelo del PDF de `ev_routing` sobre la instancia preparada: los 81 nodos clave como grafo y cada par `tramos["i|j"]` como tramo elemental. Ver si con H ≈ 30 resuelve la instancia completa.
  - Hace falta un adaptador en `arena/` que transforme la instancia preparada a su `ProblemInstance`, sin modificar su código.
  - Acordar con su autor si ese uso es aceptable según su `AGENTS.md`, que pide justificar que la agregación preserva las opciones de recorrido. Cuando todos los arcos tienen energía no negativa, la preservación está argumentada.

## Arena

- El ejecutable de SCIP 9.2.4 quedó instalado en `externos/scip-9.2.4/bin` (fuera de git, solo para el proyecto). Pyomo lo detecta (`SolverFactory('scip')` → 9.2.4) si se agrega esa carpeta al PATH del subproceso. Hay que repetir `ev_routing` con **su** flujo de solver (SCIP) y con H = 30 o mayor, en vez de `appsi_highs` con H = 10.
- Pulp se quitó del grupo `arena`. CBC se registra como no disponible.
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
