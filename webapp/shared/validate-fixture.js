// Structural checks for the UI examples, not energy or solver validation.
export function validateFixture(fixture) {
  const require = (condition, field) => {
    if (!condition) throw new Error(`Datos de ejemplo inválidos: ${field}.`);
  };
  const text = value => typeof value === 'string' && value.trim().length > 0;
  const optionalNumber = value => value == null || Number.isFinite(value);
  const coordinate = point => Array.isArray(point) && point.length === 2 &&
    point.every(Number.isFinite) && Math.abs(point[0]) <= 180 && Math.abs(point[1]) <= 90;
  const unique = (items, key, field) => {
    const ids = items.map(item => item?.[key]);
    require(ids.every(text) && new Set(ids).size === ids.length, field);
    return new Set(ids);
  };

  require(fixture && typeof fixture === 'object', 'archivo');
  const { SCENARIO, VEHICLES, NODES, ROUTES } = fixture;
  require(text(SCENARIO?.id) && text(SCENARIO?.name) && SCENARIO.demonstration === true, 'SCENARIO');
  require(Array.isArray(VEHICLES) && VEHICLES.length > 0, 'VEHICLES');
  require(Array.isArray(NODES) && NODES.length > 0, 'NODES');
  require(Array.isArray(ROUTES) && ROUTES.length > 0, 'ROUTES');
  const vehicles = unique(VEHICLES, 'id', 'VEHICLES.id duplicado o vacío');
  const nodes = unique(NODES, 'id', 'NODES.id duplicado o vacío');
  unique(ROUTES, 'vehicleId', 'ROUTES.vehicleId duplicado o vacío');

  for (const vehicle of VEHICLES) {
    require(text(vehicle.name), 'VEHICLES.name');
    require(vehicle.model == null || typeof vehicle.model === 'string', 'VEHICLES.model');
    require(/^#[0-9a-f]{6}$/i.test(vehicle.color), 'VEHICLES.color');
    require(optionalNumber(vehicle.initialSoc), 'VEHICLES.initialSoc');
  }
  for (const node of NODES) {
    require(['base', 'visit', 'charger'].includes(node.type), 'NODES.type');
    require(text(node.label), 'NODES.label');
    require(coordinate([node.lng, node.lat]), 'NODES.coordinates');
    require(node.connectors == null || typeof node.connectors === 'string', 'NODES.connectors');
  }
  for (const route of ROUTES) {
    require(vehicles.has(route.vehicleId), 'ROUTES.vehicleId desconocido');
    require(Array.isArray(route.stops) && route.stops.length > 0, 'ROUTES.stops');
    require(Array.isArray(route.stopIds) && route.stopIds.length === route.stops.length, 'ROUTES.stopIds');
    require(route.geometry?.type === 'LineString' &&
      Array.isArray(route.geometry.coordinates) && route.geometry.coordinates.length >= 2 &&
      route.geometry.coordinates.every(coordinate), 'ROUTES.geometry');
    for (const field of ['energyKwh', 'chargeKwh', 'finalSoc', 'distanceKm']) {
      require(optionalNumber(route[field]), `ROUTES.${field}`);
    }
    route.stops.forEach((stop, index) => {
      require(stop && nodes.has(stop.nodeId), 'ROUTES.stops.nodeId desconocido');
      require(route.stopIds[index] === stop.nodeId, 'ROUTES.stopIds no coincide con stops');
      for (const field of ['arrivalSoc', 'departureSoc', 'chargeKwh']) {
        require(optionalNumber(stop[field]), `ROUTES.stops.${field}`);
      }
    });
  }
  return fixture;
}
