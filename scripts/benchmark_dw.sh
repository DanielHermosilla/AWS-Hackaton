#!/usr/bin/env bash
# El mismo snapshot y el mismo motor para las tres políticas; ver --help.
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
    printf 'Usar: bash scripts/benchmark_dw.sh [opciones]\n' >&2
    return 2
fi
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
exec uv run --locked --extra dw python -m ev_routing.benchmark "$@"
