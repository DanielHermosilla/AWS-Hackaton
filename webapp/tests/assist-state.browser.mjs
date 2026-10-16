// Assistant result adoption uses the same execution/draft state as the run panel.
// HTTP doubles only; no solver, AWS or external map requests.
import assert from 'node:assert/strict';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
const {chromium} = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const origin = process.env.ZMD_QA_ORIGIN || 'http://127.0.0.1:4294';
const response = JSON.parse(await readFile(new URL('../../backend/fixtures/native-response.json', import.meta.url)));
const output = new URL('../../.local/assist-state-qa/', import.meta.url);
await mkdir(output, {recursive: true});
const key = 'zmd.webapp.execution.v1';
const browser = await chromium.launch({headless: true});
const results = [];
for (const editWhilePending of [false, true]) {
  const name = editWhilePending ? 'assistant-does-not-publish-over-later-edit' : 'assistant-result-retires-previous-draft';
  const context = await browser.newContext({viewport: {width: 1440, height: 1000}, reducedMotion: 'reduce'});
  const page = await context.newPage();
  page.setDefaultTimeout(12000);
  let release, hit;
  const waiting = new Promise(resolve => { release = resolve; });
  const requested = new Promise(resolve => { hit = resolve; });
  const observations = {};
  await context.addInitScript(() => {
    window.__assistCompleted = false;
    const channel = new MessageChannel();
    channel.port1.onmessage = () => { window.__assistCompleted = true; };
    const original = window.fetch;
    window.fetch = async (...args) => {
      const response = await original(...args);
      if (new URL(args[0], location.href).pathname === '/assist/chat') {
        const json = response.json.bind(response);
        response.json = async () => { try { return await json(); } finally { channel.port2.postMessage(true); } };
      }
      return response;
    };
  });
  await context.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.origin !== origin) return route.abort();
    if (url.pathname === '/bedrock/session') return route.fulfill({json: {api_version: '3.0', status: {connected: false}}});
    if (url.pathname === '/scenarios/hackathon') return route.fulfill({json: {api_version: '3.0', scenario: {
      name: 'Original scenario', source_file: 'competition_routing_nodes.csv',
      nodes: [{node_id: 'BASE', node_type: 'base', latitude: 42, longitude: -83},
        {node_id: 'C', node_type: 'visit', latitude: 42.1, longitude: -83.1}],
      scenario: {kind: 'hackathon', dataset: 'competition'},
    }}});
    if (url.pathname === '/assist/chat') {
      hit(); await waiting;
      return route.fulfill({json: {api_version: 'assist-1.0', session_id: 'mock-session',
        respuesta: 'Plan calculado', modo: 'local', resolvio: true, run_id: response.result.run_id}});
    }
    if (url.pathname === '/solve' && route.request().method() === 'GET') return route.fulfill({json: response});
    if (['/prepare', '/solve'].includes(url.pathname) || url.pathname.startsWith('/history'))
      return route.fulfill({status: 503, json: {error: {message: 'Unmocked backend operation'}}});
    if (url.pathname.endsWith('/positron.json')) return route.fulfill({json: {version: 8, sources: {}, layers: []}});
    return route.continue();
  });
  try {
    await page.goto(origin);
    await page.locator('#open-run').click();
    await page.locator('#input-summary').filter({hasText: 'Original scenario'}).waitFor();
    await page.locator('.run-synthetic summary').click();
    await page.locator('#use-synthetic').click();
    await page.locator('#run-capacity').fill('27');
    await page.locator('#close-run').click();
    await page.locator('.assist-toggle').click();
    await page.locator('.assist-input').fill('calcula');
    await page.locator('.assist-send').click(); await requested;
    if (editWhilePending) {
      await page.locator('#open-run').click();
      await page.locator('#run-capacity').fill('31');
      await page.locator('#close-run').click();
    }
    observations.before = await page.evaluate(key => JSON.parse(sessionStorage.getItem(key)), key);
    release();
    await page.waitForFunction(() => window.__assistCompleted);
    observations.after = await page.evaluate(key => JSON.parse(sessionStorage.getItem(key)), key);
    if (editWhilePending) {
      assert.equal(observations.after.stale, true, 'A late assistant result must not mark the newer manual draft as current.');
      assert.equal(observations.after.draftId, observations.before.draftId);
    } else {
      await page.waitForURL('**/plan.html*');
      await page.locator('main[aria-busy="false"]').waitFor();
      await page.locator('#open-run').click();
      observations.visibleCapacity = await page.locator('#run-capacity').inputValue();
      observations.expectedCapacity = String(response.result.raw.instance.parameters.battery_capacity_kwh);
      assert.equal(observations.visibleCapacity, observations.expectedCapacity, 'The accepted assistant result must restore its own input.');
      assert.equal(observations.after.draftId, null);
    }
    results.push({name, status: 'pass', observations});
    console.log('PASS', name);
  } catch (error) {
    results.push({name, status: 'fail', error: error.message, observations});
    console.log('FAIL', name, error.message, JSON.stringify(observations));
  } finally {
    release();
    await context.close();
  }
}
await browser.close();
await writeFile(new URL('results.json', output), JSON.stringify(results, null, 2));
if (results.some(result => result.status === 'fail')) process.exitCode = 1;
