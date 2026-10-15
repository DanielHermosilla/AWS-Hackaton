# Instrucciones para un agente: experimento controlado de poda top-k (k-vecinos)

## Contexto

- Repo: `C:\Users\lucas\evrp-lab` (GitHub privado `Ateuluz/evrp-lab`). Paquete `evrp` en `src/evrp`, Python 3.12, `uv`.
- El motor contrae la red OSM a caminos de mínima energía entre nodos clave y resuelve un MILP con HiGHS. El objetivo es lexicográfico: primero maximizar entregas, después minimizar energía.
- La poda **k-vecinos** (`escala.k_vecinos`, en `src/evrp/instancia.py::_podar_k_vecinos`) conserva para cada cliente solo sus k arcos cliente→cliente de menor energía. Los arcos hacia la base, los cargadores y el fin no se tocan. Es **heurística**: puede eliminar arcos de la ruta óptima.
- Hoy el valor por defecto es `k_vecinos: "auto"`: k = 0 (exacto) hasta `umbral_exacto` = 25 clientes y k = `k_auto` = 10 por encima. **Ese umbral no tiene respaldo en datos.**
- Evidencia previa en `docs/experimentos/escala.md`. No sirve para decidir: cambió poda y presupuesto a la vez, usó una sola semilla y no tuvo repeticiones.

**Pregunta:** con el mismo presupuesto total, ¿k = 10 (u otro k) empeora la energía frente a k = 0? ¿Desde cuántos clientes conviene podar?

## Reglas de operación (obligatorias)

1. **Rama y worktree propios:** `git worktree add -b exp/topk C:\Users\lucas\evrp-lab-wt\topk main`. Copia `data/*.csv` desde el repo principal. Ejecuta `uv sync --extra ia --all-groups` en el worktree.
2. **Archivos permitidos:** `experimentos/topk/**`, `tests/test_topk.py` y `docs/experimentos/topk.md`. **No edites `src/evrp/**`.** Configura todo con `evrp.resolver(csv, config_dict, perfiles)` y las claves `escala.*` y `solver.*`. Si necesitas cambiar el motor, descríbelo como "cambio solicitado".
3. **Límite de CPU:**
   - Como máximo **2 procesos trabajadores en paralelo**, cada uno con `solver.hilos: 1`.
   - Prioridad baja. En Windows: `Start-Process -Priority BelowNormal`, o `psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)` si `psutil` está disponible vía `uv run --with psutil==6.1.1`.
   - La máquina tiene 8 CPUs lógicas: 2 procesos usan ~25 %.
   - Pide el número de procesos por argumento (`--workers`, por defecto 2) para poder subirlo o bajarlo, o correrlo en otra máquina.
4. **Carga estable durante la medición:** los resultados con límite de tiempo dependen de la CPU disponible. No corras otras tareas pesadas a la vez. Registra en cada corrida el número de procesos y el `os.getloadavg()` aproximado (en Windows, el % de CPU si hay `psutil`).
5. **Reanudable:** guarda cada corrida en `experimentos/topk/resultados.jsonl` como una línea JSON con clave única (instancia, semilla, k, vehículos, repetición) y salta las ya hechas. Esto permite cortar el experimento y continuarlo.
6. **Sin Bedrock ni red:** usa el mapa OSM empaquetado (`red.osm_permitir_descarga: false`). No consume tokens.
7. **Commits pequeños en tu rama, sin push.** Mide todo con comandos reales. Español.

## Diseño (subconjunto para obtener indicios fuertes)

**Instancias:** `evrp.sintetico.generar(n, semilla, "data/competition_routing_nodes.csv")`, con los cargadores reales y semillas 1, 2 y 3. Además, la instancia `competition` (20 clientes).

**Perfil y presupuesto:** perfil `ev_routing`; `solver.presupuesto_total_s: 55`; `solver.tiempo_limite_s: 55`; `solver.hilos: 1`; 2 vehículos (más 3 vehículos en el bloque B).

| Bloque | Qué mide | Diseño | Corridas | Tiempo de CPU aprox. |
|---|---|---|---|---|
| A. Contraste principal | ¿k = 10 empeora frente a k = 0? | k ∈ {0, 10} × clientes {30, 40, 60, 100} × 3 semillas × 2 repeticiones | 48 | 48 × ~60 s ≈ 48 min |
| B. Sensibilidad de k | ¿Hay un k mejor? | k ∈ {5, 15} × 40 clientes × 3 semillas × 2 repeticiones (+3 vehículos con k ∈ {0, 10}, 40 clientes, 3 semillas, 1 repetición) | 12 + 6 | ~18 min |
| C. Referencia de calidad | Mejor solución conocida | k = 0, 600 s, 1 hilo, para 40 y 60 clientes × 3 semillas | 6 | 60 min |
| D. Daño directo (no depende del tiempo) | ¿El óptimo usa arcos que la poda elimina? | Instancias de 20, 25 y 30 clientes × 3 semillas con k = 0 hasta gap 0 (límite de 600 s). Para cada arco cliente→cliente de la ruta óptima, calcula su rango de vecino (posición por energía entre los arcos que salen de ese cliente) | 9 | ~10–30 min |

**Total estimado:** ~2,5–3 h de CPU. Con 2 procesos son **~1,5 h de reloj**; con 1 proceso, ~3 h. Si algo hace pensar que se tardará más de 6 h, reduce primero el bloque C a 1 semilla.

**Memoria:** mide el pico en la primera corrida. La estimación es menos de 1,5 GB por proceso (grafo de ~10 mil nodos más el modelo).

**Ahorro opcional:** la preparación de la red, de 3 a 5 s por corrida, es idéntica para todos los k de una misma instancia y semilla. Si encuentras una forma de reutilizarla sin editar `src/evrp`, documéntala. Si no, acéptala: es igual para todos los tratamientos.

## Métricas por corrida

- Identificación: instancia, semilla, n_clientes, vehículos, k, repetición.
- Calidad: entregas, `energia_total_kwh`, factible (validador), estado de la fase 2, gap, cota.
- Tamaño del modelo: columnas y filas.
- Tiempos: red, heurística, MILP y total.
- Entorno: número de procesos y carga.
- Bloque D: rangos de vecino de los arcos óptimos y el máximo rango por instancia.

## Análisis (en `docs/experimentos/topk.md`)

1. **Bloque A:**
   - Diferencia pareada Δ = E(k = 10) − E(k = 0) por instancia y semilla, promediando repeticiones.
   - Media, intervalo de confianza del 95 % (bootstrap con 10.000 remuestreos) y conteo de victorias, empates y derrotas por tamaño.
   - Wilcoxon pareado si hay `scipy` (grupo `bench`).
2. **Pérdida frente a la referencia** (bloque C): (E − E_ref) / E_ref para k = 0 y k = 10.
3. **Bloque D:** distribución del rango máximo de vecino en las rutas óptimas. Si el máximo es ≤ 10 en todas, la poda con k = 10 no habría eliminado ningún arco óptimo en esos tamaños.
4. **Variabilidad:** diferencia entre las 2 repeticiones de una misma configuración, que es el ruido del MILP con límite de tiempo. Compárala con Δ.
5. **Recomendación respaldada en datos:** valor por defecto de `k_vecinos`, `umbral_exacto` y `k_auto`, o volver a k = 0 por defecto si k = 10 no gana de forma consistente. Indica cuántas corridas respaldan la conclusión y qué incertidumbre queda.
6. **Limitaciones:** una máquina, un mapa (Ann Arbor), clientes sintéticos y cargadores reales.

## Entregables

- `experimentos/topk/correr.py` (CLI: `--bloques A,B,C,D --workers 2 --reanudar`).
- `experimentos/topk/analizar.py`.
- `resultados.jsonl` y `tablas.md`.
- `tests/test_topk.py`: pruebas rápidas del análisis y la reanudación con datos falsos.
- `docs/experimentos/topk.md`: el informe. Devuélvelo también como respuesta.
