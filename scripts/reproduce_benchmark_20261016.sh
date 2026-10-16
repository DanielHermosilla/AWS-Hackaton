#!/usr/bin/env bash
# Repite la cohorte C con su código histórico; plan no llama a AWS.
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
action="${1:-plan}"
if [[ $# -gt 0 ]]; then shift; fi
case "$action" in
  plan|run|report) ;;
  *)
    printf 'Uso: bash scripts/reproduce_benchmark_20261016.sh [plan|run|report] [opciones]\n' >&2
    exit 2
    ;;
esac

revision="a04a884f3efcb4896d6a3db5f23b64b5569a7b22"
git cat-file -e "${revision}^{commit}"
snapshot_dir="$(mktemp -d "${TMPDIR:-/tmp}/evrp-benchmark-c.XXXXXX")"
trap 'rm -rf -- "$snapshot_dir"' EXIT
git archive "$revision" src | tar -x -C "$snapshot_dir"
export PYTHONPATH="$snapshot_dir/src"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1

runner=(uv run --project "$project_dir" --locked --extra dw python -m ev_routing.presentation_benchmark)
if command -v caffeinate >/dev/null 2>&1; then
  runner=(caffeinate -dimsu "${runner[@]}")
fi
"${runner[@]}" "$action" \
  --customers 40 80 120 200 --families dispatch crossed \
  --development-seeds 0 --test-seeds 701 702 --solver-seeds 0 \
  --pilot-seconds 10 --time-limit-seconds 45 \
  --energy-relative-gap 0.005 \
  --llm-max-calls 2 --llm-timeout-seconds 12 \
  --bedrock-model us.openai.gpt-5.6-luna \
  --ablation --adaptive-start standard --tee \
  --impact "$project_dir/docs/benchmarks/2026-10-16/provenance/phase-c/factors.json" \
  --output-dir "$project_dir/artifacts/repeat-benchmark-20261016-c" \
  "$@"
