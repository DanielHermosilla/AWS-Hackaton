// Run with PLAYWRIGHT_MODULE and ZMD_QA_ORIGIN against a local backend.
import assert from 'node:assert/strict';
import {mkdir, readFile} from 'node:fs/promises';
const {chromium} = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const origin = process.env.ZMD_QA_ORIGIN || 'http://127.0.0.1:4333';
const output = new URL('../../.local/refined-panel/', import.meta.url);
await mkdir(output, {recursive: true});
const browser = await chromium.launch({headless: true});
const context = await browser.newContext({viewport: {width: 1280, height: 1050}, reducedMotion: 'reduce'});
await context.route('**/*', route => route.request().url().startsWith(origin) ? route.continue() : route.abort());
const page = await context.newPage();
const errors = [];
page.on('pageerror', error => errors.push(error.message));
const requests = [];
page.on('request', request => {
  if (['/solve', '/prepare'].includes(new URL(request.url()).pathname) && request.method() === 'POST')
    requests.push({path: new URL(request.url()).pathname, body: request.postDataJSON()});
});
try {
  await page.goto(origin);
  await page.locator('#open-run').click();
  assert.equal(await page.locator('#solve-run').isEnabled(), true);
  await page.locator('#solve-run').click();
  assert.match(await page.locator('#run-message').textContent(), /Falta una instancia/);
  assert.equal(requests.length, 0);
  await page.locator('#instance-format').focus();
  assert.equal(await page.locator('#instance-help').isVisible(), true);
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('#instance-help').isVisible(), false);
  await page.locator('#instance-format').hover();
  assert.equal(await page.locator('#instance-help').isVisible(), true);
  await page.locator('.run-synthetic summary').click();
  await page.locator('#synthetic-clients').fill('2');
  await page.locator('#synthetic-chargers').fill('1');
  await page.locator('#use-synthetic').click();
  assert.match(await page.locator('#input-summary').textContent(), /2 clientes · 1 cargador/);
  assert.equal(await page.locator('#run-network').inputValue(), 'haversine');
  assert.equal(await page.locator('#run-ack').count(), 0);
  await page.locator('#run-count').fill('1');
  await page.locator('#run-capacity').fill('7');
  await page.locator('#run-reserve').fill('2');
  await page.locator('#run-policy').selectOption('standard');
  await page.locator('#run-gap').fill('1.5');
  await page.locator('#run-seed').fill('41');
  await page.locator('#run-seconds').fill('3');
  await page.locator('#run-capacity').fill('');
  await page.locator('#solve-run').click();
  assert.match(await page.locator('#run-message').textContent(), /Completa «Capacidad útil/);
  assert.equal(requests.length, 0);
  await page.locator('#run-capacity').fill('7');
  await page.locator('#run-dialog').evaluate(el => { el.scrollTop = 0; });
  await page.screenshot({path: new URL('panel-desktop.png', output).pathname});
  await page.locator('#close-run').click();
  await page.goto(`${origin}/plan.html`);
  await page.locator('#open-run').click();
  for (const [id, value] of [['run-count', '1'], ['run-capacity', '7'], ['run-reserve', '2'], ['run-gap', '1.5'], ['run-seed', '41'], ['run-policy', 'standard'], ['run-network', 'haversine']])
    assert.equal(await page.locator(`#${id}`).inputValue(), value);
  await page.setViewportSize({width: 390, height: 844});
  await page.screenshot({path: new URL('panel-mobile.png', output).pathname});
  assert.equal(await page.locator('#run-dialog').evaluate(el => el.scrollWidth <= el.clientWidth), true);
  await page.evaluate(() => { document.documentElement.dataset.theme = 'dark'; });
  await page.screenshot({path: new URL('panel-mobile-dark.png', output).pathname});
  await page.evaluate(() => { document.documentElement.dataset.theme = 'light'; });
  if (process.env.ZMD_QA_VISUAL_ONLY) {
    assert.deepEqual(errors, []);
    console.log('PASS: field validation, help, generator, navigation persistence, desktop/mobile layouts.');
  } else {
    await Promise.all([page.waitForEvent('load', {timeout: 180000}), page.locator('#solve-run').click()]);
    await page.locator('#run-results').waitFor({timeout: 30000});
    assert.equal(await page.locator('#run-dialog').isVisible(), true);
    assert.equal(await page.locator('#result-details').getAttribute('open'), '');
    const preparation = requests.find(request => request.path === '/prepare').body;
    const solve = requests.find(request => request.path === '/solve').body;
    assert.equal(preparation.network_mode, 'haversine');
    assert.equal(preparation.fleet.battery_capacity_kwh, 7);
    assert.equal(solve.solver.energy_relative_gap, .015);
    assert.equal(solve.solver.random_seed, 41);
    await page.screenshot({path: new URL('results-mobile.png', output).pathname});
    await page.locator('#close-run').click();
    assert.equal(await page.locator('#run-download').textContent(), 'Ver resultados');
    await page.locator('#run-download').click();
    assert.equal(await page.locator('#run-results').isVisible(), true);
    await page.locator('#show-config').click();
    assert.equal(await page.locator('#run-gap').inputValue(), '1.5');
    const fixture = JSON.parse(await readFile(new URL('../../backend/fixtures/native-request.json', import.meta.url)));
    fixture.instance.parameters = {...fixture.instance.parameters, vehicle_count: 3, battery_capacity_kwh: 17, initial_soc: .75, reserve_kwh: 2};
    fixture.solver = {time_limit_seconds: 7, search_policy: 'standard', energy_relative_gap: .025, random_seed: 87};
    await page.locator('#instance-file').setInputFiles({name: 'parametros.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(fixture))});
    await page.waitForFunction(() => document.querySelector('#run-capacity').value === '17');
    for (const [id, value] of [['run-count', '3'], ['run-capacity', '17'], ['run-soc', '75'], ['run-gap', '2.5'], ['run-seed', '87'], ['run-seconds', '7']])
      assert.equal(await page.locator(`#${id}`).inputValue(), value);
    assert.equal(await page.locator('#run-capacity').isDisabled(), true);
    assert.equal(await page.locator('#run-gap').isEnabled(), true);
    await page.locator('#instance-file').setInputFiles({name: 'eVED_EV.csv', mimeType: 'text/csv', buffer: Buffer.from('VehId,Trip,Timestamp,Latitude,Longitude\n1,1,1,0,0')});
    await page.waitForFunction(() => document.querySelector('#run-message').textContent.includes('eVED'));
    assert.equal(await page.locator('#solve-run').isEnabled(), true);
    assert.deepEqual(errors, []);
    console.log('PASS: live solve with custom settings, automatic/repeat result access, JSON autofill and explicit eVED rejection.');
  }
} finally { await browser.close(); }
