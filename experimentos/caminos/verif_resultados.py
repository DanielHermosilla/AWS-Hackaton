from evrp.pipeline import ejecutar
from evrp import config

base = {"red": {"osm_permitir_descarga": False}, "solver": {"tiempo_limite_s": 30}}
for arch in ["data/competition_routing_nodes.csv", "data/evaluation_routing_nodes.csv"]:
    for perfil in ["eved", "ev_routing"]:
        def run(alg):
            cfg = config.cargar(None, {"red": {"osm_permitir_descarga": False,
                                               "algoritmo_caminos": alg},
                                       "solver": {"tiempo_limite_s": 30}}, [perfil])
            return ejecutar(arch, cfg, None)["kpis"]
        a = run("multi_destino")
        b = run("scipy")
        nombre = arch.split("/")[-1]
        igual = (a["entregas"] == b["entregas"]
                 and abs(a["energia_total_kwh"] - b["energia_total_kwh"]) < 1e-9
                 and abs(a["km_total"] - b["km_total"]) < 1e-9)
        print(f"{nombre:35s} {perfil:10s} IGUAL={igual} "
              f"entregas {a['entregas']}/{b['entregas']} "
              f"energia {a['energia_total_kwh']}/{b['energia_total_kwh']} "
              f"km {a['km_total']}/{b['km_total']}")
