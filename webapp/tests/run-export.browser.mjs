// Regression for switching input after an earlier road run.
// HTTP fixtures simulate a failed second calculation; no solver or AWS calls.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const {chromium} = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const origin = process.env.ZMD_QA_ORIGIN || 'http://127.0.0.1:4310';
const previous = JSON.parse(await readFile(new URL('../../backend/fixtures/native-response.json', import.meta.url)));
const preparation = JSON.parse(await readFile(new URL('../../backend/fixtures/synthetic-prepare-request.json', import.meta.url)));
preparation.network_mode = 'road';
previous.result.raw.prepare_request = preparation;
const next = JSON.parse(await readFile(new URL('../../backend/fixtures/native-request.json', import.meta.url)));
next.instance.name = 'Instancia nueva independiente';
next.instance.parameters.battery_capacity_kwh = 27;
const browser = await chromium.launch({headless: true});
try {
  const context = await browser.newContext();
  await context.route('**/*', route => route.request().url().startsWith(origin) ? route.continue() : route.abort());
  await context.route('**/solve?*', route => route.fulfill({json: previous}));
  await context.route('**/solve', route => route.fulfill({
    status: 503, json: {error: {message: 'Motor temporalmente no disponible.'}},
  }));
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(origin);
  await page.evaluate(runId => sessionStorage.setItem('zmd.webapp.execution.v1',
    JSON.stringify({runId, status: 'complete', stale: false})), previous.result.run_id);
  await page.reload();
  await page.locator('main[aria-busy="false"]').waitFor();
  await page.evaluate(() => {
    const create = URL.createObjectURL;
    URL.createObjectURL = blob => { window.exportedInstance = blob; return create(blob); };
  });
  await page.locator('#run-download').click();
  await page.locator('#export-instance').click();
  const oldExport = await page.evaluate(async () => JSON.parse(await window.exportedInstance.text()));
  assert.deepEqual(oldExport, preparation, 'the previous road run must keep its own preparation');
  await page.locator('#show-config').click();
  await page.locator('#instance-file').setInputFiles({
    name: 'nueva-instancia.json', mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify(next)),
  });
  await page.waitForFunction(() => document.querySelector('#run-capacity').value === '27');
  await page.locator('#solve-run').click();
  await page.waitForFunction(() => document.querySelector('#run-message').textContent.includes('temporalmente no disponible'));
  await page.locator('#export-instance').click();
  const newExport = await page.evaluate(async () => JSON.parse(await window.exportedInstance.text()));
  assert.deepEqual(newExport, next.instance,
    'after a failed native run, export must contain the current instance, never the previous road preparation');
  await page.locator('#show-results').click();
  assert.equal(await page.locator('#run-results').isVisible(), true,
    'the previous result remains available separately from the new input');
  assert.deepEqual(errors, []);
  console.log('PASS: road export and failed native export stay linked to their own inputs.');
} finally { await browser.close(); }
