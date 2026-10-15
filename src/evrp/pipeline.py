"""Orquestación de pasos: datos → red → instancia → inicial → solver → validación → salidas."""
from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from . import heuristica
from .asesor import crear_asesor
from .config import fusionar, validar as validar_cfg
from .datos import cargar_nodos
from .instancia import construir
from .red import RedHaversine, crear_red
from .validador import validar

log = logging.getLogger(__name__)


class Bitacora:
    def __init__(self):
        self.t0 = time.perf_counter()
        self.eventos: list[dict] = []

    def paso(self, nombre: str, **datos):
        ev = {"paso": nombre, "t_s": round(time.perf_counter() - self.t0, 3), **datos}
        self.eventos.append(ev)
        log.info("%s %s", nombre, datos)


def _rutas_por_vehiculo(inst, sol) -> tuple[dict[str, list[str]], dict[str, str]]:
    rutas, tipo_de, k = {}, {}, 0
    for dt in inst.tipos:
        propias = sol.rutas.get(dt.tipo.nombre, [])
        for idx in range(dt.tipo.cantidad):
            k += 1
            veh = str(k)
            r = propias[idx] if idx < len(propias) else [inst.ini, inst.fin]
            rutas[veh] = [inst.real(v) for v in r]
            tipo_de[veh] = dt.tipo.nombre
    return rutas, tipo_de


def _verificar_compatibilidad(preparada, energia) -> None:
    """Los caminos se eligieron con un modelo de energía; resolver con otro distinto en
    pendiente/eficiencias haría que los caminos ya no sean los de mínima energía."""
    e = preparada.energia_caminos
    if bool(e.get("usar_pendiente")) != bool(energia.usar_pendiente):
        raise ValueError("La instancia se preparó con pipeline.energia="
                         f"{'pendiente' if e.get('usar_pendiente') else 'plano'}; use la misma al resolver "
                         "o vuelva a preparar")
    if energia.usar_pendiente:
        for k in ("eta_traccion", "eta_regeneracion", "masa_kg"):
            if abs(float(e[k]) - float(getattr(energia, k))) > 1e-9:
                raise ValueError(f"{k} distinto al de la preparación; vuelva a preparar")
    # Con terreno plano el camino de mínima energía es el de menor km para cualquier consumo:
    # cambiar consumo_kwh_km al resolver es válido.


def ejecutar(ruta_nodos: str | None, cfg: dict, salida: str | Path | None = "results",
             preparada=None, excluir: list[str] | None = None) -> dict:
    """Pipeline completo. Si `preparada` (InstanciaPreparada) viene dada, se omite la etapa de
    red (preprocesamiento) y solo se resuelve. `excluir`: ids de nodos a ignorar (p.ej. un
    cargador fuera de servicio o un cliente cancelado) sin volver a preparar."""
    bit = Bitacora()
    asesor = crear_asesor(cfg)
    if preparada is not None:
        nodos = list(preparada.nodos)
        bit.paso("datos", nodos=len(nodos), archivo=preparada.origen.get("archivo"), preparada=True)
    else:
        nodos = cargar_nodos(ruta_nodos)
        bit.paso("datos", nodos=len(nodos), archivo=str(ruta_nodos))
    if excluir:
        quitar = set(excluir)
        if any(n.tipo == "base" and n.id in quitar for n in nodos):
            raise ValueError("No se puede excluir la base")
        nodos = [n for n in nodos if n.id not in quitar]
        bit.paso("excluir", nodos=sorted(quitar))

    if cfg["asesor"].get("sugerir_config"):
        resumen = {"clientes": sum(n.tipo == "cliente" for n in nodos),
                   "cargadores": sum(n.tipo == "cargador" for n in nodos),
                   "vehiculos": sum(g["cantidad"] for g in cfg["flota"])}
        ajustes = asesor.sugerir_config(resumen, cfg)
        if ajustes:
            cfg = validar_cfg(fusionar(cfg, ajustes))
        bit.paso("asesor_config", ajustes=ajustes)

    from .instancia import tipos_desde_config
    energia_ref = tipos_desde_config(cfg)[0].energia
    if preparada is not None:
        _verificar_compatibilidad(preparada, energia_ref)
        red = preparada.a_red()
        red.preparar(nodos, energia_ref)
        bit.paso("red", tipo=red.nombre, preparada=True, tiempos_preparacion=preparada.red.get("tiempos"))
    else:
        red = crear_red(cfg)
        try:
            red.preparar(nodos, energia_ref)
        except Exception as exc:
            if cfg["pipeline"]["red"] == "osm" and cfg["red"].get("respaldo_linea_recta"):
                log.warning("Red OSM no disponible (%s); se usa haversine", exc)
                bit.paso("red_respaldo", motivo=str(exc)[:200])
                red = RedHaversine(cfg["red"]["factor_vial"])
                red.preparar(nodos, energia_ref)
            else:
                raise
        bit.paso("red", tipo=red.nombre, tiempos=getattr(red, "tiempos", None))

    # Escala: k-vecinos "auto" = exacto (0) hasta umbral_exacto clientes; si no, k_auto.
    esc = dict(cfg.get("escala", {}))
    n_cli = sum(n.tipo == "cliente" for n in nodos)
    if esc.get("k_vecinos") == "auto":
        esc["k_vecinos"] = 0 if n_cli <= int(esc.get("umbral_exacto", 25)) else int(esc.get("k_auto", 10))
    cfg = {**cfg, "escala": esc}

    inst = construir(nodos, red, cfg)
    for dt in inst.tipos:
        bit.paso("instancia", tipo=dt.tipo.nombre, cargadores=len(dt.F), arcos=len(dt.arcos),
                 incompatibles=dt.descartados_compat, podados=len(dt.podados))

    inicial = None
    if cfg["pipeline"]["inicial"] == "insercion" or cfg["pipeline"]["solver"] == "heuristica":
        inicial = heuristica.resolver(inst, bool(cfg["solver"].get("usar_todos_vehiculos")))
        bit.paso("inicial", atendidos=len(inicial.atendidos), energia=round(inicial.energia, 4))

    sol, traza = inicial, {}
    if cfg["pipeline"]["solver"] == "milp":
        certificado = inicial is not None and len(inicial.atendidos) == len(inst.clientes)
        # Presupuesto: si hay presupuesto_total_s, el MILP recibe lo que queda del reloj total.
        cfg_solver = {**cfg["solver"], "escala": cfg["escala"]}
        total = cfg["solver"].get("presupuesto_total_s")
        if total:
            restante = float(total) - (time.perf_counter() - bit.t0) - float(cfg["escala"].get("overshoot_margen_s", 2.0))
            cfg_solver["tiempo_limite_s"] = max(float(cfg["escala"].get("min_s", 1.0)),
                                                min(float(cfg["solver"]["tiempo_limite_s"]), restante))
        bit.paso("presupuesto", milp_s=round(cfg_solver["tiempo_limite_s"], 2))
        if cfg["solver"].get("formulacion", "compacta") == "compacta":
            from .milp_compacto import ModeloCompacto  # importa highspy solo si se usa

            modelo = ModeloCompacto(inst, cfg_solver, inicial)
        else:
            from .milp import ModeloMILP

            modelo = ModeloMILP(inst, cfg_solver)
        sol_milp, traza = modelo.optimizar(inicial, certificado)
        # La formulación compacta no encadena cargadores (F→F). Si deja clientes sin
        # atender, se intenta la completa con el mismo presupuesto y se queda la mejor.
        if (cfg["solver"].get("formulacion", "compacta") == "compacta"
                and (sol_milp is None or len(sol_milp.atendidos) < len(inst.clientes))):
            from .milp import ModeloMILP

            sol_c, traza_c = ModeloMILP(inst, cfg_solver).optimizar(sol_milp or inicial, False)
            traza = {"compacta": traza, "completa": traza_c}
            if sol_c is not None and (sol_milp is None or (len(sol_c.atendidos), -sol_c.energia) >
                                      (len(sol_milp.atendidos), -sol_milp.energia)):
                sol_milp = sol_c
        bit.paso("milp", **{k: v for k, v in traza.items()})
        if sol_milp is not None:
            def clave(s):  # (cumple flota completa si se exige, entregas, −energía)
                usados = sum(len(r) for r in s.rutas.values())
                todos = sum(dt.tipo.cantidad for dt in inst.tipos)
                cumple = not cfg["solver"].get("usar_todos_vehiculos") or usados >= min(todos, len(inst.clientes))
                return (cumple, len(s.atendidos), -s.energia)

            mejor_inicial = inicial is not None and clave(inicial) > clave(sol_milp)
            sol = inicial if mejor_inicial else sol_milp
    if sol is None:
        raise RuntimeError("No se encontró ninguna solución (ni heurística ni MILP)")

    rutas, tipo_de = _rutas_por_vehiculo(inst, sol)
    val = validar(inst, rutas, tipo_de)
    bit.paso("validacion", factible=val["factible"], errores=val["errores"])
    t_total = round(time.perf_counter() - bit.t0, 3)

    kpis = {
        "factible": val["factible"],
        "todas_entregadas": val["factible"] and not val["no_atendidos"],
        "entregas": val["entregas"],
        "clientes": val["clientes"],
        "no_atendidos": val["no_atendidos"],
        "energia_total_kwh": round(val["energia_total_kwh"], 4),
        "energia_efectiva_kwh": round(val["energia_efectiva_kwh"], 4),
        "km_total": round(sum(r.km for r in val["reportes"]), 3),
        "por_vehiculo": {r.vehiculo: {"tipo": r.tipo, "energia_kwh": round(r.energia_kwh, 4),
                                      "km": round(r.km, 3), "bateria_min_kwh": round(r.bateria_min_kwh, 4),
                                      "bateria_final_kwh": round(r.bateria_final_kwh, 4),
                                      "recargas": sum(p["tipo"] == "cargador" for p in r.paradas),
                                      "vuelve_a_base": bool(r.nodos) and r.nodos[-1] == inst.base}
                         for r in val["reportes"]},
        "origen_solucion": sol.origen,
        "red": {"tipo": red.nombre, "vial": red.nombre == "osm",
                "grafo": getattr(red, "origen_grafo", None)},
        "solver": traza,
        "tiempo_computo_s": t_total,
    }
    filas = {n.id: n.fila for n in nodos}
    resultado = {
        "rutas": rutas,
        "rutas_indices": {k: [filas[v] for v in r] for k, r in rutas.items()},
        "kpis": kpis,
        "detalle": {r.vehiculo: r.paradas for r in val["reportes"]},
        "bitacora": bit.eventos,
    }

    if cfg["asesor"].get("explicar") and asesor.nombre != "ninguno":
        t_ase = time.perf_counter()
        texto = asesor.explicar({"rutas": rutas, "kpis": kpis})
        resultado["explicacion"] = texto
        kpis["tiempo_asesor_s"] = round(time.perf_counter() - t_ase, 3)

    if salida:
        _escribir(Path(salida), resultado, inst, cfg)
    return resultado


def _escribir(out: Path, res: dict, inst, cfg: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    escribir = lambda nombre, obj: (out / nombre).write_text(
        json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
    escribir("routes.json", res["rutas"])
    escribir("routes_idx.json", res["rutas_indices"])
    escribir("kpis.json", res["kpis"])
    escribir("detalle.json", res["detalle"])
    with open(out / "ledger.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"fecha": datetime.now(timezone.utc).isoformat(), "pipeline": cfg["pipeline"],
                            "kpis": {k: v for k, v in res["kpis"].items() if k != "por_vehiculo"},
                            "eventos": res["bitacora"]}, ensure_ascii=False) + "\n")
    if res.get("explicacion"):
        (out / "explicacion.md").write_text(res["explicacion"], encoding="utf-8")
