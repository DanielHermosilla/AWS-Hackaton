#!/usr/bin/env bash
# Ejecutar con «bash scripts/prepare_hackathon.sh [config.json]».
# No pegar el contenido en la shell interactiva ni usar «source».
# Este archivo prepara datos; la construcción del MILP se ejecuta por separado.
set -euo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"

config_path="${1:-config/default.json}"
run_dir="${HACKATHON_RUN_DIR:-artifacts/hackathon}"
max_snap_distance_m="${MAX_SNAP_DISTANCE_M:-100}"
mkdir -p "$run_dir"
log_path="$run_dir/prepare.log"

printf 'Preparando la instancia. Log completo: %s\n' "$log_path"

# Capturar el código de la CLI antes de resumir: un fallo del resumidor no
# debe ocultar el error original ni decidir si la preparación fue correcta.
if uv run --locked ev-routing prepare \
    --nodes data/competition_routing_nodes.csv \
    --graphml artifacts/network/competition_delivery.graphml \
    --download-network \
    --network-profile delivery \
    --eved data/eVED_EV.csv \
    --energy-cache artifacts/energy/eved-summary.json \
    --config "$config_path" \
    --max-snap-distance-m "$max_snap_distance_m" \
    --name competition-full \
    --output "$run_dir/instance.json" >"$log_path" 2>&1; then
    distill "Indica nodos, arcos, entregas y ruta del JSON preparado." <"$log_path" \
        || cat "$log_path"
    printf 'Preparación completada. Revisar tamaño y accesos antes de resolver.\n'
else
    status=$?
    # El error exacto es necesario para diagnosticar; no resumirlo con un LLM.
    cat "$log_path" >&2
    printf 'Preparación fallida (código %s). El script termina aquí.\n' "$status" >&2
    exit "$status"
fi
