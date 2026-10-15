# 05: Revisión crítica y resumen ejecutivo

> El agente revisor se canceló sin avance tras 1 h. Esta revisión la hizo el orquestador sobre 01–04, sin ejecutar código.

## Hallazgos y correcciones

| Severidad | Hallazgo | Corrección |
|---|---|---|
| Alta | 04 §A decía "capacidad útil `B` = `H` del compañero". **Es falso:** en `modelamiento.pdf`, `B` es la capacidad y `H` el máximo de movimientos por vehículo. | Corregido en 04. `H` solo afecta al modelo posicional (ver la interfaz más abajo). |
| Alta | El tope de regeneración por potencia (p95 ≈ 27 kW, doc 02) necesita **tiempo por arco**: E_regen_máx = P·t. Sin modelo de tiempo no se puede aplicar. | Orden de fases: primero tiempo por arco (F2), después regeneración acotada (F3). Mientras tanto, solo se puede usar el tope por batería llena (σ̂). |
| Alta | Un etiquetado multicriterio (ê, π̂, t̂, σ̂) en Python puro sobre ~10 mil nodos × 75 orígenes puede costar minutos: las variantes par a par ya eran 10–100 veces más lentas que scipy (doc `caminos.md`). | Limitar la frontera (top-k por par, ε-dominancia en ê y π̂), poda con A* y la cota T_max, y escribir el núcleo en numba o C, o quedarse con Dijkstra de scipy más la reparación de pares infactibles (k caminos alternativos). Medir antes de decidir. |
| Media | "Límite de X minutos por trayecto": si el trayecto es la ruta completa, es un **recurso del MILP** (tipo ventanas de tiempo). El preprocesamiento solo puede filtrar pares con t̂ > T_max. | Implementar las dos capas: el filtro de pares va en caminos; el límite por ruta va en el solver, que el compañero va a reemplazar. Hay que acordar su interfaz: t̂ por arco. |
| Media | El signo de la regeneración en eVED se separa bien (doc 02), pero el `Gradient` del CSV está casi siempre en 0 (solo el 12 % de las filas es distinto de 0). Por eso η_d y η_r calibrados con este CSV tienen **baja confianza**, y contradicen en parte la calibración NNLS previa (η_d ≈ 0,50 y η_r ≈ 0,94, en `elevacion_eved.md`). | Recalibrar con el desnivel tomado del DEM (USGS) sobre las trazas ajustadas a la red, no con `Gradient`. Reportar intervalos. |
| Media | `max(red, 0.0)` en `red.py:230` es un recorte silencioso (doc 03). | Usar `assert red >= -EPS`, o una advertencia con contador. Cambio de bajo costo. |
| Media | Citas de García Bustos: los DOI (10.1016/j.engappai.2024.109925 y 10.3390/batteries11120451) coinciden con la ficha de Google Scholar (EAAI 142:109925, 2025; Batteries 11(12):451, 2025). **No se accedió al texto completo**: no está verificado si usan VED/eVED ni cómo tratan la regeneración. | Citar como respaldo del enfoque (segmentación más el modelo híbrido físico + datos, y el margen desde el pronóstico de autonomía) y no atribuirles cifras. Si es posible, confirmar con el contacto del desafío, que es el mismo autor. |
| Baja | El ajuste a la calle usa un solo nodo extremo. En calles de un sentido puede forzar un rodeo (doc 03, no verificado). | Ajustar al punto proyectado con dos arcos de acceso (hacia u y hacia v) según el sentido. |
| Baja | Aristas paralelas: hoy se elige la de menor energía. Con tiempo, la de menor tiempo puede ser otra. | Al agregar tiempo, conservar ambas paralelas en la frontera. |

## Resumen ejecutivo del paquete 01–05

1. **Correcto hoy, con un riesgo:** Dijkstra con potencial es exacto en energía, incluso con bajadas (doc 03, verificado). El riesgo es tener **un solo camino por par**: si ese camino tiene un pico de consumo alto, el par se descarta aunque exista otro camino factible (contraejemplo en doc 03). En Ann Arbor no ocurrió con las configuraciones medidas, pero con pendiente real o rutas largas puede ocurrir.
2. **Energía negativa realista:** los datos muestran que se regenera ~25 % de la energía de tracción, sobre todo **frenando**, y con potencia acotada (p95 ≈ 27 kW; frenadas fuertes = freno de fricción). Modelo recomendado por arco: `e = c(v)·ℓ + κΔh⁺/η_d − min(κη_rΔh⁻, P_regen·t) + P_aux·t`, con la batería llena limitada por σ̂. Necesita tiempo por arco.
3. **Tiempo:** t_a = ℓ / v_ef(tipo de vía, `maxspeed`), calibrado con eVED (velocidad efectiva por límite). Habilita a la vez T_max por trayecto, el tope de regeneración y los consumos auxiliares.
4. **SoC válido en todo punto:** la condición correcta ya está en π̂ y λ̂. Para no perder pares factibles, se necesita una **frontera de Pareto por par** (ê, π̂, t̂, σ̂) mediante etiquetado con dominancia (RCSPP, Irnich & Desaulniers), o una versión barata: k caminos alternativos solo para los pares que hoy se descartan.
5. **Para ser defendible ante el jurado:**
   - reserva robusta (percentil 85–90 del consumo, regeneración en p25, factor de frío);
   - DEM real (USGS);
   - validación separando viajes;
   - validador con un modelo de energía distinto al del optimizador.

   Quedan como extensiones documentadas: carga no lineal, SoH, temperatura y giros.
6. **Interfaz de cálculo (requisitos, no implementación):**
   - **Entradas:** grafo dirigido con atributos por arco (ℓ, Δh, t o v, tipo de vía); nodos clave tipados (base, clientes, cargadores con conectores y potencia); flota y física (B, b̲, β, SoH, modelo de energía intercambiable); límites (T_max por trayecto o por ruta, H para el modelo posicional, k o ε de la frontera).
   - **Salidas:** para cada par, una lista de caminos Pareto con (ê, π̂, σ̂, λ̂, t̂), secuencia de arcos, geometría y procedencia.
   - **Garantía declarada:** un camino es SoC-factible si se sale con β ≥ b̲ + π̂, y cumple el tiempo si t̂ ≤ T_max.
   - **Compatibilidad:**
     - con el MILP actual, como arcos paralelos;
     - con el modelo del compañero, exponiendo los caminos como "tramos elementales" del grafo de nodos clave. Así H ≈ paradas + recargas + 1.
7. **Plan sugerido:**

   | Fase | Contenido | Esfuerzo |
   |---|---|---|
   | F0 | Blindaje: assert en vez de recorte silencioso; ajuste a la calle por sentido | 0,5 día |
   | F2 | Tiempo por arco y T_max | 1–2 días |
   | F1 | k caminos o frontera Pareto para pares infactibles | 2–4 días |
   | F3 | Energía con regeneración acotada y DEM | 2–4 días |
   | F4 | Validación independiente | 1–2 días |

   Se recomienda empezar por F0 y F2, que son las más baratas y habilitan el resto.
