// Display names never replace the opaque identifiers used by the engine.
export function locationLabels(nodes) {
  const counts = {base: 0, visit: 0, charger: 0, junction: 0};
  const names = {base: 'Depósito', visit: 'Cliente', charger: 'Estación de carga', junction: 'Intersección'};
  return new Map(nodes.map(node => {
    const type = node.node_type ?? node.type;
    const id = node.node_id ?? node.id;
    const position = (counts[type] = (counts[type] || 0) + 1);
    const address = node.address?.trim();
    const fallback = type === 'base' ? names.base : `${names[type] || 'Ubicación'} ${position}`;
    return [id, address && address !== id ? address : fallback];
  }));
}

export function phaseTermination(phase = {}) {
  const known = {
    optimal: 'Búsqueda completada',
    witness_and_cardinality_bound: 'Máximo de entregas comprobado',
    validated_route_and_relaxation_bound: 'Mejor solución comprobada',
    energy_gap_limit: 'Tolerancia de energía alcanzada',
    timelimit: 'Tiempo disponible agotado',
    time_limit: 'Tiempo disponible agotado',
    maxtimelimit: 'Tiempo disponible agotado',
    budget_exhausted: 'Tiempo disponible agotado',
    pricing_incomplete: 'Búsqueda detenida antes de completarse',
    restricted_pool_heuristic: 'Búsqueda parcial completada',
    infeasible: 'No existe un plan que cumpla estas condiciones',
    infeasibleOrUnbounded: 'No se pudo determinar un plan factible',
    unbounded: 'El modelo no tiene un límite válido',
    userinterrupt: 'Cálculo interrumpido',
    interrupted: 'Cálculo interrumpido',
    nodelimit: 'Límite de búsqueda alcanzado',
    totalnodelimit: 'Límite de búsqueda alcanzado',
    stallnodelimit: 'La búsqueda dejó de avanzar',
    memlimit: 'Memoria disponible agotada',
    gaplimit: 'Tolerancia de búsqueda alcanzada',
    sollimit: 'Límite de soluciones alcanzado',
    bestsollimit: 'Límite de mejoras alcanzado',
    restartlimit: 'Límite de reinicios alcanzado',
    error: 'El cálculo terminó con un error',
    unknown: 'Finalización sin detalle disponible',
    not_run: 'Esta fase no se ejecutó',
    skipped: 'Esta fase no se ejecutó'
  };
  return known[phase.termination_condition] || 'El motor terminó esta fase; el detalle técnico está en el archivo de resultados.';
}

export function phaseStatus(phase = {}) {
  if (phase.proven_optimal) return 'Mejor resultado demostrado';
  if (phase.has_solution) return 'Solución encontrada';
  return {
    infeasible: 'Sin plan factible',
    error: 'Error de cálculo',
    time_limit: 'Sin solución al terminar el tiempo',
    skipped: 'Sin ejecutar'
  }[phase.status] || 'Sin solución disponible';
}

// Result exports retain the original provider strings. The product speaks in
// terms of roles rather than the names of individual implementers.
export function presentationText(value) {
  if (typeof value !== 'string') return value;
  return value
    .replace(/\b(?:motor(?: nativo)?|solver) de Daniel(?: Hermosilla)?\b/gi, 'motor de cálculo')
    .replace(/\b(?:Daniel(?: Hermosilla)?|Lucas(?: Zulueta)?|Diego(?: Caballero)?)\b/gi, 'el equipo');
}
