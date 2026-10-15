const { chromium } = require('/Users/caballero/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const output = __dirname;
const baseUrl = 'http://127.0.0.1:4173/round-2/energia/';
const results = {date: new Date().toISOString(), page:baseUrl, browser:'Google Chrome / Playwright', checks:[], errors:[], networkHosts:[]};
const check = (name,detail) => results.checks.push({name,passed:true,detail});
const fixtures = JSON.parse(fs.readFileSync(path.join(output,'../shared/fixture.local.json'),'utf8'));
const waitMap = async page => {
  await page.waitForSelector('body[data-app-ready="true"]');
  await page.waitForSelector('#map[data-map-ready="true"]',{timeout:30000});
  await page.waitForFunction(() => document.querySelectorAll('.zmd-pin').length > 0);
};
const selectedStep = page => page.locator('.step-button[aria-pressed="true"]').getAttribute('data-step-index');
const noOverflow = async page => page.evaluate(() => ({
  viewport:innerWidth,
  page:document.documentElement.scrollWidth,
  chart:document.getElementById('soc-chart').getBoundingClientRect().width,
  map:document.getElementById('map').getBoundingClientRect().width
}));

(async () => {
  const browser = await chromium.launch({
    headless:true,
    executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    args:['--enable-unsafe-swiftshader']
  });
  const hosts = new Set();
  try {
    const desktop = await browser.newContext({viewport:{width:1440,height:1080},deviceScaleFactor:1});
    const page = await desktop.newPage();
    page.on('pageerror',error=>results.errors.push(error.message));
    page.on('request',request=>hosts.add(new URL(request.url()).host));
    await page.goto(baseUrl,{waitUntil:'domcontentloaded'});
    await waitMap(page);
    assert.equal(await page.locator('.vehicle-card').count(),2);
    assert.equal(await page.locator('.vehicle-model').allTextContents().then(texts=>texts.every(text=>text==='Nissan Leaf 2013')),true);
    assert.equal(await page.locator('.vehicle-start').allTextContents().then(texts=>texts.every(text=>text.includes('60 %'))),true);
    assert.equal(await page.locator('#delivery-count').textContent(),'20');
    check('Contexto eléctrico visible','Dos Nissan Leaf 2013, salida al 60 %, veinte entregas, retorno a BASE y cifras etiquetadas como ejemplo.');

    const charge = await page.locator('[data-charge-index]').evaluate(line=>({
      from:Number(line.getAttribute('y1')),to:Number(line.getAttribute('y2')),
      x1:line.getAttribute('x1'),x2:line.getAttribute('x2')
    }));
    assert.equal(charge.x1,charge.x2);
    assert.ok(charge.to < charge.from);
    assert.ok((await page.locator('#stop-detail').textContent()).includes('+4,5'));
    check('Recarga como aumento de SoC',charge);

    await page.locator('[data-vehicle="auto-2"]').focus();
    await page.keyboard.press('Enter');
    assert.equal(await page.locator('[data-vehicle="auto-2"]').getAttribute('aria-pressed'),'true');
    assert.equal(await page.evaluate(()=>document.activeElement.dataset.vehicle),'auto-2');
    assert.equal(await selectedStep(page),'4');
    check('Selección de vehículo por teclado','Enter conserva el foco, actualiza el perfil de Auto 2 y selecciona su recarga C9.');

    await page.locator('[data-chart-index="4"]').focus();
    await page.keyboard.press('ArrowRight');
    assert.equal(await selectedStep(page),'5');
    assert.equal(await page.evaluate(()=>document.activeElement.dataset.chartIndex),'5');
    assert.ok((await page.locator('#stop-detail').textContent()).includes('Local 10'));
    assert.equal(await page.locator('.zmd-pin[aria-label="Local 10 (V10)"]').getAttribute('aria-pressed'),'true');
    await page.keyboard.press('End');
    assert.equal(await selectedStep(page),'12');
    assert.ok((await page.locator('#stop-detail').textContent()).includes('Regreso a BASE'));
    await page.keyboard.press('Home');
    assert.equal(await selectedStep(page),'0');
    check('Gráfico, teclado y mapa sincronizados','Flechas y Home/End conservan foco y seleccionan el mismo nodo en detalle, lista y mapa.');

    await page.locator('[data-step-index="4"]').focus();
    await page.keyboard.press('Space');
    assert.equal(await selectedStep(page),'4');
    assert.equal(await page.evaluate(()=>document.activeElement.dataset.stepIndex),'4');
    assert.equal(await page.locator('.zmd-pin[aria-label="Cargador 9 (C9)"]').getAttribute('aria-pressed'),'true');
    check('Secuencia por teclado','Espacio en C9 conserva foco de la lista y lo relaciona con el mapa.');

    await page.locator('[data-vehicle="auto-1"]').click();
    await page.locator('#fit-map').click();
    await page.locator('.zmd-pin[aria-label="Local 16 (V16)"]').click();
    assert.equal(await selectedStep(page),'10');
    assert.ok((await page.locator('#stop-detail').textContent()).includes('Local 16'));
    check('Mapa hacia perfil','Click real en Local 16 actualiza parada 10, detalle y gráfico de Auto 1.');

    await page.locator('[data-step-index="12"]').click();
    await page.locator('.zmd-pin[aria-label="Centro de distribución (BASE)"]').focus();
    await page.keyboard.press('Enter');
    assert.equal(await selectedStep(page),'12');
    check('BASE repetida en la ruta','La selección de BASE preserva el retorno cuando esa parada ya está activa.');

    await page.locator('#show-source').click();
    assert.equal(await page.locator('#source-dialog').evaluate(dialog=>dialog.open),true);
    assert.ok((await page.locator('#source-battery').textContent()).includes('no una capacidad útil confirmada'));
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('#source-dialog').evaluate(dialog=>dialog.open),false);
    assert.equal(await page.evaluate(()=>document.activeElement.id),'show-source');
    check('Procedencia y diálogo accesible','Se declara el balance ilustrativo de 16 kWh; Escape cierra y devuelve foco.');

    await page.locator('#show-chargers').check();
    await page.locator('#fit-map').click();
    const before = await page.locator('.zmd-pin.type-charger:not([hidden])').count();
    assert.equal(before,60);
    const unused = await page.locator('.zmd-pin.type-charger:not([hidden])').evaluateAll(pins=>{
      const bounds=document.getElementById('map').getBoundingClientRect();
      return pins.find(pin=>{
        const box=pin.getBoundingClientRect(),label=pin.getAttribute('aria-label');
        return !/\((C3|C9)\)$/.test(label)&&box.left>bounds.left+20&&box.right<bounds.right-20&&box.top>bounds.top+20&&box.bottom<bounds.bottom-45;
      })?.getAttribute('aria-label');
    });
    assert.ok(unused);
    await page.locator(`.zmd-pin[aria-label="${unused}"]`).click();
    assert.equal(await page.locator('.step-button[aria-pressed="true"]').count(),0);
    assert.equal(await page.locator('.chart-target[tabindex="0"]').count(),1);
    assert.ok((await page.locator('#stop-detail').textContent()).includes('no forma parte'));
    assert.ok((await page.locator('#map-selection').textContent()).includes('disponibilidad sin verificar'));
    await page.locator('#show-chargers').uncheck();
    check('Cargador fuera de la secuencia','Mostrar sesenta estaciones permite seleccionar una registrada sin inventar balance ni disponibilidad.');

    await page.locator('[data-vehicle="auto-1"]').click();
    await page.locator('#fit-map').click();
    const size = await noOverflow(page);
    assert.equal(size.page,size.viewport);
    await page.screenshot({path:path.join(output,'qa-desktop.png'),fullPage:true});
    check('Desktop 1440 px sin desbordamiento',size);

    const mobile = await browser.newContext({viewport:{width:390,height:844},deviceScaleFactor:1,reducedMotion:'reduce'});
    const mp = await mobile.newPage();
    mp.on('pageerror',error=>results.errors.push(error.message));
    mp.on('request',request=>hosts.add(new URL(request.url()).host));
    await mp.goto(baseUrl,{waitUntil:'domcontentloaded'});
    await waitMap(mp);
    const mobileSize = await noOverflow(mp);
    assert.equal(mobileSize.page,390);
    assert.ok(mobileSize.chart>=350 && mobileSize.map>=350);
    await mp.locator('[data-vehicle="auto-2"]').click();
    await mp.locator('[data-step-index="12"]').click();
    assert.ok((await mp.locator('#stop-detail').textContent()).includes('Regreso a BASE'));
    assert.equal(await mp.locator('.zmd-pin[aria-label="Centro de distribución (BASE)"]').getAttribute('aria-pressed'),'true');
    const motion = await mp.evaluate(()=>({
      preference:matchMedia('(prefers-reduced-motion:reduce)').matches,
      card:getComputedStyle(document.querySelector('.vehicle-card')).transitionDuration,
      mapPin:getComputedStyle(document.querySelector('.zmd-pin')).transitionDuration
    }));
    assert.equal(motion.preference,true);
    assert.equal(motion.card,'0s');
    assert.equal(motion.mapPin,'0s');
    await mp.locator('[data-vehicle="auto-1"]').click();
    await mp.locator('#fit-map').click();
    await mp.screenshot({path:path.join(output,'qa-mobile.png'),fullPage:true});
    check('Móvil 390 px y movimiento reducido',{...mobileSize,motion,selection:'Retorno BASE de Auto 2 comprobado antes de captura del ejemplo inicial.'});

    const unknown = await browser.newContext({viewport:{width:1440,height:1080},reducedMotion:'reduce'});
    const up = await unknown.newPage();
    up.on('pageerror',error=>results.errors.push(error.message));
    const missing = structuredClone(fixtures);
    missing.ROUTES[0].stops[9].arrivalSoc = null;
    missing.ROUTES[0].stops[9].departureSoc = null;
    missing.ROUTES[0].stops[9].chargeKwh = null;
    missing.ROUTES[0].energyKwh = null;
    missing.ROUTES[0].finalSoc = null;
    await up.route('**/shared/fixture.local.json',route=>route.fulfill({json:missing}));
    await up.goto(baseUrl,{waitUntil:'domcontentloaded'});
    await waitMap(up);
    await up.locator('[data-step-index="9"]').click();
    assert.equal(await up.locator('.detail-value strong').allTextContents().then(values=>values.every(value=>value==='—')),true);
    assert.equal(await up.locator('.vehicle-card[data-vehicle="auto-1"] .battery-reading strong').textContent(),'—');
    const nullMetrics = await up.locator('#route-summary strong').allTextContents();
    assert.equal(nullMetrics[0],'—');
    assert.equal(nullMetrics[2],'—');
    check('Datos desconocidos conservados','SoC de entrada/salida, recarga, consumo y SoC final nulos muestran —; no se convierten en cero.');
    await unknown.close();
    assert.equal(results.errors.length,0);
    results.networkHosts = [...hosts].sort();
    results.passed = true;
    fs.writeFileSync(path.join(output,'qa-results.json'),JSON.stringify(results,null,2));
    console.log(JSON.stringify(results,null,2));
  } catch (error) {
    results.passed=false;
    results.failure=error.stack;
    fs.writeFileSync(path.join(output,'qa-results.json'),JSON.stringify(results,null,2));
    throw error;
  } finally {
    await browser.close();
  }
})();
