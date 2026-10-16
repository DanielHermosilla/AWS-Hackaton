import json
import statistics as st

d = json.load(open("e1_sensibilidad.json", encoding="utf-8"))
print(f'{"inst":12} {"plano":>6} {"pend":>6} {"dPend%":>6} {"cal":>6} {"frio":>6} {"temp":>6} {"arcDif%":>7} {"frioFact":>8}')
difs, dpcts, nfrio = [], [], 0
for x in d:
    r = x["recalculo_energia_rutas_plano"]
    ro = x["reoptimizacion_pendiente"]
    pl = x["energia_plano_kwh"]
    pn = r["pendiente_nominal"]["energia_total_kwh"]
    cal = r["pendiente_calibrado_eved"]["energia_total_kwh"]
    fr = r["temp_frio_<0"]["energia_total_kwh"]
    tp = r["temp_templado_20_30"]["energia_total_kwh"]
    ad = ro["dif_arcos_vs_plano"]["pct_distintos"]
    frf = r["temp_frio_<0"]["factible"]
    difs.append(ad)
    dpcts.append(ro["delta_energia_pct"])
    nfrio += 0 if frf else 1
    print(f'{x["nombre"]:12} {pl:6.2f} {pn:6.2f} {100*(pn-pl)/pl:6.1f} {cal:6.2f} {fr:6.2f} {tp:6.2f} {ad:7.1f} {str(frf):>8}')
print(f"\narcos_dif%: medio={st.mean(difs):.2f} max={max(difs):.1f}")
print(f"delta_energia_reopt%: medio={st.mean(dpcts):.3f} max={max(dpcts):.3f}")
print(f"frio(<0C) infeasibles: {nfrio}/{len(d)}")
