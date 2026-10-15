"""Orquestador de la arena: materializa instancias, corre motores, revalida de forma
neutral, corre la competencia de solvers y escribe resultados.
"""
from __future__ import annotations

import json
import tracemalloc
from pathlib import Path

from arena import instancias as inst_mod
from arena import reporte, solvers
from arena.adaptadores import evrp_adaptador, ev_routing_adaptador
from arena.supuestos import resolver as resolver_supuestos
from arena.validador_neutral import Supuestos, ValidadorNeutral

ADAPTADORES = {"evrp": evrp_adaptador, "ev_routing": ev_routing_adaptador}


def cargar_escenario(ruta: str | Path) -> dict:
    return json.loads(Path(ruta).read_text(encoding="utf-8"))


def _combos_flota(esc: dict) -> list[int]:
    if esc.get("flota_barrido"):
        return [int(v) for v in esc["flota_barrido"]]
    return [int(esc.get("flota", {}).get("vehiculos", 2))]


def correr(ruta_escenario: str | Path, out_dir: str | Path) -> dict:
    esc = cargar_escenario(ruta_escenario)
    sup = resolver_supuestos(esc)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cache_csv = out / "instancias"
    osm_cache = str((inst_mod.CACHE / "osm").resolve())
    grafo = str(inst_mod.grafo_osm_descomprimido()) if sup.red == "osm" else None

    presupuesto = float(esc.get("presupuesto_s", 60))
    hilos = int(esc.get("hilos", 1))
    reps = int(esc.get("repeticiones", 1))
    motores = esc.get("motores", ["evrp"])
    solvers_cfg = esc.get("solvers", [])
    opciones = esc.get("opciones_motor", {})

    filas_motor: list[dict] = []
    filas_solver: list[dict] = []
    crudo: list[dict] = []

    for inst_desc in esc["instancias"]:
        csv_path = str(inst_mod.materializar(inst_desc, cache_csv))
        validador = _validador(csv_path, sup, grafo, osm_cache)
        for vehiculos in _combos_flota(esc):
            for motor in motores:
                for rep in range(reps):
                    fila = _correr_motor(motor, csv_path, sup, vehiculos, presupuesto,
                                         hilos, opciones.get(motor), osm_cache, validador,
                                         inst_desc["nombre"], rep)
                    filas_motor.append(fila)
                    crudo.append({"tipo": "motor", **fila})
        # Competencia de solvers (una vez por instancia, con la flota base).
        if solvers_cfg:
            veh_base = _combos_flota(esc)[0]
            for fase in ("entregas", "energia"):
                comp = _correr_solvers(csv_path, sup, veh_base, osm_cache, solvers_cfg,
                                       presupuesto, hilos, inst_desc["nombre"], fase)
                filas_solver.extend(comp)
                crudo.extend({"tipo": "solver", **c} for c in comp)

    nombre = esc.get("nombre", "arena")
    reporte.escribir_jsonl(crudo, out / "resultados.jsonl")
    reporte.escribir_csv(filas_motor, out / "tabla_motores.csv")
    reporte.escribir_markdown(nombre, filas_motor, filas_solver, out / "reporte.md")
    return {"motores": filas_motor, "solvers": filas_solver, "out": str(out)}


def _validador(csv_path, sup, grafo, osm_cache) -> ValidadorNeutral:
    vsup = Supuestos(bateria_kwh=sup.bateria_kwh, reserva_kwh=sup.reserva_kwh,
                     soc_inicial=sup.soc_inicial, consumo_kwh_km=sup.consumo_kwh_km,
                     conectores=set(sup.conectores), pendiente=sup.pendiente)
    return ValidadorNeutral(csv_path, vsup, red=sup.red, grafo=grafo, osm_cache=osm_cache)


def _correr_motor(motor, csv_path, sup, vehiculos, presupuesto, hilos, opciones_motor,
                  osm_cache, validador, nombre_inst, rep) -> dict:
    adaptador = ADAPTADORES[motor]
    tracemalloc.start()
    res = adaptador.resolver(csv_path, sup, vehiculos, presupuesto, hilos,
                             opciones_motor, osm_cache)
    _, pico = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    fila = {
        "motor": motor, "solver": res.get("detalles", {}).get("solver") if res.get("detalles") else res.get("solver"),
        "instancia": nombre_inst, "vehiculos": vehiculos, "rep": rep,
        "entregas": res.get("entregas"), "clientes": validador.clientes and len(validador.clientes),
        "energia_validada_kwh": None, "km": None,
        "tiempo_total_s": res.get("tiempo_s"), "tiempo_solver_s": res.get("tiempo_solver_s"),
        "gap": res.get("gap"), "estado": res.get("estado"),
        "factible_neutral": None, "mem_pico_mb": round(pico / 1e6, 1),
        "movement_limit": res.get("movement_limit"),
    }
    # Revalidacion neutral.
    val = _revalidar(validador, res)
    if val is not None:
        fila["energia_validada_kwh"] = val.energia_total_kwh
        fila["km"] = val.km_total
        fila["clientes"] = val.clientes
        fila["entregas"] = val.entregas
        fila["factible_neutral"] = val.factible
        fila["errores_neutral"] = val.errores[:5]
    else:
        fila["factible_neutral"] = False if res.get("estado") not in ("ok", "infactible") else None
    return fila


def _revalidar(validador, res):
    rutas = res.get("rutas")
    if not rutas:
        return None
    try:
        if res.get("tipo_rutas") == "calle":
            tramos = res.get("tramos_por_paso", {})
            entrada = {veh: {"nodos": nodos, "tramos_por_paso": tramos.get(veh, [])}
                       for veh, nodos in rutas.items()}
            return validador.validar_calle(entrada)
        return validador.validar_clave(rutas)
    except Exception as exc:  # noqa: BLE001
        return _ResultadoError(str(exc))


class _ResultadoError:
    def __init__(self, msg):
        self.energia_total_kwh = None
        self.km_total = None
        self.clientes = None
        self.entregas = None
        self.factible = False
        self.errores = [f"validador neutral fallo: {msg[:200]}"]
        self.no_atendidos = []


def _correr_solvers(csv_path, sup, vehiculos, osm_cache, solvers_cfg, presupuesto, hilos,
                    nombre_inst, fase) -> list[dict]:
    mps = Path(osm_cache).parent / "mps" / f"{nombre_inst}_{fase}.mps"
    try:
        meta = solvers.construir_mps_evrp(csv_path, sup, vehiculos, osm_cache, mps, fase)
    except Exception as exc:  # noqa: BLE001
        return [{"instancia": nombre_inst, "fase": fase, "solver": s, "estado": "error_mps",
                 "error": str(exc)[:300]} for s in solvers_cfg]
    salidas = solvers.competir(str(mps), solvers_cfg, presupuesto, hilos)
    for s in salidas:
        s["instancia"] = nombre_inst
        s["fase"] = fase
        s["columnas"] = meta["columnas"]
        s["filas"] = meta["filas"]
    return salidas
