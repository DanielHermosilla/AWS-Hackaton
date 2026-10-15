"""Arena SCIP: comparacion justa evrp (HiGHS) vs ev_routing (flujo propio del companero
con SCIP via Pyomo), sobre instancias de competition.

Correcciones respecto de la primera arena:
  - usa el flujo PROPIO del companero: ev_routing.solve.solve_instance con
    SolverConfig(solver='scip'), SIN Gurobi y SIN reimplementar la logica lexicografica;
  - agrega scip.exe al PATH SOLO del subproceso del companero;
  - barre H in {30, 60, 100} (su default es H=30);
  - registra el max_snap_distance_m necesario por instancia (su default 100 m);
  - valida AMBOS motores con un validador neutral INDEPENDIENTE de evrp y ev_routing
    (arena/validador_osm.py: networkx + CSV sobre el MISMO GraphML).

Uso:
    uv run python -m arena scip --out results/arena_scip
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from arena.instancias import (
    grafo_osm_descomprimido,
    grafo_osm_recortado,
    materializar,
)
from arena.supuestos import resolver as resolver_sup
from arena.validador_osm import ValidadorOSM

PROYECTO_EXTERNO = Path(os.environ.get("EVRP_ARENA_PROYECTO_EXTERNO")
                        or Path(__file__).resolve().parents[1] / "externos" / "AWS-Hackaton")
SCIP_BIN = Path(os.environ.get("EVRP_ARENA_SCIP_BIN")
                or Path(__file__).resolve().parents[1] / "externos" / "scip-9.2.4" / "bin")
RUNNER = Path(__file__).parent / "adaptadores" / "ev_routing_runner.py"
PY_EXTERNO = PROYECTO_EXTERNO / ".venv" / "Scripts" / "python.exe"


def _verificar_binarios() -> None:
    """La arena ejecuta un intérprete externo: debe existir y estar en una ruta
    configurada a propósito (no en el perfil de otro usuario por defecto)."""
    for nombre, ruta in (("intérprete externo", PY_EXTERNO), ("SCIP", SCIP_BIN)):
        if not ruta.exists():
            raise FileNotFoundError(
                f"{nombre} no encontrado en {ruta}; defina EVRP_ARENA_PROYECTO_EXTERNO / "
                "EVRP_ARENA_SCIP_BIN. La arena es solo para máquinas de desarrollo.")

# Clientes de competition por tamano (central y cercanos a la BASE).
CLIENTES = {
    "c1": ["V5"],
    "c2": ["V5", "V15"],
    "c3": ["V5", "V15", "V13"],
    "c5": ["V5", "V15", "V13", "V16", "V11"],
}
H_SWEEP = [30, 60, 100]


def _materializar_todas(csv_base: str, out: Path, max_cargadores: int | None) -> dict[str, str]:
    inst_dir = out / "inst"
    rutas = {}
    for nombre, ids in CLIENTES.items():
        desc = {"nombre": f"comp_{nombre}", "csv": csv_base, "clientes_ids": ids}
        if max_cargadores is not None:
            desc["max_cargadores"] = max_cargadores
        rutas[nombre] = str(materializar(desc, inst_dir))
    return rutas


def _validador(csv_path: str, gml: str, sup, max_snap: float = 100.0) -> ValidadorOSM:
    return ValidadorOSM(
        csv_path, gml,
        bateria_kwh=sup.bateria_kwh, reserva_kwh=sup.reserva_kwh,
        soc_inicial=sup.soc_inicial, consumo_kwh_km=sup.consumo_kwh_km,
        conectores_vehiculo=set(sup.conectores), max_snap_distance_m=max_snap)


def correr_evrp(csv_path: str, sup, gml: str, osm_cache: str, vehiculos: int,
                presupuesto: float) -> dict:
    from arena.adaptadores import evrp_adaptador
    r = evrp_adaptador.resolver(csv_path, sup, vehiculos, presupuesto, 1,
                                {"formulacion": "compacta"}, osm_cache)
    val = _validador(csv_path, gml, sup)
    v = val.validar_clave(r["rutas"]) if r.get("rutas") else None
    return {
        "motor": "evrp", "solver": "highs", "H": None,
        "entregas": v.entregas if v else r.get("entregas"),
        "clientes": len(val.clientes),
        "energia_val_kwh": v.energia_total_kwh if v else None,
        "km": v.km_total if v else None,
        "t_construccion_s": None,
        "t_solver_s": r.get("tiempo_solver_s"),
        "gap": r.get("gap"), "estado": r.get("estado"),
        "factible_neutral": v.factible if v else None,
        "energia_motor_kwh": r.get("energia_kwh"),
        "errores_neutral": (v.errores[:3] if v else None),
    }


def correr_companero(csv_path: str, sup, gml: str, h: int, vehiculos: int,
                     presupuesto: float, max_snap: float, out_json: Path,
                     timeout_s: float) -> dict:
    _verificar_binarios()
    env = dict(os.environ)
    env["PATH"] = str(SCIP_BIN) + os.pathsep + env.get("PATH", "")
    cmd = [
        str(PY_EXTERNO), str(RUNNER),
        "--csv", str(Path(csv_path).resolve()),
        "--graphml", str(Path(gml).resolve()),
        "--out", str(out_json.resolve()),
        "--bateria-kwh", repr(sup.bateria_kwh),
        "--reserva-kwh", repr(sup.reserva_kwh),
        "--soc-inicial", repr(sup.soc_inicial),
        "--consumo-kwh-km", repr(sup.consumo_kwh_km),
        "--conectores", ",".join(sup.conectores),
        "--vehiculos", str(int(vehiculos)),
        "--movement-limit", str(int(h)),
        "--presupuesto-s", repr(float(presupuesto)),
        "--hilos", "1",
        "--max-snap-m", repr(float(max_snap)),
        "--flujo-companero", "--solver", "scip",
    ]
    out_json.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, env=env)
    except subprocess.TimeoutExpired:
        return {"motor": "ev_routing", "solver": "scip", "H": h, "estado": "timeout_arena",
                "t_total_arena_s": round(time.perf_counter() - t0, 1)}
    t_total = round(time.perf_counter() - t0, 1)
    if not out_json.exists():
        return {"motor": "ev_routing", "solver": "scip", "H": h, "estado": "error",
                "error": (proc.stderr or proc.stdout or "sin salida")[:600],
                "t_total_arena_s": t_total}
    d = json.loads(out_json.read_text(encoding="utf-8"))
    fila = {
        "motor": "ev_routing", "solver": "scip", "H": h,
        "entregas": d.get("entregas"),
        "energia_motor_kwh": d.get("energia_neta_motor_kwh"),
        "t_construccion_s": d.get("tiempo_construccion_s"),
        "t_solver_s": d.get("tiempo_solver_s"),
        "gap": d.get("gap"), "estado": d.get("estado"),
        "accesos_m": d.get("accesos_m"),
        "nodos_red": d.get("nodos_red"), "arcos_red": d.get("arcos_red"),
        "solver_version": d.get("solver_version"),
        "t_total_arena_s": t_total,
        "fases": d.get("fases"),
    }
    val = _validador(csv_path, gml, sup, max_snap=max_snap)
    fila["clientes"] = len(val.clientes)
    rutas = d.get("rutas") or {}
    if rutas:
        v = val.validar_clave(dict(rutas))
        fila["entregas"] = v.entregas
        fila["energia_val_kwh"] = v.energia_total_kwh
        fila["km"] = v.km_total
        fila["factible_neutral"] = v.factible
        fila["errores_neutral"] = v.errores[:3]
    else:
        fila["energia_val_kwh"] = 0.0
        fila["km"] = 0.0
        fila["factible_neutral"] = True  # ruta vacia: trivialmente factible
    return fila


def _snap_necesario(csv_path: str, gml: str, sup) -> dict:
    val = ValidadorOSM(csv_path, gml, bateria_kwh=sup.bateria_kwh,
                       reserva_kwh=sup.reserva_kwh, soc_inicial=sup.soc_inicial,
                       consumo_kwh_km=sup.consumo_kwh_km,
                       conectores_vehiculo=set(sup.conectores), max_snap_distance_m=1e9)
    return {
        "max_acceso_todos_m": round(val.snap_max_m(), 1),
        "max_acceso_base_clientes_m": round(val.snap_max_cliente_base_m(), 1),
        "accesos_m": {s.node_id: round(val._snap_dist[s.node_id], 1) for s in val.servicios},
    }


def correr(out_dir: str | Path, presupuesto_companero: float = 60.0,
           presupuesto_evrp: float = 60.0, margen_m: float = 800.0,
           timeout_s: float = 420.0, hs: list[int] | None = None,
           instancias: list[str] | None = None,
           max_cargadores: int | None = 5) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    sup = resolver_sup({"supuestos": {"perfil": "ev_routing", "red": "osm"}})
    gml_full = str(grafo_osm_descomprimido())
    osm_cache = str((Path("results/arena/.cache") / "osm").resolve())
    csv_base = str(Path("data/competition_routing_nodes.csv").resolve())
    rutas_csv = _materializar_todas(csv_base, out, max_cargadores)
    # CSV con TODOS los cargadores (para reportar el snap que exige la instancia oficial).
    rutas_full = _materializar_todas(csv_base, out / "full", None)
    hs = hs or H_SWEEP
    instancias = instancias or list(CLIENTES)

    filas: list[dict] = []
    snaps: dict[str, dict] = {}

    for nombre in instancias:
        csv_path = rutas_csv[nombre]
        meta = grafo_osm_recortado(csv_path, out / "osm" / f"comp_{nombre}.graphml",
                                   margen_m=margen_m)
        gml_sub = meta["graphml"]
        snap_sub = _snap_necesario(csv_path, gml_sub, sup)
        # Snap exigido por la instancia con TODOS los cargadores (sobre mapa completo).
        snap_full = _snap_necesario(rutas_full[nombre], gml_full, sup)
        snaps[nombre] = {
            "cargadores_subset": max_cargadores,
            "max_acceso_base_clientes_m": snap_sub["max_acceso_base_clientes_m"],
            "max_acceso_subset_m": snap_sub["max_acceso_todos_m"],
            "max_acceso_todos_cargadores_m": snap_full["max_acceso_todos_m"],
            "subgrafo_nodos": meta["nodos"], "subgrafo_arcos": meta["arcos"],
            "accesos_m": snap_sub["accesos_m"],
        }

        fe = correr_evrp(csv_path, sup, gml_full, osm_cache, 2, presupuesto_evrp)
        fe["instancia"] = nombre
        filas.append(fe)

        # max_snap usado = minimo que acepta el subset (+1 m). Se registra tambien el
        # minimo que exigiria la instancia con TODOS los cargadores.
        max_snap_usado = round(snap_sub["max_acceso_todos_m"] + 1.0, 1)
        snaps[nombre]["max_snap_usado_m"] = max_snap_usado

        for h in hs:
            oj = out / "ev_routing" / f"comp_{nombre}_h{h}.json"
            fc = correr_companero(csv_path, sup, gml_sub, h, 2, presupuesto_companero,
                                  max_snap_usado, oj, timeout_s)
            fc["instancia"] = nombre
            fc["max_snap_usado_m"] = max_snap_usado
            filas.append(fc)

    (out / "resultados.jsonl").write_text(
        "\n".join(json.dumps(f, ensure_ascii=False) for f in filas), encoding="utf-8")
    (out / "snaps.json").write_text(json.dumps(snaps, ensure_ascii=False, indent=1),
                                    encoding="utf-8")
    _escribir_tabla(filas, snaps, out / "tabla.md")
    return {"filas": filas, "snaps": snaps, "out": str(out)}


def _fmt(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "si" if v else "no"
    if isinstance(v, float):
        return f"{v:.4g}"
    return str(v)


def _escribir_tabla(filas, snaps, ruta: Path):
    L = ["# Arena SCIP: evrp (HiGHS) vs ev_routing (flujo propio + SCIP)", ""]
    L.append("Sin ganador: evidencia medida con comandos reales.")
    L.append("")
    cab = ["motor", "solver", "H", "instancia", "entregas/clientes", "energia_val_kwh",
           "km", "t_constr_s", "t_solver_s", "gap", "estado", "factible_neutral"]
    L.append("| " + " | ".join(cab) + " |")
    L.append("|" + "|".join(["---"] * len(cab)) + "|")
    for r in filas:
        ec = f"{_fmt(r.get('entregas'))}/{_fmt(r.get('clientes'))}"
        L.append("| " + " | ".join([
            _fmt(r.get("motor")), _fmt(r.get("solver")), _fmt(r.get("H")),
            _fmt(r.get("instancia")), ec, _fmt(r.get("energia_val_kwh")),
            _fmt(r.get("km")), _fmt(r.get("t_construccion_s")), _fmt(r.get("t_solver_s")),
            _fmt(r.get("gap")), _fmt(r.get("estado")), _fmt(r.get("factible_neutral")),
        ]) + " |")
    L.append("")
    L.append("## max_snap_distance_m por instancia")
    L.append("")
    L.append("El default del companero (100 m) RECHAZA la instancia con TODOS los cargadores "
             "(hay cargadores alejados de la calle, p.ej. C7~416 m). Para el companero se usa "
             "un subconjunto de cargadores cercano (documentado) y el min snap que lo acepta.")
    L.append("")
    cab2 = ["instancia", "cargadores_subset", "max_acceso_base_clientes_m",
            "max_acceso_subset_m", "max_snap_usado_m", "max_acceso_TODOS_cargadores_m",
            "default_100m_acepta_todos", "subgrafo_nodos", "subgrafo_arcos"]
    L.append("| " + " | ".join(cab2) + " |")
    L.append("|" + "|".join(["---"] * len(cab2)) + "|")
    for nombre, s in snaps.items():
        acepta_100 = s.get("max_acceso_todos_cargadores_m", 1e9) <= 100.0
        L.append("| " + " | ".join([
            nombre, _fmt(s.get("cargadores_subset")),
            _fmt(s.get("max_acceso_base_clientes_m")), _fmt(s.get("max_acceso_subset_m")),
            _fmt(s.get("max_snap_usado_m")), _fmt(s.get("max_acceso_todos_cargadores_m")),
            "si" if acepta_100 else "no",
            _fmt(s.get("subgrafo_nodos")), _fmt(s.get("subgrafo_arcos")),
        ]) + " |")
    ruta.write_text("\n".join(L), encoding="utf-8")
