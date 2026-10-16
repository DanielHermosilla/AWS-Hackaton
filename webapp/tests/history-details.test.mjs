import assert from 'node:assert/strict';
import {test} from 'node:test';
import {historyDetailGroups, historyCoverageSnapshot} from '../shared/history-details.js';

test('historical details distinguish observations, suggestions not applied and preparation assumptions', () => {
  const profile = {assumptions: [{key: 'speed', label: 'Velocidad', value: {median: 21, p10: 8, p90: 45}, unit: 'km/h', kind: 'observed_distribution'}],
    ai_analysis: {observations: [{name: 'Temperatura', value: 12, unit: '°C', explanation: 'Valor presente en el resumen.', evidence: [{kind: 'computed', key: 'temperature.median', value: 12}]}],
      assumptions: [{description: 'Probar una reserva mayor en invierno.', applied: false, evidence: [{kind: 'metadata', key: 'season', value: 'invierno'}]}],
      limitations: ['No hay viajes nocturnos.']}};
  const groups = historyDetailGroups(profile, {summary: {mixed_sign_arc_count: 3}, assumptions: [
    {...profile.assumptions[0]}, {key: 'mixed_sign_order', label: 'Descarga y recuperación', value: 'Se supone descarga primero', kind: 'model_assumption', applied: true, evidence: 'El orden no se observa.'}],
    warnings: ['Cobertura parcial de calles.']});
  assert.equal(groups.length, 5);
  assert.match(groups[0].items[0].text, /Observado.*mediana 21 km\/h/);
  assert.match(groups[0].items[0].note, /80 % central: 8–45/);
  assert.match(groups[1].items[0].text, /Temperatura: 12 °C/);
  assert.match(groups[1].items[0].note, /temperature.median = 12/);
  assert.match(groups[2].title, /sin aplicar/);
  assert.equal(groups[3].items.length, 2);
  assert.match(groups[3].items[1].text, /Supuesto aplicado.*Descarga/);
  assert.match(groups[4].items[1].text, /Cobertura parcial/);
});

test('zero, null and untrusted text remain explicit data without object stringification', () => {
  const groups = historyDetailGroups({assumptions: [
    {label: '<img onerror=alert(1)>', value: 0, unit: 'kWh', evidence: '<script>not HTML</script>'},
    {label: 'Detenciones', value: null, unit: 'kWh'},
  ]});
  assert.equal(groups[0].items[0].text, '<img onerror=alert(1)>: 0 kWh');
  assert.equal(groups[0].items[1].text, 'Detenciones: Sin dato');
  assert.equal(JSON.stringify(groups).includes('[object Object]'), false);
});

test('the recoverable coverage summary retains only bounded display fields', () => {
  const result = historyCoverageSnapshot({summary: {calibrated_arc_count: 2, road_arc_count: 5, mixed_sign_arc_count: 1, source_rows: [1, 2, 3]},
    assumptions: [{key: 'order', label: 'Orden', value: 'Descarga primero', evidence: 'Supuesto', raw_samples: [1, 2, 3]}],
    warnings: ['Cobertura parcial'], raw_file: 'must-not-retain'});
  assert.deepEqual(result.summary, {calibrated_arc_count: 2, road_arc_count: 5, mixed_sign_arc_count: 1});
  assert.match(historyDetailGroups({assumptions: []}, result)[0].items[1].text, /Descarga primero/);
  assert.equal(JSON.stringify(result).includes('must-not-retain'), false);
  assert.equal(JSON.stringify(result).includes('raw_samples'), false);
});
