// Optional browser QA with explicit HTTP doubles; no AWS or solver calls.
import assert from 'node:assert/strict';
import {mkdir} from 'node:fs/promises';
const {chromium} = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const origin = process.env.ZMD_QA_ORIGIN || 'http://127.0.0.1:4389';
const output = new URL('../../artifacts/hackathon-ui-qa/', import.meta.url);
await mkdir(output, {recursive: true});
const browser = await chromium.launch({headless: true, ...(process.env.CHROME_EXECUTABLE ? {executablePath: process.env.CHROME_EXECUTABLE} : {})});
const context = await browser.newContext({viewport: {width: 1200, height: 1000}, reducedMotion: 'reduce'});
const errors = [], calls = [];
let releaseScenario, holdScenario = true;
const profile = {profile_id: 'history-only', filename: 'EV.csv', status: 'ready',
  summary: {row_count: 400, trip_count: 4, vehicle_count: 1}, ai_analysis: {status: 'not_requested'}};
const nodes = [
  {node_id: 'BASE', node_type: 'base', latitude: 42.27708, longitude: -83.76281},
  {node_id: 'C1', node_type: 'visit', latitude: 42.28, longitude: -83.76},
  {node_id: 'F1', node_type: 'charger', latitude: 42.27, longitude: -83.77, connector_types: 'CHAdeMO'},
];
await context.route('**/*', async route => {
  const request = route.request(), url = new URL(request.url());
  if (url.origin !== origin) return route.abort();
  const reply = (body, status = 200) => route.fulfill({status, contentType: 'application/json',
    body: JSON.stringify({api_version: '3.0', ...body})});
  if (url.pathname === '/bedrock/session') return reply({status: {connected: false}});
  if (url.pathname === '/history/upload' || url.pathname === '/history') return reply({profile});
  if (url.pathname === '/history/remove') return reply({removed: true});
  if (url.pathname === '/scenarios/hackathon') {
    const body = request.method() === 'POST' ? request.postDataJSON() : null;
    const dataset = body?.dataset || url.searchParams.get('dataset');
    calls.push({path: url.pathname, dataset, body});
    if (holdScenario) await new Promise(resolve => { releaseScenario = resolve; });
    const variantNodes = body?.simulation
      ? [nodes[0], nodes[1], {...nodes[1], node_id: 'SIM-CLIENT', latitude: 42.281}]
      : nodes;
    return reply({
      ...(body ? {profile} : {}),
      scenario: {
        name: body?.simulation ? 'Simulación · Ann Arbor' : 'Hackatón · Ann Arbor, Michigan',
        source_file: `${dataset}_routing_nodes.csv`, nodes: variantNodes,
        scenario: {kind: body?.simulation ? 'hackathon_simulation' : 'hackathon', dataset, ...(body?.simulation ? {seed: body.simulation.seed} : {})},
      },
    });
  }
  if (url.pathname === '/prepare') {
    calls.push({path: url.pathname, body: request.postDataJSON()});
    return reply({error: {message: 'Fin de prueba: preparación registrada.'}}, 400);
  }
  return route.continue();
});
const page = await context.newPage();
page.on('pageerror', error => errors.push(error.message));
try {
  await page.goto(origin);
  await page.locator('#open-run').click();
  await page.locator('#run-count').fill('3');
  await page.locator('#run-capacity').fill('30');
  await page.locator('#run-policy').selectOption('standard');
  await page.locator('#history-file').setInputFiles({name: 'EV.csv', mimeType: 'text/csv', buffer: Buffer.from('test')});
  await page.waitForFunction(() => document.querySelector('#use-hackathon').disabled);
  while (!releaseScenario) await new Promise(resolve => setTimeout(resolve, 10));
  await page.locator('#run-reserve').fill('3');
  holdScenario = false;
  releaseScenario();
  await page.waitForFunction(() => document.querySelector('#input-summary').textContent.includes('Ann Arbor'));
  assert.equal(await page.locator('#run-count').inputValue(), '3');
  assert.equal(await page.locator('#run-capacity').inputValue(), '30');
  assert.equal(await page.locator('#run-reserve').inputValue(), '3');
  assert.equal(await page.locator('#run-network').inputValue(), 'road');
  assert.equal(await page.locator('#run-policy').inputValue(), 'standard');
  await page.locator('#solve-run').click();
  await page.locator('#run-message').filter({hasText: 'Fin de prueba:'}).waitFor();
  const request = calls.find(call => call.path === '/prepare').body;
  assert.equal(request.energy_profile_id, 'history-only');
  assert.equal(request.fleet.num_vehicles, 3);
  assert.equal(request.fleet.battery_capacity_kwh, 30);
  assert.deepEqual(request.nodes, nodes);
  await page.reload();
  await page.locator('#open-run').click();
  await page.getByText('Histórico preparado.', {exact: false}).waitFor();
  assert.equal(await page.locator('#run-count').inputValue(), '3');
  assert.equal(calls.filter(call => call.path === '/scenarios/hackathon').length, 1);
  await page.locator('#edit-locations').click();
  assert.equal(await page.locator('#location-latitude').inputValue(), '42.27708');
  assert.equal(await page.locator('#location-longitude').inputValue(), '-83.76281');
  await page.locator('#cancel-locations').click();
  await page.locator('#history-remove').click();
  await page.locator('#solve-run').click();
  await page.locator('#run-message').filter({hasText: 'Fin de prueba:'}).waitFor();
  assert.equal('energy_profile_id' in calls.filter(call => call.path === '/prepare').at(-1).body, false);
  await page.locator('#hackathon-dataset').selectOption('evaluation');
  await page.locator('#use-hackathon').click();
  await page.waitForFunction(() => !document.querySelector('#use-hackathon').disabled);
  assert.equal(calls.filter(call => call.path === '/scenarios/hackathon').at(-1).dataset, 'evaluation');
  await page.getByText('Histórico preparado.', {exact: false}).waitFor();
  await page.locator('.run-variant summary').click();
  await page.locator('#variant-clients').fill('2');
  await page.locator('#variant-chargers').fill('0');
  await page.locator('#variant-seed').fill('17');
  await page.locator('#run-margin').fill('15');
  await page.locator('#simulate-hackathon').click();
  await page.locator('#run-message').filter({hasText: 'Variante lista'}).waitFor();
  const variant = calls.filter(call => call.path === '/scenarios/hackathon').at(-1).body;
  assert.deepEqual(variant, {dataset: 'evaluation', simulation: {customers: 2, chargers: 0, seed: 17}, energy_profile_id: 'history-only'});
  await page.locator('#solve-run').click();
  await page.locator('#run-message').filter({hasText: 'Fin de prueba:'}).waitFor();
  const variantRequest = calls.filter(call => call.path === '/prepare').at(-1).body;
  assert.equal(variantRequest.nodes.length, 3);
  assert.equal(variantRequest.nodes.filter(node => node.node_type === 'charger').length, 0);
  assert.equal(variantRequest.scenario.kind, 'hackathon_simulation');
  assert.equal(variantRequest.operations.energy_margin_fraction, .15);
  assert.equal(variantRequest.fleet.num_vehicles, 3);
  await page.reload();
  await page.locator('#open-run').click();
  await page.getByText('Histórico preparado.', {exact: false}).waitFor();
  assert.equal(await page.locator('#run-margin').inputValue(), '15');
  assert.equal(await page.locator('#variant-seed').inputValue(), '17');
  assert.equal(await page.locator('#variant-chargers').inputValue(), '0');
  await page.locator('.run-variant summary').click();
  await page.locator('#run-dialog').evaluate(element => { element.scrollTop = 0; });
  await page.screenshot({path: new URL('desktop.png', output).pathname});
  await page.setViewportSize({width: 390, height: 844});
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await page.screenshot({path: new URL('mobile.png', output).pathname});
  assert.equal(await page.locator('#run-dialog').evaluate(element => element.scrollWidth <= element.clientWidth), true);
  assert.deepEqual(errors, []);
  console.log('PASS: upload without instance, local historical case, reproducible variant, retained fleet and margin, draft recovery, evaluation selection and mobile layout.');
} finally { await browser.close(); }
