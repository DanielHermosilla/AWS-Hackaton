import test from 'node:test';
import assert from 'node:assert/strict';
import { nativeRunResult, resultSections, stopFacts } from '../shared/solver-output.js';
import { parseInstanceFile } from '../shared/solver-input.js';
import { readFileSync } from 'node:fs';
import { adaptSolverResponse } from '../shared/solver-adapter.js';

const native = () => ({
  schema_version: '1.0', run_id: 'native-id', status: 'feasible',
  solve: {used_solver: 'scip-routes', solver_version: '10.0.0'},
  kpis: {
    served_deliveries: 0, total_deliveries: 1, net_battery_energy_kwh: -0.25,
    charged_to_battery_kwh: 0, charging_stops: 0, minimum_battery_kwh: 1,
    distance_km: 2, grid_energy_kwh: null, operational_duration_seconds: 3580,
    time_saved_seconds: null, co2e_saved_kg: null,
    unavailable_reasons: {grid_energy_kwh: 'Sin pérdidas modeladas.', co2e_saved_kg: 'Faltan factores.'}
  },
  runtime_seconds: {resolution_including_model: 2, validation: 0.25, total: 2.3, llm: 0},
  validation: {feasible: true, violations: [], checks: {battery: true, charging: true}},
  tuning: {status: 'disabled', reason: 'Sin llamadas AWS.'},
  future_field: {opaque: ['sí', null, -2]}
});
const envelope = result => ({
  api_version: '3.0', result: {run_id: 'web-id', raw: {result},
    validation: {feasible: true, scope: 'Modelo declarado', violations: []},
    runtime_seconds: {preparation: .02, solver: 2, total: 2.4},
    metadata: {native_status: 'feasible', lexicographic_optimal: false, provider_commit: '6242035'},
    phases: [], warnings: [], assumptions: []}
});
const row = (sections, label) => sections.flatMap(section => section.rows || []).find(item => item.label === label);

test('native export keeps the entire original object, including future fields, without rewriting it', () => {
  const original = native();
  const before = structuredClone(original);
  assert.equal(nativeRunResult(envelope(original)), original);
  assert.deepEqual(JSON.parse(JSON.stringify(nativeRunResult(envelope(original)))), before);
  resultSections(envelope(original).result);
  assert.deepEqual(original, before);
  assert.equal(nativeRunResult(envelope({schema_version: '1.0', nodes: [], arcs: []})), null);
});

test('native KPI presentation preserves zero, signed energy, null reasons and operational time', () => {
  const sections = resultSections(envelope(native()).result);
  assert.equal(row(sections, 'Entregas planificadas').value, '0');
  assert.equal(row(sections, 'Paradas de recarga').value, '0');
  assert.equal(row(sections, 'Energía neta de batería').value, '-0,25 kWh');
  assert.equal(row(sections, 'Electricidad de la red').value, 'No disponible');
  assert.equal(row(sections, 'Electricidad de la red').reason, 'Sin pérdidas modeladas.');
  assert.match(row(sections, 'Tiempo hasta el último retorno').value, /3[.\s]?580 s/);
  assert.equal(row(sections, 'Batería').value, 'Cumple');
  assert.equal(row(sections, 'Resolución, incluido el modelo').value, '2 s');
  assert.equal(row(sections, 'Comprobación independiente').value, '0,25 s');
});

test('no native metrics remain unavailable, never inferred from routes or solver time', () => {
  const result = envelope(native()).result;
  result.raw.result.kpis = {};
  result.routes = [{energy_kwh: 99, steps: [{charge_kwh: 0.000001}]}];
  const sections = resultSections(result);
  assert.equal(row(sections, 'Paradas de recarga').value, 'No disponible');
  assert.equal(row(sections, 'Tiempo hasta el último retorno').value, 'No disponible');
});

test('an invalid candidate keeps its solver trace without presenting optimality as a valid certificate', () => {
  const result = envelope(native()).result;
  result.validation.feasible = false;
  result.metadata.lexicographic_optimal = true;
  result.raw.result.status = 'invalid_solution';
  result.raw.result.kpis.served_deliveries = null;
  const sections = resultSections(result);
  assert.equal(row(sections, 'Entregas planificadas').value, 'No disponible');
  assert.equal(row(sections, 'Optimalidad lexicográfica reportada por el solver').value, 'Sí');
  assert.ok(sections.flatMap(section => section.notes).some(note => /rechazada.*independiente/.test(note)));
  assert.equal(row(sections, 'Óptimo lexicográfico demostrado'), undefined);
});

test('step facts label outgoing energy and native seconds without losing signed or zero values', () => {
  const facts = stopFacts({
    nextNodeId: 'C|ñ', predictedArcEnergyKwh: -2, effectiveArcEnergyKwh: -1,
    arrivalSeconds: 0, serviceStartSeconds: 0, departureSeconds: 30,
    serviceDurationSeconds: 30, chargingDurationSeconds: 0, travelTimeSeconds: 60
  });
  assert.deepEqual(facts.slice(0, 3), [
    {label: 'Siguiente nodo', value: 'C|ñ'},
    {label: 'Energía prevista al siguiente nodo', value: '-2 kWh'},
    {label: 'Energía efectiva al siguiente nodo', value: '-1 kWh'}
  ]);
  assert.ok(facts.some(item => item.label === 'Llegada desde t=0' && item.value === '0 s'));
  assert.deepEqual(stopFacts({nextNodeId: null}), []);
});

test('native RunResult receives an actionable message rather than being mistaken for ProblemInstance', () => {
  assert.throws(() => parseInstanceFile(JSON.stringify(native()), 'resultado-nativo.json'),
    /resultado.*instancia.*ejecución completa/i);
});

test('real SCIP operational output crosses HTTP and UI without losing native values', () => {
  const response = JSON.parse(readFileSync(new URL('../../backend/fixtures/native-operations-response.json', import.meta.url)));
  const before = structuredClone(response);
  const {RUN_INFO, ROUTES} = adaptSolverResponse(response);
  const native = nativeRunResult(response);
  assert.deepEqual(RUN_INFO.kpis, native.kpis);
  assert.deepEqual(RUN_INFO.operations, native.operations);
  assert.deepEqual(RUN_INFO.validationChecks, native.validation.checks);
  assert.deepEqual(RUN_INFO.tuning, native.tuning);
  assert.equal(RUN_INFO.kpis.charging_stops, 1);
  assert.equal(RUN_INFO.kpis.operational_duration_seconds, 3580);
  assert.equal(RUN_INFO.kpis.charged_to_battery_kwh, 9);
  assert.equal(RUN_INFO.kpis.grid_energy_kwh, 10);
  for (const route of ROUTES) {
    const original = native.solve.solution.routes.find(item => item.vehicle_id === route.vehicleId);
    assert.equal(route.durationSeconds, original.duration_seconds);
    route.stops.forEach((stop, index) => {
      for (const [ui, key] of Object.entries({
        nextNodeId: 'next_node_id', predictedArcEnergyKwh: 'predicted_arc_energy_kwh',
        effectiveArcEnergyKwh: 'effective_arc_energy_kwh', arrivalSeconds: 'arrival_seconds',
        serviceStartSeconds: 'service_start_seconds', departureSeconds: 'departure_seconds',
        serviceDurationSeconds: 'service_duration_seconds', chargingDurationSeconds: 'charging_duration_seconds',
        travelTimeSeconds: 'travel_time_seconds'
      })) assert.equal(stop[ui], original.steps[index][key]);
    });
  }
  assert.deepEqual(response, before);
  assert.deepEqual(JSON.parse(JSON.stringify(nativeRunResult(response))), before.result.raw.result);
});

test('malformed native step timings and next-node references fail at the presentation boundary', () => {
  const original = JSON.parse(readFileSync(new URL('../../backend/fixtures/native-operations-response.json', import.meta.url)));
  for (const [key, value] of [['arrival_seconds', -1], ['travel_time_seconds', '60'], ['next_node_id', 'unknown-node']]) {
    const copy = structuredClone(original);
    copy.result.routes[0].steps[0][key] = value;
    assert.throws(() => adaptSolverResponse(copy), new RegExp(key));
  }
});
