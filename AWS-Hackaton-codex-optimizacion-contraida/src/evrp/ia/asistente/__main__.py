"""REPL de prueba del asistente con streaming en consola.

Uso:
    uv run python -m evrp.ia.asistente
    $env:AWS_PROFILE='<perfil>'; uv run python -m evrp.ia.asistente --modelo us.anthropic.claude-haiku-4-5-20251001-v1:0

Comandos: /estado, /reset, /salir. El resto se envía al asistente y se imprime
el texto token a token (streaming), marcando las herramientas usadas.
"""
from __future__ import annotations

import argparse
import os
import sys

from .asistente import Asistente
from .sesion import Sesion


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="REPL del asistente E-VRP (streaming).")
    p.add_argument("--modelo", default=os.environ.get(
        "EVRP_BEDROCK_MODELO", "us.anthropic.claude-sonnet-4-6"))
    p.add_argument("--region", default=None,
                   help="Región AWS (por defecto EVRP_AWS_REGION / AWS_REGION / us-east-1).")
    p.add_argument("--perfil", default=os.environ.get("AWS_PROFILE"),
                   help="Perfil AWS; sin él se usa la cadena estándar de credenciales.")
    p.add_argument("--instancia", default=None, help="CSV a cargar al iniciar (operador local).")
    args = p.parse_args(argv)

    try:
        asis = Asistente(region=args.region, modelo=args.modelo, perfil=args.perfil)
    except Exception as exc:  # noqa: BLE001
        print(f"No se pudo crear el asistente: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    sesion = Sesion()
    if args.instancia:
        # El operador local elige el archivo: se carga directo, sin pasar por la
        # herramienta del LLM (que está confinada al directorio de datos).
        from .sesion import cargar_nodos_sesion
        sesion.nodos = cargar_nodos_sesion(args.instancia)
        print(f"[instancia] {len(sesion.nodos)} nodos cargados")

    print(f"Asistente E-VRP ({args.modelo}). Escribe /salir para terminar.\n")
    while True:
        try:
            msg = input("tú> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not msg:
            continue
        if msg == "/salir":
            break
        if msg == "/reset":
            sesion = Sesion()
            print("[sesión reiniciada]")
            continue
        if msg == "/estado":
            print(sesion.resumen_estado())
            continue

        print("ia> ", end="", flush=True)
        tokens = 0
        for ev in asis.enviar_stream(msg, sesion):
            t = ev.get("tipo")
            if t == "texto":
                print(ev["texto"], end="", flush=True)
            elif t == "herramienta_inicio":
                print(f"\n  [🔧 {ev['herramienta']}({ev.get('entrada')})]", flush=True)
            elif t == "herramienta_fin":
                ok = ev["resultado"].get("ok")
                print(f"  [↳ {'ok' if ok else 'error'}: "
                      f"{ev['resultado'].get('error', '') or 'listo'}]", flush=True)
            elif t == "error":
                print(f"\n[error] {ev['error']}", flush=True)
            elif t == "fin":
                tokens = ev.get("tokens", 0)
        print(f"\n  (tokens: {tokens})\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
