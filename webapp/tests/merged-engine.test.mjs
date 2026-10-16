import test from 'node:test';
import assert from 'node:assert/strict';
import {createSolverClient} from '../shared/solver-client.js';
import {parseInstanceFile, validateNativeInstance, solverSettings, SYNTHETIC_PREPARATION} from '../shared/solver-input.js';
import {resultSections} from '../shared/solver-output.js';

test('prepared street context is carried to solve without filesystem paths', async () => {
  const requests = [];
  const instance = {schema_version: '1.1', nodes: [], arcs: []};
  const client = createSolverClient({fetchImpl: async (url, options) => {
    requests.push([url, JSON.parse(options.body)]);
    return {ok: true, json: async () => url === '/prepare'
      ? {api_version: '3.0', instance, prepared_instance_id: 'server-context'}
      : {api_version: '3.0', result: {}}};
  }});
  await client.solve({solver: solverSettings(120, 'adaptive')}, {prepareRequest: SYNTHETIC_PREPARATION});
  assert.equal(requests[1][1].prepared_instance_id, 'server-context');
  assert.equal(requests[1][1].solver.search_policy, 'adaptive');
  assert.deepEqual(requests[1][1].instance, instance);
});

test('road execution downloads replay original preparation instead of an expired token', () => {
  const preparation = {...SYNTHETIC_PREPARATION, network_mode: 'road'};
  const envelope = {api_version: '3.0', result: {raw: {
    input: {api_version: '3.0', prepared_instance_id: 'expired', solver: solverSettings(60, 'adaptive')},
    prepare_request: preparation,
  }}};
  const input = parseInstanceFile(JSON.stringify(envelope), 'run.json');
  assert.equal(input.prepareRequest.network_mode, 'road');
  assert.equal(input.request.solver.search_policy, 'adaptive');
  assert.deepEqual(input.nodes, preparation.nodes);
});

test('resource paths preserve parallel and useful self arcs by identity', () => {
  const profile = {consumption_kwh: 1, minimum_departure_kwh: 2, maximum_arrival_kwh: 9};
  const instance = {schema_version: '1.1', nodes: [
    {node_id: '0', node_type: 'base'}, {node_id: 'C', node_type: 'visit'},
  ], provenance: {representation: {kind: 'resource_paths'}}, arcs: [
    {from_node_id: '0', to_node_id: 'C', energy_kwh: 1, arc_id: 'a', battery_profile: profile},
    {from_node_id: '0', to_node_id: 'C', energy_kwh: 2, arc_id: 'b', battery_profile: profile},
    {from_node_id: '0', to_node_id: '0', energy_kwh: -1, arc_id: 'c', battery_profile: profile},
  ]};
  assert.equal(validateNativeInstance(instance), instance);
  const bad = structuredClone(instance);
  bad.arcs[1].arc_id = 'a';
  assert.throws(() => validateNativeInstance(bad), /duplicados/);
});

test('energy tolerance and LLM applied/rejected decisions are visible separately', () => {
  const groups = resultSections({
    phases: [{name: 'energy', relative_gap: 0.002838, termination_condition: 'energy_gap_limit', proven_optimal: false}],
    tuning: {status: 'adaptive', model_id: 'us.openai.gpt-5.6-luna', calls: 2, applied_decisions: 1,
      decisions: [
        {call_index: 1, status: 'applied', effective_changes: {repair_strategy: {before: 'greedy', after: 'regret'}}, proposal: {rationale: 'Use resource repair.'}},
        {call_index: 2, status: 'not_applied', reason: 'decision_deadline'},
      ]},
  });
  assert(groups.find(g => g.title === 'Fase: minimizar energía').notes.some(n => n.includes('no acredita óptimo exacto')));
  assert(groups.find(g => g.title.includes('Decisión de IA 1')).rows.some(r => r.value.includes('regret')));
  assert(groups.find(g => g.title.includes('Decisión de IA 2')).notes.includes('decision_deadline'));
});
