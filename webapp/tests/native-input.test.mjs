import test from 'node:test';
import assert from 'node:assert/strict';
import { parseInstanceFile, makePrepareRequest, makeSolveRequest } from '../shared/solver-input.js';
import { createSolverClient } from '../shared/solver-client.js';

const native = () => ({
  schema_version: '1.0', name: 'Native preserved',
  nodes: [
    {node_id: 'BASE', node_type: 'base'},
    {node_id: 'J|ñ', node_type: 'junction'},
    {node_id: 'A', node_type: 'visit'},
    {node_id: 'F', node_type: 'charger', connector_types: ['J1772']}
  ],
  arcs: [
    {from_node_id: 'BASE', to_node_id: 'J|ñ', energy_kwh: 1, distance_m: 120},
    {from_node_id: 'J|ñ', to_node_id: 'A', energy_kwh: -2, source_id: 'signed'},
    {from_node_id: 'A', to_node_id: 'BASE', energy_kwh: 2}
  ],
  parameters: {vehicle_count: 2, battery_capacity_kwh: 10, reserve_kwh: 1, initial_soc: .6, movement_limit: 3, vehicle_connector_types: ['J1772']},
  operations: {energy_margin_fraction: .1, disabled_charger_ids: ['F']},
  compatible_chargers: {vehicle_1: ['F'], vehicle_2: []},
  provenance: {kind: 'synthetic', note: '<not markup>', nested: {source: 'operator'}}
});
const csv = 'node_id,node_type,latitude,longitude\nBASE,base,42,-83\nA,visit,42.1,-83.1\n';
const fleet = {num_vehicles: 2, battery_capacity_kwh: 10, reserve_kwh: 1, initial_soc: .6, consumption_kwh_km: 1};
const response = body => ({ok: true, status: 200, json: async () => body});
const deferred = () => {let resolve; const promise = new Promise(r => {resolve = r;}); return {promise, resolve};};

test('native uploads reject duplicate physical keys before any value can be overwritten', () => {
  const text = JSON.stringify(native());
  for (const [field, duplicate] of [
    ['"battery_capacity_kwh":10', '"battery_capacity_kwh":10,"battery_capacity_kwh":20'],
    ['"energy_kwh":1', '"energy_kwh":1,"energy_kwh":-5'],
    ['"energy_margin_fraction":0.1', '"energy_margin_fraction":0.1,"energy_margin_fraction":0']
  ]) {
    assert.throws(() => parseInstanceFile(text.replace(field, duplicate), 'ambigua.json'),
      /claves JSON duplicadas.*una sola definición/i);
  }
});

test('escaped-equivalent keys are duplicates inside native objects', () => {
  const text = JSON.stringify(native());
  assert.throws(() => parseInstanceFile(text.replace('"battery_capacity_kwh":10',
    String.raw`"battery_capacity_kwh":10,"\u0062attery_capacity_kwh":20`), 'ambigua.json'),
  /claves JSON duplicadas/i);
  assert.throws(() => parseInstanceFile(text.replace('"source":"operator"',
    String.raw`"quote\"key":1,"quote\u0022key":2`), 'ambigua.json'),
  /claves JSON duplicadas/i);
});

test('the same key in separate objects and array entries preserves the original native input', () => {
  const original = native();
  original.provenance.records = [{source: 'first'}, {source: 'second', nested: {source: 'third'}}];
  original.provenance.empty = {};
  assert.deepEqual(parseInstanceFile(JSON.stringify(original), 'native.json').instance, original);
});

test('strings containing braces, key-like text and escaped quotes remain unchanged', () => {
  const original = native();
  original.provenance.note = String.raw`{"battery_capacity_kwh":10,"battery_capacity_kwh":20} · [}, {] · \"source\": "\\path"`;
  original.provenance.nested = {'quote"key': 'escaped \\ slash and " quote', tail: 'next'};
  assert.deepEqual(parseInstanceFile(JSON.stringify(original, null, 2), 'native.json').instance, original);
});

test('invalid JSON syntax still returns the existing actionable syntax error', () => {
  for (const text of [
    '{"schema_version":"1.0",}',
    '{"schema_version":"1.0","schema_version":"1.0",}',
    '{"schema_version":"1.0","schema_version":"1.0" "nodes":[]}',
    '{"schema_version":"1.0","provenance":{"note":"unfinished}}',
    String.raw`{"schema_version":"1.0","provenance":{"bad\qkey":1}}`
  ]) assert.throws(() => parseInstanceFile(text, 'invalid.json'), /no contiene JSON válido/i);
});

test('native JSON preserves every physical field including absent coordinates and signed arcs', () => {
  const original = native();
  const input = parseInstanceFile(JSON.stringify(original), 'native.json');
  const request = makeSolveRequest(input, 12);
  assert.deepEqual(request, {api_version: '3.0', instance: original, solver: {time_limit_seconds: 12}});
  assert.deepEqual(input.instance, original);
  assert.equal(input.instance.nodes[0].latitude, undefined);
});

test('canonical request, native export and API3 result reload without physics overrides', () => {
  const request = {api_version: '3.0', instance: native(), solver: {time_limit_seconds: 12}};
  for (const data of [request.instance, request, {api_version: '3.0', result: {raw: {input: request, instance: request.instance}}}]) {
    const input = parseInstanceFile(JSON.stringify(data), 'native.json');
    assert.deepEqual(makeSolveRequest(input, 12), request);
  }
});

test('omitted native parameters stay omitted until the backend applies its contract defaults', () => {
  const original = native();
  delete original.parameters;
  const input = parseInstanceFile(JSON.stringify(original), 'native-defaults.json');
  assert.deepEqual(makeSolveRequest(input, 10).instance, original);
  assert.equal(Object.hasOwn(makeSolveRequest(input, 10).instance, 'parameters'), false);
});

test('a preparation failure export restores the original solver budget and preparation input', () => {
  const prepareRequest = makePrepareRequest(parseInstanceFile(csv, 'nodes.csv'), fleet);
  const exported = {
    schema_version: 'zmd.integration-beta.attempt/2',
    request: {api_version: '3.0', solver: {time_limit_seconds: 42}},
    prepare_request: prepareRequest,
    stage: 'preparing',
    response: {api_version: '3.0', error: {code: 'preparation_failed', message: 'Preparation failed'}},
    status: 'error',
    message: 'Preparation failed',
    observed_at: '2026-10-15T12:00:00.000Z'
  };
  const restored = parseInstanceFile(JSON.stringify(exported), 'intento.json');
  assert.deepEqual(restored.request, exported.request);
  assert.deepEqual(restored.prepareRequest, prepareRequest);
  assert.deepEqual(makePrepareRequest(restored, restored.prepareRequest.fleet), prepareRequest);
});

test('a failed road solve restores preparation and settings without its temporary instance handle', () => {
  const prepareRequest = makePrepareRequest(parseInstanceFile(csv, 'nodes.csv'),
    {...fleet, network_mode: 'road', energy_margin_percent: 15});
  const solver = {time_limit_seconds: 42, search_policy: 'deterministic', energy_relative_gap: .005, random_seed: 17};
  const exported = {
    schema_version: 'zmd.integration-beta.attempt/2',
    request: {api_version: '3.0', instance: native(), prepared_instance_id: 'expired-preparation', solver},
    prepare_request: prepareRequest,
    stage: 'solving',
    response: {api_version: '3.0', error: {code: 'solver_failed', message: 'Solver failed'}},
    status: 'error'
  };
  const restored = parseInstanceFile(JSON.stringify(exported), 'intento-fallido-beta.json');
  assert.deepEqual(restored.nodes, prepareRequest.nodes);
  assert.deepEqual(restored.prepareRequest, prepareRequest);
  assert.deepEqual(restored.request, {api_version: '3.0', solver});
  assert.equal(restored.instance, undefined);
  assert.deepEqual(makePrepareRequest(restored, {...fleet, network_mode: 'road', energy_margin_percent: 15}), prepareRequest);
});

test('CSV creates only a prepare request; it never creates arcs or estimated energy in the UI', () => {
  const input = parseInstanceFile(csv, 'nodes.csv');
  const request = makePrepareRequest(input, fleet);
  assert.deepEqual(Object.keys(request).sort(), ['api_version', 'fleet', 'network_mode', 'nodes']);
  assert.equal(request.api_version, '3.0');
  assert.equal(request.network_mode, 'haversine');
  assert.equal(request.instance, undefined);
  assert.throws(() => makeSolveRequest(input, 10), /prepar/i);
});

test('old prepared provider, old API and old export wrappers are explicitly rejected', () => {
  for (const data of [
    {esquema: 'evrp.instancia_preparada/1', nodos: []},
    {api_version: '2.0-beta.1', nodes: []},
    {schema_version: 'zmd.integration-beta.instance/1', request: {}}
  ]) assert.throws(() => parseInstanceFile(JSON.stringify(data), 'old.json'), /no admitid|anterior/i);
});

test('native invalid references and unpaired coordinates are actionable without normalizing them', () => {
  const first = native(); first.nodes[0].latitude = 42;
  assert.throws(() => parseInstanceFile(JSON.stringify(first), 'x.json'), /coordenadas/i);
  const second = native(); second.arcs[0].to_node_id = 'missing';
  assert.throws(() => parseInstanceFile(JSON.stringify(second), 'x.json'), /referencia/i);
});

test('preparation completes before solve and the returned canonical instance is used exactly', async () => {
  const canonical = native(), calls = [], accepted = [];
  const client = createSolverClient({
    fetchImpl: async (url, options) => {
      calls.push({url, body: JSON.parse(options.body)});
      return response(url === '/prepare' ? {api_version: '3.0', instance: canonical} : {api_version: '3.0', result: {run_id: 'new'}});
    },
    onResult: value => accepted.push(value)
  });
  const prepareRequest = makePrepareRequest(parseInstanceFile(csv, 'nodes.csv'), fleet);
  await client.solve({api_version: '3.0', solver: {time_limit_seconds: 10}}, {prepareRequest});
  assert.deepEqual(calls.map(call => call.url), ['/prepare', '/solve']);
  assert.deepEqual(calls[1].body.instance, canonical);
  assert.equal(accepted.length, 1);
});

test('editing while preparation is in flight prevents launching the stale solve', async () => {
  const waiting = deferred(), calls = [];
  const client = createSolverClient({fetchImpl: (url) => {calls.push(url); return waiting.promise;}});
  const task = client.solve({api_version: '3.0', solver: {time_limit_seconds: 10}}, {prepareRequest: {api_version: '3.0', nodes: []}});
  client.invalidate();
  waiting.resolve(response({api_version: '3.0', instance: native()}));
  await task;
  assert.deepEqual(calls, ['/prepare']);
});

test('a malformed preparation never launches solve and retains a recoverable error', async () => {
  const calls = [], states = [];
  const client = createSolverClient({fetchImpl: async url => {calls.push(url); return response({api_version: '1.0', instance: native()});}, onChange: state => states.push(state)});
  await client.solve({api_version: '3.0', solver: {time_limit_seconds: 10}}, {prepareRequest: {api_version: '3.0'}});
  assert.deepEqual(calls, ['/prepare']);
  assert.equal(states.at(-1).status, 'error');
});
