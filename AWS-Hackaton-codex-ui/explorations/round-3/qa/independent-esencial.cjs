const { chromium } = require('/Users/caballero/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const root = path.resolve(__dirname, '..');
const result = { startedAt: new Date().toISOString(), scope: 'Independent Esencial UI QA only', checks: [], layouts: [], pageErrors: [], httpErrors: [], requestsFailed: [] };
let browser, page;
function check(name, pass, evidence) {
  result.checks.push({ name, pass: !!pass, evidence });
  console.log(JSON.stringify({ name, pass: !!pass, evidence }));
}
async function settled() {
  await page.evaluate(() => new Promise(resolve => {
    const pin = document.querySelector('.zmd-pin[aria-label$="(V14)"]');
    let last = '', stable = 0;
    const step = () => {
      const r = pin?.getBoundingClientRect();
      const now = r ? `${r.x.toFixed(2)},${r.y.toFixed(2)}` : '';
      stable = now === last ? stable + 1 : 0;
      last = now;
      if (stable >= 12) return resolve();
      requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }));
}
async function detailState() {
  return page.evaluate(() => {
    const s = document.querySelector('#selection');
    const active = document.querySelector('.stop-row.active');
    return {
      hidden: s.hidden, inert: s.inert, opacity: getComputedStyle(s).opacity,
      transform: getComputedStyle(s).transform,
      title: s.querySelector('h3')?.textContent,
      eyebrow: s.querySelector('.detail-eyebrow')?.textContent,
      soc: [...s.querySelectorAll('.stop-battery strong')].map(x => x.textContent.trim()),
      route: active?.dataset.route, index: active?.dataset.index,
      status: document.querySelector('#selection-status')?.textContent,
      activeElement: document.activeElement?.outerHTML.slice(0, 400),
      muted: [...document.querySelectorAll('.zmd-pin.is-muted')].map(x => x.getAttribute('aria-label'))
    };
  });
}
async function pointer(selector) {
  const el = page.locator(selector);
  await el.scrollIntoViewIfNeeded();
  const r = await el.boundingBox();
  if (!r) throw new Error(`No visible pointer target ${selector}`);
  await page.mouse.click(r.x + r.width / 2, r.y + r.height / 2);
}
async function closeSettled() {
  if (await page.locator('#selection').isVisible()) await pointer('#close-selection');
  await page.waitForFunction(() => document.querySelector('#selection').hidden);
}
async function openRoute(id) {
  if (await page.locator('#all-routes').isVisible()) await page.locator('#all-routes').click();
  await page.locator('#fleet-tab').click();
  await page.locator(`[data-vehicle="${id}"]`).click();
  await settled();
}
async function measureLayout(width, height) {
  await page.setViewportSize({ width, height });
  await settled();
  const evidence = await page.evaluate(() => {
    const rect = selector => {
      const r = document.querySelector(selector).getBoundingClientRect();
      return { left:r.left, right:r.right, top:r.top, bottom:r.bottom, width:r.width, height:r.height };
    };
    const map = rect('.map-region'), summary = rect('.map-summary');
    const markers = [...document.querySelectorAll('.zmd-pin')].filter(x => !x.hidden && x.classList.contains('type-visit')).map(x => {
      const r = x.getBoundingClientRect();
      return { name:x.getAttribute('aria-label'), left:r.left, right:r.right, top:r.top, bottom:r.bottom };
    });
    return {
      viewport: { width:innerWidth, height:innerHeight },
      documentWidth:document.documentElement.scrollWidth,
      bodyWidth:document.body.scrollWidth,
      map, summary,
      summaryInsideMap:summary.left >= map.left - 1 && summary.right <= map.right + 1,
      allVisitsInsideMap:markers.every(r => r.left >= map.left - 1 && r.right <= map.right + 1 && r.top >= map.top && r.bottom <= map.bottom),
      markers,
      models:[...document.querySelectorAll('.vehicle-model')].map(x => x.textContent),
      cards:[...document.querySelectorAll('.soc-row')].map(x => x.textContent.trim()),
      canvas:document.querySelector('#map canvas') ? {width:document.querySelector('#map canvas').width,height:document.querySelector('#map canvas').height}:null,
      mapReady:document.querySelector('#map').dataset.mapReady,
      mapStatus:document.querySelector('.map-status')?.textContent
    };
  });
  result.layouts.push(evidence);
  check(`Esencial layout ${width}`, evidence.documentWidth <= width && evidence.bodyWidth <= width && evidence.summaryInsideMap && evidence.mapReady === 'true', evidence);
  if ([1440,390,319,701].includes(width)) await page.screenshot({ path:path.join(__dirname, `independent-esencial-${width}.png`),fullPage:width < 700 });
}
(async () => {
  browser = await chromium.launch({ executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless:true,args:['--enable-unsafe-swiftshader'] });
  page = await browser.newPage({viewport:{width:1440,height:900}});
  page.on('pageerror', e => result.pageErrors.push(e.message));
  page.on('response', response => { if (response.status() >= 400) result.httpErrors.push({url:response.url(),status:response.status()}); });
  page.on('requestfailed', r => result.requestsFailed.push({url:r.url(),failure:r.failure()?.errorText}));
  await page.goto('http://127.0.0.1:4173/round-3/esencial/');
  await page.waitForSelector('#map[data-map-ready="true"]', {timeout:45000});
  await measureLayout(1440,900);
  const fixture = await page.evaluate(async () => {
    const d = await import('/round-3/shared/data.js');
    const visits = d.ROUTES.flatMap(r => r.stops.filter(s=>d.nodeById(s.nodeId).type==='visit').map(s=>s.nodeId));
    return {vehicles:d.VEHICLES.map(v=>({name:v.name,model:v.model,initialSoc:v.initialSoc})),visits:visits.length,uniqueVisits:new Set(visits).size,routes:d.ROUTES.map(r=>({id:r.vehicleId,finalSoc:r.finalSoc,totalEnergy:r.stops.reduce((n,s)=>n+s.energyKwh,0),charge:r.stops.reduce((n,s)=>n+s.chargeKwh,0),first:r.stops[0],last:r.stops.at(-1)}))};
  });
  check('Existing fixture and two BASE occurrences',fixture.visits===20 && fixture.uniqueVisits===20 && fixture.vehicles.every(v=>v.initialSoc===60) && fixture.routes.every(r=>r.first.nodeId==='BASE'&&r.last.nodeId==='BASE'),fixture);
  for (const [id,soc] of [['auto-1','37,5'],['auto-2','41,25']]) {
    await openRoute(id);
    await page.locator(`[data-stop="BASE"][data-index="12"]`).click();
    await settled();
    await page.locator('.zmd-pin[aria-label$="(BASE)"]').click();
    await settled();
    let e = await detailState();
    check(`Repeated map BASE preserves return ${id}`,e.title==='Regreso a base'&&e.route===id&&e.index==='12'&&e.soc.every(v=>v.includes(soc)),e);
    await page.locator('[data-stop="BASE"][data-index="0"]').click();
    await settled();
    await page.locator('.zmd-pin[aria-label$="(BASE)"]').click();
    e = await detailState();
    check(`Map BASE preserves departure ${id}`,e.title==='Salida de base'&&e.index==='0'&&e.soc.every(v=>v.includes('60')),e);
  }
  await openRoute('auto-1');
  await page.locator('.zmd-pin[aria-label$="(V5)"]').click();
  let cross = await detailState();
  const listRoutes = await page.locator('.stop-row').evaluateAll(rows=>[...new Set(rows.map(x=>x.dataset.route))]);
  check('Cross vehicle selects Auto 2 consistently',cross.eyebrow==='Auto 2 · V5'&&cross.route==='auto-2'&&cross.index==='1'&&listRoutes.join(',')==='auto-2'&&cross.muted.length===10,cross);
  await closeSettled();
  await page.locator('[data-stop="V5"]').focus();
  await page.keyboard.press('Enter');
  let keyState = await detailState();
  check('Keyboard selection is immediate',!keyState.hidden&&!keyState.inert&&keyState.opacity==='1',keyState);
  await page.locator('#close-selection').focus();
  await page.keyboard.press('Escape');
  keyState = await detailState();
  check('Escape returns focus to original row',keyState.hidden&&keyState.activeElement?.includes('data-stop="V5"'),keyState);
  // Real pointer clicks deliberately reverse an in-progress transition.
  await pointer('[data-stop="V5"]');
  await page.waitForFunction(() => {
    const s=document.querySelector('#selection'),a=Number(getComputedStyle(s).opacity);
    return !s.hidden && a>0 && a<.99;
  },null,{polling:'raf',timeout:3000});
  const beforeClose = await detailState();
  await pointer('#close-selection');
  const whileClosing = await detailState();
  await pointer('[data-stop="V9"]');
  await page.waitForFunction(() => {
    const s=document.querySelector('#selection');
    return !s.hidden&&!s.inert&&Number(getComputedStyle(s).opacity)>.999&&document.querySelector('.stop-row.active')?.dataset.stop==='V9'&&s.getAnimations().length===0;
  },null,{polling:'raf',timeout:4000});
  const afterReopen = await detailState();
  await page.evaluate(() => new Promise(resolve => {
    let frames=0;
    const step=()=>++frames>=20?resolve():requestAnimationFrame(step);
    requestAnimationFrame(step);
  }));
  const afterOldExit = await detailState();
  check('Pointer interruption preserves new stop after old exit',beforeClose.opacity!=='1'&&whileClosing.inert&&afterReopen.eyebrow==='Auto 2 · V9'&&afterOldExit.eyebrow==='Auto 2 · V9'&&!afterOldExit.hidden&&!afterOldExit.inert&&afterOldExit.opacity==='1',{beforeClose,whileClosing,afterReopen,afterOldExit});
  await page.screenshot({path:path.join(__dirname,'independent-esencial-interruption.png')});
  await closeSettled();
  await pointer('[data-stop="V5"]');
  await page.waitForFunction(()=>Number(getComputedStyle(document.querySelector('#selection')).opacity)>0&&Number(getComputedStyle(document.querySelector('#selection')).opacity)<.99,null,{polling:'raf',timeout:3000});
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.waitForFunction(()=>getComputedStyle(document.querySelector('#selection')).opacity==='1',null,{polling:'raf',timeout:4000});
  const reduced = await detailState();
  const animationCount = await page.locator('#selection').evaluate(e=>e.getAnimations().length);
  check('Live reduced-motion interrupts and settles detail',reduced.opacity==='1'&&reduced.transform==='none'&&animationCount===0,{...reduced,animationCount});
  await page.locator('#about').focus();
  await page.keyboard.press('Enter');
  const accessible = await page.locator('#about-dialog').evaluate(e=>({open:e.open,label:e.getAttribute('aria-labelledby'),labelText:document.getElementById(e.getAttribute('aria-labelledby'))?.textContent,focus:e.contains(document.activeElement)}));
  await page.keyboard.press('Escape');
  const aboutReturn = await page.evaluate(()=>document.activeElement?.id);
  check('Provenance dialog has name and returns focus',accessible.open&&accessible.labelText&&accessible.focus&&aboutReturn==='about',{...accessible,aboutReturn});
  await page.locator('#close-selection').focus();
  await page.keyboard.press('Escape');
  await page.emulateMedia({reducedMotion:'no-preference'});
  await page.locator('#all-routes').click();
  await page.locator('#fleet-tab').click();
  for (const [width,height] of [[900,900],[720,900],[701,900],[390,844],[319,859]]) await measureLayout(width,height);
  const baseline=JSON.parse(fs.readFileSync(path.join(__dirname,'baseline-sha256.json'),'utf8'));
  const changed=Object.entries(baseline).filter(([p,h])=>crypto.createHash('sha256').update(fs.readFileSync(path.resolve(root,'..',p))).digest('hex')!==h).map(([p])=>p);
  check('Original 18 baseline hashes unchanged',Object.keys(baseline).length===18&&changed.length===0,{count:Object.keys(baseline).length,changed});
  check('No JavaScript exceptions or HTTP failures',result.pageErrors.length===0&&result.httpErrors.length===0,{pageErrors:result.pageErrors,httpErrors:result.httpErrors});
})().catch(e=>{result.fatal={message:e.message,stack:e.stack};console.error(e);process.exitCode=1;}).finally(async()=>{
  result.finishedAt=new Date().toISOString();
  fs.writeFileSync(path.join(__dirname,'independent-esencial-results.json'),JSON.stringify(result,null,2));
  await browser?.close();
});
