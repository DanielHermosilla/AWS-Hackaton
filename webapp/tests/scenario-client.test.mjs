import assert from 'node:assert/strict';
import {test} from 'node:test';
import {loadHackathonScenario, loadHistoricalCase} from '../shared/scenario-client.js';

test('challenge scenario preserves real coordinates and charger metadata', async () => {
  const scenario = {nodes: [
    {node_id: 'B', node_type: 'base', latitude: 42.27708, longitude: -83.76281},
    {node_id: 'F', node_type: 'charger', latitude: 42.28, longitude: -83.76, connector_types: 'J1772;CHAdeMO', max_power_kw: 50},
  ]};
  let requested;
  const result = await loadHackathonScenario('competition', async url => {
    requested = url;
    return {ok: true, json: async () => ({api_version: '3.0', scenario})};
  });
  assert.equal(requested, '/scenarios/hackathon?dataset=competition');
  assert.deepEqual(result, scenario);
});

test('missing local dataset is actionable and never replaced with invented nodes', async () => {
  await assert.rejects(() => loadHackathonScenario('competition', async () => ({
    ok: false, json: async () => ({error: {message: 'Falta competition_routing_nodes.csv en data/ del servidor.'}}),
  })), /Falta competition/);
  await assert.rejects(() => loadHackathonScenario('../secret'), /Elige/);
});

test('complete case loads local history and variants explicitly reuse the selected profile', async () => {
  const calls = [], profile = {profile_id: 'local-ev', status: 'ready'};
  const scenario = {nodes: [{node_id: 'B', node_type: 'base', latitude: 42.27708, longitude: -83.76281}]};
  const fetch = async (url, options) => {
    calls.push({url, options});
    return {ok: true, json: async () => ({api_version: '3.0', scenario, profile})};
  };
  assert.equal((await loadHistoricalCase({}, fetch)).profile.profile_id, 'local-ev');
  assert.deepEqual(JSON.parse(calls[0].options.body), {dataset: 'competition'});
  const simulation = {customers: 25, chargers: 65, seed: 12};
  await loadHistoricalCase({dataset: 'evaluation', simulation, energy_profile_id: 'local-ev'}, fetch);
  assert.equal(calls[1].url, '/scenarios/hackathon');
  assert.equal(calls[1].options.method, 'POST');
  assert.deepEqual(JSON.parse(calls[1].options.body), {
    dataset: 'evaluation', simulation, energy_profile_id: 'local-ev',
  });
  await assert.rejects(() => loadHistoricalCase({}, async () => ({
    ok: true, json: async () => ({api_version: '3.0', scenario, profile: {...profile, status: 'error'}}),
  })), /histórico/);
});
