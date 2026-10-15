"""Arena neutral de comparación de motores E-VRP y solvers.

No modifica el código de los motores comparados. Expone:
  - adaptadores (evrp in-process, ev_routing por subproceso en su entorno),
  - un validador neutral sobre el mismo grafo OSM,
  - una competencia de solvers sobre el MILP exportado a MPS,
  - un runner por línea de comandos: `python -m arena correr <escenario.json>`.
"""
__version__ = "0.1.0"
