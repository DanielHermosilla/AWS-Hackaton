import json

d = json.load(open("e2_robustez.json", encoding="utf-8"))
print("viajes", d["viajes"], "pctiles", d["consumo_pctiles_kwh_km"])
print("por_banda_oat:")
for k, v in d["por_banda_oat"].items():
    print(f"  {k:6} n={v['n']:4} mediana={v['mediana']} p90={v['p90']}")
for esc, filas in d["escenarios"].items():
    print(f"\n=== {esc} ===")
    for pq in ("p75", "p90", "p95"):
        inf = [f["inst"] for f in filas if not f[pq]["factible"]]
        margs = [f[pq]["margen_min_kwh"] for f in filas if f[pq]["margen_min_kwh"] is not None]
        print(f"  {pq}: infactibles={len(inf)}/{len(filas)} {inf if inf else ''} "
              f"margen_min_global={min(margs):.3f}" if margs else f"  {pq}: infactibles={len(inf)}/{len(filas)} {inf}")
