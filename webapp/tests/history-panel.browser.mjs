// UI integration against a static local server; all AWS/history/solver responses
// here are explicit doubles, not evidence of access to a real AWS account.
import assert from 'node:assert/strict';
import {mkdir, readFile} from 'node:fs/promises';
const {chromium} = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const origin = process.env.ZMD_QA_ORIGIN || 'http://127.0.0.1:4326';
const output = new URL('../../.local/history-panel/', import.meta.url);
await mkdir(output, {recursive: true});
const browser = await chromium.launch({headless: true});
const context = await browser.newContext({viewport: {width: 1250, height: 1000}, reducedMotion: 'reduce'});
const errors = [], calls = [];
const native = JSON.parse(await readFile(new URL('../../backend/fixtures/native-request.json', import.meta.url)));
let connected = false, expired = false, uploadStatus = 'ready', aiStatus = 'not_requested', resolveConnect;
const profile = () => ({profile_id: 'history-123', status: uploadStatus, filename: 'Viajes EV.csv',
  summary: {row_count: 340, trip_count: 4, vehicle_count: 2, energy_kwh: -0.5, distance_km: 30},
  assumptions: [{label: 'Velocidad observada', value: 28, unit: 'km/h', evidence: 'Mediana de cuatro viajes.'}],
  warnings: ['Los intervalos sin señal se excluyen.'], ai_analysis: {status: aiStatus,
    observations: aiStatus === 'reviewed' ? [{name: 'Temperatura', value: 18, unit: '°C', evidence: [{kind: 'computed', key: 'temperature.median', value: 18}]}] : [],
    assumptions: aiStatus === 'reviewed' ? [{description: 'Evaluar un escenario frío <img src=x onerror=alert(1)>', applied: false, evidence: [{kind: 'metadata', key: 'season', value: 'invierno'}]}] : []}});
const status = () => ({state: connected ? 'connected' : 'disconnected', connected, region: 'us-east-1', model_id: 'model-with-high', reasoning_effort: 'high'});
await context.route('**/*', async route => {
  const request = route.request(), url = new URL(request.url());
  if (!request.url().startsWith(origin)) return route.abort();
  const fulfill = (body, code = 200) => route.fulfill({status: code, contentType: 'application/json', body: JSON.stringify({api_version: '3.0', ...body})});
  if (url.pathname === '/bedrock/session') {
    if (request.method() === 'POST') {
      calls.push({path: url.pathname, body: request.postDataJSON()});
      await new Promise(resolve => { resolveConnect = resolve; });
      connected = true;
    }
    return fulfill({status: status()});
  }
  if (url.pathname === '/bedrock/disconnect') { connected = false; calls.push({path: url.pathname}); return fulfill({status: status()}); }
  if (url.pathname === '/history/upload') {
    aiStatus = 'not_requested';
    calls.push({path: url.pathname, filename: request.headers()['x-history-filename'], body: request.postData()});
    return fulfill({profile: profile()});
  }
  if (url.pathname === '/history') return expired ? fulfill({error: {message: 'expired'}}, 404) : fulfill({profile: profile()});
  if (url.pathname === '/history/remove') { calls.push({path: url.pathname}); return fulfill({removed: true}); }
  if (url.pathname === '/history/analyze') { uploadStatus = 'ready'; aiStatus = 'reviewed'; calls.push({path: url.pathname}); return fulfill({profile: profile()}); }
  if (url.pathname === '/prepare') {
    calls.push({path: url.pathname, body: request.postDataJSON()});
    return fulfill({instance: native.instance, preparation: {energy_profile: {
      summary: {calibrated_arc_count: 3, road_arc_count: 10, arc_coverage_fraction: .3, mixed_sign_arc_count: 2},
      assumptions: [{key: 'mixed_sign_order', label: 'Descarga y recuperación', value: 'Descarga primero', kind: 'model_assumption', evidence: 'El orden interno es supuesto.'}],
      warnings: ['La cobertura de calles es parcial.'],
    }}});
  }
  if (url.pathname === '/solve' && request.method() === 'POST') return fulfill({error: {message: 'Error sintético de prueba: no se ejecutó el solver.'}}, 400);
  return route.continue();
});
const page = await context.newPage();
page.on('pageerror', error => errors.push(error.message));
const storage = () => page.evaluate(() => JSON.stringify([Object.entries(localStorage), Object.entries(sessionStorage)]));
try {
  await page.goto(origin);
  await page.locator('#open-run').click();
  await page.locator('.run-synthetic summary').click();
  await page.locator('#use-synthetic').click();
  await page.locator('#run-policy').selectOption('standard');
  const instanceText = await page.locator('#input-summary').textContent();
  await page.locator('#history-file').setInputFiles({name: 'Viajes EV.csv', mimeType: 'text/csv', buffer: Buffer.from('VehId,Trip,Timestamp,Latitude,Longitude\n1,1,1,0,0')});
  await page.getByText('Histórico preparado.', {exact: false}).waitFor();
  assert.equal(await page.locator('#input-summary').textContent(), instanceText);
  assert.match(await page.locator('#history-stats').textContent(), /340.*4.*2.*30.*-0,5/s);
  assert.equal(calls.filter(call => call.path === '/prepare').length, 0);
  assert.equal(calls.find(call => call.path === '/history/upload').filename, 'Viajes%20EV.csv');
  assert.doesNotMatch(await storage(), /VehId,Trip|Timestamp/);
  await page.locator('#solve-run').click();
  await page.waitForFunction(() => document.querySelector('#run-message').textContent.includes('Error sintético'));
  assert.equal(calls.find(call => call.path === '/prepare').body.energy_profile_id, 'history-123');
  assert.match(await page.locator('#history-coverage').textContent(), /3 de 10 tramos/);
  assert.match(await page.locator('#history-detail-groups').textContent(), /Supuesto aplicado.*Descarga primero.*cobertura de calles es parcial/s);
  await page.reload();
  await page.locator('#open-run').click();
  await page.waitForFunction(() => !document.querySelector('#history-coverage').hidden);
  assert.match(await page.locator('#history-detail-groups').textContent(), /2 tramos combinan.*Descarga primero.*cobertura de calles es parcial/s);
  await page.locator('#run-consumption').fill('1.2');
  assert.equal(await page.locator('#history-coverage').isVisible(), false);
  await page.locator('#history-remove').click();
  assert.match(await page.locator('#history-state').textContent(), /retirado/);
  assert.equal(await page.locator('#export-instance').isDisabled(), true);
  await page.locator('#solve-run').click();
  await page.waitForFunction(() => document.querySelector('#run-message').textContent.includes('Error sintético'));
  assert.equal('energy_profile_id' in calls.filter(call => call.path === '/prepare').at(-1).body, false);

  uploadStatus = 'needs_mapping';
  await page.locator('#history-file').setInputFiles({name: 'datos-propios.json', mimeType: 'application/json', buffer: Buffer.from('{"mediciones":[]}')});
  await page.locator('#history-analyze').waitFor();
  await page.locator('#history-analyze').click();
  await page.locator('#bedrock-dialog').waitFor();
  await page.locator('#bedrock-mode').selectOption('temporary');
  for (const [id, value] of [['bedrock-access', 'TEMP-ACCESS-TEST'], ['bedrock-secret', 'TEMP-SECRET-TEST'], ['bedrock-token', 'TEMP-TOKEN-TEST']]) {
    assert.equal(await page.locator(`#${id}`).getAttribute('type'), 'password');
    await page.locator(`#${id}`).fill(value);
  }
  await page.locator('#bedrock-connect').click();
  await page.waitForFunction(() => document.querySelector('#bedrock-access').value === '');
  assert.doesNotMatch(await storage(), /TEMP-ACCESS-TEST|TEMP-SECRET-TEST|TEMP-TOKEN-TEST/);
  assert.equal(await page.locator('#bedrock-secret').inputValue(), '');
  assert.equal(await page.locator('#bedrock-token').inputValue(), '');
  assert.deepEqual(calls.find(call => call.path === '/bedrock/session').body, {
    mode: 'temporary', region: 'us-east-1', model_id: 'model-with-high', access_key_id: 'TEMP-ACCESS-TEST', secret_access_key: 'TEMP-SECRET-TEST', session_token: 'TEMP-TOKEN-TEST',
  });
  resolveConnect();
  await page.waitForFunction(() => !document.querySelector('#bedrock-disconnect').hidden);
  await page.locator('#bedrock-close').click();
  await page.locator('#history-analyze').click();
  await page.waitForFunction(() => document.querySelector('#history-analyze').hidden);
  assert.equal(calls.filter(call => call.path === '/history/analyze').length, 1);
  assert.match(await page.locator('#history-detail-groups').textContent(), /Observaciones de la IA.*Temperatura: 18 °C.*Sugerencias de la IA · sin aplicar.*escenario frío/s);
  assert.equal(await page.locator('#history-detail-groups img').count(), 0);
  await page.locator('#close-run').click();
  await page.goto(`${origin}/plan.html`);
  await page.locator('#open-run').click();
  await page.getByText('Histórico preparado.', {exact: false}).waitFor();
  assert.match(await page.locator('#input-summary').textContent(), /Borrador/);
  assert.equal(await page.locator('#history-aws').textContent(), 'AWS conectado');
  await page.locator('#history-assumptions summary').click();
  await page.locator('#run-history').scrollIntoViewIfNeeded();
  await page.screenshot({path: new URL('history-desktop.png', output).pathname});
  await page.setViewportSize({width: 390, height: 844});
  await page.screenshot({path: new URL('history-mobile.png', output).pathname});
  assert.equal(await page.locator('#run-dialog').evaluate(el => el.scrollWidth <= el.clientWidth), true);
  await page.locator('#history-aws').click();
  await page.locator('#bedrock-mode').selectOption('temporary');
  await page.locator('#bedrock-access').fill('SHOULD-BE-CLEARED');
  await page.screenshot({path: new URL('connection-mobile.png', output).pathname});
  assert.equal(await page.locator('#bedrock-dialog').evaluate(el => el.scrollWidth <= el.clientWidth), true);
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('#bedrock-access').inputValue(), '');
  await page.locator('#history-aws').click();
  await page.locator('#bedrock-disconnect').click();
  await page.waitForFunction(() => document.querySelector('#bedrock-disconnect').hidden);
  assert.equal(calls.filter(call => call.path === '/bedrock/disconnect').length, 1);
  await page.locator('#bedrock-close').click();
  await page.locator('#instance-file').setInputFiles({name: 'nativa.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(native))});
  await page.waitForFunction(() => !document.querySelector('#history-native-note').hidden);
  assert.equal(await page.locator('#choose-history').isDisabled(), true);
  assert.match(await page.locator('#history-state').textContent(), /consumo incluido/);
  expired = true;
  await page.reload();
  await page.locator('#open-run').click();
  await page.waitForFunction(() => document.querySelector('#history-native-note').hidden === false);
  await page.locator('.run-synthetic summary').click();
  await page.locator('#use-synthetic').click();
  await page.waitForFunction(() => document.querySelector('#history-state').textContent.includes('ya no está'));
  assert.equal(await page.locator('#history-profile').isVisible(), false);
  assert.doesNotMatch(await storage(), /TEMP-ACCESS-TEST|TEMP-SECRET-TEST|TEMP-TOKEN-TEST|SHOULD-BE-CLEARED/);
  assert.deepEqual(errors, []);
  console.log('PASS: separate history upload, fallback, current prepare reference, coverage, removal invalidation, AWS secrets cleared/not stored, interpretation, disconnect, native protection, navigation and expiry; desktop/mobile inspected. API responses mocked.');
} finally { await browser.close(); }
