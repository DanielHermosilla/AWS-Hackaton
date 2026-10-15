"""Adaptador del motor ev_routing (subproceso en SU entorno).

Invoca `uv run --project <ruta> --with highspy==1.11.0 python <runner>` con los mismos
supuestos fisicos. El runner (ev_routing_runner.py) importa la API publica del companero
y escribe un JSON con rutas en nodos clave y tramos por paso. Si el modelo no puede
resolver por H o por tiempo, se registra como resultado (no como error de la arena).
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from arena.supuestos import SupuestosComunes

PROYECTO_EXTERNO = Path(os.environ.get("EVRP_ARENA_PROYECTO_EXTERNO")
                        or Path(__file__).resolve().parents[2] / "externos" / "AWS-Hackaton")
RUNNER = Path(__file__).parent / "ev_routing_runner.py"
HIGHSPY = "highspy==1.11.0"


def resolver(csv_nodos: str, sup: SupuestosComunes, vehiculos: int, presupuesto_s: float,
             hilos: int, opciones: dict | None = None,
             osm_cache: str = "results/arena/.cache/osm",
             proyecto_externo: Path | None = None) -> dict:
    opciones = opciones or {}
    proyecto = Path(proyecto_externo or PROYECTO_EXTERNO)
    from arena.instancias import grafo_osm_descomprimido
    graphml = str(grafo_osm_descomprimido())

    out = Path(osm_cache).parent / "ev_routing" / (Path(csv_nodos).stem + ".json")
    out.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "uv", "run", "--project", str(proyecto), "--with", HIGHSPY,
        "python", str(RUNNER),
        "--csv", str(Path(csv_nodos).resolve()),
        "--graphml", str(Path(graphml).resolve()),
        "--out", str(out.resolve()),
        "--bateria-kwh", repr(sup.bateria_kwh),
        "--reserva-kwh", repr(sup.reserva_kwh),
        "--soc-inicial", repr(sup.soc_inicial),
        "--consumo-kwh-km", repr(sup.consumo_kwh_km),
        "--conectores", ",".join(sup.conectores),
        "--vehiculos", str(int(vehiculos)),
        "--movement-limit", str(int(opciones.get("movement_limit", 30))),
        "--presupuesto-s", repr(float(presupuesto_s)),
        "--hilos", str(int(hilos)),
        "--max-snap-m", repr(float(opciones.get("max_snap_distance_m", 100.0))),
        "--solver-pyomo", str(opciones.get("solver_pyomo", "appsi_highs")),
    ]
    # Margen generoso sobre el presupuesto (construccion del modelo + arranque solver).
    timeout = float(presupuesto_s) * 2 + 180
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(cmd, cwd=str(Path.cwd()), capture_output=True, text=True,
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"motor": "ev_routing", "estado": "timeout_arena",
                "tiempo_s": round(time.perf_counter() - t0, 3),
                "movement_limit": int(opciones.get("movement_limit", 30))}
    t_total = round(time.perf_counter() - t0, 3)

    if out.exists():
        datos = json.loads(out.read_text(encoding="utf-8"))
    else:
        return {"motor": "ev_routing", "estado": "error",
                "error": (proc.stderr or proc.stdout or "sin salida")[:800],
                "tiempo_s": t_total, "returncode": proc.returncode}

    estado = datos.get("estado", "error")
    resultado = {
        "motor": "ev_routing",
        "estado": estado,
        "rutas": datos.get("rutas", {}),
        "tramos_por_paso": datos.get("tramos_por_paso", {}),
        "tipo_rutas": datos.get("tipo_rutas", "calle"),
        "energia_kwh": datos.get("energia_neta_motor_kwh"),
        "entregas": datos.get("entregas"),
        "tiempo_s": t_total,
        "tiempo_solver_s": datos.get("tiempo_solver_s"),
        "gap": datos.get("gap"),
        "movement_limit": datos.get("movement_limit"),
        "detalles": {"solver": datos.get("solver"), "fases": datos.get("fases"),
                     "nodos_red": datos.get("nodos_red"), "arcos_red": datos.get("arcos_red"),
                     "error": datos.get("error"), "detalle": datos.get("detalle")},
    }
    return resultado
