import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {adaptSolverResponse} from '../shared/solver-adapter.js';
import {buildPlanSummary} from '../shared/plan-summary-model.js';
import {renderPlanSummary} from '../plan-summary.js';
const fixture = () => JSON.parse(readFileSync(new URL('../../backend/fixtures/native-operations-response.json', import.meta.url)));
const data = envelope => ({RAW_RESPONSE: envelope, DATA_SOURCE: 'solver', ...adaptSolverResponse(envelope)});
function summary(envelope = fixture(), options = {}) {
  return buildPlanSummary(data(envelope), {
    execution: {runId: envelope.result.run_id, stale: false, status: 'complete'}, ...options
  });
}
const row = (model, label) => model.sections.flatMap(section => section.rows).find(item => item.label === label);

test('summary keeps the exact run, native metrics, explicit service and source without changing the response', () => {
  const response = fixture();
  const before = structuredClone(response);
  const model = summary(response);
  assert.equal(model.available, true);
  assert.equal(model.runId, response.result.run_id);
  assert.equal(model.scenarioName, response.result.raw.result.instance_name);
  assert.equal(model.freshness.state, 'current');
  assert.equal(row(model, 'Energía neta de batería').value, '14 kWh');
  assert.equal(row(model, 'Electricidad de la red').value, '10 kWh');
  assert.equal(row(model, 'Paradas de recarga').value, '1');
  assert.match(row(model, 'Tiempo hasta el último retorno').value, /3[.\s]?580 s/);
  assert.equal(model.routes[0].steps[1].service, 'Entrega planificada');
  assert.deepEqual(model.routes[0].steps[1].delivered_visit_ids, ['A']);
  assert.equal(model.routes[0].steps[2].arrival_energy_kwh, 1);
  assert.equal(model.routes[0].steps[2].charge_kwh, 9);
  assert.equal(model.routes[0].durationSeconds, response.result.routes[0].duration_seconds);
  assert.deepEqual(model.assumptions, response.result.assumptions);
  assert.deepEqual(model.warnings, response.result.warnings);
  assert.deepEqual(response, before);
});

test('an edited, replaced, missing or running execution cannot label the saved run current', () => {
  const response = fixture();
  const runId = response.result.run_id;
  for (const execution of [
    {runId, stale: true}, {runId: 'a-new-run', stale: false}, null,
    {runId, stale: false, status: 'running'}, {runId, status: 'error'}
  ]) {
    const model = summary(response, {execution});
    assert.equal(model.freshness.state, 'stale');
    assert.match(model.freshness.title, /Resultado anterior/);
    assert.equal(model.runId, runId);
  }
  assert.equal(summary(response, {stale: true}).freshness.state, 'stale');
});

test('example, pending and expired execution explain absence without printing example KPIs', () => {
  for (const DATA_SOURCE of ['synthetic', 'local', 'pending']) {
    const model = buildPlanSummary({DATA_SOURCE, RAW_RESPONSE: null}, {});
    assert.equal(model.available, false);
    assert.equal(model.routes.length, 0);
    assert.equal(model.sections.length, 0);
    assert.match(model.message, /motor|calcular/);
  }
  const expired = buildPlanSummary(null, {error: new Error('Esta ejecución expiró.')});
  assert.equal(expired.available, false);
  assert.match(expired.message, /expiró/);
});

test('no incumbent keeps unknown metrics and pending demand distinct from zero or infeasibility', () => {
  const response = fixture();
  Object.assign(response.result, {status: 'no_solution', has_solution: false, routes: [],
    served_count: null, total_energy_kwh: null, unserved_visit_ids: []});
  response.result.validation = {feasible: null, scope: 'Sin solución que comprobar.', violations: [], checks: {}};
  response.result.kpis = {total_deliveries: 2, served_deliveries: null, net_battery_energy_kwh: null,
    unavailable_reasons: {served_deliveries: 'No hay incumbente.'}};
  const model = summary(response);
  assert.equal(model.status.label, 'Sin solución encontrada');
  assert.equal(row(model, 'Entregas planificadas').value, 'No disponible');
  assert.equal(row(model, 'Entregas planificadas').reason, 'No hay incumbente.');
  assert.equal(model.pending.available, false);
  assert.match(model.pending.message, /No se dispone.*pendientes/);
  assert.deepEqual(model.routes, []);
});

test('failed validation labels the candidate and its service as unvalidated even if the solver reports optimal', () => {
  const response = fixture();
  response.result.status = 'validation_failed';
  response.result.validation = {feasible: false, scope: 'Modelo declarado', violations: ['Reserva incumplida.'], checks: {battery: false}};
  response.result.kpis.served_deliveries = null;
  response.result.kpis.net_battery_energy_kwh = null;
  response.result.total_energy_kwh = null;
  for (const route of response.result.routes) route.energy_kwh = null;
  const model = summary(response);
  assert.match(model.status.label, /Validación fallida/);
  assert.match(model.routes[0].steps[1].service, /sin validar/);
  assert.match(model.solutionNote, /no acredita.*factible/);
  assert.equal(row(model, 'Energía neta de batería').value, 'No disponible');
  assert.ok(model.validation.notes.includes('Reserva incumplida.'));
});

test('zero and negative energy remain data; unavailable metrics are not re-estimated from route steps', () => {
  const response = fixture();
  response.result.kpis.net_battery_energy_kwh = -0.25;
  response.result.kpis.charging_stops = 0;
  response.result.kpis.grid_energy_kwh = null;
  response.result.kpis.unavailable_reasons.grid_energy_kwh = 'Sin pérdidas modeladas.';
  // Summary must use native KPIs, regardless of the illustrative route values.
  const model = summary(response);
  assert.equal(row(model, 'Energía neta de batería').value, '-0,25 kWh');
  assert.equal(row(model, 'Paradas de recarga').value, '0');
  assert.equal(row(model, 'Electricidad de la red').value, 'No disponible');
  assert.equal(row(model, 'Electricidad de la red').reason, 'Sin pérdidas modeladas.');
});

test('repeated visits preserve every occurrence and distinguish transit from explicit service', () => {
  const response = fixture();
  const route = response.result.routes[0];
  const first = {...route.steps[1], delivered_visit_ids: []};
  route.steps.splice(1, 0, first);
  route.steps.forEach((step, position) => { step.position = position; });
  const model = summary(response);
  const visits = model.routes[0].steps.filter(step => step.node_id === 'A');
  assert.equal(visits.length, 2);
  assert.deepEqual(visits.map(step => step.position), [1, 2]);
  assert.deepEqual(visits.map(step => step.service), ['Paso sin entrega', 'Entrega planificada']);
});

test('partial feasible result keeps pending IDs and phase certificates without inferring causes or a joint gap', () => {
  const response = fixture();
  const route = response.result.routes[0];
  route.served_visit_ids = ['A'];
  route.steps.find(step => step.node_id === 'B').delivered_visit_ids = [];
  Object.assign(response.result, {status: 'partial', served_count: 1, unserved_visit_ids: ['B']});
  response.result.kpis.served_deliveries = 1;
  response.result.phases[0].proven_optimal = false;
  response.result.metadata.lexicographic_optimal = false;
  const model = summary(response);
  assert.deepEqual(model.pending.items.map(item => item.id), ['B']);
  assert.match(model.pending.message, /no informa la causa/);
  assert.match(model.solutionNote, /condicionada/);
  assert.equal(model.phases.length, 2);
  assert.equal(model.phases[0].rows.find(item => item.label === 'Óptimo de fase reportado por el solver').value, 'No');
  assert.equal(model.phases[1].rows.find(item => item.label === 'Gap relativo (fracción)').value,
    response.result.phases[1].relative_gap.toLocaleString('es-CL', {maximumFractionDigits: 6}));
});

test('missing step batteries and route durations stay null; labels keep opaque IDs and long text', () => {
  const response = fixture();
  response.result.nodes.find(node => node.node_id === 'A').address = '<script>etiqueta</script> & dirección larga';
  response.result.routes[0].steps[1].arrival_energy_kwh = null;
  response.result.routes[0].duration_seconds = null;
  const model = summary(response);
  assert.equal(model.routes[0].steps[1].arrival_energy_kwh, null);
  assert.equal(model.routes[0].durationSeconds, null);
  assert.equal(model.routes[0].steps[1].label, '<script>etiqueta</script> & dirección larga');
  assert.equal(model.routes[0].steps[1].node_id, 'A');
});

test('summary markup escapes imported labels and retains table headings, units and unavailable reasons', () => {
  const response = fixture();
  response.result.nodes[1].address = '<img src=x onerror=alert(1)> & destino';
  response.result.kpis.grid_energy_kwh = null;
  response.result.kpis.unavailable_reasons.grid_energy_kwh = 'Falta <eficiencia>.';
  const html = renderPlanSummary(summary(response));
  assert.ok(!html.includes('<img src=x'));
  assert.ok(html.includes('&lt;img src=x onerror=alert(1)&gt; &amp; destino'));
  assert.ok(html.includes('Falta &lt;eficiencia&gt;.'));
  assert.match(html, /<th scope="col">Llegada.*kWh/);
  assert.match(html, /Paso sin entrega|Entrega planificada/);
  assert.ok(html.includes(response.result.run_id));
  assert.ok(html.includes(response.result.raw.result.instance_name));
  assert.ok(html.includes('Gap absoluto / relativo'));
  assert.ok(html.includes('Servicio por defecto: 60 s'));
  assert.ok(html.includes('Límite por ruta: 10.000 s'));
  assert.ok(!html.includes('<h2>Trazabilidad</h2>'));
  assert.match(html, /no confirman entregas realizadas/);
});

test('a single base step describes a vehicle staying at base instead of a departure', () => {
  const model = summary();
  const idleRoute = model.routes.find(route => route.steps.length === 1);
  assert.ok(idleRoute, 'fixture includes a vehicle with one base step');
  assert.equal(idleRoute.steps[0].service, 'En base · sin recorrido');
});
