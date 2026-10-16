import test from 'node:test';
import assert from 'node:assert/strict';
import * as inputs from '../shared/solver-input.js';
import { createSolverClient } from '../shared/solver-client.js';

test('synthetic controls generate the requested services and preserve their synthetic network', () => {
  assert.equal(typeof inputs.createSyntheticPreparation, 'function');
  const preparation = inputs.createSyntheticPreparation({clients: 2, chargers: 0});
  assert.equal(preparation.network_mode, 'haversine');
  assert.equal(preparation.nodes.filter(n => n.node_type === 'visit').length, 2);
  assert.equal(preparation.nodes.filter(n => n.node_type === 'charger').length, 0);
  assert.deepEqual(inputs.createSyntheticPreparation({clients: 2, chargers: 0}), preparation);
  assert.equal(inputs.createSyntheticPreparation({clients: 20, chargers: 60}).nodes.length, 81);
  assert.throws(() => inputs.createSyntheticPreparation({clients: 199, chargers: 1}), /200/);
  assert.throws(() => inputs.createSyntheticPreparation({clients: 2.5, chargers: 0}), /entero/);
});

test('gap and seed survive solve requests, export reload and form restoration', () => {
  const instance = {schema_version: '1.0', nodes: [{node_id: 'B', node_type: 'base'}], arcs: []};
  const request = inputs.makeSolveRequest({instance}, 23, 'deterministic', .012, 17);
  assert.equal(request.solver.energy_relative_gap, .012);
  assert.equal(request.solver.random_seed, 17);
  const restored = inputs.parseInstanceFile(JSON.stringify(request), 'instance.json');
  const values = inputs.inputFormValues(restored);
  assert.equal(values.energy_relative_gap, .012);
  assert.equal(values.random_seed, 17);
  assert.equal(values.time_limit_seconds, 23);
  assert.equal(values.search_policy, 'deterministic');
  assert.equal(values.battery_capacity_kwh, 24);
  assert.equal(values.reserve_kwh, 2.4);
  assert.equal(values.initial_soc, .6);
  assert.deepEqual(restored.instance, instance, 'form defaults must not rewrite the original instance');
});

test('invalid seed and gap are rejected before transport', () => {
  for (const seed of [-1, 1.5, 2_000_000_001, true, '']) {
    assert.throws(() => inputs.solverSettings(10, 'standard', .005, seed), /semilla/i);
  }
  for (const gap of [-1, 1.1, NaN, true, '']) {
    assert.throws(() => inputs.solverSettings(10, 'standard', gap, 0), /gap|tolerancia/i);
  }
});

test('eVED telemetry is rejected with instructions for the correct input', () => {
  assert.throws(() => inputs.parseInstanceFile(
    'VehId,Trip,Timestamp(ms),Latitude[deg],Longitude[deg]\n1,2,3,42,-83', 'eVED_EV.csv'
  ), /histórico.*eVED.*Consumo con históricos.*CSV de ubicaciones/i);
});

test('connection failure does not expose beta wording to the operator', async () => {
  const changes = [];
  const client = createSolverClient({
    fetchImpl: async () => { throw new TypeError('Failed to fetch'); },
    onChange: value => changes.push(value),
  });
  await client.solve({});
  assert.match(changes.at(-1).message, /servidor/);
  assert.doesNotMatch(changes.at(-1).message, /beta/);
});
