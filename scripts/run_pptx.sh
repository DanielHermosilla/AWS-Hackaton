#!/usr/bin/env bash
# Ejecutar con bash, sin source ni pegar este contenido en la terminal.
# Argumentos: segundos, none (sin H), archivo opcional de configuración.
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
    printf 'Usar: bash scripts/run_pptx.sh [segundos] [traslados]\n' >&2
    return 2
fi
set -euo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"
run_dir="${HACKATHON_RUN_DIR:-artifacts/hackathon}"
seconds="${1:-120}"
movements="${2:-none}"
config_args=()
if [[ -n "${3:-}" ]]; then
    config_args=(--config "$3")
fi
reuse_args=()
if [[ "${HACKATHON_REUSE_SERVICE_GRAPH:-0}" == "1" ]]; then
    reuse_args=(--reuse-instance "$run_dir/service-instance.json"
        --reuse-path-archive "$run_dir/service-paths.json")
fi

if [[ ! -f "$run_dir/instance.json" ]]; then
    printf 'Falta %s/instance.json. Preparar primero con:\n' "$run_dir" >&2
    printf 'bash scripts/prepare_hackathon.sh config/default.json\n' >&2
    exit 2
fi

printf 'Variante: servicios y caminos con recursos, optimización sin H.\n'
printf 'El JSON distingue la equivalencia de la reducción y la prueba del solver.\n'
printf 'Preparando caminos. Log: %s/service-prepare.log\n' "$run_dir"
if uv run --locked ev-routing service-graph \
    "${config_args[@]}" "${reuse_args[@]}" \
    --road-instance "$run_dir/instance.json" \
    --service-movements "$movements" \
    --cache-directory "$run_dir/preprocessing-cache" \
    --output "$run_dir/service-instance.json" \
    --path-archive "$run_dir/service-paths.json" >"$run_dir/service-prepare.log" 2>&1; then
    # Cantidades exactas; un resumen no debe cambiar la evidencia numérica.
    tail -n 1 "$run_dir/service-prepare.log"
else
    status=$?
    cat "$run_dir/service-prepare.log" >&2
    exit "$status"
fi

printf 'Resolviendo, presupuesto blando de %s s. Log: %s/service-solve.log\n' "$seconds" "$run_dir"
if uv run --locked --extra dw ev-routing run \
    "${config_args[@]}" \
    --instance "$run_dir/service-instance.json" \
    --road-instance "$run_dir/instance.json" \
    --path-archive "$run_dir/service-paths.json" \
    --initial-solution "$run_dir/service-instance.start.json" \
    --solver scip-routes --time-limit-seconds "$seconds" --threads 2 --tee \
    --output "$run_dir/service-result.json" >"$run_dir/service-solve.log" 2>&1; then
    tail -n 1 "$run_dir/service-solve.log"
    printf 'Resultado validado: %s/service-result.json\n' "$run_dir"
else
    status=$?
    tail -n 30 "$run_dir/service-solve.log" >&2
    printf 'No se obtuvo una solución validada (código %s). Revisar log y JSON, si existe.\n' "$status" >&2
    exit "$status"
fi
