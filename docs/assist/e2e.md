# Prueba end-to-end: `assist` con el solver real

> Instruido por **Ateuluz** — verificación de integración.

Esta prueba confirma que `ev_routing.assist` se integra con el solver real
(no con dobles): carga una instancia, resuelve con `pipeline.run_instance`,
explica el resultado (eje C) y aplica/revierte un cambio de configuración
(eje A) sobre el campo real `vehicle_count`.

## Entorno

```bash
uv venv .venv --python 3.12
uv pip install -e .           # stack completo del solver (pyscipopt, pydantic, ...)
# opcional para el chat real: uv pip install -e .[assist]
```

## Instancia de prueba

`examples/toy_recharge.json`: 2 entregas que exigen recargar en el cargador `F`,
flota `vehicle_count = 2`, conector `J1772`. Es sintética (no datos reales).

## Pasos verificados

1. **Carga**: `inputs.load_instance` → `parameters.vehicle_count == 2`.
2. **Resolver (solver real)**: `Sesion.resolver()` → `pipeline.run_instance`
   devuelve estado `optimal`.
3. **Explicación (C)**: `explicar(resultado, cliente=None)` produce, desde los
   hechos del solver, texto confiable (sin Bedrock usa plantilla determinista).
4. **Configuración (A, sin red)**: `aplicar("vehiculos", 1)` valida contra la
   lista blanca y escribe el campo real `vehicle_count`; `reiniciar()` restaura
   la flota inicial (2).

## Resultado observado (referencia)

```
flota inicial (vehicle_count): 2
estado solve: optimal
entregados: ['A', 'B'] | sin_atender: []
fuente explicacion: plantilla | confiable: True
TEXTO:
  Estado de la solucion: optima (lexicografica).
  Se atendieron 2 entregas; no quedaron entregas pendientes.
  Vehiculo vehicle_1: 2 entregas. Recarga en: F.
  Vehiculo vehicle_2: 0 entregas. Sin recargas.
override aplicado: vehiculos -> 1 (destino vehicle_count)
flota efectiva tras override: 1
flota tras reiniciar: 2
E2E_OK
```

La explicación coincide con la procedencia de la instancia (un vehículo cierra
el ciclo recargando en `F`, el otro puede quedarse en base).

## Tests sin red (complementarios)

```bash
uv pip install pytest
python -m pytest tests/test_assist.py -q      # 9 passed
```
Cubren lista blanca (flota máx 10, rechazo de claves/valores inválidos),
extracción de hechos, verificador anti-alucinación y explicación por plantilla.

## Cómo convertir esto en test permanente (recomendado)

Añadir un test marcado `@pytest.mark.solver` que replique los pasos 1–4 con
`toy_recharge.json`, separado de los tests sin red, para que CI lo ejecute solo
donde haya solver instalado. Ver `docs/assist/integracion.md` §4.4.
