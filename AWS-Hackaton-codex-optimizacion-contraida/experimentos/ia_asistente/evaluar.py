"""Evaluación por modelo del asistente E-VRP: éxito, turnos, tool-calls, latencia,
tiempo hasta el primer token (streaming) y tokens.

Uso (requiere credenciales 'hackathon'):
    $env:AWS_PROFILE='hackathon'
    uv run python -m experimentos.ia_asistente.evaluar
    uv run python -m experimentos.ia_asistente.evaluar --modelos haiku sonnet
    uv run python -m experimentos.ia_asistente.evaluar --subconjunto-opus seguridad fuera_de_dominio

Escribe experimentos/ia_asistente/resultados.json y resumen por consola.
Respeta un presupuesto de tokens global y se detiene si lo supera.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from evrp.ia import ClienteBedrock
from evrp.ia.asistente import Asistente
from evrp.ia.asistente.sesion import NodoSesion, Sesion

from .banco import banco

AQUI = Path(__file__).resolve().parent

MODELOS = {
    "haiku": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "sonnet": "us.anthropic.claude-sonnet-4-6",
    "opus": "us.anthropic.claude-opus-4-5-20251101-v1:0",
}


def _sesion_base() -> Sesion:
    s = Sesion()
    s.nodos = [
        NodoSesion("BASE", "base", 42.27708, -83.76281),
        NodoSesion("V1", "cliente", 42.2768, -83.7312),
        NodoSesion("V2", "cliente", 42.2281, -83.7979),
        NodoSesion("V3", "cliente", 42.3139, -83.8002),
        NodoSesion("C1", "cargador", 42.29, -83.75, conectores="J1772;CHADEMO"),
    ]
    return s


def _enviar_medido(asis: Asistente, mensaje: str, sesion: Sesion) -> tuple[dict, float, float, int]:
    """Envía por streaming y mide latencia total, TTFT y tokens del turno."""
    t0 = time.perf_counter()
    ttft = None
    tokens = 0
    fin = None
    acciones = []
    for ev in asis.enviar_stream(mensaje, sesion):
        if ev["tipo"] == "texto" and ttft is None:
            ttft = time.perf_counter() - t0
        elif ev["tipo"] == "herramienta_inicio" and ttft is None:
            ttft = time.perf_counter() - t0
        elif ev["tipo"] == "fin":
            fin = ev
            tokens = ev.get("tokens", 0)
            acciones = ev.get("acciones", [])
        elif ev["tipo"] == "error":
            fin = {"respuesta": "", "acciones": [], "estado": sesion.resumen_estado(),
                   "resultado": None, "tokens": 0, "error": ev["error"]}
    latencia = time.perf_counter() - t0
    out = fin or {"respuesta": "", "acciones": acciones, "resultado": sesion.ultimo_resultado,
                  "tokens": tokens, "error": "sin_fin"}
    out.setdefault("acciones", acciones)
    return out, latencia, (ttft if ttft is not None else latencia), tokens


def evaluar_modelo(nombre: str, modelo_id: str, casos, perfil: str, region: str,
                   presupuesto_tokens: int, categorias: set[str] | None = None) -> dict:
    cliente = ClienteBedrock(region=region, modelo=modelo_id, perfil=perfil)
    asis = Asistente(cliente=cliente, modelo=modelo_id, perfiles_evrp=["ev_routing"])
    resultados = []
    tokens_modelo = 0
    for caso in casos:
        if categorias and caso.categoria not in categorias:
            continue
        if tokens_modelo >= presupuesto_tokens:
            resultados.append({"caso": caso.nombre, "saltado": "presupuesto_tokens"})
            continue
        s = _sesion_base()
        salidas = []
        lat_total = ttft_turno1 = 0.0
        tool_calls = 0
        error = None
        try:
            for i, msg in enumerate(caso.mensajes):
                out, lat, ttft, tok = _enviar_medido(asis, msg, s)
                salidas.append(out)
                lat_total += lat
                if i == 0:
                    ttft_turno1 = ttft
                tool_calls += len(out.get("acciones", []))
                tokens_modelo += tok
                if out.get("error"):
                    error = out["error"]
        except Exception as exc:  # noqa: BLE001
            error = f"{type(exc).__name__}: {exc}"[:300]
        try:
            exito = bool(caso.exito(s, salidas)) and error is None
        except Exception as exc:  # noqa: BLE001
            exito = False
            error = error or f"verificador: {exc}"[:200]
        resultados.append({
            "caso": caso.nombre, "categoria": caso.categoria,
            "exito": exito, "turnos": len(caso.mensajes),
            "tool_calls": tool_calls,
            "latencia_total_s": round(lat_total, 3),
            "ttft_s": round(ttft_turno1, 3),
            "error": error,
        })
    ok = [r for r in resultados if r.get("exito")]
    evaluados = [r for r in resultados if "saltado" not in r]
    lat = sorted(r["latencia_total_s"] for r in evaluados) or [0.0]
    ttfts = sorted(r["ttft_s"] for r in evaluados) or [0.0]
    return {
        "modelo": modelo_id, "alias": nombre,
        "casos": len(evaluados),
        "exitos": len(ok),
        "exito_frac": round(len(ok) / max(1, len(evaluados)), 3),
        "tool_calls_total": sum(r.get("tool_calls", 0) for r in evaluados),
        "latencia_p50_s": lat[len(lat) // 2],
        "latencia_p95_s": lat[min(len(lat) - 1, int(len(lat) * 0.95))],
        "ttft_p50_s": ttfts[len(ttfts) // 2],
        "ttft_p95_s": ttfts[min(len(ttfts) - 1, int(len(ttfts) * 0.95))],
        "tokens_usados": tokens_modelo,
        "detalle": resultados,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Evaluación por modelo del asistente.")
    p.add_argument("--modelos", nargs="+", default=["haiku", "sonnet"],
                   choices=list(MODELOS))
    p.add_argument("--subconjunto-opus", nargs="*", default=["seguridad", "fuera_de_dominio",
                                                             "fuera_de_rango", "confirmacion"],
                   help="Categorías del banco a usar SOLO para opus.")
    p.add_argument("--region", default="us-east-1")
    p.add_argument("--perfil", default=os.environ.get("AWS_PROFILE", "hackathon"))
    p.add_argument("--presupuesto-tokens", type=int, default=40000,
                   help="Tope de tokens por modelo.")
    p.add_argument("--categorias", nargs="*", default=None,
                   help="Si se da, limita el banco a estas categorías (todos los modelos).")
    p.add_argument("--salida", default=str(AQUI / "resultados.json"))
    args = p.parse_args(argv)

    casos = banco()
    salida = {"region": args.region, "n_casos": len(casos), "modelos": []}
    for alias in args.modelos:
        modelo_id = MODELOS[alias]
        if args.categorias:
            cats = set(args.categorias)
        elif alias == "opus" and args.subconjunto_opus:
            cats = set(args.subconjunto_opus)
        else:
            cats = None
        print(f"== {alias} ({modelo_id}) "
              f"{'[subconjunto: ' + ','.join(sorted(cats)) + ']' if cats else ''} ==")
        try:
            res = evaluar_modelo(alias, modelo_id, casos, args.perfil, args.region,
                                 args.presupuesto_tokens, cats)
        except Exception as exc:  # noqa: BLE001
            print(f"  modelo no disponible: {exc}")
            salida["modelos"].append({"alias": alias, "modelo": modelo_id,
                                      "disponible": False, "error": str(exc)[:300]})
            continue
        res["disponible"] = True
        salida["modelos"].append(res)
        print(f"  éxito {res['exitos']}/{res['casos']} ({res['exito_frac']:.0%}), "
              f"tool_calls={res['tool_calls_total']}, "
              f"lat_p50={res['latencia_p50_s']}s, ttft_p50={res['ttft_p50_s']}s, "
              f"tokens={res['tokens_usados']}")

    Path(args.salida).write_text(json.dumps(salida, indent=2, ensure_ascii=False),
                                 encoding="utf-8")
    print(f"\nEscrito: {args.salida}")
    total = sum(m.get("tokens_usados", 0) for m in salida["modelos"])
    print(f"Tokens totales: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
