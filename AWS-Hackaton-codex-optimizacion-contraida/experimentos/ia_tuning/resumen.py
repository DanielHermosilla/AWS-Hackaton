"""Agrega los resultados del experimento ia_tuning para el informe."""
import json
import statistics as st
from pathlib import Path

d = json.load(open(Path(__file__).parent / "resultados.json", encoding="utf-8"))
c = d["corridas"]

print("=== Por variante (syn40+syn60) ===")
hdr = ("var", "energia_med", "gap_med", "tmilp_med", "ttot_med", "llm_tok_med", "llm_lat_med")
print("%-10s%12s%10s%11s%10s%12s%12s" % hdr)
for v in ["base", "haiku", "sonnet", "aleatorio"]:
    rs = [r for r in c if r["variante"] == v and r["instancia"] != "competition"]
    en = st.mean(r["energia_kwh"] for r in rs)
    gp = st.mean(r["gap"] for r in rs if r["gap"] is not None)
    tm = st.mean(r["t_milp_s"] for r in rs)
    tt = st.mean(r["t_total_s"] for r in rs)
    tok = [r.get("llm_tokens_in", 0) + r.get("llm_tokens_out", 0) for r in rs if "llm_tokens_in" in r]
    lat = [r.get("llm_latencia_s", 0) for r in rs if r.get("llm_latencia_s")]
    tokm = st.mean(tok) if tok else 0
    latm = st.mean(lat) if lat else 0
    print("%-10s%12.4f%10.4f%11.2f%10.2f%12.0f%12.2f" % (v, en, gp, tm, tt, tokm, latm))

print("\n=== vs base: gap (menor=mejor) y energia (syn40/60) ===")
base = {(r["instancia"], r["semilla"], r["rep"]): r for r in c if r["variante"] == "base"}
for v in ["haiku", "sonnet", "aleatorio"]:
    mejor = peor = igual = 0
    de = []
    for r in c:
        if r["variante"] != v or r["instancia"] == "competition":
            continue
        b = base[(r["instancia"], r["semilla"], r["rep"])]
        dg = r["gap"] - b["gap"]
        if dg < -1e-6:
            mejor += 1
        elif dg > 1e-6:
            peor += 1
        else:
            igual += 1
        de.append(r["energia_kwh"] - b["energia_kwh"])
    print("%-10s gap: mejor=%d igual=%d peor=%d | dEnergia_med=%+.4f kWh (max %+.4f)"
          % (v, mejor, igual, peor, st.mean(de), max(de, key=abs)))

tin = sum(r.get("llm_tokens_in", 0) for r in c)
tout = sum(r.get("llm_tokens_out", 0) for r in c)
lat = sum(r.get("llm_latencia_s", 0) for r in c)
print("\nTokens Bedrock totales: in=%d out=%d total=%d; latencia LLM acumulada=%.1fs"
      % (tin, tout, tin + tout, lat))

print("\n=== Propuestas LLM por instancia (primera aparicion) ===")
seen = set()
for r in c:
    if r["variante"] in ("haiku", "sonnet") and "llm_propuesta" in r:
        k = (r["variante"], r["instancia"])
        if k in seen:
            continue
        seen.add(k)
        print(r["variante"], r["instancia"], r["llm_propuesta"])

print("\n=== Perfiles estructurales ===")
for k, p in d["perfiles"].items():
    print(k, "cols=%d filas=%d bin=%d dens=%.4f rango_log10=%.2f base_gap=%.4f"
          % (p["columnas"], p["filas"], p["binarias"], p["densidad"],
             p["rango_coef_log10"], p["base_gap"] or 0))
