#!/usr/bin/env bash
# Log completo solicitado: la salida SCIP/LLM se conserva sin resumir.
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
    printf 'Usar: bash scripts/test_clients.sh [opciones]\n' >&2
    return 2
fi
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
exec uv run --locked --extra dw python -u scripts/test_routing_verbose.py "$@"
