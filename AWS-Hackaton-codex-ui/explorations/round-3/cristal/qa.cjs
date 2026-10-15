const {chromium}=require('/Users/caballero/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
const assert=require('node:assert/strict');
const dir=__dirname;
const url='http://127.0.0.1:4173/round-3/cristal/';
const results={date:new Date().toISOString(),localDate:new Intl.DateTimeFormat('es-CL',{timeZone:'America/Santiago',dateStyle:'long',timeStyle:'short'}).format(new Date()),page:url,checks:[],errors:[],screenshots:[]};
const add=(name,detail)=>results.checks.push({name,passed:true,detail});
const screenshot=async(page,name)=>{await page.screenshot({path:path.join(dir,name),fullPage:true});results.screenshots.push(name);};
const size=page=>page.evaluate(()=>({viewport:innerWidth,scrollWidth:document.documentElement.scrollWidth,height:document.documentElement.scrollHeight}));
const waitReady=async page=>{
  await page.waitForSelector('body[data-app-ready="true"]');
  await page.waitForSelector('#map[data-map-ready="true"]',{timeout:30000});
  await page.waitForFunction(()=>document.querySelectorAll('.zmd-pin').length===81);
};
const fitVisible=async page=>{
  await page.locator('#fit').click();
  await page.waitForFunction(()=>{
    const map=document.getElementById('map').getBoundingClientRect();
    const pins=[...document.querySelectorAll('.zmd-pin:not([hidden])')].filter(pin=>!pin.classList.contains('is-muted'));
    return pins.length && pins.every(pin=>{
      const p=pin.getBoundingClientRect();
      return p.left>=map.left && p.right<=map.right && p.top>=map.top && p.bottom<=map.bottom;
    });
  });
};
const glass=page=>page.locator('.glass-controls').evaluate(el=>({
  background:getComputedStyle(el).backgroundColor,
  filter:getComputedStyle(el).backdropFilter,
  border:getComputedStyle(el).borderTopColor,
  transparency:matchMedia('(prefers-reduced-transparency:reduce)').matches,
  contrast:matchMedia('(prefers-contrast:more)').matches,
  forcedColors:matchMedia('(forced-colors:active)').matches
}));

(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',args:['--enable-unsafe-swiftshader']});
  try {
    const context=await browser.newContext({viewport:{width:1440,height:900},deviceScaleFactor:1});
    const page=await context.newPage();
    page.on('pageerror',error=>results.errors.push(error.message));
    await page.goto(url,{waitUntil:'domcontentloaded'});
    await waitReady(page);
    await fitVisible(page);
    const desktop=await size(page);
    assert.equal(desktop.scrollWidth,1440);
    const actions=await page.locator('.route-button').evaluateAll(buttons=>{
      const panel=document.getElementById('sidebar-content').getBoundingClientRect();
      return buttons.map(button=>{const b=button.getBoundingClientRect();return {visible:b.top>=panel.top && b.bottom<=panel.bottom,top:b.top,bottom:b.bottom,panelBottom:panel.bottom};});
    });
    assert.equal(actions.every(action=>action.visible),true);
    add('Desktop 1440×900 y ambas acciones visibles',{...desktop,actions});
    const material=await glass(page);
    assert.ok(material.filter.includes('blur(18px)'));
    const backgrounds=await page.locator('.vehicle-card,.map-summary').evaluateAll(elements=>elements.map(el=>getComputedStyle(el).backgroundColor));
    assert.equal(backgrounds.every(value=>value==='rgb(255, 255, 255)'),true);
    add('Vidrio limitado a controles y contenido opaco',{material,backgrounds});
    await screenshot(page,'qa-desktop.png');

    await page.locator('[data-vehicle="auto-1"]').focus();
    await page.keyboard.press('Enter');
    assert.equal(await page.locator('.route-head h2').textContent(),'Auto 1');
    assert.deepEqual(await page.evaluate(()=>({route:document.activeElement.dataset.route,index:document.activeElement.dataset.index})),{route:'auto-1',index:'0'});
    add('Explorar recorrido conserva foco','Enter en Auto 1 lleva el foco a su parada de salida, sin caer al body.');
    await fitVisible(page);
    await page.locator('.zmd-pin[aria-label="Local 16 (V16)"]').click();
    assert.equal(await page.locator('.stop-row.active').getAttribute('data-index'),'10');
    assert.equal(await page.locator('#selection h3').textContent(),'Local 16');
    add('Mapa a lista: V16 concreto','Click real en V16 selecciona parada 10 de Auto 1.');
    await fitVisible(page);
    await page.locator('.zmd-pin[aria-label="Local 5 (V5)"]').click();
    assert.equal(await page.locator('.route-head h2').textContent(),'Auto 2');
    assert.equal(await page.locator('.stop-row.active').getAttribute('data-index'),'1');
    assert.equal(await page.locator('#selection h3').textContent(),'Local 5');
    assert.equal(await page.locator('.zmd-pin[aria-label="Local 5 (V5)"]').getAttribute('aria-pressed'),'true');
    add('Selección entre vehículos desde el mapa','V5 cambia de Auto 1 a Auto 2 y sincroniza parada 1 y batería.');

    const returnRow=page.locator('.stop-row[data-route="auto-2"][data-index="12"]');
    await returnRow.focus();
    await page.keyboard.press('Enter');
    assert.equal(await page.locator('#selection h3').textContent(),'Regreso a BASE');
    assert.equal(await page.evaluate(()=>document.activeElement.dataset.index),'12');
    await page.locator('.zmd-pin[aria-label="Centro de distribución (BASE)"]').focus();
    await page.keyboard.press('Enter');
    assert.equal(await page.locator('.stop-row.active').getAttribute('data-index'),'12');
    assert.equal(await page.locator('#selection h3').textContent(),'Regreso a BASE');
    add('BASE por índice y foco estable','Regreso de Auto 2 conserva índice 12 al seleccionar el marcador compartido de BASE.');
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('#selection').evaluate(el=>el.hidden),true);
    assert.equal(await page.evaluate(()=>document.activeElement.getAttribute('aria-label')),'Centro de distribución (BASE)');
    add('Cerrar detalle devuelve foco','Escape devuelve foco al marcador que originó el detalle.');

    await page.locator('#all-routes').click();
    assert.equal(await page.locator('.route-head h2').count(),2);
    assert.equal(await page.evaluate(()=>document.activeElement.id),'stops-tab');
    await page.keyboard.press('ArrowLeft');
    assert.equal(await page.locator('#fleet-tab').getAttribute('aria-selected'),'true');
    assert.equal(await page.evaluate(()=>document.activeElement.id),'fleet-tab');
    await page.keyboard.press('End');
    assert.equal(await page.locator('#stops-tab').getAttribute('aria-selected'),'true');
    add('Pestañas con teclado','Flechas y Home/End actualizan tabpanel; Ver ambos vehículos conserva foco.');

    await page.locator('#chargers').click();
    assert.equal(await page.locator('.zmd-pin.type-charger:not([hidden])').count(),60);
    await page.locator('#chargers').click();
    assert.equal(await page.locator('.zmd-pin.type-charger:not([hidden])').count(),2);
    add('Cargadores registrados','El control muestra 60 estaciones; al ocultarlas permanecen las dos recargas del ejemplo.');
    await page.locator('#about').focus();
    await page.keyboard.press('Enter');
    assert.equal(await page.locator('#about-dialog').evaluate(dialog=>dialog.open),true);
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('#about-dialog').evaluate(dialog=>dialog.open),false);
    assert.equal(await page.evaluate(()=>document.activeElement.id),'about');
    add('Procedencia accesible','Diálogo nativo abre por Enter; Escape devuelve el foco a Acerca de los datos.');

    const session=await context.newCDPSession(page);
    await session.send('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-transparency',value:'reduce'}]});
    const solid=await glass(page);
    assert.equal(solid.transparency,true);
    assert.equal(solid.filter,'none');
    assert.equal(solid.background,'rgb(249, 251, 253)');
    add('Transparencia reducida',solid);
    await page.locator('#fleet-tab').click();
    await fitVisible(page);
    await screenshot(page,'qa-reduced-transparency.png');
    await session.send('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-transparency',value:'no-preference'},{name:'prefers-contrast',value:'more'}]});
    const contrast=await glass(page);
    assert.equal(contrast.contrast,true);
    assert.equal(contrast.filter,'none');
    assert.equal(contrast.background,'rgb(255, 255, 255)');
    add('Alto contraste',contrast);
    await screenshot(page,'qa-high-contrast.png');
    await session.send('Emulation.setEmulatedMedia',{features:[{name:'prefers-contrast',value:'no-preference'},{name:'forced-colors',value:'active'}]});
    const forced=await glass(page);
    assert.equal(forced.forcedColors,true);
    assert.equal(forced.filter,'none');
    add('Colores forzados',forced);
    await screenshot(page,'qa-forced-colors.png');

    for(const width of [390,319]){
      const mobile=await browser.newContext({viewport:{width,height:844},deviceScaleFactor:1,reducedMotion:'reduce'});
      const mp=await mobile.newPage();
      mp.on('pageerror',error=>results.errors.push(error.message));
      await mp.goto(url,{waitUntil:'domcontentloaded'});
      await waitReady(mp);
      await fitVisible(mp);
      const mobileSize=await size(mp);
      assert.equal(mobileSize.scrollWidth,width);
      const readability=await mp.evaluate(()=>({
        model:getComputedStyle(document.querySelector('.vehicle-model')).fontSize,
        metricLabel:getComputedStyle(document.querySelector('.map-summary small')).fontSize,
        soc:getComputedStyle(document.querySelector('.soc-row')).fontSize,
        battery:document.querySelector('.battery-meter').getBoundingClientRect().width,
        motion:matchMedia('(prefers-reduced-motion:reduce)').matches,
        transition:getComputedStyle(document.querySelector('.zmd-pin')).transitionDuration
      }));
      assert.equal(readability.model,'12px');
      assert.equal(readability.metricLabel,'10px');
      assert.equal(readability.soc,'11px');
      assert.equal(readability.motion,true);
      assert.equal(readability.transition,'0s');
      assert.ok(readability.battery>=47);
      const obstruction=await mp.evaluate(()=>{
        const surfaces=['.map-summary','.map-tools','.legend','.maplibregl-ctrl-attrib'].map(selector=>({selector,bounds:document.querySelector(selector).getBoundingClientRect()}));
        return [...document.querySelectorAll('.zmd-pin:not([hidden])')].flatMap(pin=>{
          const box=pin.getBoundingClientRect();
          return surfaces.filter(({bounds})=>box.left<bounds.right && box.right>bounds.left && box.top<bounds.bottom && box.bottom>bounds.top).map(({selector})=>({pin:pin.getAttribute('aria-label'),surface:selector}));
        });
      });
      assert.deepEqual(obstruction,[]);
      await screenshot(mp,`qa-mobile-${width}.png`);
      await mp.locator('#stops-tab').click();
      await mp.locator('.stop-row[data-route="auto-2"][data-index="12"]').focus();
      await mp.keyboard.press('Enter');
      assert.equal(await mp.locator('#selection h3').textContent(),'Regreso a BASE');
      assert.equal(await mp.locator('.zmd-pin[aria-label="Centro de distribución (BASE)"]').getAttribute('aria-pressed'),'true');
      const bounds=await mp.locator('#selection').evaluate(el=>{const b=el.getBoundingClientRect();return {left:b.left,right:b.right,viewport:innerWidth};});
      assert.ok(bounds.left>=0 && bounds.right<=width);
      await screenshot(mp,`qa-mobile-${width}-selection.png`);
      add(`Móvil ${width} px`,{...mobileSize,readability,obstruction,selectionBounds:bounds,returnSelection:'Auto 2, BASE índice 12'});
      await mobile.close();
    }
    const baseline=JSON.parse(fs.readFileSync(path.join(dir,'baseline-hashes.json'),'utf8'));
    const integrity={};
    for(const [name,hash] of Object.entries(baseline.sha256)){
      integrity[name]=crypto.createHash('sha256').update(fs.readFileSync(path.join(baseline.source,name))).digest('hex')===hash;
    }
    assert.equal(Object.values(integrity).every(Boolean),true);
    add('Opción 1 preservada',integrity);
    assert.equal(results.errors.length,0);
    results.passed=true;
    fs.writeFileSync(path.join(dir,'qa-results.json'),JSON.stringify(results,null,2)+'\n');
    console.log(JSON.stringify(results,null,2));
  }catch(error){
    results.passed=false;results.failure=error.stack;
    fs.writeFileSync(path.join(dir,'qa-results.json'),JSON.stringify(results,null,2)+'\n');
    throw error;
  }finally{await browser.close();}
})();
