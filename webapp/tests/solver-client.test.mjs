import test from 'node:test';
import assert from 'node:assert/strict';
import { createSolverClient, getSavedRun } from '../shared/solver-client.js';
import { parseInstanceFile, makeSolveRequest } from '../shared/solver-input.js';

const header = 'node_id,node_type,latitude,longitude,address,network,total_ports,dc_fast_ports,level2_ports,connector_types,max_power_kw';
const csv = `\ufeff${header}\r\nBASE#fin,base,42,-83,"Depósito, norte",,,,,,\r\n"V|ñ",visit,42.001,-83.002,"Tienda ""Sur""",,,,,,\r\n`;
const fleet = {num_vehicles: 2, battery_capacity_kwh: 10, reserve_kwh: 1, initial_soc: .6, consumption_kwh_km: 1};
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return {promise, resolve}; };
const response = body => ({ok: true, status: 200, json: async () => body});

test('CSV preserves BOM, quoted commas, escaped quotes and opaque identifiers', () => {
  const input = parseInstanceFile(csv, 'nodos.csv');
  assert.equal(input.nodes[0].node_id, 'BASE#fin');
  assert.equal(input.nodes[0].address, 'Depósito, norte');
  assert.equal(input.nodes[1].node_id, 'V|ñ');
  assert.equal(input.nodes[1].address, 'Tienda "Sur"');
  assert.equal(input.nodes[1].total_ports, undefined);
  assert.equal(makeSolveRequest(input, fleet, 10).network_mode, 'haversine');
});

test('CSV rejects duplicate IDs, malformed quotes, wrong columns and nonfinite coordinates', () => {
  assert.throws(() => parseInstanceFile(csv.replace('"V|ñ"', 'BASE#fin'), 'x.csv'), /repetido/i);
  assert.throws(() => parseInstanceFile(csv + '"incompleto', 'x.csv'), /comillas/i);
  assert.throws(() => parseInstanceFile(`${header}\nBASE,base,42,-83\n`, 'x.csv'), /columnas/i);
  assert.throws(() => parseInstanceFile(csv.replace('42.001', 'Infinity'), 'x.csv'), /latitud/i);
});

test('configuration is explicit and physically consistent before solve', () => {
  const input = parseInstanceFile(csv, 'x.csv');
  assert.throws(() => makeSolveRequest(input, {...fleet, battery_capacity_kwh: ''}, 10), /capacidad/i);
  assert.throws(() => makeSolveRequest(input, {...fleet, reserve_kwh: 8}, 10), /reserva/i);
  assert.throws(() => makeSolveRequest(input, fleet, Infinity), /tiempo/i);
  assert.equal(makeSolveRequest(input, fleet, 10).fleet.initial_soc, .6);
});

test('exported request and result reload without losing parameters or provenance', () => {
  const request = makeSolveRequest(parseInstanceFile(csv, 'x.csv'), fleet, 10);
  const imported = parseInstanceFile(JSON.stringify({schema_version: 'zmd.integration-beta.instance/1', request}), 'x.json');
  assert.deepEqual(imported.request, request);
  const fromResult = parseInstanceFile(JSON.stringify({api_version: '2.0-beta.1', result: {raw: {input: request}}}), 'resultado.json');
  assert.deepEqual(fromResult.request, request);
  const fromAttempt = parseInstanceFile(JSON.stringify({schema_version: 'zmd.integration-beta.attempt/1', request, status: 'error'}), 'intento.json');
  assert.deepEqual(fromAttempt.request, request);
});

test('a late response cannot overwrite a newer execution', async () => {
  const a = deferred(), b = deferred(), accepted = [];
  // Fetch order must be independent of completion.
  let calls = 0;
  const ordered = createSolverClient({fetchImpl: () => (++calls === 1 ? a.promise : b.promise), onResult: value => accepted.push(value)});
  const first = ordered.solve({id: 'a'});
  const second = ordered.solve({id: 'b'});
  b.resolve(response({result: {run_id: 'b'}}));
  await second;
  a.resolve(response({result: {run_id: 'a'}}));
  await first;
  assert.deepEqual(accepted.map(x => x.result.run_id), ['b']);
});

test('editing invalidates the response even if abort does not stop the server', async () => {
  const pending = deferred(), accepted = [];
  const client = createSolverClient({fetchImpl: () => pending.promise, onResult: value => accepted.push(value)});
  const solve = client.solve({});
  client.invalidate();
  pending.resolve(response({result: {run_id: 'old'}}));
  await solve;
  assert.deepEqual(accepted, []);
});

test('HTTP failure, corrupt JSON, and abort are distinct recoverable states', async () => {
  const states = [];
  const client = createSolverClient({fetchImpl: async () => ({ok: false, status: 422, json: async () => ({error: {message: 'No se encontró solución.'}})}), onChange: s => states.push(s)});
  await client.solve({});
  assert.equal(states.at(-1).status, 'error');
  assert.match(states.at(-1).message, /No se encontró solución/);
  assert.deepEqual(states.at(-1).response, {error: {message: 'No se encontró solución.'}});
  const corrupt = createSolverClient({fetchImpl: async () => ({ok: true, json: async () => { throw new Error('bad JSON'); }}), onChange: s => states.push(s)});
  await corrupt.solve({});
  assert.match(states.at(-1).message, /JSON/i);
});

test('missing saved run never falls back to sample data', async () => {
  await assert.rejects(getSavedRun('expired', async () => ({ok: false, status: 404, json: async () => ({error: {message: 'Ejecución expirada'}})})), /expirada/);
});

test('asynchronous response validation can check currency again before saving', async () => {
  const validation = deferred(), started = deferred(), accepted = [];
  let guard;
  const client = createSolverClient({
    fetchImpl: async () => response({result: {run_id: 'old'}}),
    onResult: async (value, isCurrent) => { guard = isCurrent; started.resolve(); await validation.promise; if (isCurrent()) accepted.push(value); },
  });
  const solve = client.solve({});
  await started.promise;
  assert.equal(typeof guard, 'function');
  client.invalidate();
  validation.resolve();
  await solve;
  assert.deepEqual(accepted, []);
});

test('unsupported imported configuration is rejected instead of silently discarded', () => {
  const request = makeSolveRequest(parseInstanceFile(csv, 'x.csv'), fleet, 10);
  assert.throws(() => parseInstanceFile(JSON.stringify({...request, movement_limit: 6}), 'x.json'), /movement_limit/);
  assert.throws(() => parseInstanceFile(JSON.stringify({...request, solver: {...request.solver, mip_gap: .1}}), 'x.json'), /mip_gap/);
  assert.throws(() => parseInstanceFile(JSON.stringify({...request, nodes: undefined, prepared: {}, network_mode: 'haversine'}), 'x.json'), /network_mode/);
  const optionalSolver = {...request}; delete optionalSolver.solver;
  assert.doesNotThrow(() => parseInstanceFile(JSON.stringify(optionalSolver), 'x.json'));
});

test('nullable optional CSV-schema fields roundtrip and fleet limits match the service', () => {
  const request = makeSolveRequest(parseInstanceFile(csv, 'x.csv'), fleet, 10);
  Object.assign(request.nodes[1], {total_ports: null, dc_fast_ports: null, level2_ports: null, max_power_kw: null});
  assert.doesNotThrow(() => parseInstanceFile(JSON.stringify(request), 'x.json'));
  assert.throws(() => makeSolveRequest(parseInstanceFile(csv, 'x.csv'), {...fleet, num_vehicles: 21}, 10), /20/);
});

test('numeric CSV fields in API downloads remain reusable without changing original input', () => {
  const request = makeSolveRequest(parseInstanceFile(csv, 'x.csv'), fleet, 10);
  request.nodes[0].latitude = '42';
  request.nodes[0].total_ports = '';
  request.nodes[1].max_power_kw = '0';
  const input = parseInstanceFile(JSON.stringify(request), 'x.json');
  assert.equal(input.request.nodes[0].latitude, '42');
  request.nodes[0].latitude = true;
  assert.throws(() => parseInstanceFile(JSON.stringify(request), 'x.json'), /latitud/i);
});
