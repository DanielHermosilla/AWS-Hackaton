import {nativeRunResult, resultSections} from './solver-output.js';

// A view of the already validated API 3.0 response. It never totals route
// energies, infers service from a visit, or issues a feasibility certificate.
export function buildPlanSummary(data, {execution = null, stale = false, error = null} = {}) {
  const result = data?.RAW_RESPONSE?.result;
  if (!result) return {
    available: false, runId: null, routes: [], sections: [],
    freshness: {state: 'unavailable', title: 'Sin resultado del motor'},
    message: error?.message || (data?.DATA_SOURCE === 'pending'
      ? 'La instancia está pendiente de calcular. Abre «Cargar y calcular» para obtener un resultado.'
      : 'El ejemplo de diseño no es una ejecución del motor. Carga y calcula una instancia para consultar su resumen.')
  };
  const native = nativeRunResult(data.RAW_RESPONSE);
  const sections = resultSections(result);
  const nodes = new Map(result.nodes.map(node => [node.node_id, node]));
  const fleet = new Map(result.fleet.map(vehicle => [vehicle.id, vehicle]));
  const current = execution?.runId === result.run_id && execution?.stale === false &&
    execution?.status === 'complete' && !stale;
  const validated = result.validation.feasible === true;
  const noSolutionLabels = {no_solution: 'Sin solución encontrada', unavailable: 'Solver no disponible', error: 'Ejecución con error'};
  const validationFailed = result.validation.feasible === false;
  const phases = sections.filter(section => section.title.startsWith('Fase:'))
    .map((section, index) => ({...section, status: result.phases[index].status}));
  const conditionalEnergy = result.phases.some(phase => phase.name === 'deliveries' && !phase.proven_optimal) &&
    result.phases.some(phase => phase.name === 'energy');
  return {
    available: true, runId: result.run_id,
    scenarioName: native?.instance_name || result.raw?.instance?.name || 'Instancia sin nombre',
    createdAt: native?.created_at_utc || null,
    operations: result.operations || native?.operations || {},
    provider: result.metadata.provider,
    providerCommit: result.metadata.provider_commit,
    freshness: current
      ? {state: 'current', title: 'Ejecución vigente', message: 'Corresponde a la instancia calculada que está seleccionada en esta pestaña.'}
      : {state: 'stale', title: 'Resultado anterior · no vigente',
        message: 'Este resumen conserva una ejecución anterior. No corresponde a los cambios o al cálculo actual. Vuelve a calcular para obtener un plan vigente.'},
    status: {
      label: !result.has_solution ? noSolutionLabels[result.status] || 'Sin solución disponible'
        : validationFailed ? 'Validación fallida · solución sin validar'
          : validated ? 'Plan comprobado para el modelo' : 'Solución sin comprobación de factibilidad',
      tone: validated && result.has_solution ? 'verified' : 'attention',
      timeLimitReached: result.metadata.time_limit_reached === true,
    },
    solutionNote: validationFailed
      ? 'La comprobación independiente rechazó esta solución. El estado del solver no acredita un plan factible.'
      : !result.has_solution
        ? 'La ejecución no encontró una solución disponible. Esto por sí solo no demuestra que el problema sea infactible.'
        : conditionalEnergy
          ? 'La mejora de energía está condicionada a las entregas encontradas; no hay prueba de óptimo lexicográfico.'
          : 'Los certificados de cada fase se muestran por separado y se limitan al grafo y al modelo energético de esta instancia.',
    sections, phases,
    validation: sections.find(section => section.title === 'Comprobación independiente'),
    network: result.network.vial
      ? 'Red vial declarada por la instancia; procedencia y condiciones en terreno sin verificar.'
      : 'Red no vial. Las distancias y energías de esta instancia no acreditan un recorrido por calles.',
    assumptions: [...result.assumptions], warnings: [...result.warnings],
    pending: {
      available: result.has_solution,
      items: result.has_solution ? result.unserved_visit_ids.map(id => ({id, label: nodes.get(id)?.address || id})) : [],
      message: !result.has_solution
        ? 'No se dispone de entregas pendientes sin una solución. La lista vacía no significa que se haya atendido la demanda.'
        : validationFailed
          ? 'Son destinos sin servicio en la solución rechazada. El motor no informa la causa individual.'
          : result.unserved_visit_ids.length
            ? 'Destinos sin servicio planificado en esta ejecución. El motor no informa la causa individual.'
            : 'La solución incluye servicio explícito para todos los destinos de la instancia.',
    },
    routes: result.has_solution ? result.routes.map(route => {
      const vehicle = fleet.get(route.vehicle_id);
      return {
        vehicleId: route.vehicle_id, label: vehicle.label, vehicle,
        servedVisitIds: [...route.served_visit_ids],
        distanceKm: route.distance_km, energyKwh: route.energy_kwh, durationSeconds: route.duration_seconds ?? null,
        steps: route.steps.map((step, index) => {
          const node = nodes.get(step.node_id);
          return {
            ...step, delivered_visit_ids: [...step.delivered_visit_ids],
            label: node.address || node.node_id,
            service: step.delivered_visit_ids.length
              ? validated ? 'Entrega planificada' : 'Servicio indicado (sin validar)'
              : node.node_type === 'visit' ? 'Paso sin entrega'
                : node.node_type === 'base' ? route.steps.length === 1 ? 'En base · sin recorrido' : index === 0 ? 'Salida de base'
                  : index === route.steps.length - 1 ? 'Regreso a base' : 'Paso por base'
                  : node.node_type === 'charger' ? 'Parada en cargador' : 'Tránsito',
          };
        }),
      };
    }) : [],
  };
}
