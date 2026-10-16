// Deterministic source-switch regressions against a local static webapp server.
// No solver, AWS, history processing or map downloads.
import assert from 'node:assert/strict';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
const {chromium} = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const origin = process.env.ZMD_QA_ORIGIN || 'http://127.0.0.1:4294';
const output = new URL('../../.local/source-switch-qa/', import.meta.url);
await mkdir(output, {recursive: true});
const {instance: native} = JSON.parse(await readFile(new URL('../../backend/fixtures/native-request.json', import.meta.url)));
const nodes = [
  {node_id: 'BASE', node_type: 'base', latitude: 42.27708, longitude: -83.76281},
  {node_id: 'C1', node_type: 'visit', latitude: 42.28, longitude: -83.76},
];
const profile = {profile_id: 'ready-history', status: 'ready', filename: 'EV.csv', summary: {row_count: 10}};
const scenario = (name = 'Current historical scenario') => ({
  name, source_file: 'competition_routing_nodes.csv', nodes, network_mode: 'road',
  scenario: {kind: 'hackathon', dataset: 'competition'},
});
const browser = await chromium.launch({headless: true,
  ...(process.env.CHROME_EXECUTABLE ? {executablePath: process.env.CHROME_EXECUTABLE} : {})});
const results = [];
const filter = process.env.ZMD_QA_CASE;

async function run(name, check) {
  if (filter && filter !== name) return;
  const context = await browser.newContext({viewport: {width: 1440, height: 900}, reducedMotion: 'reduce'});
  const page = await context.newPage();
  page.setDefaultTimeout(15000);
  page.setDefaultNavigationTimeout(30000);
  const releases = [], errors = [], requests = [];
  const observations = {};
  page.on('pageerror', error => errors.push(error.message));
  await context.addInitScript(() => {
    window.__scenarioBodiesCompleted = 0;
    let completed = 0;
    const channel = new MessageChannel();
    channel.port1.onmessage = event => { window.__scenarioBodiesCompleted = event.data; };
    const fetch = window.fetch;
    window.fetch = async (...args) => {
      const response = await fetch(...args);
      if (new URL(args[0], location.href).pathname === '/scenarios/hackathon') {
        const json = response.json.bind(response);
        response.json = async () => {
          try { return await json(); }
          finally {
            // Observe a browser task after the request's promise continuations.
            channel.port2.postMessage(++completed);
          }
        };
      }
      return response;
    };
  });
  const reply = (route, body, status = 200) => route.fulfill({status, json: {api_version: '3.0', ...body}});
  await context.route('**/*', route => {
    const request = route.request(), url = new URL(request.url());
    if (url.origin !== origin) return route.abort();
    if (url.pathname === '/bedrock/session') return reply(route, {status: {connected: false}});
    if (url.pathname === '/history') return reply(route, {profile});
    if (url.pathname === '/scenarios/hackathon' && request.method() === 'GET')
      return reply(route, {scenario: scenario('Initial map')});
    if (url.pathname === '/prepare' || url.pathname === '/solve') {
      requests.push({path: url.pathname, body: request.postDataJSON()});
      return reply(route, {error: {message: 'CURRENT REQUEST RECEIVED'}}, 400);
    }
    if (url.pathname.startsWith('/history') || url.pathname.startsWith('/scenarios'))
      return reply(route, {error: {message: 'Unmocked backend operation'}}, 503);
    if (url.pathname.endsWith('/positron.json')) return route.fulfill({json: {version: 8, sources: {}, layers: []}});
    return route.continue();
  });
  const tools = {
    page, context, requests, observations, reply,
    hold() {
      let resolve;
      const promise = new Promise(done => { resolve = done; });
      releases.push(resolve);
      return {promise, resolve};
    },
    async settled(count) {
      await page.waitForFunction(expected => window.__scenarioBodiesCompleted >= expected, count);
    },
    async open() {
      await page.goto(origin);
      await page.locator('#scenario-counts').filter({hasText: '1 clientes · 0 cargadores'}).waitFor();
      await page.locator('#open-run').click();
    },
    async synthetic() {
      await page.locator('.run-synthetic summary').click();
      await page.locator('#use-synthetic').click();
    },
    async native() {
      await page.locator('#instance-file').setInputFiles({name: 'native.json', mimeType: 'application/json',
        buffer: Buffer.from(JSON.stringify(native))});
      await page.locator('#run-message').filter({hasText: 'Archivo cargado'}).waitFor();
    },
  };
  try {
    await check(tools);
    assert.deepEqual(errors, []);
    results.push({name, status: 'pass', observations});
    console.log('PASS', name, JSON.stringify(observations));
  } catch (error) {
    observations.message = await page.locator('#run-message').textContent().catch(() => null);
    observations.requests = requests;
    results.push({name, status: 'fail', error: error.message, observations, errors});
    console.error('FAIL', name, error.message, JSON.stringify(observations));
    await page.screenshot({path: new URL(`${name}.png`, output).pathname, fullPage: true}).catch(() => {});
  } finally {
    releases.forEach(resolve => resolve());
    await context.close();
  }
}

await run('obsolete-scenario-submit', async ({page, context, requests, observations, reply, hold, settled, open, synthetic}) => {
  const hit = hold(), release = hold();
  await context.route('**/scenarios/hackathon', async route => {
    hit.resolve(); await release.promise;
    return reply(route, {error: {message: 'OBSOLETE HISTORY ERROR'}}, 500);
  });
  await open();
  await page.locator('#use-hackathon').click(); await hit.promise;
  await page.locator('#solve-run').click();
  await synthetic();
  await page.locator('#run-policy').selectOption('standard');
  await page.locator('#solve-run').click();
  await page.locator('#run-message').filter({hasText: 'CURRENT REQUEST RECEIVED'}).waitFor();
  release.resolve(); await settled(2);
  observations.message = await page.locator('#run-message').innerText();
  assert.equal(observations.message, 'CURRENT REQUEST RECEIVED');
  assert.equal(requests.length, 1);
  assert.equal(requests[0].body.network_mode, 'haversine');
});

await run('abandoned-autoload-submit', async ({page, context, requests, observations, reply, hold, settled, synthetic}) => {
  const hit = hold(), release = hold();
  let calls = 0;
  // A missing initial preview leaves the supported upload-first path available.
  await context.route('**/scenarios/hackathon?*', async route => {
    if (++calls <= 2) return reply(route, {error: {message: `SCENARIO FAILURE ${calls}`}}, 500);
    hit.resolve(); await release.promise;
    return reply(route, {scenario: scenario('Obsolete retry')});
  });
  await context.route('**/history/upload', route => reply(route, {profile}));
  await page.goto(origin);
  await page.locator('#scenario-message').filter({hasText: 'SCENARIO FAILURE 1'}).waitFor();
  await page.locator('#open-run').click();
  await page.locator('#history-file').setInputFiles({name: 'EV.csv', mimeType: 'text/csv', buffer: Buffer.from('VehId,Trip\n1,1')});
  await page.locator('#run-message').filter({hasText: 'SCENARIO FAILURE 2'}).waitFor();
  await page.locator('#solve-run').click(); await hit.promise;
  await synthetic();
  observations.before = await page.locator('#run-message').innerText();
  release.resolve(); await settled(3);
  observations.after = await page.locator('#run-message').innerText();
  assert.equal(requests.length, 0, 'The abandoned submit must not prepare the replacement source.');
  assert.equal(observations.after, observations.before);
});

await run('overlapping-scenario-loads', async ({page, context, observations, reply, hold, settled, open, synthetic}) => {
  const firstHit = hold(), firstRelease = hold(), secondHit = hold(), secondRelease = hold();
  let calls = 0;
  await context.route('**/scenarios/hackathon', async route => {
    if (++calls === 1) {
      firstHit.resolve(); await firstRelease.promise;
      return reply(route, {error: {message: 'OBSOLETE FIRST LOAD'}}, 500);
    }
    secondHit.resolve(); await secondRelease.promise;
    return reply(route, {profile, scenario: scenario()});
  });
  await open();
  await page.locator('#use-hackathon').click(); await firstHit.promise;
  await synthetic();
  await page.locator('#use-hackathon').click(); await secondHit.promise;
  firstRelease.resolve(); await settled(2);
  assert.equal(await page.locator('#use-hackathon').isDisabled(), true, 'An old finally must not unlock the current request.');
  assert.doesNotMatch(await page.locator('#run-message').innerText(), /OBSOLETE FIRST LOAD/);
  secondRelease.resolve(); await settled(3);
  await page.locator('#input-summary').filter({hasText: 'Current historical scenario'}).waitFor();
  observations.network = await page.locator('#run-network').inputValue();
  observations.history = await page.locator('#history-filename').innerText();
  assert.equal(await page.locator('#use-hackathon').isEnabled(), true);
  assert.equal(observations.network, 'road');
  assert.equal(observations.history, 'EV.csv');
});

await run('native-during-upload', async ({page, context, requests, observations, reply, hold, open, native}) => {
  const hit = hold(), release = hold();
  await context.route('**/history/upload', async route => {
    hit.resolve(); await release.promise;
    return reply(route, {error: {message: 'Controlled upload failure'}}, 400);
  });
  await open();
  await page.locator('#history-file').setInputFiles({name: 'pending.csv', mimeType: 'text/csv', buffer: Buffer.from('VehId,Trip\n1,1')});
  await hit.promise;
  await native();
  await page.locator('#run-policy').selectOption('standard');
  await page.locator('#solve-run').click();
  await page.locator('#run-message').filter({hasText: 'CURRENT REQUEST RECEIVED'}).waitFor();
  assert.equal(requests.length, 1);
  assert.equal(requests[0].path, '/solve');
  release.resolve();
  await page.waitForFunction(() => document.querySelector('#history-cancel').hidden);
  observations.message = await page.locator('#run-message').innerText();
  assert.equal(observations.message, 'CURRENT REQUEST RECEIVED');
  assert.match(await page.locator('#history-state').innerText(), /consumo incluido en el JSON/);
});

await run('historical-case-during-default-history', async ({page, context, requests, observations, reply, hold, settled, open}) => {
  const hit = hold(), release = hold();
  let calls = 0;
  await context.route('**/scenarios/hackathon', async route => {
    if (++calls === 1) {
      hit.resolve(); await release.promise;
      return reply(route, {error: {message: 'OBSOLETE DEFAULT HISTORY ERROR'}}, 500);
    }
    return reply(route, {profile, scenario: scenario()});
  });
  await open();
  await page.locator('#run-policy').selectOption('standard');
  await page.locator('#solve-run').click(); await hit.promise;
  await page.locator('#use-hackathon').click();
  await page.locator('#input-summary').filter({hasText: 'Current historical scenario'}).waitFor();
  await page.locator('#solve-run').click();
  await page.locator('#run-message').filter({hasText: 'CURRENT REQUEST RECEIVED'}).waitFor();
  release.resolve(); await settled(3);
  observations.message = await page.locator('#run-message').innerText();
  assert.equal(observations.message, 'CURRENT REQUEST RECEIVED');
  assert.equal(requests.length, 1);
  assert.equal(requests[0].body.energy_profile_id, profile.profile_id);
  assert.deepEqual(requests[0].body.nodes, nodes);
});

for (const succeeds of [false, true]) {
  await run(`obsolete-default-history-${succeeds ? 'success' : 'failure'}`, async ({page, context, requests, observations, reply, hold, settled, open, native}) => {
    const hit = hold(), release = hold();
    await context.route('**/scenarios/hackathon', async route => {
      hit.resolve(); await release.promise;
      return succeeds ? reply(route, {profile, scenario: scenario('Old default history')})
        : reply(route, {error: {message: 'OBSOLETE DEFAULT HISTORY ERROR'}}, 500);
    });
    await open();
    await page.locator('#run-policy').selectOption('standard');
    await page.locator('#solve-run').click(); await hit.promise;
    await native();
    await page.locator('#solve-run').click();
    await page.locator('#run-message').filter({hasText: 'CURRENT REQUEST RECEIVED'}).waitFor();
    release.resolve(); await settled(2);
    observations.message = await page.locator('#run-message').innerText();
    assert.equal(observations.message, 'CURRENT REQUEST RECEIVED');
    assert.equal(requests.length, 1);
    assert.equal(requests[0].path, '/solve');
    assert.match(await page.locator('#history-state').innerText(), /consumo incluido en el JSON/);
  });
}

for (const choice of ['pending', 'ready', 'removed']) {
  for (const succeeds of [false, true]) {
    await run(`explicit-history-${choice}-old-${succeeds ? 'success' : 'failure'}`, async ({page, context, requests, observations, reply, hold, settled, open}) => {
      const defaultHit = hold(), defaultRelease = hold(), uploadHit = hold(), uploadRelease = hold();
      const selected = {...profile, profile_id: 'user-history', filename: 'my-choice.csv'};
      await context.route('**/scenarios/hackathon', async route => {
        defaultHit.resolve(); await defaultRelease.promise;
        return succeeds ? reply(route, {profile, scenario: scenario('Old default history')})
          : reply(route, {error: {message: 'OBSOLETE DEFAULT HISTORY ERROR'}}, 500);
      });
      await context.route('**/history/upload', async route => {
        uploadHit.resolve(); await uploadRelease.promise;
        return reply(route, {profile: selected});
      });
      await context.route('**/history/remove', route => reply(route, {removed: true}));
      const waitForSelection = async () => {
        await page.locator('#history-filename').filter({hasText: selected.filename}).waitFor();
        await page.waitForFunction(() => document.querySelector('#history-cancel').hidden);
      };
      await open();
      await page.locator('#run-policy').selectOption('standard');
      await page.locator('#solve-run').click(); await defaultHit.promise;
      await page.locator('#history-file').setInputFiles({name: selected.filename, mimeType: 'text/csv', buffer: Buffer.from('VehId,Trip\n1,1')});
      await uploadHit.promise;
      if (choice !== 'pending') {
        uploadRelease.resolve(); await waitForSelection();
        if (choice === 'removed') {
          await page.locator('#history-remove').click();
          await page.locator('#history-state').filter({hasText: 'Histórico retirado'}).waitFor();
        }
        await page.locator('#solve-run').click();
        await page.locator('#run-message').filter({hasText: 'CURRENT REQUEST RECEIVED'}).waitFor();
      }
      observations.before = await page.locator('#run-message').innerText();
      defaultRelease.resolve(); await settled(2);
      observations.after = await page.locator('#run-message').innerText();
      assert.equal(requests.length, choice === 'pending' ? 0 : 1, 'Choosing a history source must retire the previous submit.');
      assert.equal(observations.after, observations.before);
      if (choice === 'pending') {
        assert.equal(await page.locator('#history-cancel').isVisible(), true, 'The old default must not cancel the user upload.');
        uploadRelease.resolve(); await waitForSelection();
      } else if (choice === 'ready') {
        assert.equal(await page.locator('#history-filename').innerText(), selected.filename);
      } else {
        assert.equal(await page.locator('#history-profile').isHidden(), true, 'The explicit removal must remain selected.');
      }
      if (choice === 'pending') {
        await page.locator('#solve-run').click();
        await page.locator('#run-message').filter({hasText: 'CURRENT REQUEST RECEIVED'}).waitFor();
      }
      assert.equal(requests.length, 1);
      assert.equal(requests[0].body.energy_profile_id, choice === 'removed' ? undefined : selected.profile_id);
    });
  }
}

for (const succeeds of [false, true]) {
  await run(`confirmed-location-edit-old-${succeeds ? 'success' : 'failure'}`, async ({page, context, requests, observations, reply, hold, settled, open}) => {
    const firstHit = hold(), firstRelease = hold(), secondRelease = hold();
    let calls = 0;
    await context.route('**/scenarios/hackathon', async route => {
      if (++calls === 1) {
        firstHit.resolve(); await firstRelease.promise;
        return succeeds ? reply(route, {profile, scenario: scenario('Old default history')})
          : reply(route, {error: {message: 'OBSOLETE DEFAULT HISTORY ERROR'}}, 500);
      }
      await secondRelease.promise;
      return reply(route, {profile, scenario: scenario()});
    });
    await open();
    await page.locator('#run-policy').selectOption('standard');
    await page.locator('#solve-run').click(); await firstHit.promise;
    await page.locator('#edit-locations').click();
    await page.locator('#location-address').fill('Confirmed updated depot');
    await page.locator('#confirm-locations').click();
    const secondStarted = page.waitForRequest(request => new URL(request.url()).pathname === '/scenarios/hackathon' && request.method() === 'POST');
    await page.locator('#solve-run').click(); await secondStarted;
    observations.before = await page.locator('#run-message').innerText();
    firstRelease.resolve(); await settled(2);
    observations.after = await page.locator('#run-message').innerText();
    assert.equal(requests.length, 0);
    assert.equal(observations.after, observations.before);
    secondRelease.resolve();
    await page.locator('#run-message').filter({hasText: 'CURRENT REQUEST RECEIVED'}).waitFor();
    assert.equal(requests.length, 1);
    assert.equal(requests[0].body.nodes[0].address, 'Confirmed updated depot');
  });
}

await browser.close();
assert.ok(results.length, 'No source-switch test matched ZMD_QA_CASE.');
await writeFile(new URL('results.json', output), JSON.stringify(results, null, 2));
if (results.some(result => result.status === 'fail')) process.exitCode = 1;
