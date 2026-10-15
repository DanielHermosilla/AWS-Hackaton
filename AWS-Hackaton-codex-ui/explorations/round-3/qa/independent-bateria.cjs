const {chromium}=require('/Users/caballero/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs'),path=require('path');
const result={startedAt:new Date().toISOString(),checks:[],layouts:[],contrast:[],errors:[],httpErrors:[],requestsFailed:[]};
let browser,page;
function check(name,pass,evidence){result.checks.push({name,pass:!!pass,evidence});console.log(JSON.stringify({name,pass:!!pass,evidence}));}
async function settled(){
  await page.evaluate(()=>new Promise(resolve=>{
    let last='',stable=0;
    const step=()=>{
      const r=document.querySelector('.zmd-pin[aria-label$="(V14)"]')?.getBoundingClientRect();
      const now=r?`${r.x.toFixed(2)},${r.y.toFixed(2)}`:'';
      stable=now===last?stable+1:0;last=now;
      if(stable>=12)return resolve();
      requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }));
}
async function state(){
  return page.evaluate(()=>{
    const e=document.querySelector('#selection');
    return {hidden:e.hidden,title:e.querySelector('h3')?.textContent,text:e.textContent.trim(),route:e.dataset.route,index:e.dataset.index,soc:[...e.querySelectorAll('.stop-battery strong')].map(x=>x.textContent),active:[...document.querySelectorAll('[data-stop].active')].map(x=>({node:x.dataset.stop,route:x.dataset.route,index:x.dataset.index,kind:x.className})),focus:document.activeElement?.dataset.focusKey,status:document.querySelector('#selection-status').textContent,profileContext:document.querySelector('[data-profile-context]')?.textContent,mapSelected:document.querySelector('.zmd-pin.is-selected')?.getAttribute('aria-label')};
  });
}
async function route(id){
  if(await page.locator('#all-routes').isVisible())await page.locator('#all-routes').click();
  await page.locator('#fleet-tab').click();
  await page.locator(`[data-vehicle="${id}"]`).click();
  await settled();
}
async function layout(width,height){
  await page.setViewportSize({width,height});await settled();
  const e=await page.evaluate(()=>{
    const r=s=>{const b=document.querySelector(s).getBoundingClientRect();return {left:b.left,right:b.right,top:b.top,bottom:b.bottom,width:b.width,height:b.height};};
    const map=r('.map-region'),summary=r('.map-summary');
    const sidebar=document.querySelector('#sidebar-content').getBoundingClientRect();
    const cta=[...document.querySelectorAll('[data-vehicle]')].map(x=>{const b=x.getBoundingClientRect();return {vehicle:x.dataset.vehicle,top:b.top,bottom:b.bottom,visibleInSidebar:b.top>=sidebar.top&&b.bottom<=sidebar.bottom};});
    return {viewport:{width:innerWidth,height:innerHeight},documentWidth:document.documentElement.scrollWidth,bodyWidth:document.body.scrollWidth,map,summary,summaryInside:summary.left>=map.left-1&&summary.right<=map.right+1,mapReady:document.querySelector('#map').dataset.mapReady,mapStatus:document.querySelector('.map-status').textContent,models:[...document.querySelectorAll('.vehicle-model')].map(x=>x.textContent),miniProfiles:document.querySelectorAll('.mini-profile').length,cta};
  });
  result.layouts.push(e);
  check(`Batería layout ${width}`,e.documentWidth<=width&&e.bodyWidth<=width&&e.summaryInside&&e.mapReady==='true'&&(width!==1440||e.cta.every(c=>c.visibleInSidebar)),e);
  await page.screenshot({path:path.join(__dirname,`independent-bateria-${width}.png`),fullPage:width<700});
}
async function profileOpen(id,keyboard=false){
  const toggle=page.locator(`#profile-toggle-${id}`);
  if(await toggle.getAttribute('aria-expanded')!=='true'){
    if(keyboard){await toggle.focus();await page.keyboard.press('Enter');}
    else await toggle.click();
  }
  await page.waitForFunction(id=>{
    const p=document.querySelector(`#profile-content-${id}`);
    return !p.hidden&&!p.inert&&getComputedStyle(p).opacity==='1'&&p.style.height==='auto'&&p.getAnimations().length===0;
  },id,{polling:'raf',timeout:4000});
}
function luminance(rgb){
  return rgb.map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;}).reduce((n,v,i)=>n+v*[.2126,.7152,.0722][i],0);
}
(async()=>{
  browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:['--enable-unsafe-swiftshader']});
  page=await browser.newPage({viewport:{width:1440,height:900}});
  page.on('pageerror',e=>result.errors.push(e.message));
  page.on('response',r=>{if(r.status()>=400)result.httpErrors.push({url:r.url(),status:r.status()});});
  page.on('requestfailed',r=>result.requestsFailed.push({url:r.url(),failure:r.failure()?.errorText}));
  await page.goto('http://127.0.0.1:4173/round-3/bateria/');
  await page.waitForSelector('#map[data-map-ready=true]',{timeout:45000});
  await layout(1440,900);
  await page.locator('#fleet-tab').focus();await page.keyboard.press('End');
  let tab=await page.evaluate(()=>({active:document.activeElement.id,selected:document.querySelector('#stops-tab').getAttribute('aria-selected'),fleetTabIndex:document.querySelector('#fleet-tab').tabIndex,stopsTabIndex:document.querySelector('#stops-tab').tabIndex}));
  check('Tabs use End with roving focus and selection',tab.active==='stops-tab'&&tab.selected==='true'&&tab.fleetTabIndex===-1&&tab.stopsTabIndex===0,tab);
  await page.keyboard.press('Home');
  tab=await page.evaluate(()=>({active:document.activeElement.id,selected:document.querySelector('#fleet-tab').getAttribute('aria-selected')}));
  check('Tabs use Home to return to vehicles',tab.active==='fleet-tab'&&tab.selected==='true',tab);
  await route('auto-1');await profileOpen('auto-1',true);
  const profile=await page.locator('#profile-content-auto-1').evaluate(e=>({height:e.style.height,opacity:getComputedStyle(e).opacity,hidden:e.hidden,inert:e.inert,animations:e.getAnimations().length,focus:document.activeElement?.id}));
  check('Keyboard opens full battery profile immediately',profile.height==='auto'&&profile.opacity==='1'&&!profile.hidden&&!profile.inert&&profile.animations===0,profile);
  await page.locator('.profile-point[data-index="9"]').focus();await page.keyboard.press('Enter');await settled();
  let e=await state();
  check('C3 point links profile, list and map to charge fixture',e.title==='Cargador 3'&&e.route==='auto-1'&&e.index==='9'&&e.soc[0]==='22 %'&&e.soc[1]==='50,1 %'&&e.text.includes('+4,5 kWh')&&e.active.length===2&&e.active.every(a=>a.node==='C3'&&a.index==='9')&&e.mapSelected.endsWith('(C3)'),e);
  await page.screenshot({path:path.join(__dirname,'independent-bateria-profile-charge.png')});
  const styles=await page.evaluate(()=>{
    const selectors=['.profile-label','.profile-axis','.profile-plot text','.profile-legend','.profile-note'];
    return selectors.map(s=>{
      const e=document.querySelector(s),c=getComputedStyle(e);
      let p=e,bg;
      while(p){const b=getComputedStyle(p).backgroundColor;if(b!=='rgba(0, 0, 0, 0)'&&b!=='transparent'){bg=b;break;}p=p.parentElement;}
      return {selector:s,text:e.textContent.trim(),color:s==='.profile-plot text'?c.fill:c.color,background:bg,fontSize:c.fontSize};
    });
  });
  for(const s of styles){
    const fg=s.color.match(/[\d.]+/g).slice(0,3).map(Number),bg=s.background.match(/[\d.]+/g).slice(0,3).map(Number);
    const l1=luminance(fg),l2=luminance(bg);
    s.ratio=(Math.max(l1,l2)+.05)/(Math.min(l1,l2)+.05);
  }
  result.contrast=styles;
  check('Battery profile functional text contrast',styles.every(s=>s.ratio>=4.5),styles);
  await page.locator('#close-selection').focus();await page.keyboard.press('Escape');
  e=await state();
  check('Escape restores exact charging point focus',e.hidden&&e.focus==='profile:auto-1:9',e);
  await page.locator('.profile-point[data-index="12"]').click();await settled();
  await page.locator('.zmd-pin[aria-label$="(BASE)"]').click();await settled();
  e=await state();
  check('BASE map preserves profile return occurrence',e.title==='Regreso a base'&&e.index==='12'&&e.route==='auto-1'&&e.soc.every(s=>s==='37,5 %')&&e.active.every(a=>a.index==='12'),e);
  await page.locator('.profile-point[data-index="0"]').click();await settled();
  e=await state();
  check('Departure BASE point remains separate from return',e.title==='Salida de base'&&e.index==='0'&&e.soc.every(s=>s==='60 %'),e);
  await page.locator('#close-selection').click();
  await page.locator('#fit').click();await settled();
  await page.locator('.zmd-pin[aria-label$="(V5)"]').click();await settled();
  e=await state();
  check('Cross vehicle map selection updates list and profile context',e.route==='auto-2'&&e.index==='1'&&e.title==='Local 5'&&e.active.every(a=>a.route==='auto-2')&&e.status.includes('Auto 2'),e);
  await profileOpen('auto-2');
  await page.locator('.profile-point[data-index="4"]').click();await settled();
  e=await state();
  check('Auto 2 charge uses existing C9 fixture',e.title==='Cargador 9'&&e.route==='auto-2'&&e.index==='4'&&e.soc[0]==='46 %'&&e.soc[1]==='66 %'&&e.text.includes('+3,2 kWh'),e);
  // Reverse an actual CSS close while the rendered panel is between endpoints.
  await page.locator('#close-selection').click();
  const toggle=page.locator('#profile-toggle-auto-2');
  await toggle.scrollIntoViewIfNeeded();
  let b=await toggle.boundingBox();
  await page.mouse.click(b.x+b.width/2,b.y+b.height/2);
  await page.waitForFunction(()=>{const p=document.querySelector('#profile-content-auto-2');const a=Number(getComputedStyle(p).opacity);return !p.hidden&&p.inert&&a>0&&a<1;},null,{polling:'raf',timeout:4000});
  const before=await page.locator('#profile-content-auto-2').evaluate(p=>({height:p.getBoundingClientRect().height,opacity:getComputedStyle(p).opacity,hidden:p.hidden,inert:p.inert,animations:p.getAnimations().length}));
  b=await toggle.boundingBox();
  await page.mouse.click(b.x+b.width/2,b.y+b.height/2);
  await profileOpen('auto-2');
  const after=await page.locator('#profile-content-auto-2').evaluate(p=>({height:p.getBoundingClientRect().height,opacity:getComputedStyle(p).opacity,hidden:p.hidden,inert:p.inert,animations:p.getAnimations().length}));
  check('Pointer reversal settles expanded battery profile',Number(before.opacity)>0&&Number(before.opacity)<1&&!before.hidden&&before.inert&&!after.hidden&&!after.inert&&after.opacity==='1'&&after.animations===0,{before,after});
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.waitForFunction(()=>matchMedia('(prefers-reduced-motion:reduce)').matches);
  await toggle.click();
  const reduced=await page.locator('#profile-content-auto-2').evaluate(p=>({hidden:p.hidden,inert:p.inert,height:p.style.height,opacity:getComputedStyle(p).opacity,animations:p.getAnimations().length}));
  check('Reduced motion closes profile immediately',reduced.hidden&&reduced.inert&&reduced.opacity==='0'&&reduced.animations===0,reduced);
  await page.locator('#all-routes').click();await page.locator('#fleet-tab').click();
  await page.emulateMedia({reducedMotion:'no-preference'});
  for(const [w,h]of[[701,900],[390,844],[319,859]])await layout(w,h);
  check('No JS exceptions or HTTP errors',result.errors.length===0&&result.httpErrors.length===0,{errors:result.errors,httpErrors:result.httpErrors});
})().catch(e=>{result.fatal={message:e.message,stack:e.stack};console.error(e);process.exitCode=1;}).finally(async()=>{
  result.finishedAt=new Date().toISOString();
  fs.writeFileSync(path.join(__dirname,'independent-bateria-results.json'),JSON.stringify(result,null,2));
  await browser?.close();
});
