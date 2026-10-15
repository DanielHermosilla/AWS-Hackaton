import json
from evrp.ia.contexto import calibrar_por_temperatura, guardar_calibracion

cal = calibrar_por_temperatura("data/eVED_EV.csv")
guardar_calibracion(cal, "experimentos/ia_contexto/calibracion_temp.json")
print(json.dumps(cal.a_dict(), indent=2, ensure_ascii=False))
