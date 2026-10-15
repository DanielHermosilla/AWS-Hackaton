"""Experimento IDEA E: ajuste del solver estilo LLM4MIP.

Compara, por instancia y repetición:
  - base         : config del perfil sin cambios.
  - haiku        : propuesta de Claude Haiku 4.5 sobre el perfil estructural.
  - sonnet       : propuesta de Claude Sonnet 4.6 sobre el perfil estructural.
  - aleatorio    : control (misma lista blanca, mismo nº de pruebas = 1 propuesta/corrida).

Presupuesto TOTAL igual para todas las variantes (por defecto 55 s). Para las
variantes LLM, la latencia de la llamada a Bedrock se descuenta del presupuesto
del MILP (se cuenta dentro del tiempo total). El perfil estructural se extrae una
sola vez por instancia (de la construcción base) y se reutiliza para los dos LLM.

Métricas por corrida: energía, gap, tiempo MILP, tiempo total (incl. LLM),
entregas, factibilidad, y costo del LLM (latencia + tokens).

Uso:
    uv run python experimentos/ia_tuning/bench.py --clientes 40 60 --semillas 1 2 3 \
        --competition --total 55 --reps 2 --salida experimentos/ia_tuning/resultados.json

    # Sin Bedrock (sólo base vs aleatorio), para humo rápido:
    uv run python experimentos/ia_tuning/bench.py --clientes 40 --semillas 1 --reps 1 \
        --sin-llm --total 20 --salida experimentos/ia_tuning/humo.json
"""
from __future__ import annotations

import argparse
import copy
import json
import random
import time
from pathlib import Path

from evrp import config as cfgmod
from evrp import heuristica
from evrp.datos import cargar_nodos
from evrp.instancia import construir, tipos_desde_config
from evrp.red import RedHaversine, crear_red
from evrp.sintetico import escribir, generar
from evrp.validador import validar

from evrp.ia.tuning import whitelist as wl
from evrp.ia.tuning.perfil import perfil_desde_modelo

RAIZ = Path(__file__).resolve().parents[2]
REF = RAIZ / "data" / "competition_routing_nodes.csv"
COMPETITION = RAIZ / "data" / "competition_routing_nodes.csv"
TMP = Path(__file__).resolve().parent / "_tmp"

HAIKU = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
SONNET = "us.anthropic.claude-sonnet-4-6"


def _fusionar(base, extra):
    out = copy.deepcopy(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _fusionar(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _nodos(nclientes: int | None, semilla: int, competition: bool) -> Path:
    if competition:
        return COMPETITION
    TMP.mkdir(parents=True, exist_ok=True)
    filas = generar(nclientes, semilla, str(REF))
    ruta = TMP / f"syn_{nclientes}_{semilla}.csv"
    escribir(filas, ruta)
    return ruta


def _extraer_gap(traza: dict):
    if not traza:
        return None
    if "fase2" in traza and isinstance(traza["fase2"], dict):
        return traza["fase2"].get("gap")
    if "compacta" in traza:
        g = _extraer_gap(traza["compacta"])
        if traza.get("completa"):
            g2 = _extraer_gap(traza["completa"])
            return g2 if g2 is not None else g
        return g
    return None


def _preparar(ruta: Path, nveh: int, perfil: str, overrides: dict):
    """Carga nodos, red, instancia y heurística; devuelve (cfg, inst, inicial, t_prep)."""
    extra = {"flota": [{"tipo": "leaf2013", "cantidad": nveh}]}
    extra = _fusionar(extra, overrides)
    if "escala" in extra:
        extra.setdefault("solver", {})["escala"] = extra["escala"]
    cfg = cfgmod.cargar(None, extra, [perfil])

    t0 = time.perf_counter()
    nodos = cargar_nodos(str(ruta))
    red = crear_red(cfg)
    energia_ref = tipos_desde_config(cfg)[0].energia
    try:
        red.preparar(nodos, energia_ref)
    except Exception as exc:  # noqa: BLE001
        if cfg["red"].get("respaldo_linea_recta"):
            red = RedHaversine(cfg["red"]["factor_vial"])
            red.preparar(nodos, energia_ref)
        else:
            raise RuntimeError(f"red fallo: {exc}")

    # Resolver k_vecinos "auto" como en el pipeline, salvo que el override lo fije.
    esc = dict(cfg.get("escala", {}))
    n_cli = sum(n.tipo == "cliente" for n in nodos)
    if esc.get("k_vecinos") == "auto":
        esc["k_vecinos"] = 0 if n_cli <= int(esc.get("umbral_exacto", 25)) else int(esc.get("k_auto", 10))
    cfg = {**cfg, "escala": esc}
    cfg["solver"]["escala"] = esc

    inst = construir(nodos, red, cfg)
    inicial = heuristica.resolver(inst, bool(cfg["solver"].get("usar_todos_vehiculos")))
    return cfg, inst, red, inicial, time.perf_counter() - t0


def _resolver_milp(cfg, inst, inicial, red, limite_milp: float):
    """Corre el MILP con un límite de tiempo dado; devuelve dict de métricas."""
    from evrp.milp_compacto import ModeloCompacto

    cfg_solver = {**cfg["solver"], "escala": cfg["escala"],
                  "tiempo_limite_s": limite_milp}
    t0 = time.perf_counter()
    modelo = ModeloCompacto(inst, cfg_solver, inicial)
    certificado = len(inicial.atendidos) == len(inst.clientes)
    sol_milp, traza = modelo.optimizar(inicial, certificado)
    if sol_milp is None or len(sol_milp.atendidos) < len(inst.clientes):
        from evrp.milp import ModeloMILP
        sol_c, traza_c = ModeloMILP(inst, cfg_solver).optimizar(sol_milp or inicial, False)
        traza = {"compacta": traza, "completa": traza_c}
        if sol_c is not None and (sol_milp is None or (len(sol_c.atendidos), -sol_c.energia) >
                                  (len(sol_milp.atendidos), -sol_milp.energia)):
            sol_milp = sol_c
    t_milp = time.perf_counter() - t0

    sol = sol_milp if sol_milp is not None else inicial
    if sol_milp is not None and (len(inicial.atendidos), -inicial.energia) > \
            (len(sol_milp.atendidos), -sol_milp.energia):
        sol = inicial

    rutas, tipo_de, k = {}, {}, 0
    for dt in inst.tipos:
        propias = sol.rutas.get(dt.tipo.nombre, [])
        for idx in range(dt.tipo.cantidad):
            k += 1
            r = propias[idx] if idx < len(propias) else [inst.ini, inst.fin]
            rutas[str(k)] = [inst.real(v) for v in r]
            tipo_de[str(k)] = dt.tipo.nombre
    val = validar(inst, rutas, tipo_de)
    return {
        "factible": val["factible"], "entregas": val["entregas"],
        "energia_kwh": round(val["energia_total_kwh"], 4),
        "gap": _extraer_gap(traza), "t_milp_s": round(t_milp, 3), "origen": sol.origen,
        "modelo_cols": modelo.h.getNumCol(), "modelo_filas": modelo.h.getNumRow(),
    }, modelo, inst


def _corrida(etiqueta, ruta, nveh, perfil, overrides, total, llm_latencia=0.0,
             modelo_base=None, inst_base=None, extra_info=None):
    """Una corrida completa (prep + MILP) con presupuesto total menos la latencia LLM."""
    cfg, inst, red, inicial, t_prep = _preparar(ruta, nveh, perfil, overrides)
    margen = float(cfg["solver"].get("escala", {}).get("overshoot_margen_s", 3.0))
    min_s = float(cfg["solver"].get("escala", {}).get("min_s", 10.0))
    limite_milp = max(min_s, total - t_prep - llm_latencia - margen)
    met, _, _ = _resolver_milp(cfg, inst, inicial, red, limite_milp)
    fila = {
        "variante": etiqueta, "overrides": overrides,
        "t_prep_s": round(t_prep, 3), "llm_latencia_s": round(llm_latencia, 3),
        "limite_milp_s": round(limite_milp, 3),
        "t_total_s": round(t_prep + llm_latencia + met["t_milp_s"], 3),
        **met,
    }
    if extra_info:
        fila.update(extra_info)
    return fila


def medir_instancia(nclientes, nveh, semilla, perfil, total, cliente, sin_llm, rng):
    """Mide base, haiku, sonnet y aleatorio para una instancia concreta."""
    competition = nclientes is None
    ruta = _nodos(nclientes, semilla, competition)
    etiqueta_inst = "competition" if competition else f"syn{nclientes}"
    filas = []

    # 1) Base + extracción de perfil estructural.
    cfg0, inst0, red0, inicial0, t_prep0 = _preparar(ruta, nveh, perfil, {})
    from evrp.milp_compacto import ModeloCompacto
    cfg_solver0 = {**cfg0["solver"], "escala": cfg0["escala"]}
    modelo0 = ModeloCompacto(inst0, cfg_solver0, inicial0)
    base = _corrida("base", ruta, nveh, perfil, {}, total)
    perf = perfil_desde_modelo(modelo0, inst0, cfg0["solver"]["cargadores_por_arco"],
                               base_gap=base.get("gap"), base_tiempo_s=base.get("t_milp_s"),
                               base_energia_kwh=base.get("energia_kwh"))
    base["instancia"] = etiqueta_inst
    base["clientes"] = perf.clientes
    base["semilla"] = semilla
    filas.append(base)

    propuestas = []  # (etiqueta, overrides, llm_latencia, extra)

    if not sin_llm and cliente is not None:
        from evrp.ia.tuning import llm as llmmod
        for etiqueta, modelo_id in (("haiku", HAIKU), ("sonnet", SONNET)):
            pr = llmmod.proponer(cliente, perf, modelo=modelo_id)
            ov = wl.aplicar_overrides({}, pr.propuesta)
            propuestas.append((etiqueta, ov, pr.latencia_s, {
                "llm_tokens_in": pr.tokens_in, "llm_tokens_out": pr.tokens_out,
                "llm_propuesta": pr.propuesta, "llm_error": pr.error,
            }))

    # Control aleatorio: misma lista blanca, 1 propuesta por corrida (mismo nº de pruebas).
    rnd = wl.muestra_aleatoria(rng)
    propuestas.append(("aleatorio", wl.aplicar_overrides({}, rnd), 0.0,
                       {"propuesta": rnd}))

    for etiqueta, ov, lat, extra in propuestas:
        fila = _corrida(etiqueta, ruta, nveh, perfil, ov, total, llm_latencia=lat,
                        extra_info=extra)
        fila["instancia"] = etiqueta_inst
        fila["clientes"] = perf.clientes
        fila["semilla"] = semilla
        filas.append(fila)

    return filas, perf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clientes", type=int, nargs="*", default=[40, 60])
    ap.add_argument("--competition", action="store_true", help="añade la instancia competition")
    ap.add_argument("--veh", type=int, default=2)
    ap.add_argument("--semillas", type=int, nargs="+", default=[1, 2, 3])
    ap.add_argument("--perfil", default="ev_routing")
    ap.add_argument("--total", type=float, default=55.0)
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--sin-llm", action="store_true", help="omite Bedrock (sólo base vs aleatorio)")
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--perfil-aws", default="hackathon")
    ap.add_argument("--seed", type=int, default=12345, help="semilla del control aleatorio")
    ap.add_argument("--salida", default=None)
    args = ap.parse_args()

    cliente = None
    if not args.sin_llm:
        from evrp.ia.bedrock import ClienteBedrock
        cliente = ClienteBedrock(region=args.region, perfil=args.perfil_aws)

    rng = random.Random(args.seed)
    todas = []
    perfiles = {}
    tareas = list(args.clientes)
    if args.competition:
        tareas.append(None)  # None = competition

    for nclientes in tareas:
        semillas = args.semillas if nclientes is not None else [args.semillas[0]]
        for s in semillas:
            for rep in range(args.reps):
                filas, perf = medir_instancia(nclientes, args.veh, s, args.perfil,
                                              args.total, cliente, args.sin_llm, rng)
                for f in filas:
                    f["rep"] = rep
                    print(json.dumps({k: f[k] for k in ("variante", "instancia", "semilla", "rep",
                          "entregas", "energia_kwh", "gap", "t_milp_s", "t_total_s",
                          "llm_latencia_s")}, ensure_ascii=False), flush=True)
                todas.extend(filas)
                etq = "competition" if nclientes is None else f"syn{nclientes}"
                perfiles[f"{etq}_s{s}"] = perf.a_dict()

    salida = {"config": {"total_s": args.total, "veh": args.veh, "reps": args.reps,
                         "perfil": args.perfil, "sin_llm": args.sin_llm,
                         "haiku": HAIKU, "sonnet": SONNET},
              "perfiles": perfiles, "corridas": todas}
    if args.salida:
        Path(args.salida).parent.mkdir(parents=True, exist_ok=True)
        Path(args.salida).write_text(json.dumps(salida, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n-> {args.salida} ({len(todas)} corridas)")


if __name__ == "__main__":
    main()
