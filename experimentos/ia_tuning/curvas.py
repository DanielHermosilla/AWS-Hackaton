"""Curvas gap–tiempo: base vs LLM (Haiku 4.5) vs control aleatorio, presupuesto 120 s.

Uso:
    $env:AWS_PROFILE='hackathon'
    uv run python -m experimentos.ia_tuning.curvas --total 120 --reps 2
    uv run --with matplotlib==3.9.2 python -m experimentos.ia_tuning.curvas --graficar

La propuesta del LLM se pide UNA vez por instancia, ANTES de resolver (como ocurriría en
producción): el perfil estructural no incluye resultados de una corrida base. Su latencia se
descuenta del presupuesto del MILP. El control aleatorio usa una muestra fija de la misma
lista blanca por instancia. Hilos = 1 en todas las corridas.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import time
from pathlib import Path

from experimentos.ia_tuning.bench import HAIKU, _nodos, _preparar

SALIDA = Path("experimentos/ia_tuning/curvas.jsonl")
FIG = Path("docs/experimentos/figuras/tuning_gap_tiempo.png")
FILA_LOG = re.compile(r"^\s*[A-Za-z]?\s*\d+\s+\d+\s+\d+\s+[\d.]+%\s+(?P<bound>\S+)\s+(?P<sol>\S+)\s+"
                      r"(?P<gap>\S+%|inf|Large)\s+.*\s(?P<t>[\d.]+)s\s*$")


def _num(x):
    try:
        return float(x.rstrip("%"))
    except ValueError:
        return None


def _curva(log: Path, t_offset: float) -> list[dict]:
    puntos = []
    for linea in log.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = FILA_LOG.match(linea)
        if m:
            puntos.append({"t_s": round(float(m["t"]) + t_offset, 2), "cota": _num(m["bound"]),
                           "sol": _num(m["sol"]), "gap_pct": _num(m["gap"])})
    return puntos


def _normalizar(overrides: dict) -> dict:
    """La lista blanca devuelve {'solver': {'escala': {...}}}, pero `_preparar` del bench lee
    la escala desde el nivel superior y sobrescribe solver.escala: sin este paso los ajustes de
    escala (k_vecinos, presolve, mip_heuristic_effort) se descartaban en silencio."""
    ov = json.loads(json.dumps(overrides))
    esc = ov.get("solver", {}).pop("escala", None)
    if esc:
        ov["escala"] = {**ov.get("escala", {}), **esc}
    return ov


def correr_una(ruta, etiqueta, overrides, total, latencia_llm, rep, tmp: Path) -> dict:
    from evrp.milp_compacto import ModeloCompacto

    cfg, inst, red, inicial, t_prep = _preparar(ruta, 2, "ev_routing", _normalizar(overrides))
    efectiva = {"k_vecinos": cfg["escala"].get("k_vecinos"), "presolve": cfg["escala"].get("presolve"),
                "mip_heuristic_effort": cfg["escala"].get("mip_heuristic_effort"),
                "cargadores_por_arco": cfg["solver"].get("cargadores_por_arco")}
    limite = max(10.0, total - t_prep - latencia_llm - 3.0)
    cfg_solver = {**cfg["solver"], "escala": cfg["escala"], "tiempo_limite_s": limite, "hilos": 1}
    modelo = ModeloCompacto(inst, cfg_solver, inicial)
    log = tmp / f"{ruta.stem}_{etiqueta}_{rep}.log"
    log.unlink(missing_ok=True)
    h = modelo.h
    h.setOptionValue("output_flag", True)
    h.setOptionValue("log_to_console", False)
    h.setOptionValue("log_file", str(log))
    h.setOptionValue("threads", 1)
    t0 = time.perf_counter()
    sol, traza = modelo.optimizar(inicial, len(inicial.atendidos) == len(inst.clientes))
    t_milp = time.perf_counter() - t0
    f2 = traza.get("fase2", {}) if isinstance(traza, dict) else {}
    offset = t_prep + latencia_llm
    return {"instancia": ruta.stem, "config": etiqueta, "rep": rep, "overrides": overrides,
            "config_efectiva": efectiva,
            "t_prep_s": round(t_prep, 2), "latencia_llm_s": round(latencia_llm, 2),
            "limite_milp_s": round(limite, 2), "t_total_s": round(offset + t_milp, 2),
            "energia_kwh": f2.get("energia"), "cota": f2.get("cota"),
            "gap_pct": None if f2.get("gap") is None else round(100 * f2["gap"], 3),
            "heuristica_kwh": round(inicial.energia, 4), "columnas": h.getNumCol(), "filas": h.getNumRow(),
            "curva": _curva(log, offset)}


def propuesta_llm(ruta) -> tuple[dict, float, dict]:
    from evrp.ia.bedrock import ClienteBedrock
    from evrp.ia.tuning import llm as llmmod
    from evrp.ia.tuning import whitelist as wl
    from evrp.ia.tuning.perfil import perfil_desde_modelo
    from evrp.milp_compacto import ModeloCompacto

    cfg, inst, red, inicial, _ = _preparar(ruta, 2, "ev_routing", {})
    modelo = ModeloCompacto(inst, {**cfg["solver"], "escala": cfg["escala"]}, inicial)
    perfil = perfil_desde_modelo(modelo, inst, cfg["solver"]["cargadores_por_arco"])
    pr = llmmod.proponer(ClienteBedrock(modelo=HAIKU), perfil, modelo=HAIKU)
    info = {"propuesta": pr.propuesta, "tokens": pr.tokens_total, "error": pr.error}
    return wl.aplicar_overrides({}, pr.propuesta), pr.latencia_s, info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--total", type=float, default=120.0)
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--clientes", type=int, nargs="+", default=[40, 60])
    ap.add_argument("--graficar", action="store_true")
    a = ap.parse_args()
    if a.graficar:
        return graficar()
    from evrp.ia.tuning import whitelist as wl

    tmp = Path(".cache/curvas")
    tmp.mkdir(parents=True, exist_ok=True)
    hechos = set()
    if SALIDA.exists():
        for l in SALIDA.read_text(encoding="utf-8").splitlines():
            d = json.loads(l)
            hechos.add((d["instancia"], d["config"], d["rep"]))
    for n in a.clientes:
        ruta = _nodos(n, 1, False)
        ov_llm, lat, info = propuesta_llm(ruta)
        ov_rnd = wl.aplicar_overrides({}, wl.muestra_aleatoria(random.Random(1000 + n)))
        print(f"[{ruta.stem}] LLM propone {info}  | aleatorio {ov_rnd}", flush=True)
        for etiqueta, ov, l in (("base", {}, 0.0), ("llm_haiku", ov_llm, lat), ("aleatorio", ov_rnd, 0.0)):
            for rep in range(a.reps):
                if (ruta.stem, etiqueta, rep) in hechos:
                    continue
                fila = correr_una(ruta, etiqueta, ov, a.total, l, rep, tmp)
                if etiqueta == "llm_haiku":
                    fila["llm"] = info
                with open(SALIDA, "a", encoding="utf-8") as f:
                    f.write(json.dumps(fila, ensure_ascii=False) + "\n")
                print(f"  {etiqueta} rep{rep}: E={fila['energia_kwh']} gap={fila['gap_pct']}% "
                      f"t={fila['t_total_s']}s puntos={len(fila['curva'])}", flush=True)


def graficar():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    filas = [json.loads(l) for l in SALIDA.read_text(encoding="utf-8").splitlines()]
    insts = sorted({f["instancia"] for f in filas})
    colores = {"base": "tab:blue", "llm_haiku": "tab:red", "aleatorio": "tab:gray"}
    fig, ejes = plt.subplots(1, len(insts), figsize=(6.5 * len(insts), 4.5), squeeze=False)
    for ax, inst in zip(ejes[0], insts):
        for f in (x for x in filas if x["instancia"] == inst):
            pts = [p for p in f["curva"] if p["gap_pct"] is not None]
            if not pts:
                continue
            estilo = "-" if f["rep"] == 0 else "--"
            ax.step([p["t_s"] for p in pts], [p["gap_pct"] for p in pts], where="post", ls=estilo,
                    color=colores.get(f["config"], "k"),
                    label=f"{f['config']} rep{f['rep']} (final {f['gap_pct']}%, {f['energia_kwh']:.3f} kWh)")
        ax.set_title(f"{inst}: gap vs tiempo (presupuesto 120 s, 1 hilo)")
        ax.set_xlabel("tiempo total desde el inicio (s): preparación + LLM + MILP")
        ax.set_ylabel("gap (%)")
        ax.set_ylim(bottom=0)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=7)
    FIG.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(FIG, dpi=130)
    print(f"figura: {FIG}")


if __name__ == "__main__":
    main()
