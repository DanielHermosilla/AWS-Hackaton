"""Tabula y compara dos o más refs ya corridos por benchmarks/correr.py.

Lee benchmarks/resultados/<ref>.jsonl y produce una tabla Markdown por escenario con
entregas, energía, km, tiempo total y hash de rutas de cada ref, más columnas de
diferencia (energía, tiempo) y una marca si las rutas cambiaron.

Uso:
    uv run python benchmarks/comparar.py v0.3.0 WT
    uv run python benchmarks/comparar.py v0.3.0 WT --md docs/experimentos/_tabla.md
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RESULTADOS = Path(__file__).resolve().parent / "resultados"


def _cargar(ref: str) -> dict:
    ruta = RESULTADOS / f"{ref.replace('/', '_')}.jsonl"
    if not ruta.exists():
        raise FileNotFoundError(f"No existe {ruta}; corre antes benchmarks/correr.py {ref}")
    out = {}
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        if linea.strip():
            d = json.loads(linea)
            out[d["escenario"]] = d
    return out


def _fmt(v, dec=3):
    return "-" if v is None else (f"{v:.{dec}f}" if isinstance(v, float) else str(v))


def comparar(refs: list[str]) -> str:
    datos = {ref: _cargar(ref) for ref in refs}
    escenarios = sorted({e for d in datos.values() for e in d})
    lineas = []
    cab = ["escenario"]
    for ref in refs:
        cab += [f"{ref}·ent", f"{ref}·kWh", f"{ref}·s", f"{ref}·rutas"]
    if len(refs) == 2:
        cab += ["ΔkWh", "Δ%kWh", "Δs", "rutas="]
    lineas.append("| " + " | ".join(cab) + " |")
    lineas.append("|" + "---|" * len(cab))
    tot_e = {ref: 0.0 for ref in refs}
    tot_t = {ref: 0.0 for ref in refs}
    tot_ent = {ref: 0 for ref in refs}
    for esc in escenarios:
        fila = [esc]
        vals = {}
        for ref in refs:
            d = datos[ref].get(esc, {})
            if d.get("ok"):
                fila += [_fmt(d.get("entregas"), 0), _fmt(d.get("energia_kwh"), 3),
                         _fmt(d.get("t_total_s"), 1), (d.get("hash_rutas") or "-")[:8]]
                vals[ref] = d
                tot_e[ref] += d.get("energia_kwh") or 0.0
                tot_t[ref] += d.get("t_total_s") or 0.0
                tot_ent[ref] += d.get("entregas") or 0
            else:
                fila += ["ERR", "-", "-", "-"]
        if len(refs) == 2 and all(r in vals for r in refs):
            a, b = vals[refs[0]], vals[refs[1]]
            de = (b.get("energia_kwh") or 0) - (a.get("energia_kwh") or 0)
            pe = (100 * de / a["energia_kwh"]) if a.get("energia_kwh") else 0.0
            dt = (b.get("t_total_s") or 0) - (a.get("t_total_s") or 0)
            igual = "sí" if a.get("hash_rutas") == b.get("hash_rutas") else "**no**"
            fila += [_fmt(de, 4), _fmt(pe, 2), _fmt(dt, 1), igual]
        elif len(refs) == 2:
            fila += ["-", "-", "-", "-"]
        lineas.append("| " + " | ".join(fila) + " |")
    tot = ["**TOTAL**"]
    for ref in refs:
        tot += [str(tot_ent[ref]), f"{tot_e[ref]:.3f}", f"{tot_t[ref]:.1f}", "-"]
    if len(refs) == 2:
        de = tot_e[refs[1]] - tot_e[refs[0]]
        pe = 100 * de / tot_e[refs[0]] if tot_e[refs[0]] else 0.0
        tot += [f"{de:.4f}", f"{pe:.2f}", f"{tot_t[refs[1]] - tot_t[refs[0]]:.1f}", "-"]
    lineas.append("| " + " | ".join(tot) + " |")
    return "\n".join(lineas)


def main(argv=None):
    args = list(argv or sys.argv[1:])
    md = None
    if "--md" in args:
        i = args.index("--md")
        md = args[i + 1]
        del args[i:i + 2]
    if len(args) < 2:
        print("Uso: comparar.py <ref1> <ref2> [...] [--md salida.md]")
        return 1
    tabla = comparar(args)
    print(tabla)
    if md:
        Path(md).parent.mkdir(parents=True, exist_ok=True)
        Path(md).write_text(tabla + "\n", encoding="utf-8")
        print(f"\n-> {md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
