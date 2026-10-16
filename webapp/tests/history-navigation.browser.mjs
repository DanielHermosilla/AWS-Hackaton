// Regression: the last run's H1 preparation must never replace the tab's H2
// choice or resurrect a removed profile during navigation. All APIs are doubles.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const {chromium} = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const origin = process.env.ZMD_QA_ORIGIN || 'http://127.0.0.1:4326';
const fixture = JSON.parse(await readFile(new URL('../../backend/fixtures/native-response.json', import.meta.url)));
const preparation = JSON.parse(await readFile(new URL('../../backend/fixtures/synthetic-prepare-request.json', import.meta.url)));
fixture.result.raw.prepare_request = {...preparation, energy_profile_id: 'history-old'};
const browser = await chromium.launch({headless: true});
const context = await browser.newContext();
let connected = false, ai = 'not_requested';
const calls = [], errors = [];
const status = () => ({state: connected ? 'connected' : 'disconnected', connected, reasoning_effort: 'high'});
const profile = id => ({profile_id: id, status: 'ready', filename: `${id}.csv`, summary: {row_count: 20, trip_count: 2}, warnings: [], assumptions: [], ai_analysis: {status: ai}});
await context.addInitScript(({runId}) => {
  if (!sessionStorage.getItem('zmd.webapp.execution.v1')) sessionStorage.setItem('zmd.webapp.execution.v1', JSON.stringify({runId, status: 'complete', stale: false}));
}, {runId: fixture.result.run_id});
await context.route('**/*', async route => {
  const request = route.request(), url = new URL(request.url());
  if (!url.href.startsWith(origin)) return route.abort();
  const respond = (body, code = 200) => route.fulfill({status: code, contentType: 'application/json', body: JSON.stringify({api_version: '3.0', ...body})});
  if (url.pathname === '/solve') return respond({result: fixture.result});
  if (url.pathname === '/history') {
    const id = url.searchParams.get('profile_id'); calls.push({path: '/history', id});
    return respond({profile: profile(id)});
  }
  if (url.pathname === '/history/upload') return respond({profile: profile('history-new')});
  // H1 and H2 remain available server-side after this explicit failed removal.
  if (url.pathname === '/history/remove') return respond({error: {message: 'Simulated removal failure'}}, 503);
  if (url.pathname === '/bedrock/session') {
    if (request.method() === 'POST') connected = true;
    return respond({status: status()});
  }
  if (url.pathname === '/history/analyze') {
    calls.push({path: '/history/analyze', body: request.postDataJSON()});
    ai = 'reviewed'; return respond({profile: profile('history-new')});
  }
  return route.continue();
});
const page = await context.newPage();
page.on('pageerror', error => errors.push(error.message));
const selected = () => page.evaluate(() => JSON.parse(sessionStorage.getItem('zmd.webapp.execution.v1')).energyProfile);
const draftProfile = () => page.evaluate(() => JSON.parse(sessionStorage.getItem('zmd.webapp.location-draft.v1')).input.prepareRequest.energy_profile_id ?? null);
try {
  await page.goto(origin);
  await page.locator('#open-run').click();
  await page.waitForFunction(() => document.querySelector('#history-filename')?.textContent === 'history-old.csv');
  await page.locator('#history-file').setInputFiles({name: 'nuevo-eVED.csv', mimeType: 'text/csv', buffer: Buffer.from('VehId,Trip\n1,1')});
  await page.waitForFunction(() => document.querySelector('#history-filename').textContent === 'history-new.csv');
  assert.equal((await selected()).profile_id, 'history-new');
  assert.equal(await draftProfile(), 'history-new');
  assert.equal(await page.locator('#history-analyze').textContent(), 'Ampliar análisis con IA');
  await page.locator('#history-analyze').click();
  await page.locator('#bedrock-dialog').waitFor();
  assert.equal(calls.filter(call => call.path === '/history/analyze').length, 0);
  await page.locator('#bedrock-connect').click();
  await page.waitForFunction(() => !document.querySelector('#bedrock-disconnect').hidden);
  await page.locator('#bedrock-close').click();
  await page.locator('#history-analyze').click();
  await page.waitForFunction(() => document.querySelector('#history-analyze').hidden);
  assert.deepEqual(calls.filter(call => call.path === '/history/analyze'), [{path: '/history/analyze', body: {profile_id: 'history-new'}}]);
  // Recover tabs saved by the previous buggy version too: explicit H2 wins even
  // if their nested preparation still contains H1.
  await page.evaluate(() => {
    const draft = JSON.parse(sessionStorage.getItem('zmd.webapp.location-draft.v1'));
    draft.input.prepareRequest.energy_profile_id = 'history-old';
    sessionStorage.setItem('zmd.webapp.location-draft.v1', JSON.stringify(draft));
  });
  await page.goto(`${origin}/plan.html`);
  await page.locator('#open-run').click();
  await page.waitForFunction(() => document.querySelector('#history-filename').textContent === 'history-new.csv');
  assert.equal((await selected()).profile_id, 'history-new');
  assert.equal(await draftProfile(), 'history-new');
  await page.locator('#history-remove').click();
  await page.waitForFunction(() => document.querySelector('#history-state').textContent.includes('no pudimos retirarlo'));
  assert.equal(await selected(), null);
  assert.equal(await draftProfile(), null);
  await page.evaluate(() => {
    const draft = JSON.parse(sessionStorage.getItem('zmd.webapp.location-draft.v1'));
    draft.input.prepareRequest.energy_profile_id = 'history-old';
    sessionStorage.setItem('zmd.webapp.location-draft.v1', JSON.stringify(draft));
  });
  const retrievalsBeforeNavigation = calls.filter(call => call.path === '/history').length;
  await page.goto(origin);
  await page.locator('#open-run').click();
  await page.waitForFunction(() => document.querySelector('#input-summary').textContent.includes('Borrador'));
  assert.equal(await selected(), null);
  assert.equal(await draftProfile(), null);
  assert.equal(await page.locator('#history-profile').isVisible(), false);
  assert.match(await page.locator('#history-state').textContent(), /Sin histórico/);
  assert.equal(calls.filter(call => call.path === '/history').length, retrievalsBeforeNavigation);
  assert.deepEqual(errors, []);
  console.log('PASS: H1→H2 and removal survive navigation despite old result/server profile; ready eVED can request explicit AI analysis after AWS connection. API responses mocked.');
} finally { await browser.close(); }
