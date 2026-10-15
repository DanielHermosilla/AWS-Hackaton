"""Arnés de versiones: ejecuta un conjunto fijo de escenarios sobre un ref de git.

Dado un ref (tag v0.3.0, rama exp/*, o 'WT' = working tree actual), crea un worktree
temporal en .cache/bench-wt/<ref> (git worktree add, sin tocar ramas), ejecuta ahí la
API `evrp.resolver` del propio ref y guarda una línea JSON por escenario en
benchmarks/resultados/<ref>.jsonl con: entregas, energía, km, tiempos (total y por
etapa), gap y un hash determinista de las rutas.

Uso:
    uv run python benchmarks/correr.py v0.3.0
    uv run python benchmarks/correr.py WT            # working tree de esta rama
    uv run python benchmarks/correr.py v0.3.0 WT     # varios refs

Un núcleo por proceso (solver.hilos=1), sin paralelismo. Pensado para tardar pocos minutos.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CACHE_WT = RAIZ / ".cache" / "bench-wt"
RESULTADOS = Path(__file__).resolve().parent / "resultados"

# Escenarios fijos. Cada uno: (nombre, kind, args). kind 'csv' usa data/*.csv;
# kind 'sint' genera un sintético reproducible de N clientes con una semilla.
ESCENARIOS = []
for perfil in ("ev_routing", "eved"):
    ESCENARIOS.append((f"competition__{perfil}", "csv", {"csv": "data/competition_routing_nodes.csv", "perfil": perfil}))
    ESCENARIOS.append((f"evaluation__{perfil}", "csv", {"csv": "data/evaluation_routing_nodes.csv", "perfil": perfil}))
    for semilla in (1, 2, 3):
        ESCENARIOS.append((f"sint20_s{semilla}__{perfil}", "sint",
                           {"clientes": 20, "semilla": semilla, "perfil": perfil}))

PRESUPUESTO_S = 30.0  # por escenario; mantiene el total en pocos minutos


def _hash_rutas(rutas: dict) -> str:
    """Hash determinista de las rutas (orden de vehículos irrelevante)."""
    canon = sorted(tuple(r) for r in rutas.values())
    return hashlib.sha1(json.dumps(canon, ensure_ascii=False).encode()).hexdigest()[:12]


def _etapas(bitacora: list) -> dict:
    """Extrae tiempos acumulados por hito de la bitácora (t_s es acumulado desde t0)."""
    hitos = {}
    for ev in bitacora or []:
        hitos[ev["paso"]] = ev.get("t_s")
    red = hitos.get("red")
    milp = hitos.get("milp")
    etapa_red = red
    etapa_milp = (milp - red) if (milp is not None and red is not None) else None
    return {"t_red_s": etapa_red, "t_milp_s": etapa_milp}


def _gap(solver_traza) -> float | None:
    if not isinstance(solver_traza, dict):
        return None
    f2 = solver_traza.get("fase2") or (solver_traza.get("compacta") or {}).get("fase2")
    if isinstance(f2, dict):
        return f2.get("gap")
    return None


# --- script que se ejecuta DENTRO del worktree del ref (su propio código evrp) ---
RUNNER = r'''
import csv, json, sys, time, tempfile
from pathlib import Path

def generar_sint(clientes, semilla, ref_csv, destino):
    try:
        from evrp.sintetico import generar, escribir
        filas = generar(clientes, semilla=semilla, referencia=ref_csv)
        escribir(filas, destino)
        return destino
    except Exception as e:
        print(json.dumps({"error_sint": str(e)}), file=sys.stderr); raise

def resolver_csv(csv_path, perfil, presupuesto):
    from evrp.api import resolver
    cfg = {"solver": {"hilos": 1, "tiempo_limite_s": presupuesto, "presupuesto_total_s": presupuesto}}
    t0 = time.perf_counter()
    r = resolver(csv_path, cfg, [perfil], salida=None)
    return r, round(time.perf_counter() - t0, 3)

esc = json.loads(sys.argv[1])
presupuesto = float(sys.argv[2])
tmp = Path(sys.argv[3])
out = []
for nombre, kind, args in esc:
    try:
        if kind == "csv":
            csv_path = args["csv"]
        else:
            csv_path = str(tmp / f"{nombre}.csv")
            generar_sint(args["clientes"], args["semilla"], "data/competition_routing_nodes.csv", csv_path)
        r, t_wall = resolver_csv(csv_path, args["perfil"], presupuesto)
        k = r.kpis
        out.append({"escenario": nombre, "ok": True, "factible": k.get("factible"),
                    "entregas": k.get("entregas"), "clientes": k.get("clientes"),
                    "energia_kwh": k.get("energia_total_kwh"), "km": k.get("km_total"),
                    "t_total_s": k.get("tiempo_computo_s"), "t_wall_s": t_wall,
                    "solver": k.get("solver"), "rutas": r.rutas, "bitacora": r.bitacora})
    except Exception as e:
        out.append({"escenario": nombre, "ok": False, "error": str(e)[:400]})
print("___BENCH_JSON___")
print(json.dumps(out))
'''


def _preparar_worktree(ref: str) -> Path:
    if ref.upper() == "WT":
        return RAIZ
    destino = CACHE_WT / ref.replace("/", "_")
    if destino.exists():
        return destino
    CACHE_WT.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "worktree", "add", "--detach", str(destino), ref],
                   cwd=RAIZ, check=True, capture_output=True, text=True)
    # copiar data/ (grande, fuera de git) para que el ref vea los CSV
    data_src = RAIZ / "data"
    data_dst = destino / "data"
    if data_src.exists() and not any(data_dst.glob("*.csv")):
        import shutil
        data_dst.mkdir(parents=True, exist_ok=True)
        for f in data_src.glob("*.csv"):
            shutil.copy2(f, data_dst / f.name)
    return destino


def correr_ref(ref: str) -> Path:
    wt = _preparar_worktree(ref)
    RESULTADOS.mkdir(parents=True, exist_ok=True)
    salida = RESULTADOS / f"{ref.replace('/', '_')}.jsonl"
    print(f"[{ref}] worktree={wt}")
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        cmd = ["uv", "run", "python", "-c", RUNNER,
               json.dumps(ESCENARIOS), str(PRESUPUESTO_S), td]
        t0 = time.perf_counter()
        proc = subprocess.run(cmd, cwd=wt, capture_output=True, text=True)
        wall = time.perf_counter() - t0
    if "___BENCH_JSON___" not in proc.stdout:
        print(proc.stdout[-2000:]); print(proc.stderr[-2000:], file=sys.stderr)
        raise RuntimeError(f"[{ref}] el runner no produjo salida JSON")
    bruto = json.loads(proc.stdout.split("___BENCH_JSON___", 1)[1])
    with open(salida, "w", encoding="utf-8") as f:
        for r in bruto:
            fila = {"ref": ref, "escenario": r["escenario"], "ok": r.get("ok")}
            if r.get("ok"):
                etapas = _etapas(r.get("bitacora"))
                fila.update({"factible": r.get("factible"), "entregas": r.get("entregas"),
                             "clientes": r.get("clientes"), "energia_kwh": r.get("energia_kwh"),
                             "km": r.get("km"), "t_total_s": r.get("t_total_s"),
                             "gap": _gap(r.get("solver")),
                             "hash_rutas": _hash_rutas(r.get("rutas", {})), **etapas})
            else:
                fila["error"] = r.get("error")
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")
    print(f"[{ref}] {len(bruto)} escenarios en {wall:.0f}s -> {salida}")
    return salida


def main(argv=None):
    refs = (argv or sys.argv[1:]) or ["WT"]
    for ref in refs:
        correr_ref(ref)


if __name__ == "__main__":
    main()
