// These formulas match webapp/plan.js. All route outputs are design fixtures.
export function summarizePlan({ SCENARIO, NODES, VEHICLES, ROUTES, SOURCE_DETAILS }, saved) {
  const nodeById = id => NODES.find(node => node.id === id);
  const assigned = new Set(ROUTES.flatMap(route => route.stopIds)
    .filter(id => nodeById(id)?.type === 'visit')).size;
  const energyKwh = ROUTES.length && ROUTES.every(route => Number.isFinite(route.energyKwh))
    ? ROUTES.reduce((sum, route) => sum + route.energyKwh, 0) : NaN;
  const charges = ROUTES.flatMap(route => route.stops.flatMap((stop, index) =>
    stop.chargeKwh > 0 ? [{ vehicleId: route.vehicleId, index, nodeId: stop.nodeId }] : []));
  const fleet = VEHICLES.map(vehicle => {
    const route = ROUTES.find(item => item.vehicleId === vehicle.id);
    return {
      ...vehicle,
      assigned: route ? route.stops.filter(stop => nodeById(stop.nodeId)?.type === 'visit').length : null,
      energyKwh: route?.energyKwh,
      finalSoc: route?.finalSoc,
      chargeStops: route ? route.stops.filter(stop => stop.chargeKwh > 0).length : null,
    };
  });
  const vehicle = fleet.find(item => item.id === saved?.vehicle);
  const stopRoute = ROUTES.find(route => route.vehicleId === saved?.stop?.vehicleId);
  const stop = saved?.stop && Number.isInteger(saved.stop.index) ? stopRoute?.stops[saved.stop.index] : null;
  const valid = !!saved && saved.scenario === SCENARIO.id
    && (saved.vehicle === null || !!vehicle)
    && ['fleet', 'stops'].includes(saved.tab)
    && (saved.stop === null || (!!stop && saved.stop.vehicleId === saved.vehicle))
    && typeof saved.chargers === 'boolean';
  const stopLabel = stop && nodeById(stop.nodeId)?.type === 'base'
    ? (saved.stop.index === 0 ? 'Salida de base' : saved.stop.index === stopRoute.stops.length - 1 ? 'Regreso a base' : 'Base')
    : stop && (nodeById(stop.nodeId)?.label || stop.nodeId);
  const context = valid
    ? [
      vehicle?.name || 'Toda la flota',
      saved.tab === 'stops' ? 'Paradas' : 'Vehículos',
      stopLabel,
      saved.chargers ? 'Estaciones visibles' : null,
    ].filter(Boolean).join(' · ')
    : `${SCENARIO.name} · ${VEHICLES.length} vehículos · ${SOURCE_DETAILS?.context || 'Demostración'}`;
  return {
    scenario: SCENARIO, fleet, charges,
    stats: {
      assigned, visits: NODES.filter(node => node.type === 'visit').length,
      energyKwh, chargeStops: charges.length, vehicles: VEHICLES.length,
      stations: NODES.filter(node => node.type === 'charger').length,
    },
    resume: {
      title: valid ? 'Donde lo dejaste' : 'Tu plan a mano',
      heading: valid ? 'Vuelve a tu recorrido' : 'Tu plan de reparto',
      context, cta: valid ? 'Continuar plan' : 'Abrir plan', valid,
    },
  };
}
