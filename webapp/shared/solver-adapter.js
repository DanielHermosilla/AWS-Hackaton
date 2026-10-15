// Presentation boundary for the versioned beta bridge. These checks validate
// the response contract; feasibility remains the provider's reported result.
const palette = ['#1664ec', '#8152d9', '#0f8a6a', '#c2571a', '#b23a7a', '#5b6b7f'];
const record = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const text = value => typeof value === 'string' && value.trim().length > 0;
const nullableNumber = value => value === null || Number.isFinite(value);
const coordinate = value => Array.isArray(value) && value.length === 2 &&
  value.every(Number.isFinite) && Math.abs(value[0]) <= 180 && Math.abs(value[1]) <= 90;
const require = (condition, field) => {
  if (!condition) throw new Error(`Respuesta del motor inválida: ${field}. Revisa el contrato de la ejecución.`);
};
const sameSet = (left, right) => left.size === right.size && [...left].every(value => right.has(value));

function uniqueIds(items, key, field) {
  const ids = items.map(item => item?.[key]);
  require(ids.every(text) && new Set(ids).size === ids.length, `${field}: IDs vacíos o duplicados`);
  return new Set(ids);
}

function stringArray(value, field, unique = false) {
  require(Array.isArray(value) && value.every(item => typeof item === 'string'), field);
  if (unique) require(value.every(text) && new Set(value).size === value.length, field);
  return value;
}

export function adaptSolverResponse(envelope) {
  require(record(envelope) && envelope.api_version === '2.0-beta.1', 'api_version no admitida');
  const result = envelope.result;
  require(record(result), 'result');
  require(text(result.run_id), 'run_id');
  require(['result_available', 'partial', 'validation_failed'].includes(result.status), 'status no admitido');
  for (const field of ['nodes', 'fleet', 'routes', 'phases']) require(Array.isArray(result[field]), field);
  const nodes = uniqueIds(result.nodes, 'node_id', 'nodes');
  const vehicles = uniqueIds(result.fleet, 'id', 'fleet');
  uniqueIds(result.routes, 'vehicle_id', 'routes');
  require(result.nodes.filter(node => node.node_type === 'base').length === 1, 'se requiere una base');
  const visits = new Set(result.nodes.filter(node => node.node_type === 'visit').map(node => node.node_id));
  const NODES = result.nodes.map((node, index) => {
    const path = `nodes[${index}]`;
    require(['base', 'visit', 'charger'].includes(node.node_type), `${path}.node_type`);
    require(Number.isFinite(node.latitude) && Math.abs(node.latitude) <= 90, `${path}.latitude`);
    require(Number.isFinite(node.longitude) && Math.abs(node.longitude) <= 180, `${path}.longitude`);
    for (const field of ['address', 'network', 'connector_types']) {
      require(node[field] == null || typeof node[field] === 'string', `${path}.${field}`);
    }
    for (const field of ['total_ports', 'dc_fast_ports', 'level2_ports']) {
      require(node[field] == null || (Number.isInteger(node[field]) && node[field] >= 0), `${path}.${field}`);
    }
    require(node.max_power_kw == null || (Number.isFinite(node.max_power_kw) && node.max_power_kw >= 0), `${path}.max_power_kw`);
    return {
      id: node.node_id, type: node.node_type, lat: node.latitude, lng: node.longitude,
      label: node.address?.trim() || (node.node_type === 'base' ? 'Base' : node.node_id),
      address: node.address || '', connectors: node.connector_types || '',
      network: node.network || '', powerKw: node.max_power_kw ?? null
    };
  });
  const VEHICLES = result.fleet.map((vehicle, index) => {
    const path = `fleet[${index}]`;
    require(text(vehicle.type) && text(vehicle.label), `${path}.type/label`);
    require(Number.isFinite(vehicle.battery_capacity_kwh) && vehicle.battery_capacity_kwh > 0, `${path}.battery_capacity_kwh`);
    require(Number.isFinite(vehicle.reserve_kwh) && vehicle.reserve_kwh >= 0 &&
      vehicle.reserve_kwh <= vehicle.battery_capacity_kwh, `${path}.reserve_kwh`);
    require(Number.isFinite(vehicle.initial_soc) && vehicle.initial_soc >= 0 &&
      vehicle.initial_soc <= 1, `${path}.initial_soc debe estar entre 0 y 1`);
    return {
      id: vehicle.id, name: vehicle.label, model: vehicle.type,
      color: palette[index % palette.length], initialSoc: vehicle.initial_soc * 100,
      capacityKwh: vehicle.battery_capacity_kwh, reserveKwh: vehicle.reserve_kwh
    };
  });
  const fleetById = new Map(VEHICLES.map(vehicle => [vehicle.id, vehicle]));
  const base = NODES.find(node => node.type === 'base').id;
  const delivered = new Set();
  const ROUTES = result.routes.map((route, routeIndex) => {
    const path = `routes[${routeIndex}]`;
    require(vehicles.has(route.vehicle_id), `${path}.vehicle_id desconocido`);
    require(Array.isArray(route.steps), `${path}.steps`);
    require(nullableNumber(route.distance_km) && (route.distance_km === null || route.distance_km >= 0), `${path}.distance_km`);
    require(nullableNumber(route.energy_kwh), `${path}.energy_kwh`);
    const geometry = route.geometry;
    require(geometry === null || (record(geometry) && geometry.type === 'LineString' &&
      Array.isArray(geometry.coordinates) && geometry.coordinates.length >= 2 &&
      geometry.coordinates.every(coordinate)), `${path}.geometry`);
    const servedIds = stringArray(route.served_visit_ids, `${path}.served_visit_ids`, true);
    require(servedIds.every(id => visits.has(id) && !delivered.has(id)), `${path}.served_visit_ids desconocidos o duplicados entre vehículos`);
    const served = new Set(servedIds);
    const vehicle = fleetById.get(route.vehicle_id);
    const occurrences = new Set();
    const steps = route.steps.map((step, index) => {
      const stepPath = `${path}.steps[${index}]`;
      require(record(step) && step.position === index, `${stepPath}.position`);
      require(nodes.has(step.node_id), `${stepPath}.node_id desconocido`);
      for (const field of ['arrival_energy_kwh', 'departure_energy_kwh']) {
        require(nullableNumber(step[field]) && (step[field] === null ||
          (step[field] >= 0 && step[field] <= vehicle.capacityKwh)), `${stepPath}.${field}`);
      }
      require(nullableNumber(step.charge_kwh) && (step.charge_kwh === null || step.charge_kwh >= 0), `${stepPath}.charge_kwh`);
      require(nullableNumber(step.energy_kwh), `${stepPath}.energy_kwh`);
      const ids = stringArray(step.delivered_visit_ids, `${stepPath}.delivered_visit_ids`, true);
      require(ids.every(id => visits.has(id) && served.has(id) && id === step.node_id && !occurrences.has(id)),
        `${stepPath}.delivered_visit_ids inconsistentes o repetidos`);
      ids.forEach(id => occurrences.add(id));
      const soc = energy => energy === null ? null : energy / vehicle.capacityKwh * 100;
      return {
        nodeId: step.node_id, position: step.position,
        occurrenceId: JSON.stringify([route.vehicle_id, step.position]),
        arrivalSoc: soc(step.arrival_energy_kwh), departureSoc: soc(step.departure_energy_kwh),
        chargeKwh: step.charge_kwh, energyKwh: step.energy_kwh,
        deliveredVisitIds: [...ids]
      };
    });
    require(sameSet(served, occurrences), `${path}.steps.delivered_visit_ids no coincide con served_visit_ids`);
    served.forEach(id => delivered.add(id));
    return {
      vehicleId: route.vehicle_id, active: steps.some(step => step.nodeId !== base),
      servedVisitIds: [...served], stops: steps, stopIds: steps.map(step => step.nodeId),
      geometry, distanceKm: route.distance_km, energyKwh: route.energy_kwh,
      finalSoc: steps.at(-1)?.departureSoc ?? null
    };
  });
  require(Number.isInteger(result.served_count) && result.served_count === delivered.size, 'served_count no coincide con las entregas explícitas');
  require(Number.isInteger(result.total_visits) && result.total_visits === visits.size, 'total_visits no coincide con los nodos');
  const unserved = stringArray(result.unserved_visit_ids, 'unserved_visit_ids', true);
  require(sameSet(new Set(unserved), new Set([...visits].filter(id => !delivered.has(id)))), 'unserved_visit_ids no coincide con las entregas pendientes');
  require(nullableNumber(result.total_energy_kwh), 'total_energy_kwh');
  if (result.total_energy_kwh !== null && ROUTES.every(route => route.energyKwh !== null)) {
    const suppliedTotal = ROUTES.reduce((sum, route) => sum + route.energyKwh, 0);
    require(Math.abs(suppliedTotal - result.total_energy_kwh) <= 1e-7 * Math.max(1, Math.abs(result.total_energy_kwh)),
      'total_energy_kwh no coincide con los valores por vehículo');
  }
  const validation = result.validation;
  require(record(validation) && [true, false, null].includes(validation.feasible), 'validation.feasible');
  const violations = stringArray(validation.violations, 'validation.violations');
  require(typeof validation.scope === 'string', 'validation.scope');
  require(validation.feasible !== true || violations.length === 0, 'validation: factible con violaciones');
  require((result.status === 'validation_failed') === (validation.feasible === false), 'validation y status no coinciden');
  require(record(result.runtime_seconds), 'runtime_seconds');
  for (const field of ['preparation', 'solver', 'total']) {
    require(nullableNumber(result.runtime_seconds[field]) && (result.runtime_seconds[field] === null ||
      result.runtime_seconds[field] >= 0), `runtime_seconds.${field}`);
  }
  require(result.phases.every(record), 'phases');
  stringArray(result.warnings, 'warnings');
  stringArray(result.assumptions, 'assumptions');
  require(record(result.network), 'network');
  require(record(result.metadata), 'metadata');
  for (const field of ['provider', 'provider_commit', 'input_hash', 'config_hash', 'network_hash']) {
    require(text(result.metadata[field]), `metadata.${field}`);
  }
  return {
    SCENARIO: { id: result.run_id, name: 'Resultado del motor', demonstration: false, synthetic: false },
    VEHICLES, NODES, ROUTES,
    RUN_INFO: {
      runId: result.run_id, source: 'solver', status: result.status,
      feasible: validation.feasible, validationScope: validation.scope, violations: [...violations],
      servedCount: result.served_count, totalVisits: result.total_visits, unservedVisitIds: [...unserved],
      totalEnergyKwh: result.total_energy_kwh, phases: result.phases,
      runtimeSeconds: { ...result.runtime_seconds }, warnings: [...result.warnings],
      assumptions: [...result.assumptions], network: result.network, metadata: { ...result.metadata }
    }
  };
}
