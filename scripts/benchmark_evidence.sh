#!/usr/bin/env bash
# Plan por defecto. --execute inicia la campaña; --with-bedrock habilita AWS.
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
exec uv run --locked --extra dw python -m ev_routing.evidence "$@"
