#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
if command -v caffeinate >/dev/null 2>&1; then
  exec caffeinate -dimsu uv run --locked --extra dw python -m ev_routing.presentation_benchmark "$@"
fi
exec uv run --locked --extra dw python -m ev_routing.presentation_benchmark "$@"
