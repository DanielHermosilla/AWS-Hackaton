import test from 'node:test';
import assert from 'node:assert/strict';
import { adaptSolverResponse } from '../shared/solver-adapter.js';
import { escapeHtml } from '../shared/html.js';

function response() {
  return {
    api_version: '3.0',
    result: {
      run_id: 'run-one',
      status: 'result_available',
      has_solution: true,
      nodes: [
        { node_id: 'BASE', node_type: 'base', latitude: -33.45, longitude: -70.66, address: 'Depósito' },
        { node_id: 'V|1', node_type: 'visit', latitude: -33.46, longitude: -70.65, address: 'Local uno' },
        { node_id: 'V2', node_type: 'visit', latitude: -33.47, longitude: -70.64, address: 'Local dos' },
        { node_id: 'C#fin', node_type: 'charger', latitude: -33.48, longitude: -70.63, address: 'Estación', connector_types: ['CHAdeMO', 'CCS'], max_power_kw: 50 }
      ],
      fleet: [{ id: 'vehicle|1', type: 'Leaf', label: 'Vehículo uno', battery_capacity_kwh: 20, reserve_kwh: 2, initial_soc: 0.6 }],
      routes: [{
        vehicle_id: 'vehicle|1',
        served_visit_ids: ['V|1'],
        steps: [
          { position: 0, node_id: 'BASE', arrival_energy_kwh: 12, departure_energy_kwh: 12, charge_kwh: 0, energy_kwh: null, delivered_visit_ids: [] },
          { position: 1, node_id: 'V|1', arrival_energy_kwh: 10, departure_energy_kwh: 10, charge_kwh: 0, energy_kwh: 2, delivered_visit_ids: ['V|1'] },
          { position: 2, node_id: 'V2', arrival_energy_kwh: 9, departure_energy_kwh: 9, charge_kwh: 0, energy_kwh: 1, delivered_visit_ids: [] },
          { position: 3, node_id: 'BASE', arrival_energy_kwh: 8, departure_energy_kwh: 8, charge_kwh: 0, energy_kwh: 1, delivered_visit_ids: [] }
        ],
        geometry: null,
        distance_km: 7,
        energy_kwh: null
      }],
      served_count: 1,
      total_visits: 2,
      unserved_visit_ids: ['V2'],
      total_energy_kwh: null,
      validation: { feasible: true, violations: [], scope: 'Comprobación del proveedor en la red preparada.' },
      phases: [],
      warnings: ['Consumo efectivo no disponible.'],
      runtime_seconds: { preparation: 0.5, solver: 2.5, total: 3.1 },
      assumptions: ['Capacidad útil configurada: 20 kWh.'],
      network: { type: 'osm', road: true },
      metadata: { provider: 'ev_routing', provider_commit: '624203573bffdeec334a9e07a64b361a515f9725', input_hash: 'input', config_hash: 'config', network_hash: 'network' },
      raw: { input: {}, instance: {}, effective_config: {}, result: {} }
    }
  };
}

test('adapts one real run without reconstructing unavailable energy or geometry', () => {
  const envelope = response();
  const { SCENARIO, VEHICLES, ROUTES, NODES, RUN_INFO } = adaptSolverResponse(envelope);
  assert.equal(SCENARIO.id, envelope.result.run_id);
  assert.equal(SCENARIO.demonstration, false);
  assert.equal(VEHICLES[0].initialSoc, 60);
  assert.equal(ROUTES[0].stops[1].arrivalSoc, 50);
  assert.equal(ROUTES[0].finalSoc, 40);
  assert.equal(ROUTES[0].energyKwh, null);
  assert.equal(ROUTES[0].geometry, null);
  assert.equal(RUN_INFO.totalEnergyKwh, null);
  assert.deepEqual(RUN_INFO.runtimeSeconds, envelope.result.runtime_seconds);
  assert.equal(NODES[0].lng, -70.66);
  assert.equal(NODES[0].lat, -33.45);
});

test('passing through a client does not add an explicit delivery', () => {
  const { ROUTES, RUN_INFO } = adaptSolverResponse(response());
  assert.deepEqual(ROUTES[0].servedVisitIds, ['V|1']);
  assert.deepEqual(ROUTES[0].stops[2].deliveredVisitIds, []);
  assert.equal(RUN_INFO.servedCount, 1);
});

test('repeated visits, chargers and intermediate base keep their occurrences', () => {
  const envelope = response();
  const route = envelope.result.routes[0];
  route.steps.splice(2, 0,
    { ...route.steps[1], delivered_visit_ids: [] },
    { ...route.steps[1], node_id: 'C#fin', charge_kwh: 1, delivered_visit_ids: [] },
    { ...route.steps[1], node_id: 'BASE', delivered_visit_ids: [] },
    { ...route.steps[1], node_id: 'C#fin', charge_kwh: 2, delivered_visit_ids: [] });
  route.steps.forEach((step, index) => { step.position = index; });
  const { ROUTES } = adaptSolverResponse(envelope);
  assert.deepEqual(ROUTES[0].stopIds, route.steps.map(step => step.node_id));
  assert.equal(new Set(ROUTES[0].stops.map(step => step.occurrenceId)).size, route.steps.length);
  assert.deepEqual(ROUTES[0].servedVisitIds, ['V|1']);
  assert.equal(ROUTES[0].active, true);
});

test('BASE to BASE is an inactive route with supplied return battery preserved', () => {
  const envelope = response();
  const route = envelope.result.routes[0];
  route.steps = [route.steps[0], { ...route.steps[0], position: 1 }];
  route.served_visit_ids = [];
  route.distance_km = 0;
  envelope.result.served_count = 0;
  envelope.result.unserved_visit_ids = ['V|1', 'V2'];
  const { ROUTES } = adaptSolverResponse(envelope);
  assert.equal(ROUTES[0].active, false);
  assert.equal(ROUTES[0].finalSoc, 60);
  assert.equal(ROUTES[0].stops.length, 2);
});

test('zero destinations, empty fleets, empty routes and missing metrics are valid', () => {
  const envelope = response();
  envelope.result.nodes = [envelope.result.nodes[0]];
  envelope.result.fleet = [];
  envelope.result.routes = [];
  envelope.result.served_count = 0;
  envelope.result.total_visits = 0;
  envelope.result.unserved_visit_ids = [];
  envelope.result.validation.feasible = null;
  envelope.result.runtime_seconds = { preparation: null, solver: null, total: null };
  const { VEHICLES, ROUTES, RUN_INFO } = adaptSolverResponse(envelope);
  assert.deepEqual(VEHICLES, []);
  assert.deepEqual(ROUTES, []);
  assert.equal(RUN_INFO.totalVisits, 0);
  assert.equal(RUN_INFO.totalEnergyKwh, null);
  assert.equal(RUN_INFO.feasible, null);
});

test('an empty route does not fabricate base steps or return battery', () => {
  const envelope = response();
  const route = envelope.result.routes[0];
  route.steps = [];
  route.served_visit_ids = [];
  envelope.result.served_count = 0;
  envelope.result.unserved_visit_ids = ['V|1', 'V2'];
  envelope.result.validation.feasible = null;
  const { ROUTES } = adaptSolverResponse(envelope);
  assert.deepEqual(ROUTES[0].stops, []);
  assert.equal(ROUTES[0].finalSoc, null);
  assert.equal(ROUTES[0].active, false);
});

test('GeoJSON longitude/latitude is preserved and never swapped a second time', () => {
  const envelope = response();
  envelope.result.routes[0].geometry = { type: 'LineString', coordinates: [[-70.66, -33.45], [-70.65, -33.46]] };
  const { ROUTES } = adaptSolverResponse(envelope);
  assert.deepEqual(ROUTES[0].geometry, envelope.result.routes[0].geometry);
});

test('coherent signed energy is preserved for regenerative results', () => {
  const envelope = response();
  envelope.result.routes[0].energy_kwh = -1.2;
  envelope.result.routes[0].steps[1].energy_kwh = -2;
  envelope.result.total_energy_kwh = -1.2;
  const { ROUTES, RUN_INFO } = adaptSolverResponse(envelope);
  assert.equal(ROUTES[0].energyKwh, -1.2);
  assert.equal(RUN_INFO.totalEnergyKwh, -1.2);
  assert.equal(ROUTES[0].stops[1].energyKwh, -2);
});

test('partial and validation-failed states are kept without inventing certificates', () => {
  for (const [status, feasible, violations] of [
    ['partial', null, []],
    ['validation_failed', false, ['Reserva insuficiente.']]
  ]) {
    const envelope = response();
    Object.assign(envelope.result, { status });
    Object.assign(envelope.result.validation, { feasible, violations });
    const { RUN_INFO } = adaptSolverResponse(envelope);
    assert.equal(RUN_INFO.status, status);
    assert.equal(RUN_INFO.feasible, feasible);
    assert.deepEqual(RUN_INFO.phases, []);
    assert.deepEqual(RUN_INFO.violations, violations);
  }
});

test('opaque IDs and untrusted labels remain data and can be escaped at rendering', () => {
  const envelope = response();
  envelope.result.fleet[0].label = '<img src=x onerror=alert(1)>';
  envelope.result.nodes[1].address = 'A "norte" & <sur>';
  const { VEHICLES, NODES } = adaptSolverResponse(envelope);
  assert.equal(VEHICLES[0].id, 'vehicle|1');
  assert.equal(escapeHtml(VEHICLES[0].name), '&lt;img src=x onerror=alert(1)&gt;');
  assert.equal(escapeHtml(NODES[1].label), 'A &quot;norte&quot; &amp; &lt;sur&gt;');
});

for (const [name, mutate, field] of [
  ['unknown API version', d => { d.api_version = '1.0'; }, /api_version/],
  ['unknown result state', d => { d.result.status = 'optimal'; }, /status/],
  ['missing run identity', d => { d.result.run_id = ''; }, /run_id/],
  ['duplicate node', d => { d.result.nodes[1].node_id = 'BASE'; }, /nodes/],
  ['unknown node type', d => { d.result.nodes[1].node_type = 'customer'; }, /node_type/],
  ['latitude outside range', d => { d.result.nodes[0].latitude = 91; }, /latitude/],
  ['numeric coordinate string', d => { d.result.nodes[0].longitude = '-70.66'; }, /longitude/],
  ['multiple bases', d => { d.result.nodes[1].node_type = 'base'; }, /base/],
  ['duplicate vehicle', d => { d.result.fleet.push(d.result.fleet[0]); }, /fleet/],
  ['unknown vehicle', d => { d.result.routes[0].vehicle_id = 'ghost'; }, /vehicle_id/],
  ['duplicate route', d => { d.result.routes.push(d.result.routes[0]); }, /routes/],
  ['unknown stop', d => { d.result.routes[0].steps[1].node_id = 'ghost'; }, /node_id/],
  ['unordered position', d => { d.result.routes[0].steps[1].position = 8; }, /position/],
  ['unknown served visit', d => { d.result.routes[0].served_visit_ids = ['ghost']; }, /served_visit_ids/],
  ['duplicate served visit', d => { d.result.routes[0].served_visit_ids.push('V|1'); }, /served_visit_ids/],
  ['service and route mismatch', d => { d.result.routes[0].steps[1].delivered_visit_ids = []; }, /delivered_visit_ids/],
  ['duplicate delivery occurrences', d => { d.result.routes[0].steps[2].delivered_visit_ids = ['V|1']; }, /delivered_visit_ids/],
  ['served total mismatch', d => { d.result.served_count = 2; }, /served_count/],
  ['visit total mismatch', d => { d.result.total_visits = 8; }, /total_visits/],
  ['unserved visit mismatch', d => { d.result.unserved_visit_ids = []; }, /unserved_visit_ids/],
  ['initial SOC in percent instead of fraction', d => { d.result.fleet[0].initial_soc = 60; }, /initial_soc/],
  ['zero capacity', d => { d.result.fleet[0].battery_capacity_kwh = 0; }, /battery_capacity_kwh/],
  ['arrival beyond capacity', d => { d.result.routes[0].steps[1].arrival_energy_kwh = 21; }, /arrival_energy_kwh/],
  ['negative charge', d => { d.result.routes[0].steps[1].charge_kwh = -1; }, /charge_kwh/],
  ['NaN energy', d => { d.result.total_energy_kwh = NaN; }, /total_energy_kwh/],
  ['infinite runtime', d => { d.result.runtime_seconds.solver = Infinity; }, /runtime_seconds/],
  ['inconsistent energy aggregate', d => { d.result.total_energy_kwh = 5; d.result.routes[0].energy_kwh = 4; }, /total_energy_kwh/],
  ['invalid geometry', d => { d.result.routes[0].geometry = { type: 'LineString', coordinates: [[0, 91], [0, 0]] }; }, /geometry/],
  ['missing geometry field', d => { delete d.result.routes[0].geometry; }, /geometry/],
  ['contradictory valid flag', d => { d.result.validation.violations = ['Falló reserva']; }, /validation/],
  ['contradictory failed state', d => { d.result.status = 'validation_failed'; }, /validation/]
]) {
  test(`rejects ${name} with a field-specific contract error`, () => {
    const envelope = response();
    mutate(envelope);
    assert.throws(() => adaptSolverResponse(envelope), field);
  });
}


test('native junctions and missing paired coordinates remain in the list without fake map points', () => {
  const envelope = response();
  envelope.result.nodes[0].latitude = null; envelope.result.nodes[0].longitude = null;
  envelope.result.nodes.push({node_id: 'J', node_type: 'junction', latitude: null, longitude: null, connector_types: []});
  const data = adaptSolverResponse(envelope);
  assert.equal(data.NODES[0].lat, null);
  assert.equal(data.NODES[0].lng, null);
  assert.equal(data.NODES.at(-1).type, 'junction');
});

test('no incumbent preserves unknown delivery, energy and feasibility instead of fabricated zero', () => {
  for (const status of ['no_solution', 'unavailable', 'error']) {
    const envelope = response();
    Object.assign(envelope.result, {status, has_solution: false, routes: [], served_count: null, unserved_visit_ids: [], total_energy_kwh: null});
    envelope.result.validation.feasible = null;
    const {RUN_INFO, ROUTES} = adaptSolverResponse(envelope);
    assert.equal(RUN_INFO.hasSolution, false);
    assert.equal(RUN_INFO.servedCount, null);
    assert.equal(RUN_INFO.totalVisits, 2);
    assert.equal(RUN_INFO.feasible, null);
    assert.deepEqual(ROUTES, []);
  }
});

test('a no-solution envelope cannot also claim deliveries or feasibility', () => {
  const envelope = response();
  Object.assign(envelope.result, {status: 'no_solution', has_solution: false, routes: [], served_count: null, unserved_visit_ids: []});
  assert.throws(() => adaptSolverResponse(envelope), /sin solución|has_solution/);
});

test('native phase certificates preserve per-phase bounds and never combine gaps', () => {
  const envelope = response();
  envelope.result.phases = [{name: 'deliveries', sense: 'maximize', status: 'ok', termination_condition: 'timelimit', has_solution: true, proven_optimal: false, incumbent: 1, best_bound: 2, absolute_gap: 1, relative_gap: .5, runtime_seconds: 2}];
  assert.deepEqual(adaptSolverResponse(envelope).RUN_INFO.phases, envelope.result.phases);
  envelope.result.phases[0].best_bound = Infinity;
  assert.throws(() => adaptSolverResponse(envelope), /phases/);
});
