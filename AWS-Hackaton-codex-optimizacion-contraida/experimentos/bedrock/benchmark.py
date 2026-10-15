"""Benchmark de modelos Anthropic en Amazon Bedrock (región us-east-1).

Para cada modelo/perfil invocable ejecuta 4 tareas × 3 repeticiones:
  (a) ping   -> "Responde solo OK"
  (b) json   -> extraer {nombre, direccion, lat, lon} de un pedido de reparto
  (c) tool   -> forzar la herramienta 'resolver_rutas' con argumentos correctos
  (d) imagen -> leer direcciones de un PNG generado localmente (png_texto.py)

Mide latencia p50/p95, tokens in/out, éxito/formato válido y errores. Respeta un
presupuesto total aproximado de tokens (`--presupuesto`, por defecto 60000) y se
detiene antes de excederlo. Guarda `resultados.json` en esta carpeta.

Uso:
    uv run python -m experimentos.bedrock.benchmark --perfil hackathon
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

# Permite ejecutar como script suelto o como módulo.
AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
from png_texto import png_con_texto  # noqa: E402

from evrp.ia import ClienteBedrock, ModeloNoDisponible, extraer_json  # noqa: E402

# Candidatos: ids directos y perfiles us./global. El benchmark descubre cuáles
# son invocables (ValidationException/AccessDenied => no disponible).
CANDIDATOS: list[str] = [
    "us.anthropic.claude-sonnet-4-6",
    "global.anthropic.claude-sonnet-4-6",
    "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "us.anthropic.claude-opus-4-5-20251101-v1:0",
    "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "us.anthropic.claude-opus-4-1-20250805-v1:0",
    "us.anthropic.claude-3-haiku-20240307-v1:0",
    "us.anthropic.claude-3-sonnet-20240229-v1:0",
]

PEDIDO = ("Pedido #42 para Ana Pérez. Entregar en Av. Libertad 1234, Ciudad Verde. "
          "Coordenadas aproximadas: latitud -33.45, longitud -70.66.")

TOOL_RESOLVER = {
    "toolSpec": {
        "name": "resolver_rutas",
        "description": "Reoptimiza las rutas E-VRP agregando o quitando nodos del escenario.",
        "inputSchema": {"json": {
            "type": "object",
            "properties": {
                "agregar_cliente": {"type": "string", "description": "id de cliente a agregar, p.ej. V21"},
                "quitar_cargador": {"type": "string", "description": "id de cargador a quitar, p.ej. C6"},
            },
            "required": ["agregar_cliente", "quitar_cargador"],
        }},
    }
}

PEDIDO_TOOL = ("Reoptimiza el plan de reparto: agrega el cliente V21 y quita el cargador C6. "
               "Llama a la herramienta resolver_rutas con esos argumentos.")

IMG = png_con_texto(["PEDIDO 42", "AV LIBERTAD 1234", "CIUDAD VERDE", "LAT -33.45 LON -70.66"])


def _ok_json(obj) -> bool:
    return isinstance(obj, dict) and {"nombre", "direccion", "lat", "lon"} <= set(obj)


def _ok_tool(args) -> bool:
    return (isinstance(args, dict)
            and str(args.get("agregar_cliente", "")).upper().replace(" ", "") == "V21"
            and str(args.get("quitar_cargador", "")).upper().replace(" ", "") == "C6")


def _ok_imagen(texto: str) -> bool:
    t = (texto or "").upper()
    return "LIBERTAD" in t and "1234" in t


def _pXX(valores: list[float], q: float) -> float:
    if not valores:
        return 0.0
    s = sorted(valores)
    k = max(0, min(len(s) - 1, int(round(q * (len(s) - 1)))))
    return round(s[k], 3)


def _tarea(nombre: str, fn, reps: int) -> dict:
    lat, tin, tout, exitos, errores = [], [], [], 0, []
    for _ in range(reps):
        try:
            ok, resp = fn()
            lat.append(resp.latencia_s)
            tin.append(resp.tokens_entrada)
            tout.append(resp.tokens_salida)
            exitos += int(bool(ok))
        except ModeloNoDisponible as exc:
            errores.append(exc.codigo or "ModeloNoDisponible")
        except Exception as exc:  # noqa: BLE001
            errores.append(type(exc).__name__)
    return {
        "tarea": nombre,
        "reps": reps,
        "exitos": exitos,
        "exito_frac": round(exitos / reps, 3) if reps else 0.0,
        "latencia_p50_s": _pXX(lat, 0.5),
        "latencia_p95_s": _pXX(lat, 0.95),
        "tokens_in": sum(tin),
        "tokens_out": sum(tout),
        "errores": errores,
    }


def evaluar_modelo(modelo: str, perfil: str, region: str, reps: int) -> dict:
    c = ClienteBedrock(region=region, modelo=modelo, perfil=perfil)

    def ping():
        r = c.preguntar("Responde solo con OK.", max_tokens=10)
        return ("OK" in r.texto.upper()), r

    def json_tarea():
        sistema = "Eres un extractor de datos de pedidos de reparto."
        obj, r = c.preguntar_json(
            f"Extrae {{nombre, direccion, lat, lon}} de este pedido:\n{PEDIDO}",
            sistema=sistema, max_tokens=200)
        return _ok_json(obj), r

    def tool_tarea():
        args, r = c.usar_herramienta(PEDIDO_TOOL, TOOL_RESOLVER, max_tokens=200)
        return _ok_tool(args), r

    def imagen_tarea():
        r = c.preguntar("Lee y transcribe en texto todas las líneas de direcciones de la imagen.",
                        imagenes=[IMG], max_tokens=200)
        return _ok_imagen(r.texto), r

    tareas = [("ping", ping), ("json", json_tarea), ("tool", tool_tarea), ("imagen", imagen_tarea)]
    resultados, disponible, tokens = [], True, 0
    for nombre, fn in tareas:
        res = _tarea(nombre, fn, reps)
        resultados.append(res)
        tokens += res["tokens_in"] + res["tokens_out"]
        # Si la primera tarea (ping) solo da errores de disponibilidad, marca no disponible.
        if nombre == "ping" and res["exitos"] == 0 and res["errores"]:
            cods = set(res["errores"])
            if cods <= {"AccessDeniedException", "ValidationException", "ResourceNotFoundException"}:
                disponible = False
                break
    return {"modelo": modelo, "disponible": disponible, "tokens_usados": tokens,
            "tareas": resultados}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--perfil", default="hackathon")
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--presupuesto", type=int, default=60000, help="tope aprox. de tokens totales")
    ap.add_argument("--salida", default=str(AQUI / "resultados.json"))
    args = ap.parse_args()

    inicio = time.time()
    salida = {"region": args.region, "reps": args.reps, "presupuesto_tokens": args.presupuesto,
              "candidatos": CANDIDATOS, "modelos": []}
    total_tokens = 0
    for modelo in CANDIDATOS:
        if total_tokens >= args.presupuesto:
            salida["detenido_por_presupuesto"] = True
            break
        print(f"[bench] evaluando {modelo} ...", flush=True)
        res = evaluar_modelo(modelo, args.perfil, args.region, args.reps)
        total_tokens += res["tokens_usados"]
        res["tokens_acumulados"] = total_tokens
        salida["modelos"].append(res)
        print(f"        disponible={res['disponible']} tokens_usados={res['tokens_usados']} "
              f"acumulado={total_tokens}", flush=True)

    salida["tokens_totales"] = total_tokens
    salida["segundos_totales"] = round(time.time() - inicio, 1)
    Path(args.salida).write_text(json.dumps(salida, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[bench] escrito {args.salida} ({total_tokens} tokens, {salida['segundos_totales']}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
