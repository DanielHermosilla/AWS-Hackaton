// UI acceptance with deterministic API doubles; no solver, AWS or map downloads.
import assert from 'node:assert/strict';
import {mkdir, readFile} from 'node:fs/promises';
const {chromium} = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const origin = process.env.ZMD_QA_ORIGIN || 'http://127.0.0.1:4294';
const output = new URL('../../artifacts/scenario-workspace-qa/', import.meta.url);
await mkdir(output, {recursive: true});
const browser = await chromium.launch({headless: true,
  ...(process.env.CHROME_EXECUTABLE ? {executablePath: process.env.CHROME_EXECUTABLE} : {})});
const context = await browser.newContext({viewport: {width: 1440, height: 900}, reducedMotion: 'reduce'});
const requests = [], errors = [];
const original = [
  {node_id: 'depot', node_type: 'base', latitude: 42.27708, longitude: -83.76281, address: 'Depósito'},
  {node_id: 'customer', node_type: 'visit', latitude: 42.28, longitude: -83.76, address: 'Cliente'},
  {node_id: 'charger', node_type: 'charger', latitude: 42.27, longitude: -83.77, connector_types: 'CHAdeMO'},
];
const profile = {profile_id: 'local-ev', filename: 'eVED_EV.csv', status: 'ready', summary: {trip_count: 4}};
let unavailable = false, failVariant = false;
let solveSuccess = false;
const native = JSON.parse(await readFile(new URL('../../backend/fixtures/native-request.json', import.meta.url)));
const result = JSON.parse(await readFile(new URL('../../backend/fixtures/native-response.json', import.meta.url)));
await context.route('**/*', async route => {
  const request = route.request(), url = new URL(request.url());
  if (url.origin !== origin) return route.abort();
  const reply = (body, status = 200) => route.fulfill({status, contentType: 'application/json',
    body: JSON.stringify({api_version: '3.0', ...body})});
  if (url.pathname === '/bedrock/session') return reply({status: {connected: false}});
  if (url.pathname === '/history') return reply({profile});
  if (url.pathname === '/history/remove') return reply({removed: true});
  if (url.pathname === '/scenarios/hackathon') {
    const body = request.method() === 'POST' ? request.postDataJSON() : null;
    const dataset = body?.dataset || url.searchParams.get('dataset');
    requests.push({path: url.pathname, body, dataset});
    if (unavailable) return reply({error: {message: 'Falta el dataset local.'}}, 404);
    if (body?.simulation && failVariant) return reply({error: {message: 'Falta la red vial para añadir ubicaciones.'}}, 400);
    const simulation = body?.simulation;
    const nodes = simulation ? [
      original[0],
      ...Array.from({length: simulation.customers}, (_, i) => i === 0 ? original[1]
        : {...original[1], node_id: `SIM-CLIENT-${i}`, latitude: 42.28 + i * .001}),
      ...Array.from({length: simulation.chargers}, (_, i) => i === 0 ? original[2]
        : {...original[2], node_id: `SIM-CHARGER-${i}`, longitude: -83.77 - i * .001}),
    ] : original;
    return reply({...(body ? {profile} : {}), scenario: {
      name: `${simulation ? 'Simulación' : 'Hackatón'} · ${dataset} · Ann Arbor`,
      source_file: `${dataset}_routing_nodes.csv`, nodes, network_mode: 'road',
      scenario: {kind: simulation ? 'hackathon_simulation' : 'hackathon', dataset,
        ...(simulation ? {seed: simulation.seed} : {})},
    }});
  }
  if (url.pathname === '/prepare') {
    requests.push({path: '/prepare', body: request.postDataJSON()});
    return solveSuccess ? reply({instance: native.instance})
      : reply({error: {message: 'Preparación registrada para QA.'}}, 400);
  }
  if (url.pathname === '/solve') {
    if (request.method() === 'POST') requests.push({path: '/solve', body: request.postDataJSON()});
    return reply(result);
  }
  if (url.pathname.includes('/data/')) requests.push({path: url.pathname});
  // A local blank basemap isolates marker logic and offline behavior.
  if (url.pathname.endsWith('/positron.json')) return route.fulfill({json: {version: 8, sources: {}, layers: []}});
  return route.continue();
});
const page = await context.newPage();
page.on('pageerror', error => errors.push(error.message));
try {
  await page.goto(origin);
  await page.locator('#scenario-counts').filter({hasText: '1 clientes · 1 cargadores'}).waitFor();
  await page.waitForFunction(() => document.querySelector('#scenario-map')?.dataset.nodeCount === '3');
  assert.equal(requests.filter(r => r.path === '/scenarios/hackathon').length, 1);
  assert.equal(requests.filter(r => r.body).length, 0, 'Opening only fetches locations, never processes history or solves');
  assert.equal(requests.some(r => r.path.includes('/data/')), false, 'No illustrative fixture is requested');
  assert.equal(await page.locator('.vision-content').isVisible(), false);
  assert.equal(await page.locator('#scenario-calculate').isEnabled(), true);
  assert((await page.locator('#scenario-calculate').boundingBox()).y < 900, 'Run action is above the fold');
  // Run the unmodified default: history is loaded on demand and the exact
  // displayed locations reach the shared preparation contract.
  await page.locator('#scenario-calculate').click();
  await page.locator('#run-message').filter({hasText: 'Preparación registrada'}).waitFor();
  assert.deepEqual(requests.find(r => r.path === '/prepare').body.nodes, original);
  assert.equal(requests.find(r => r.path === '/prepare').body.energy_profile_id, 'local-ev');
  await page.locator('#run-count').fill('3');
  await page.locator('#run-policy').selectOption('standard');
  await page.locator('#run-margin').fill('12');
  await page.locator('#close-run').click();
  await page.locator('#scenario-customers').fill('3');
  await page.locator('#scenario-chargers').fill('2');
  await page.locator('#scenario-seed').fill('17');
  assert.equal(await page.locator('#scenario-calculate').isEnabled(), false);
  await page.locator('#scenario-preview').click();
  await page.locator('#scenario-counts').filter({hasText: '3 clientes · 2 cargadores'}).waitFor();
  const variant = requests.filter(r => r.path === '/scenarios/hackathon').at(-1).body;
  assert.deepEqual(variant, {dataset: 'competition', simulation: {customers: 3, chargers: 2, seed: 17}, energy_profile_id: 'local-ev'});
  await page.waitForFunction(() => document.querySelectorAll('.scenario-pin').length === 6);
  assert.equal(await page.locator('.scenario-pin.simulated').count(), 3);
  assert.match(await page.locator('#scenario-fleet').innerText(), /3 vehículos/);
  // Click a map point, preserve its ID/type, and verify it is the very same
  // draft as the advanced panel and subsequent /prepare.
  await page.locator('.scenario-pin.base').click();
  await page.locator('#scenario-edit').click();
  assert.equal(await page.locator('#location-latitude').inputValue(), '42.27708');
  assert.match(await page.locator('#location-scope').innerText(), /red vial/);
  await page.locator('#location-address').fill('Depósito editado desde el mapa');
  await page.locator('#confirm-locations').click();
  await page.reload();
  await page.locator('#scenario-counts').filter({hasText: '3 clientes · 2 cargadores'}).waitFor();
  assert.equal(await page.locator('#scenario-seed').inputValue(), '17');
  assert.equal(requests.filter(r => r.path === '/scenarios/hackathon' && !r.body).length, 1);
  await page.goto(`${origin}/plan.html`);
  await page.locator('#scenario-counts').filter({hasText: '3 clientes · 2 cargadores'}).waitFor();
  assert.match(await page.locator('#scenario-fleet').innerText(), /3 vehículos/);
  await page.locator('#scenario-calculate').click();
  await page.locator('#run-message').filter({hasText: 'Preparación registrada'}).waitFor();
  const preparation = requests.filter(r => r.path === '/prepare').at(-1).body;
  assert.equal(preparation.nodes.length, 6);
  assert.equal(preparation.nodes[0].address, 'Depósito editado desde el mapa');
  assert.equal(preparation.scenario.seed, 17);
  assert.equal(preparation.network_mode, 'road');
  assert.equal(preparation.operations.energy_margin_fraction, .12);
  assert.equal(preparation.fleet.num_vehicles, 3);
  await page.locator('#close-run').click();
  // A failed variant retains the previous map and cannot silently run with
  // unapplied quantities.
  failVariant = true;
  await page.locator('#scenario-customers').fill('4');
  await page.locator('#scenario-preview').click();
  await page.locator('#scenario-message').filter({hasText: 'Falta la red vial'}).waitFor();
  assert.match(await page.locator('#scenario-counts').innerText(), /3 clientes · 2 cargadores/);
  assert.equal(await page.locator('#scenario-calculate').isEnabled(), false);
  failVariant = false;
  await page.locator('#scenario-dataset').selectOption('evaluation');
  await page.locator('#scenario-original').click();
  await page.locator('#scenario-caption').filter({hasText: 'evaluation'}).waitFor();
  await page.locator('#scenario-counts').filter({hasText: '1 clientes · 1 cargadores'}).waitFor();
  await page.setViewportSize({width: 390, height: 844});
  await page.locator('#theme-toggle').click();
  await page.screenshot({path: new URL('acceptance-mobile-dark.png', output).pathname, fullPage: true});
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  // The calculate action follows the existing prepare -> solve -> saved result
  // path, including the read-only input recovered from a native response.
  solveSuccess = true;
  await page.locator('#scenario-calculate').click();
  await page.locator('#run-results').waitFor();
  assert.equal(requests.filter(r => r.path === '/solve').length, 1);
  assert.equal(requests.find(r => r.path === '/solve').body.solver.search_policy, 'standard');
  await page.locator('#close-run').click();
  await page.goto(origin);
  await page.locator('.vision-content').waitFor();
  assert.equal(await page.locator('.vision-content').isVisible(), true);
  // Missing originals show recovery controls and no fake points.
  await page.evaluate(() => sessionStorage.clear());
  unavailable = true;
  await page.goto(origin);
  await page.locator('#scenario-message').filter({hasText: 'Falta el dataset local'}).waitFor();
  assert.equal(await page.locator('.scenario-pin').count(), 0);
  assert.equal(await page.locator('#scenario-calculate').isEnabled(), false);
  assert.equal(await page.locator('#scenario-original').isEnabled(), true);
  assert.equal(requests.some(r => r.path.includes('/data/')), false);
  assert.deepEqual(errors, []);
  console.log('PASS: default map, lazy history, variants, source preservation, map editing, reload/Plan recovery, error recovery, mobile dark layout and prepare/solve/result transport.');
} finally { await browser.close(); }
