"""Visualiza el efecto del umbral top-k (25 clientes) y el punto de rendimiento decreciente.

    uv run python -m experimentos.topk.visual correr      # 3 corridas de 60 s (24 k=0, 26 k=0, 26 k=10)
    uv run --with matplotlib==3.9.2 python -m experimentos.topk.visual graficar

Figuras en docs/experimentos/figuras/: topk_arcos.png, topk_gap_tiempo.png, parada_incumbente.png.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from experimentos.ia_tuning.bench import _nodos, _preparar
from experimentos.ia_tuning.curvas import correr_una

SALIDA = Path("experimentos/topk/visual.jsonl")
FIGS = Path("docs/experimentos/figuras")
CASOS = [(24, "k0_auto", {"escala": {"k_vecinos": 0}}),
         (26, "k0_sin_poda", {"escala": {"k_vecinos": 0}}),
         (26, "k10_auto", {"escala": {"k_vecinos": 10}})]
ETIQUETA = {"k0_auto": "k=0 (auto, ≤25)", "k0_sin_poda": "k=0 (sin poda)", "k10_auto": "k=10 (auto, >25)"}


def correr():
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(".cache/curvas")
    tmp.mkdir(parents=True, exist_ok=True)
    with open(SALIDA, "w", encoding="utf-8") as f:
        for n, etiqueta, ov in CASOS:
            fila = correr_una(_nodos(n, 1, False), etiqueta, ov, 60.0, 0.0, 0, tmp)
            fila["clientes"] = n
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")
            print(n, etiqueta, "E", fila["energia_kwh"], "gap", fila["gap_pct"], "cols", fila["columnas"], flush=True)


def _arcos_cliente(n, k):
    cfg, inst, *_ = _preparar(_nodos(n, 1, False), 2, "ev_routing", {"escala": {"k_vecinos": k}})
    Cs = set(inst.clientes)
    dt = inst.tipos[0]
    cc = [(i, j) for (i, j) in dt.arcos if i in Cs and j in Cs]
    return inst, cc


def graficar():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIGS.mkdir(parents=True, exist_ok=True)
    # --- 1) Qué hace top-k: arcos cliente→cliente de un cliente, sin poda vs k=10 ------------------
    inst0, cc0 = _arcos_cliente(26, 0)
    inst10, cc10 = _arcos_cliente(26, 10)
    pos = {i: (n.lon, n.lat) for i, n in inst0.nodos.items()}
    foco = inst0.clientes[0]
    fig, ejes = plt.subplots(1, 2, figsize=(12, 5))
    for ax, cc, titulo in ((ejes[0], cc0, f"Sin poda (k=0): {len(cc0)} arcos cliente→cliente"),
                           (ejes[1], cc10, f"Top-k (k=10): {len(cc10)} arcos cliente→cliente")):
        for (i, j) in cc:
            if i == foco:
                ax.plot(*zip(pos[i], pos[j]), color="tab:blue", lw=1.2, alpha=0.8)
        cl = [pos[c] for c in inst0.clientes]
        ca = [pos[i] for i, n in inst0.nodos.items() if n.tipo == "cargador"]
        ax.scatter(*zip(*ca), s=10, c="tab:green", marker="^", label="cargadores")
        ax.scatter(*zip(*cl), s=18, c="k", label="clientes")
        ax.scatter(*pos[inst0.base], s=80, c="tab:red", marker="s", label="base")
        ax.scatter(*pos[foco], s=90, facecolors="none", edgecolors="tab:blue", lw=2,
                   label=f"{foco}: arcos que salen de él")
        ax.set_title(titulo)
        ax.set_xlabel("longitud")
        ax.set_ylabel("latitud")
        ax.legend(fontsize=7, loc="lower left")
    fig.suptitle("Top-k: cada cliente conserva solo los k arcos de menor energía hacia otros clientes "
                 "(base y cargadores siempre se conservan) — instancia sintética de 26 clientes")
    fig.tight_layout()
    fig.savefig(FIGS / "topk_arcos.png", dpi=130)

    # --- 2) Curvas gap–tiempo y energía para 24/26 -------------------------------------------------
    filas = [json.loads(l) for l in SALIDA.read_text(encoding="utf-8").splitlines()]
    fig, ejes = plt.subplots(1, 2, figsize=(12, 4.5))
    colores = ["tab:blue", "tab:orange", "tab:red"]
    for f, col in zip(filas, colores):
        pts = [p for p in f["curva"] if p["gap_pct"] is not None]
        lab = f"{f['clientes']} cl. {ETIQUETA.get(f['config'], f['config'])} — {f['columnas']} cols, final {f['gap_pct']}%"
        ejes[0].step([p["t_s"] for p in pts], [p["gap_pct"] for p in pts], where="post", color=col, label=lab)
        sol = [p for p in f["curva"] if p["sol"] is not None]
        ejes[1].step([p["t_s"] for p in sol], [p["sol"] for p in sol], where="post", color=col,
                     label=f"{f['clientes']} cl. {ETIQUETA.get(f['config'], f['config'])} — final {f['energia_kwh']:.3f} kWh")
    ejes[0].set_title("Gap vs tiempo (60 s, 1 hilo)")
    ejes[0].set_ylabel("gap (%)")
    ejes[0].set_ylim(0, 30)
    ejes[1].set_title("Mejor energía encontrada vs tiempo")
    ejes[1].set_ylabel("kWh")
    for ax in ejes:
        ax.set_xlabel("tiempo total (s)")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(FIGS / "topk_gap_tiempo.png", dpi=130)

    # --- 3) Rendimiento decreciente: % de la mejora total del incumbente lograda en el tiempo -----
    previas = Path("experimentos/ia_tuning/curvas.jsonl")
    todas = filas + ([json.loads(l) for l in previas.read_text(encoding="utf-8").splitlines()]
                     if previas.exists() else [])
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    resumen = []
    for f in todas:
        if f.get("rep", 0) != 0 or f.get("config") in ("aleatorio",):
            continue
        sol = [p for p in f["curva"] if p["sol"] is not None]
        if len(sol) < 2:
            continue
        e0, ef = f.get("heuristica_kwh") or sol[0]["sol"], sol[-1]["sol"]
        if e0 - ef <= 1e-9:
            continue
        xs = [p["t_s"] for p in sol]
        ys = [100 * (e0 - p["sol"]) / (e0 - ef) for p in sol]
        nombre = f"{f['instancia']} {f['config']}"
        ax.step(xs, ys, where="post", label=f"{nombre} (mejora total {100 * (e0 - ef) / e0:.1f}%)")
        t95 = next((x for x, y in zip(xs, ys) if y >= 95), None)
        resumen.append({"instancia": nombre, "t_95pct_mejora_s": t95, "t_final_s": xs[-1],
                        "mejora_total_pct": round(100 * (e0 - ef) / e0, 2)})
    ax.axhline(95, color="k", ls=":", lw=1)
    ax.set_xlabel("tiempo total (s)")
    ax.set_ylabel("% de la mejora final del incumbente (desde la heurística)")
    ax.set_title("¿Cuándo deja de valer la pena seguir? (curvas previas 120 s y nuevas 60 s)")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=6)
    fig.tight_layout()
    fig.savefig(FIGS / "parada_incumbente.png", dpi=130)
    print(json.dumps(resumen, ensure_ascii=False, indent=1))
    print("arcos cliente→cliente 26 cl.:", len(cc0), "→", len(cc10))


if __name__ == "__main__":
    {"correr": correr, "graficar": graficar}[sys.argv[1] if len(sys.argv) > 1 else "graficar"]()
