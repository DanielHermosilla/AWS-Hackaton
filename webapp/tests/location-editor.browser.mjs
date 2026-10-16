// Optional browser QA: run against backend.local_server with Playwright available.
// PLAYWRIGHT_MODULE can point to an existing Playwright installation.
import assert from 'node:assert/strict';
import { readFile, mkdir } from 'node:fs/promises';
const {chromium} = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const origin = process.env.ZMD_QA_ORIGIN || 'http://127.0.0.1:4315';
const output = new URL('../../.local/f05/', import.meta.url);
await mkdir(output, {recursive: true});
const browser = await chromium.launch({headless: true});
const context = await browser.newContext({viewport: {width: 1280, height: 960}, reducedMotion: 'reduce'});
await context.route('**/*', route => route.request().url().startsWith(origin) ? route.continue() : route.abort());
const page = await context.newPage();
await page.addInitScript(() => {
  const original = window.fetch;
  window.solveCalls = 0;
  window.fetch = (url, options) => {
    if (url === '/solve' && options?.method === 'POST') {
      window.solveCalls++;
      if (window.deferSolve) return new Promise(resolve => {
        window.releaseOldSolve = body => resolve(new Response(JSON.stringify(body), {status: 200, headers: {'Content-Type': 'application/json'}}));
      });
      if (window.holdSolveResult) return original(url, options).then(async response => {
        const text = await response.text();
        return new Promise(resolve => {
          window.releaseCompletedSolve = () => resolve(new Response(text, {status: response.status, headers: {'Content-Type': 'application/json'}}));
        });
      });
    }
    if (url === '/prepare' && window.deferPrepare) return new Promise(resolve => {
      window.releaseOldPrepare = body => resolve(new Response(JSON.stringify(body), {status: 200, headers: {'Content-Type': 'application/json'}}));
    });
    return original(url, options);
  };
});
const errors = [];
page.on('pageerror', error => errors.push(error.message));
const visible = async selector => assert.equal(await page.locator(selector).isVisible(), true, selector);
async function synthetic() {
  await page.goto(origin);
  await page.locator('#open-run').click();
  await page.locator('#use-synthetic').click();
}
try {
  await synthetic();
  await page.locator('#edit-locations').click();
  await visible('#location-dialog');
  await page.locator('#location-node').selectOption('1');
  assert.equal(await page.locator('#location-id').textContent(), 'Visita|ñ');
  await page.locator('#location-latitude').fill('0');
  await page.locator('#location-longitude').fill('0');
  await page.locator('#location-address').fill('Nueva dirección manual');
  await page.locator('#cancel-locations').click();
  await page.locator('#edit-locations').click();
  await page.locator('#location-node').selectOption('1');
  assert.equal(await page.locator('#location-latitude').inputValue(), '-33.451');
  await page.locator('#location-latitude').fill('');
  assert.equal(await page.locator('#confirm-locations').isDisabled(), true);
  await page.locator('#location-latitude').fill('-33.4505');
  await page.locator('#location-longitude').fill('-70.6615');
  await page.locator('#location-address').fill('Nueva dirección manual');
  await page.screenshot({path: new URL('editor-desktop.png', output).pathname});
  await page.locator('#confirm-locations').click();
  assert.match(await page.locator('#run-message').textContent(), /Ubicaciones confirmadas/);
  assert.equal(await page.locator('#run-ack').isChecked(), false);
  assert.equal(await page.locator('#export-instance').isDisabled(), true);
  const preparations = [];
  page.on('request', request => {
    if (request.url() === `${origin}/prepare` && request.method() === 'POST') preparations.push(request.postDataJSON());
  });
  await page.locator('#run-ack').check();
  await page.locator('#run-seconds').fill('2');
  await page.locator('#run-ack').check();
  await Promise.all([page.waitForEvent('load', {timeout: 180000}), page.locator('#solve-run').click()]);
  assert.equal(await page.evaluate(() => JSON.parse(sessionStorage.getItem('zmd.webapp.execution.v1'))?.status), 'complete');
  await page.waitForFunction(() => document.querySelector('#run-source')?.textContent.includes('Resultado del motor'));
  assert.equal(preparations.length, 1);
  assert.equal(preparations[0].nodes[1].latitude, -33.4505);
  await page.locator('#open-run').click();
  const downloadPromise = page.waitForEvent('download');
  await page.locator('#export-instance').click();
  const download = await downloadPromise;
  const native = JSON.parse(await readFile(await download.path(), 'utf8'));
  assert.equal(native.nodes.find(node => node.node_id === 'Visita|ñ').latitude, -33.4505);
  await page.locator('#edit-locations').click();
  assert.equal(await page.locator('#location-latitude').isEditable(), true);
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('#edit-locations').evaluate(el => el === document.activeElement), true);
  const nativeFixture = await readFile(new URL('../../backend/fixtures/native-request.json', import.meta.url));
  await page.locator('#instance-file').setInputFiles({name: 'native.json', mimeType: 'application/json', buffer: nativeFixture});
  await page.locator('#edit-locations').click();
  assert.equal(await page.locator('#location-latitude').isEditable(), false);
  assert.equal(await page.locator('#confirm-locations').isVisible(), false);
  assert.match(await page.locator('#location-scope').textContent(), /red nativa/);
  await page.screenshot({path: new URL('native-protected.png', output).pathname});
  await page.keyboard.press('Escape');
  await page.locator('#use-synthetic').click();
  await page.setViewportSize({width: 390, height: 844});
  await page.locator('#edit-locations').click();
  assert.equal(await page.evaluate(() => document.querySelector('#location-dialog').scrollWidth <= document.querySelector('#location-dialog').clientWidth), true);
  await page.screenshot({path: new URL('editor-mobile.png', output).pathname});
  await page.locator('#cancel-locations').click();
  await page.setViewportSize({width: 1280, height: 960});
  await page.evaluate(() => {
    document.querySelector('#edit-locations').click();
    document.querySelector('#edit-locations').click();
    document.querySelector('#cancel-locations').click();
    document.querySelector('#edit-locations').click();
  });
  await page.locator('#location-node').selectOption('1');
  await page.locator('#location-latitude').fill('0');
  assert.equal(await page.locator('#location-latitude').inputValue(), '0');
  await page.locator('#cancel-locations').click();
  console.log('PASS: flujo real, exportación, origen editable, nativo protegido, móvil y reapertura rápida.');

  // The simulated transport deliberately ignores AbortSignal. It exercises the
  // client's revision guard, not server cancellation or solver feasibility.
  const delayedResult = JSON.parse(await readFile(new URL('../../backend/fixtures/native-response.json', import.meta.url)));
  await page.evaluate(() => { window.deferSolve = true; });
  await page.locator('#run-ack').check();
  await page.locator('#solve-run').click();
  await page.waitForFunction(() => typeof window.releaseOldSolve === 'function');
  await page.locator('#edit-locations').click();
  await page.locator('#location-node').selectOption('1');
  await page.locator('#location-latitude').fill('-33.453');
  await page.locator('#confirm-locations').click();
  const revision = await page.evaluate(() => JSON.parse(sessionStorage.getItem('zmd.webapp.execution.v1')).revision);
  await page.evaluate(async body => {
    window.releaseOldSolve(body);
    await new Promise(resolve => setTimeout(resolve, 0));
  }, delayedResult);
  assert.equal(await page.evaluate(() => JSON.parse(sessionStorage.getItem('zmd.webapp.execution.v1')).revision), revision);
  assert.equal(await page.locator('#export-instance').isDisabled(), true);
  await page.locator('#edit-locations').click();
  assert.equal(await page.locator('#solve-run').isDisabled(), true);
  await page.locator('#location-node').selectOption('1');
  assert.equal(await page.locator('#location-latitude').inputValue(), '-33.453');
  await page.locator('#cancel-locations').click();
  console.log('PASS: respuesta de cálculo tardía ignorando AbortSignal conserva el borrador confirmado.');

  // Map interaction remains a draft until confirmation, even without tiles.
  await page.locator('#edit-locations').click();
  await page.locator('#location-node').selectOption('1');
  await page.locator('#center-location').click();
  await page.locator('#pick-location').click();
  await page.locator('#location-map canvas').click({position: {x: 340, y: 120}});
  assert.notEqual(await page.locator('#location-latitude').inputValue(), '-33.453');
  const clickedLatitude = await page.locator('#location-latitude').inputValue();
  const marker = await page.locator('#location-map .maplibregl-marker').boundingBox();
  await page.mouse.move(marker.x + marker.width / 2, marker.y + marker.height / 2);
  await page.mouse.down();
  await page.mouse.move(marker.x + marker.width / 2 + 25, marker.y + marker.height / 2 - 20, {steps: 8});
  await page.mouse.up();
  assert.notEqual(await page.locator('#location-latitude').inputValue(), clickedLatitude);
  await page.locator('#cancel-locations').click();
  await page.locator('#edit-locations').click();
  await page.locator('#location-node').selectOption('1');
  assert.equal(await page.locator('#location-latitude').inputValue(), '-33.453');
  await page.locator('#cancel-locations').click();
  console.log('PASS: selección y arrastre reales en mapa, y cancelación sin mutar la entrada.');
  await page.evaluate(() => { window.deferPrepare = true; });
  await page.locator('#run-ack').check();
  await page.locator('#solve-run').click();
  await page.waitForFunction(() => typeof window.releaseOldPrepare === 'function');
  const solveCalls = await page.evaluate(() => window.solveCalls);
  await page.locator('#instance-file').setInputFiles({name: 'replacement.csv', mimeType: 'text/csv',
    buffer: Buffer.from('node_id,node_type,latitude,longitude\nB,base,0,0\nnuevo / ñ,visit,0.001,0\n')});
  await page.evaluate(async instance => {
    window.releaseOldPrepare({api_version: '3.0', instance});
    await new Promise(resolve => setTimeout(resolve, 0));
  }, native);
  assert.equal(await page.evaluate(() => window.solveCalls), solveCalls);
  assert.match(await page.locator('#input-summary').textContent(), /replacement.csv/);
  await page.locator('#edit-locations').click();
  await page.locator('#location-node').selectOption('1');
  assert.equal(await page.locator('#location-id').textContent(), 'nuevo / ñ');
  await page.locator('#cancel-locations').click();
  console.log('PASS: sustituir el archivo descarta una preparación tardía y no lanza su cálculo.');

  await page.locator('#use-synthetic').click();
  await page.locator('#run-seconds').fill('2');
  await page.evaluate(() => { window.deferPrepare = false; window.deferSolve = false; window.holdSolveResult = true; });
  await page.locator('#run-ack').check();
  await page.locator('#solve-run').click();
  await page.waitForFunction(() => typeof window.releaseCompletedSolve === 'function', null, {timeout: 180000});
  await page.locator('#edit-locations').click();
  await page.locator('#location-node').selectOption('1');
  await page.locator('#location-latitude').fill('-33.455');
  await page.evaluate(async () => {
    window.releaseCompletedSolve();
    await new Promise(resolve => setTimeout(resolve, 0));
  });
  assert.equal(await page.locator('#location-dialog').isVisible(), true);
  assert.equal(await page.evaluate(() => JSON.parse(sessionStorage.getItem('zmd.webapp.execution.v1')).status), 'running');
  await Promise.all([page.waitForEvent('load'), page.locator('#cancel-locations').click()]);
  await page.waitForFunction(() => document.querySelector('#run-source')?.textContent.includes('Resultado del motor'));
  await page.locator('#open-run').click();
  await page.locator('#edit-locations').click();
  await page.locator('#location-node').selectOption('1');
  assert.equal(await page.locator('#location-latitude').inputValue(), '-33.451');
  assert.equal(await page.evaluate(() => JSON.parse(sessionStorage.getItem('zmd.webapp.execution.v1')).stale), false);
  await page.locator('#cancel-locations').click();
  console.log('PASS: cancelar un borrador permite aceptar el cálculo real que terminó mientras el editor estaba abierto.');
  assert.deepEqual(errors, []);

  const fallbackContext = await browser.newContext({viewport: {width: 390, height: 844}});
  await fallbackContext.route('**/*', route => route.request().url().startsWith(origin) && !route.request().url().endsWith('/maplibre-gl.mjs') ? route.continue() : route.abort());
  const fallback = await fallbackContext.newPage();
  await fallback.goto(origin);
  await fallback.locator('#open-run').click();
  await fallback.locator('#use-synthetic').click();
  await fallback.locator('#edit-locations').click();
  await fallback.locator('#location-map-status').filter({hasText: 'Mapa no disponible'}).waitFor();
  await fallback.locator('#location-latitude').fill('0');
  await fallback.locator('#location-longitude').fill('0');
  await fallback.locator('#confirm-locations').click();
  assert.match(await fallback.locator('#run-message').textContent(), /Ubicaciones confirmadas/);
  await fallbackContext.close();
  console.log('PASS: fallo del renderizador del mapa conserva formulario, ceros y confirmación.');
} catch (error) {
  console.error(await page.evaluate(() => ({
    execution: sessionStorage.getItem('zmd.webapp.execution.v1'),
    message: document.querySelector('#run-message')?.textContent,
    invalid: [...document.querySelectorAll(':invalid')].map(el => [el.id, el.validationMessage]),
  })), errors);
  await page.screenshot({path: new URL('qa-failure.png', output).pathname});
  throw error;
} finally {
  await browser.close();
}
