"""Evaluación Idea C: explicación de rutas.

Genera resultados reales con `evrp.resolver` en varios escenarios:
  - competition / evaluation (datos oficiales),
  - sintéticas de 40 clientes con 2–3 vehículos,
  - casos con clientes NO atendidos (batería pequeña).

Mide, para la plantilla determinista y (opcional) el LLM:
  - fidelidad: fracción de explicaciones que pasan el verificador anti-alucinación,
  - longitud (caracteres y palabras), latencia, tokens,
  - rúbrica de cobertura: ¿menciona entregas, energía, recargas+por qué, batería
    mínima, pendientes?

Uso:
  uv run python experimentos/ia_explicacion/evaluar.py            # solo plantilla (sin red)
  $env:AWS_PROFILE='hackathon'; uv run python experimentos/ia_explicacion/evaluar.py --llm <modelo>
"""
from __future__ import annotations

import argparse
import json
import re
import tempfile
import time
from pathlib import Path

import evrp
from evrp.ia.explicacion import explicar, extraer_hechos, verificar_texto
from evrp import sintetico

SALIDA = Path("experimentos/ia_explicacion/evaluacion.json")


def _bateria_pequena(b_util: float) -> dict:
    """Config que fuerza clientes sin atender: batería útil muy pequeña, 1 vehículo."""
    return {"pipeline": {"red": "haversine"},
            "tipos_vehiculo": {"leaf2013": {"bateria_kwh": b_util, "soc_inicial": 0.6,
                                            "reserva_kwh": 0.2}},
            "flota": [{"tipo": "leaf2013", "cantidad": 1}]}


def _escenarios(tmp: Path) -> list[dict]:
    esc = [
        {"nombre": "competition", "nodos": "data/competition_routing_nodes.csv",
         "config": {"pipeline": {"red": "haversine"}}, "perfiles": ["eved"]},
        {"nombre": "evaluation", "nodos": "data/evaluation_routing_nodes.csv",
         "config": {"pipeline": {"red": "haversine"}}, "perfiles": ["eved"]},
    ]
    # Sintéticas de 40 clientes con 2 y 3 vehículos.
    for nv, sem in ((2, 1), (3, 2)):
        ruta = tmp / f"sint40_s{sem}.csv"
        sintetico.escribir(
            sintetico.generar(40, semilla=sem, referencia="data/competition_routing_nodes.csv"),
            ruta)
        esc.append({"nombre": f"sintetica40_v{nv}", "nodos": str(ruta),
                    "config": {"pipeline": {"red": "haversine"},
                               "flota": [{"tipo": "leaf2013", "cantidad": nv}],
                               "solver": {"tiempo_limite_s": 30}},
                    "perfiles": ["eved"]})
    # Casos con no atendidos (batería pequeña) sobre competición.
    for b in (1.0, 1.5):
        esc.append({"nombre": f"no_atendidos_B{b:.1f}", "nodos": "data/competition_routing_nodes.csv",
                    "config": _bateria_pequena(b), "perfiles": ["eved"]})
    return esc


def _cobertura(texto: str, kpis: dict) -> dict:
    t = texto.lower()
    tiene_recargas = any(d.get("recargas", 0) for d in (kpis.get("por_vehiculo") or {}).values())
    hay_pendientes = bool(kpis.get("no_atendidos"))
    cob = {
        "entregas": bool(re.search(r"entrega|clientes? atendidos|atendid", t)),
        "energia": "kwh" in t or "energ" in t,
        "recargas_y_porque": bool((("recarg" in t or re.search(r"\bc\d", texto)) and
                              ("para" in t or "porque" in t or "evitar" in t or "no agotar" in t))
                             if tiene_recargas else True),
        "bateria_minima": "mínim" in t or "minimo" in t or "margen" in t or "reserva" in t,
        "pendientes": bool(("pendiente" in t or "sin atender" in t or "no atendid" in t)
                      if hay_pendientes else True),
    }
    cob["puntaje"] = round(sum(cob.values()) / 5, 2)
    return cob


def evaluar(modelo: str | None = None):
    cliente = None
    if modelo:
        from evrp.ia import ClienteBedrock
        cliente = ClienteBedrock(region="us-east-1", modelo=modelo)

    filas = []
    tokens_tot = 0
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for e in _escenarios(tmp):
            r = evrp.resolver(e["nodos"], e["config"], e["perfiles"], salida=None)
            hechos = extraer_hechos(r)
            for estilo in ("operador", "gerencia"):
                t0 = time.perf_counter()
                out = explicar(r, estilo, cliente=cliente)
                dt = time.perf_counter() - t0
                ver = verificar_texto(out["texto"], hechos)
                cob = _cobertura(out["texto"], r.kpis)
                tokens_tot += out["uso"]["tokens_total"]
                filas.append({
                    "escenario": e["nombre"], "estilo": estilo,
                    "entregas": r.kpis["entregas"], "clientes": r.kpis["clientes"],
                    "no_atendidos": len(r.kpis.get("no_atendidos") or []),
                    "origen": out["uso"]["origen"], "intentos": out["uso"]["intentos"],
                    "fiel": ver.ok, "errores_verif": ver.errores,
                    "chars": len(out["texto"]), "palabras": len(out["texto"].split()),
                    "latencia_s": round(out["uso"]["latencia_s"] or dt, 3),
                    "tokens_total": out["uso"]["tokens_total"],
                    "cobertura": cob,
                    "hechos_citados": len(out["hechos_citados"]),
                })

    n = len(filas)
    fieles = sum(f["fiel"] for f in filas)
    resumen = {
        "modelo": modelo, "n_explicaciones": n,
        "tasa_fidelidad": round(fieles / n, 3),
        "chars_medio": round(sum(f["chars"] for f in filas) / n, 1),
        "palabras_medio": round(sum(f["palabras"] for f in filas) / n, 1),
        "latencia_media_s": round(sum(f["latencia_s"] for f in filas) / n, 3),
        "tokens_totales": tokens_tot,
        "cobertura_media": round(sum(f["cobertura"]["puntaje"] for f in filas) / n, 3),
        "origen_llm": sum(f["origen"] == "llm" for f in filas),
        "origen_plantilla": sum(f["origen"] == "plantilla" for f in filas),
    }
    salida = {"resumen": resumen, "filas": filas}
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps(salida, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(resumen, indent=2, ensure_ascii=False))
    return salida


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", dest="modelo", default=None, help="modelId de Bedrock")
    args = ap.parse_args()
    evaluar(args.modelo)
