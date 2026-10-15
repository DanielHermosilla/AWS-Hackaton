const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const {chromium} = require('/Users/caballero/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root = path.resolve(__dirname, '..');
const repo = path.resolve(root, '../../..');
const base = 'http://127.0.0.1:4173/round-3/bateria/';
const report = {tested_at_utc:new Date().toISOString(),scope:'Only the battery variant, existing fixture, linked selection, affected keyboard and accordion paths. No engine, Kiro or new metrics.',checks:[],errors:[]};
const check = (name,passed,evidence) => report.checks.push({name,passed,evidence});
const hash = p => crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
let browser;

(async () => {
  browser = await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
  report.browser = await browser.version();
  const page = await browser.newPage({viewport:{width:1440,height:900},deviceScaleFactor:1});
  page.on('pageerror',error => report.errors.push(String(error)));
  await page.goto(base,{waitUntil:'domcontentloaded'});
  await page.waitForSelector('.vehicle-card');
  await page.waitForSelector('#map[data-map-ready="true"]',{timeout:15000});
  await page.screenshot({path:path.join(root,'qa/desktop.png')});
  const layout = await page.evaluate(() => {
    const foot = document.querySelector('.sidebar-foot').getBoundingClientRect();
    return {
      sidebar_width:document.querySelector('.sidebar').getBoundingClientRect().width,
      actions:[...document.querySelectorAll('.route-button')].map(b => ({top:b.getBoundingClientRect().top,bottom:b.getBoundingClientRect().bottom,visible:b.getBoundingClientRect().bottom<=foot.top})),
      metrics:[...document.querySelectorAll('.map-summary strong')].map(e=>e.textContent),
      mini_profiles:document.querySelectorAll('.mini-profile').length,
      charges:[...document.querySelectorAll('.charge-caption')].map(e=>e.textContent.trim()),
    };
  });
  check('original_composition_and_both_actions',layout.sidebar_width===352&&layout.actions.length===2&&layout.actions.every(a=>a.visible),layout);
  check('original_three_metrics',JSON.stringify(layout.metrics)===JSON.stringify(['20 / 20','14,3 kWh','2']),layout.metrics);
  check('two_small_profiles_existing_charge_values',layout.mini_profiles===2&&layout.charges.join('|').includes('4,5 kWh')&&layout.charges.join('|').includes('3,2 kWh'),layout.charges);
  check('tab_roles',await page.locator('[role="tablist"]').count()===1&&await page.locator('[role="tab"]').count()===2&&await page.locator('[role="tabpanel"]').count()===1,true);
  await page.locator('#fleet-tab').focus();
  await page.keyboard.press('ArrowRight');
  check('tabs_arrow_right',await page.locator('#stops-tab').getAttribute('aria-selected')==='true'&&await page.locator('#stops-tab').evaluate(e=>e===document.activeElement)&&await page.locator('#fleet-tab').getAttribute('tabindex')==='-1',await page.locator('#sidebar-content').getAttribute('aria-labelledby'));
  await page.keyboard.press('Home');
  check('tabs_home',await page.locator('#fleet-tab').getAttribute('aria-selected')==='true'&&await page.locator('#fleet-tab').evaluate(e=>e===document.activeElement),true);
  await page.keyboard.press('End');
  check('tabs_end',await page.locator('#stops-tab').getAttribute('aria-selected')==='true'&&await page.locator('#stops-tab').evaluate(e=>e===document.activeElement),true);
  await page.keyboard.press('ArrowLeft');
  check('tabs_arrow_left',await page.locator('#fleet-tab').getAttribute('aria-selected')==='true',true);
  await page.locator('[data-vehicle="auto-1"]').click();
  const toggle = page.locator('#profile-toggle-auto-1');
  check('selected_route_profile_starts_collapsed',await toggle.getAttribute('aria-expanded')==='false'&&await page.locator('#profile-content-auto-1').evaluate(e=>e.hidden&&e.inert),true);
  await toggle.click();
  await page.waitForFunction(()=>document.getElementById('profile-content-auto-1').style.height==='auto');
  check('expanded_has_13_indexed_points',await page.locator('.profile-point').count()===13,await page.locator('.profile-point').evaluateAll(points=>points.map(p=>({node:p.dataset.stop,index:p.dataset.index}))));
  await page.locator('.profile-point[data-index="9"]').click();
  const charge = await page.locator('#selection').evaluate(e=>({index:e.dataset.index,route:e.dataset.route,text:e.textContent,battery:[...e.querySelectorAll('.stop-battery strong')].map(s=>s.textContent)}));
  const linked = await page.evaluate(()=>({list:document.querySelector('.stop-row.active')?.dataset.index,profile:document.querySelector('.profile-point.active')?.dataset.index,map:document.querySelector('.zmd-pin.is-selected')?.getAttribute('aria-label'),focus:document.activeElement.dataset.focusKey}));
  check('charge_point_links_list_map_and_values',charge.index==='9'&&charge.route==='auto-1'&&charge.battery.join('|')==='22 %|50,1 %'&&charge.text.includes('4,5 kWh')&&linked.list==='9'&&linked.profile==='9'&&linked.map?.includes('(C3)')&&linked.focus==='profile:auto-1:9',{charge,linked});
  await page.screenshot({path:path.join(root,'qa/profile-charge-desktop.png')});
  await page.keyboard.press('Escape');
  check('escape_closes_detail_restores_point',await page.locator('#selection').evaluate(e=>e.hidden)&&await page.locator('.profile-point[data-index="9"]').evaluate(e=>e===document.activeElement),true);
  await page.locator('.profile-point[data-index="12"]').click();
  check('base_return_is_index_12_not_departure',await page.locator('#selection').getAttribute('data-index')==='12'&&await page.locator('#selection h3').textContent()==='Regreso a base'&&(await page.locator('#selection .stop-battery strong').allTextContents()).join('|')==='37,5 %|37,5 %',await page.locator('#selection').textContent());
  await page.locator('.zmd-pin.type-base').click();
  check('map_base_keeps_selected_return_occurrence',await page.locator('#selection').getAttribute('data-index')==='12'&&await page.locator('.stop-row.active').getAttribute('data-index')==='12',await page.locator('#selection').textContent());
  await page.locator('.profile-point[data-index="0"]').click();
  check('base_departure_is_index_zero_60',await page.locator('#selection').getAttribute('data-index')==='0'&&await page.locator('#selection h3').textContent()==='Salida de base'&&(await page.locator('#selection .stop-battery strong').allTextContents()).join('|')==='60 %|60 %',await page.locator('#selection').textContent());
  await page.locator('.stop-row[data-index="10"]').click();
  check('list_links_back_to_profile',await page.locator('.profile-point.active').getAttribute('data-index')==='10'&&await page.locator('.zmd-pin.is-selected').getAttribute('aria-label').then(v=>v.includes('(V16)')),await page.locator('#selection').textContent());
  await page.locator('#close-selection').click();
  check('close_button_restores_original_list_control',await page.locator('.stop-row[data-index="10"]').evaluate(e=>e===document.activeElement),true);
  await page.locator('#fleet-tab').click();
  await page.locator('[data-vehicle="auto-2"]').click();
  const toggleB = page.locator('#profile-toggle-auto-2');
  await toggleB.focus();
  await page.keyboard.press('Enter');
  check('keyboard_expand_is_instant',await page.locator('#profile-content-auto-2').evaluate(e=>!e.hidden&&e.style.height==='auto')&&(await page.locator('#profile-toggle-auto-2 .profile-chevron').evaluate(e=>getComputedStyle(e).transitionDuration))==='0s',true);
  await page.locator('.profile-point[data-index="4"]').focus();
  await page.keyboard.press('Enter');
  check('keyboard_charge_b_uses_existing_values',(await page.locator('#selection .stop-battery strong').allTextContents()).join('|')==='46 %|66 %'&&(await page.locator('#selection').textContent()).includes('3,2 kWh'),await page.locator('#selection').textContent());
  // Dispatch both pointer clicks inside one browser task sequence. Playwright's
  // stability wait can otherwise delay the second click until the close is over.
  const reversal = await page.evaluate(async()=>{
    const panel=document.getElementById('profile-content-auto-2'),button=document.getElementById('profile-toggle-auto-2');
    const snapshot=()=>({height:panel.getBoundingClientRect().height,opacity:Number(getComputedStyle(panel).opacity)});
    button.dispatchEvent(new MouseEvent('click',{bubbles:true,detail:1}));
    await new Promise(resolve=>setTimeout(resolve,45));
    const before=snapshot();
    button.dispatchEvent(new MouseEvent('click',{bubbles:true,detail:1}));
    return {before,after:snapshot()};
  });
  await page.waitForFunction(()=>document.getElementById('profile-content-auto-2').style.height==='auto'&&!document.getElementById('profile-content-auto-2').hidden);
  check('rapid_reverse_preserves_visible_state',reversal.after.height>0&&reversal.after.opacity>0&&Math.abs(reversal.after.height-reversal.before.height)<2&&Math.abs(reversal.after.opacity-reversal.before.opacity)<.02,{...reversal,method:'Pointer MouseEvent detail=1, controlled 45 ms reversal without locator stability waits',final_height:await page.locator('#profile-content-auto-2').evaluate(e=>e.getBoundingClientRect().height)});
  await page.locator('#about').click();
  const originalHtml = fs.readFileSync(path.join(repo,'explorations/round-2/mapa/index.html'),'utf8');
  const originalParagraphs = await page.evaluate(source=>[...new DOMParser().parseFromString(source,'text/html').querySelectorAll('#about-dialog p')].map(e=>e.textContent),originalHtml);
  check('original_source_dialog_preserved',JSON.stringify(await page.locator('#about-dialog p').allTextContents())===JSON.stringify(originalParagraphs),await page.locator('#about-dialog p').allTextContents());
  await page.keyboard.press('Escape');
  check('about_escape_preserves_map_detail',!(await page.locator('#about-dialog').evaluate(e=>e.open))&&!(await page.locator('#selection').evaluate(e=>e.hidden)),true);
  await page.emulateMedia({reducedMotion:'reduce'});
  for (const width of [390,319]) {
    await page.setViewportSize({width,height:844});
    await page.goto(base,{waitUntil:'domcontentloaded'});
    await page.waitForSelector('.vehicle-card');
    await page.waitForSelector('#map[data-map-ready="true"]',{timeout:15000});
    await page.screenshot({path:path.join(root,`qa/mobile-${width}.png`),fullPage:true});
    const size = await page.evaluate(()=>({viewport:innerWidth,scroll_width:document.documentElement.scrollWidth,metrics:document.querySelectorAll('.map-summary>div').length}));
    check(`mobile_${width}_no_overflow`,size.viewport===size.scroll_width&&size.metrics===3,size);
    if (width===390) {
      await page.locator('[data-vehicle="auto-1"]').click();
      await page.locator('#profile-toggle-auto-1').click();
      const reducedPanel = await page.locator('#profile-content-auto-1').evaluate(e=>({height:e.style.height,hidden:e.hidden,transition:getComputedStyle(e).transitionDuration,inert:e.inert}));
      check('reduced_motion_expand_is_instant',reducedPanel.height==='auto'&&!reducedPanel.hidden&&!reducedPanel.inert&&reducedPanel.transition==='0s',reducedPanel);
      await page.locator('.profile-point[data-index="9"]').click();
      await page.screenshot({path:path.join(root,'qa/profile-mobile-390.png'),fullPage:true});
      check('mobile_charge_links_by_index',await page.locator('.stop-row.active').getAttribute('data-index')==='9'&&await page.locator('#selection').getAttribute('data-index')==='9',await page.locator('.profile-context').textContent());
      await page.locator('#profile-toggle-auto-1').click();
      check('collapsed_profile_is_hidden_inert',await page.locator('#profile-content-auto-1').evaluate(e=>e.hidden&&e.inert),true);
    }
  }
  const captured = JSON.parse(fs.readFileSync(path.join(root,'qa/base-hashes.json'),'utf8')).captured_before_variant;
  const current = Object.fromEntries(Object.keys(captured).map(name=>[name,hash(path.join(repo,'explorations/round-2/mapa',name))]));
  check('selected_base_unchanged',JSON.stringify(current)===JSON.stringify(captured),current);
  check('shared_fixture_unchanged_copy',hash(path.join(repo,'explorations/round-3/shared/fixture.local.json'))===hash(path.join(repo,'explorations/round-2/shared/fixture.local.json')),true);
  check('no_page_errors',report.errors.length===0,report.errors);
  report.passed = report.checks.every(c=>c.passed);
})().catch(error=>{
  report.errors.push(String(error));
  report.passed=false;
}).finally(async()=>{
  fs.writeFileSync(path.join(root,'qa/verification.json'),JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify({passed:report.passed,checks:report.checks,errors:report.errors},null,2));
  await browser?.close();
  if (!report.passed) process.exitCode=1;
});
