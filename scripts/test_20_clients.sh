#!/usr/bin/env bash
# Alias compatible del ensayo original de 20 clientes.
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
    printf 'Usar: bash scripts/test_20_clients.sh [opciones]\n' >&2
    return 2
fi
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
exec bash scripts/test_clients.sh "$@"
