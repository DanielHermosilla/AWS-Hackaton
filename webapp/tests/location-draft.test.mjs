import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createLocationDraft, readEditableSource, saveEditableSource, readEditableDraft, saveEditableDraft } from '../shared/location-draft.js';
import { SYNTHETIC_PREPARATION, makePrepareRequest } from '../shared/solver-input.js';

const source = () => {
  const prepareRequest = structuredClone(SYNTHETIC_PREPARATION);
  prepareRequest.nodes[1].node_id = 'Visita|ñ';
  prepareRequest.fleet.vehicle_connector_types = ['CHAdeMO'];
  prepareRequest.nodes.push({node_id: 'C /?# ñ', node_type: 'charger', latitude: 0, longitude: 0,
    address: 'Cargador', network: 'Red declarada', total_ports: 0, connector_types: 'CHAdeMO', max_power_kw: 0});
  return {nodes: prepareRequest.nodes, prepareRequest, request: {solver: {time_limit_seconds: 17}}};
};
const memory = () => {
  let value = null;
  return {getItem: () => value, setItem: (_, next) => {value = next;}, removeItem: () => {value = null;}};
};

test('editing and cancelling keep original nodes, metadata and preparation independent', () => {
  const input = source(), before = structuredClone(input), draft = createLocationDraft(input);
  draft.update('C /?# ñ', {latitude: '1.25', address: 'Nueva dirección'});
  assert.deepEqual(input, before);
  const snapshot = draft.nodes;
  snapshot[0].latitude = 55;
  assert.equal(draft.nodes[0].latitude, before.nodes[0].latitude);
  draft.cancel();
  assert.deepEqual(input, before);
  assert.throws(() => draft.commit(), /cerrad/i);
});

test('confirmation keeps opaque IDs and type, all untouched settings and zero coordinates', () => {
  const input = source(), draft = createLocationDraft(input);
  draft.update('Visita|ñ', {latitude: '0', longitude: '0', address: 'Dirección corregida'});
  assert.equal(draft.changed, true);
  const confirmed = draft.commit();
  const node = confirmed.nodes.find(node => node.node_id === 'Visita|ñ');
  assert.deepEqual(node, {...input.nodes[1], latitude: 0, longitude: 0, address: 'Dirección corregida'});
  assert.deepEqual(confirmed.prepareRequest.nodes, confirmed.nodes);
  assert.deepEqual(confirmed.prepareRequest.fleet, input.prepareRequest.fleet);
  assert.deepEqual(confirmed.request, input.request);
  assert.equal(makePrepareRequest(confirmed, confirmed.prepareRequest.fleet).nodes[1].longitude, 0);
  assert.notEqual(confirmed.nodes, input.nodes);
  assert.throws(() => draft.update('Visita|ñ', {latitude: 1}), /cerrad/i);
});

test('confirmation rejects absent, nonfinite and out-of-range coordinates without corrupting the source', () => {
  for (const [field, value] of [['latitude', ''], ['latitude', null], ['latitude', true],
    ['latitude', 'Infinity'], ['latitude', NaN], ['latitude', 91], ['longitude', -181]]) {
    const input = source(), before = structuredClone(input), draft = createLocationDraft(input);
    draft.update('Visita|ñ', {[field]: value});
    assert.throws(() => draft.commit(), /Latitud|Longitud/);
    assert.deepEqual(input, before);
  }
});

test('node identity, type and station metadata cannot be changed by a location patch', () => {
  const draft = createLocationDraft(source());
  for (const key of ['node_id', 'node_type', 'max_power_kw', '__proto__']) {
    assert.throws(() => draft.update('C /?# ñ', {[key]: 'other'}), /campo/i);
  }
  assert.throws(() => draft.update('missing', {latitude: 0}), /nodo/i);
});

test('confirming equivalent numeric coordinates does not count as an edit', () => {
  const input = source(), draft = createLocationDraft(input);
  draft.update('C /?# ñ', {latitude: '0.000', longitude: '0'});
  assert.equal(draft.changed, false);
  assert.deepEqual(draft.commit(), input);
});

test('native graph is inspectable, but never becomes an editable haversine preparation', async () => {
  const request = JSON.parse(await readFile(new URL('../../backend/fixtures/native-request.json', import.meta.url)));
  const input = {instance: request.instance, request}, before = structuredClone(input);
  const draft = createLocationDraft(input);
  assert.equal(draft.readOnly, true);
  assert.equal(draft.nodes[0].latitude, undefined);
  assert.throws(() => draft.update(draft.nodes[0].node_id, {latitude: 0, longitude: 0}), /red nativa/i);
  assert.throws(() => draft.commit(), /red nativa/i);
  assert.deepEqual(input, before);
});

test('editable source survives only for its exact execution, and native execution clears it', () => {
  const storage = memory(), input = source();
  saveEditableSource('run-1', input.prepareRequest, storage);
  assert.deepEqual(readEditableSource('run-1', storage).prepareRequest, input.prepareRequest);
  assert.equal(readEditableSource('run-2', storage), null);
  saveEditableSource('native', null, storage);
  assert.equal(readEditableSource('run-1', storage), null);
});

test('corrupt or unavailable saved source never changes native graph protection', () => {
  assert.equal(readEditableSource('run-1', {getItem: () => '{'}), null);
  assert.equal(readEditableSource('run-1', {getItem: () => JSON.stringify({runId: 'run-1', prepareRequest: {instance: {}}})}), null);
  assert.equal(readEditableSource('run-1', {getItem: () => {throw new Error('blocked');}}), null);
  assert.equal(saveEditableSource('run-1', source().prepareRequest, {setItem: () => {throw new Error('blocked');}}), false);
});

test('a saved editable source must also match the returned native locations', () => {
  const storage = memory(), input = source();
  saveEditableSource('run-1', input.prepareRequest, storage);
  const instance = {nodes: structuredClone(input.nodes)};
  assert.ok(readEditableSource('run-1', storage, instance));
  instance.nodes[1].longitude += .1;
  assert.equal(readEditableSource('run-1', storage, instance), null);
});

test('a pending draft persists before any run and keeps incomplete physical fields and solver budget', () => {
  const storage = memory(), input = source(), fields = {battery_capacity_kwh: '', reserve_kwh: '1.5', time_limit_seconds: '4'};
  assert.equal(saveEditableDraft('draft-1', input, fields, storage), true);
  assert.deepEqual(readEditableDraft('draft-1', storage), {input, fields});
  assert.equal(readEditableDraft('draft-2', storage), null);
  assert.equal(readEditableDraft(null, storage), null);
});

test('pending draft rejects malformed native graphs, corruption and storage quota failure', () => {
  assert.equal(saveEditableDraft('draft-1', {instance: {}}, {}, memory()), false);
  assert.equal(saveEditableDraft('draft-1', source(), {}, {setItem: () => {throw new Error('QuotaExceededError');}}), false);
  assert.equal(readEditableDraft('draft-1', {getItem: () => '{'}), null);
});

test('draft preserves engine settings and network choice across navigation', () => {
  const storage = memory(), input = source();
  const fields = {search_policy: 'standard', network_mode: 'haversine', energy_gap_percent: '2.5', random_seed: '17'};
  assert.equal(saveEditableDraft('engine-draft', input, fields, storage), true);
  assert.deepEqual(readEditableDraft('engine-draft', storage), {input, fields});
});

test('native draft retains engine edits without granting location editing', async () => {
  const request = JSON.parse(await readFile(new URL('../../backend/fixtures/native-request.json', import.meta.url)));
  const input = {instance: request.instance, request}, storage = memory();
  const fields = {time_limit_seconds: '9', search_policy: 'standard', energy_gap_percent: '0.1', random_seed: '41'};
  assert.equal(saveEditableDraft('native-draft', input, fields, storage), true);
  const restored = readEditableDraft('native-draft', storage);
  assert.deepEqual(restored, {input, fields});
  assert.equal(createLocationDraft(restored.input).readOnly, true);
});
