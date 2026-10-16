#!/usr/bin/env bash
# Generador, piloto sin AWS y comparación pareada. Consultar --help.
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
exec uv run --locked --extra dw python -m ev_routing.synthetic_benchmark "$@"
