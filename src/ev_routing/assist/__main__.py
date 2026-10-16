"""REPL de demo del asistente: ``python -m ev_routing.assist <instancia.json>``.

Carga una instancia, abre una sesion y conversa por consola. Si no hay
credenciales de Bedrock, el chat queda inactivo pero la explicacion por
plantilla y las herramientas locales siguen disponibles para la demo offline.
"""

from __future__ import annotations

import sys

from .assistant import Asistente
from .bedrock_chat import ClienteBedrock, ModeloNoDisponible
from .session import Sesion


def _cargar_instancia(ruta: str):
    from ev_routing.inputs import load_instance

    return load_instance(ruta)


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("uso: python -m ev_routing.assist <instancia.json>")
        return 2
    instancia = _cargar_instancia(argv[0])
    sesion = Sesion(instancia_base=instancia)
    try:
        cliente = ClienteBedrock()
        cliente._asegurar_cliente()
    except ModeloNoDisponible as exc:
        print(f"[aviso] Bedrock no disponible ({exc}). Chat inactivo.")
        cliente = None

    asistente = Asistente(sesion, cliente)
    print("Asistente de flota listo. Escribe 'salir' para terminar.")
    while True:
        try:
            texto = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if texto.lower() in {"salir", "exit", "quit"}:
            break
        if not texto:
            continue
        turno = asistente.turno(texto)
        if turno.error:
            print(f"[error] {turno.error}")
        else:
            print(turno.respuesta)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
