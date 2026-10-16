# Benchmark del 16 de octubre de 2026

[Resumen](../../benchmark-results-2026-10-16.md) ·
[PDF](benchmark-hackathon-2026-10-16.pdf) ·
[Tablas completas](resultados-presentacion.md) ·
[Método](../../overnight-benchmark-method.md)

Este directorio publica los resultados medidos durante la campaña, incluidos
los resultados desfavorables y los fallos. No son mediciones nuevas del código
integrado en `main`. Cada fase conserva la versión, semillas y presupuesto
utilizados; no se mezclan fases para atribuir una aceleración.

| Cohorte | Clientes | Vehículos | Presupuesto por corrida | Corridas |
| --- | --- | --- | --- | --- |
| Oficiales | 20 | 2 | 30 s | 18 |
| Piloto A | 40, 80, 120, 200 | 2 | 15 s | 48 |
| Piloto B | 40, 80, 120, 200 | 2 | 15 s | 56 |
| Piloto C | 40, 80, 120, 200 | 2 | 10 s | 64 |
| Comparación B | 40, 80, 120, 200 | 2 | 60 s | 120 |
| Comparación C | 40, 80, 120, 200 | 2 | 45 s | 80 |
| Flota | 200 | 2, 4, 8 | 30 s | 18 |
| Callbacks D | 80, 200 | 2 | 30 s | 32 |

Son **436 corridas**, incluidos cuatro fallos del piloto A. No son 436
instancias independientes. Los tiempos de preparación y validación se
registran aparte del presupuesto del solver.

## Archivos publicados

- `official-kpis.csv` y `official-runs.csv`: resumen de las dos entradas oficiales
  y las 18 corridas individuales.
- `pilots/`: las 168 corridas de desarrollo, con los fallos conservados.
- `phase-b/` y `phase-c/`: resultados individuales, comparaciones pareadas,
  factores de impacto y agregados del aporte del LLM.
- `callbacks-kpis.csv`, `callbacks-pairs.csv` y
  `callback-notification-delays.csv`: estudio de versiones y aviso al LLM.
- `fleet-kpis.csv`, `fleet-pairs.csv` y `scalability.csv`: escala de demanda y flota.
- `llm-decisions.csv`: decisiones reales, cambios aplicados, tiempos y tokens.
- `selected-llm-transcript/`: respuestas y decisiones de tres ejemplos
  seleccionados después de observar los resultados; no constituyen un promedio.
- `figures/`: gráficos PNG y SVG listos para usar.
- `provenance/`: commits, manifiestos, planes, políticas elegidas y procedencia
  de esta exportación.
- `SHA256.json`: hashes de los archivos publicados, salvo el propio manifiesto.

Los CSV y JSON copiados conservan sus mediciones. Solo se reemplazaron los
prefijos absolutos del checkout original por rutas relativas al repositorio.
Los campos `result_path` y `source_path` apuntan a originales locales dentro de
`artifacts/`; esos archivos no se incluyen aquí. Las redes completas, datos
originales, snapshots nativos y logs masivos permanecen fuera de Git.
`provenance/export.json` conserva los hashes originales y los de las copias.

## Leer los resultados

La comparación C muestra ventaja frente a una política fija, pero no una
ventaja media frente a reglas locales fuertes. La demo D de 200 clientes
ahorró 11,04 % frente a la fija; las reglas igualaron su energía y el gap final
fue 41,32 %. El objetivo de gap de 0,5 % no se alcanzó en esa demo.

Comparar energía exige atender exactamente los mismos clientes. Los costes
desconocidos permanecen ND. CO₂ y USD son aproximaciones operacionales para
Michigan con supuestos declarados, no mediciones de campo ni análisis de ciclo
de vida. `evaluation_access250` contiene un acceso supuesto de 192,9 m para
V16, sin verificación en terreno.

## Repetir la comparación C

Desde la raíz del repositorio:

```bash
bash scripts/reproduce_benchmark_20261016.sh plan
bash scripts/reproduce_benchmark_20261016.sh run
```

El script extrae el código del commit `a04a884` en un directorio temporal, sin
cambiar de rama ni tocar el checkout. Conserva el protocolo de C: 64 corridas
de piloto y 80 comparaciones, hasta 64 llamadas AWS. Usa `caffeinate` en macOS.
Requiere el historial Git que contiene ese commit, `uv` y credenciales Bedrock
para `run`; `plan` no consulta AWS.

Las opciones finales permiten cambiar `--output-dir`, `--aws-profile`,
`--aws-region`, el modelo o los presupuestos. Esos cambios constituyen otro
experimento y quedan en su manifiesto. El perfil predeterminado es `hackathon`,
la región `us-east-1`, y se respetan las variables de entorno documentadas.
Las respuestas futuras del LLM y los tiempos pueden variar.

Los resultados nuevos se guardan en `artifacts/repeat-benchmark-20261016-c`.
Para reanudar, usar `run --resume`; para recalcular sus tablas sin AWS, usar
`report`. No se sobrescriben los resultados publicados en este directorio.

Para ensayar el **motor actual de `main`**, usar el runner general:

```bash
bash scripts/benchmark_presentation.sh plan
bash scripts/benchmark_presentation.sh run \
  --customers 40 80 120 200 --families dispatch crossed \
  --test-seeds 2001 2002 --time-limit-seconds 300 \
  --adaptive-start fixed --ablation --tee \
  --output-dir artifacts/benchmark-main-300s
```

El comando de 300 segundos es una configuración para una campaña nueva;
**no se ejecutó como parte de los resultados aquí publicados**.
