import assert from 'node:assert/strict';
import {test} from 'node:test';
import {createHistoryClient, validateHistoryFile, MAX_HISTORY_BYTES, MAX_HISTORY_JSON_BYTES} from '../shared/history-client.js';
import {createSyntheticPreparation, makePrepareRequest, parseInstanceFile, inputFormValues} from '../shared/solver-input.js';
import {createSolverClient} from '../shared/solver-client.js';
import {readFile} from 'node:fs/promises';

test('history selection has its own bounded CSV/JSON contract', () => {
  validateHistoryFile({name: 'Viajes.csv', size: 100_000_000});
  validateHistoryFile({name: 'historico.csv', size: 3 * 1024 ** 3});
  validateHistoryFile({name: 'historico.csv', size: MAX_HISTORY_BYTES});
  validateHistoryFile({name: 'historico.JSON', size: MAX_HISTORY_JSON_BYTES});
  assert.throws(() => validateHistoryFile({name: 'archivo.csv', size: 0}), /vacío/);
  assert.throws(() => validateHistoryFile({name: 'archivo.csv', size: MAX_HISTORY_BYTES + 1}), /4 GiB/);
  assert.throws(() => validateHistoryFile({name: 'archivo.json', size: MAX_HISTORY_JSON_BYTES + 1}), /CSV/);
  assert.throws(() => validateHistoryFile({name: 'programa.py', size: 400}), /CSV o JSON/);
});

test('only explicitly selected ready history references enter a preparation, never native physics', () => {
  const preparation = createSyntheticPreparation({clients: 2, chargers: 1});
  preparation.energy_profile_id = 'profile-original';
  const input = parseInstanceFile(JSON.stringify(preparation), 'entrada.json');
  const values = inputFormValues(input);
  assert.equal(makePrepareRequest(input, {...values, energy_profile_id: 'new-profile'}).energy_profile_id, 'new-profile');
  assert.equal('energy_profile_id' in makePrepareRequest(input, {...values, energy_profile_id: null}), false);
  assert.equal('energy_profile_id' in makePrepareRequest(input, values), false);
  assert.throws(() => makePrepareRequest({instance: {}}, values), /nativa/);
  assert.throws(() => parseInstanceFile(JSON.stringify({...preparation, energy_profile_id: {secret: 'x'}}), 'entrada.json'), /identificador/);
});

test('historical simulation retains origin and applies the chosen consumption margin exactly once', () => {
  const preparation = createSyntheticPreparation({clients: 2, chargers: 1});
  preparation.scenario = {kind: 'hackathon_simulation', dataset: 'competition', seed: 12};
  preparation.operations = {energy_margin_fraction: .1, service_seconds: 45};
  const input = parseInstanceFile(JSON.stringify(preparation), 'variante.json');
  const values = inputFormValues(input);
  assert.equal(values.energy_margin_percent, 10);
  const request = makePrepareRequest(input, {...values, energy_margin_percent: '15', energy_profile_id: 'ev'});
  assert.deepEqual(request.scenario, preparation.scenario);
  assert.deepEqual(request.operations, {energy_margin_fraction: .15, service_seconds: 45});
  assert.equal(request.energy_profile_id, 'ev');
  assert.equal(inputFormValues({prepareRequest: request}).energy_margin_percent, 15);
  assert.equal(makePrepareRequest(input, {...values, energy_margin_percent: 0}).operations.energy_margin_fraction, 0);
  assert.throws(() => makePrepareRequest(input, {...values, energy_margin_percent: -1}), /margen/i);
  assert.equal(preparation.operations.energy_margin_fraction, .1);
});

test('connection secrets occur only in a POST body and service errors never echo them', async () => {
  const calls = [];
  const config = {mode: 'temporary', region: 'us-east-1', model_id: 'configured-model', access_key_id: 'ACCESS', secret_access_key: 'SECRET', session_token: 'TOKEN'};
  const client = createHistoryClient({fetchImpl: async (url, options) => {
    calls.push({url, options});
    return {status: 403, ok: false, json: async () => ({error: {message: JSON.stringify(config)}})};
  }});
  await assert.rejects(() => client.connect(config), error => !/SECRET|TOKEN|ACCESS/.test(error.message) && /conectar/.test(error.message));
  assert.equal(calls[0].url, '/bedrock/session');
  assert.equal(calls[0].options.method, 'POST');
  assert.equal(calls[0].options.cache, 'no-store');
  assert.deepEqual(JSON.parse(calls[0].options.body), config);
});

test('expired history is explained and cannot be silently reused', async () => {
  const client = createHistoryClient({fetchImpl: async () => ({status: 404, ok: false})});
  await assert.rejects(() => client.get('expired'), error => error.expired && /consumo supuesto/.test(error.message));
  await assert.rejects(() => client.connect({mode: 'configured'}), error => !error.expired && /conectar/.test(error.message));
});

test('upload sends the File as raw bytes with progress, without converting it into an instance', async () => {
  const progress = [];
  let xhr;
  const file = {name: 'viajes con ñ.csv', size: 12};
  const client = createHistoryClient({xhrFactory: () => xhr = {
    upload: {}, headers: {}, open(method, path) { this.method = method; this.path = path; },
    setRequestHeader(name, value) { this.headers[name] = value; },
    send(body) {
      this.body = body; this.upload.onprogress({lengthComputable: true, loaded: 12, total: 12});
      this.status = 200; this.responseText = JSON.stringify({api_version: '3.0', profile: {profile_id: 'opaque-123', status: 'ready'}});
      this.onload();
    },
  }});
  const profile = await client.upload(file, {onProgress: value => progress.push(value)});
  assert.equal(xhr.body, file);
  assert.equal(xhr.path, '/history/upload');
  assert.equal(xhr.headers['Content-Type'], 'application/octet-stream');
  assert.equal(xhr.headers['X-History-Filename'], encodeURIComponent(file.name));
  assert.deepEqual(progress, [1]);
  assert.equal(profile.profile_id, 'opaque-123');
});

test('preparation coverage reaches display callback without modifying native solve request', async () => {
  const request = JSON.parse(await readFile(new URL('../../backend/fixtures/native-request.json', import.meta.url)));
  const coverage = {summary: {calibrated_arc_count: 2, road_arc_count: 8}};
  const calls = [];
  let seen;
  const client = createSolverClient({fetchImpl: async (url, options) => {
    calls.push(JSON.parse(options.body));
    return {ok: true, json: async () => url === '/prepare'
      ? {api_version: '3.0', instance: request.instance, preparation: {energy_profile: coverage}}
      : {result: {run_id: 'fixture'}}};
  }, onPrepared(prepared, current, envelope) { seen = envelope.preparation.energy_profile; }});
  await client.solve({api_version: '3.0', solver: request.solver}, {prepareRequest: {energy_profile_id: 'opaque'}});
  assert.deepEqual(seen, coverage);
  assert.deepEqual(calls[1].instance, request.instance);
  assert.equal('preparation' in calls[1], false);
});
