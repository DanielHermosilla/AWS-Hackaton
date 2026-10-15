const { chromium } = require('/Users/caballero/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs');
const path=require('path');
const result={startedAt:new Date().toISOString(),checks:[],layouts:[],errors:[],httpErrors:[],requestsFailed:[]};
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
async function detail(){
  return page.evaluate(()=>{
    const e=document.querySelector('#selection'),rows=[...document.querySelectorAll('.stop-row.active')];
    return {hidden:e.hidden,title:e.querySelector('h3')?.textContent,text:e.textContent.trim(),soc:[...e.querySelectorAll('.stop-battery strong')].map(x=>x.textContent),active:rows.map(x=>({route:x.dataset.route,index:x.dataset.index,node:x.dataset.stop})),focus:document.activeElement?.outerHTML.slice(0,300),status:document.querySelector('#selection-status').textContent,muted:[...document.querySelectorAll('.zmd-pin.is-muted')].map(x=>x.getAttribute('aria-label'))};
  });
}
async function openRoute(id){
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
    const overlays=[...document.querySelectorAll('.map-summary,.map-tools,.legend,.maplibregl-ctrl-attrib,.maplibregl-ctrl-group')].filter(x=>getComputedStyle(x).display!=='none').map(x=>({class:x.className,rect:x.getBoundingClientRect()}));
    const pins=[...document.querySelectorAll('.zmd-pin:not([hidden])')].map(x=>{
      const b=x.getBoundingClientRect(),cx=b.left+b.width/2,cy=b.top+b.height/2;
      return {name:x.getAttribute('aria-label'),left:b.left,right:b.right,top:b.top,bottom:b.bottom,obstructedBy:overlays.filter(o=>cx>=o.rect.left&&cx<=o.rect.right&&cy>=o.rect.top&&cy<=o.rect.bottom).map(o=>o.class)};
    });
    const styles=s=>{const c=getComputedStyle(document.querySelector(s));return {background:c.backgroundColor,backdropFilter:c.backdropFilter,border:c.borderColor,color:c.color};};
    return {viewport:{width:innerWidth,height:innerHeight},documentWidth:document.documentElement.scrollWidth,bodyWidth:document.body.scrollWidth,map,summary,summaryInside:summary.left>=map.left-1&&summary.right<=map.right+1,mapReady:document.querySelector('#map').dataset.mapReady,mapStatus:document.querySelector('.map-status').textContent,pins,obstruction:pins.filter(p=>p.obstructedBy.length),materials:{glass:styles('.glass-controls'),summary:styles('.map-summary'),card:styles('.vehicle-card'),legend:styles('.legend')}};
  });
  result.layouts.push(e);
  check(`Cristal layout ${width}`,e.documentWidth<=width&&e.bodyWidth<=width&&e.summaryInside&&e.mapReady==='true'&&(width>=700||e.obstruction.length===0),e);
  await page.screenshot({path:path.join(__dirname,`independent-cristal-${width}.png`),fullPage:width<700});
}
(async()=>{
  browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:['--enable-unsafe-swiftshader']});
  page=await browser.newPage({viewport:{width:1440,height:900}});
  page.on('pageerror',e=>result.errors.push(e.message));
  page.on('response',r=>{if(r.status()>=400)result.httpErrors.push({url:r.url(),status:r.status()});});
  page.on('requestfailed',r=>result.requestsFailed.push({url:r.url(),failure:r.failure()?.errorText}));
  await page.goto('http://127.0.0.1:4173/round-3/cristal/');
  await page.waitForSelector('#map[data-map-ready="true"]',{timeout:45000});
  await layout(1440,900);
  await openRoute('auto-1');
  await page.locator('[data-stop="V16"]').focus();
  await page.keyboard.press('Enter');await settled();
  let e=await detail();
  check('V16 selects concrete occurrence without losing keyboard focus',e.title==='Local 16'&&e.active.length===1&&e.active[0].route==='auto-1'&&e.active[0].index==='10'&&e.focus?.includes('data-stop="V16"')&&e.status.includes('Auto 1'),e);
  await page.locator('#close-selection').focus();await page.keyboard.press('Escape');
  e=await detail();
  check('Escape returns focus to selected list row',e.hidden&&e.focus?.includes('data-stop="V16"'),e);
  await page.locator('#fit').click();await settled();
  await page.locator('.zmd-pin[aria-label$="(V5)"]').click();await settled();
  e=await detail();
  check('Auto 1 to V5 consistently selects Auto 2',e.title==='Local 5'&&e.active.length===1&&e.active[0].route==='auto-2'&&e.active[0].index==='1'&&e.text.includes('Auto 2')&&e.muted.length===10,e);
  for(const [id,soc]of[['auto-1','37,5'],['auto-2','41,3']]){
    await openRoute(id);
    await page.locator('[data-stop="BASE"][data-index="12"]').click();await settled();
    await page.locator('.zmd-pin[aria-label$="(BASE)"]').click();await settled();
    e=await detail();
    check(`Repeated BASE preserves return ${id}`,e.title==='Regreso a BASE'&&e.active[0]?.route===id&&e.active[0]?.index==='12'&&e.soc.every(s=>s.includes(soc)),e);
  }
  await page.locator('#all-routes').click();await page.locator('#fleet-tab').click();
  for(const [w,h]of[[900,900],[701,900],[390,844],[319,859]])await layout(w,h);
  const session=await page.context().newCDPSession(page);
  const readMaterials=()=>page.evaluate(()=>{
    const out={media:matchMedia('(prefers-reduced-transparency:reduce)').matches,contrast:matchMedia('(prefers-contrast:more)').matches};
    for(const s of ['.glass-controls','.maplibregl-ctrl-group','.map-summary','.vehicle-card','.legend']){
      const c=getComputedStyle(document.querySelector(s));out[s]={background:c.backgroundColor,backdrop:c.backdropFilter,border:c.borderColor,color:c.color};
    }
    return out;
  });
  await session.send('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-transparency',value:'reduce'}]});
  await page.waitForFunction(()=>matchMedia('(prefers-reduced-transparency:reduce)').matches);
  let material=await readMaterials();
  check('Reduced transparency makes controls opaque and removes blur',material.media&&material['.glass-controls'].background==='rgb(249, 251, 253)'&&material['.glass-controls'].backdrop==='none'&&material['.maplibregl-ctrl-group'].background==='rgb(249, 251, 253)'&&material['.maplibregl-ctrl-group'].backdrop==='none'&&material['.map-summary'].background==='rgb(255, 255, 255)',material);
  await page.screenshot({path:path.join(__dirname,'independent-cristal-reduced-transparency-319.png'),fullPage:true});
  await session.send('Emulation.setEmulatedMedia',{features:[{name:'prefers-contrast',value:'more'}]});
  await page.waitForFunction(()=>matchMedia('(prefers-contrast:more)').matches);
  material=await readMaterials();
  check('Contrast preference preserves opaque data and controls',material.contrast&&material['.glass-controls'].background==='rgb(255, 255, 255)'&&material['.glass-controls'].backdrop==='none'&&material['.legend'].color==='rgb(53, 74, 97)',material);
  check('No JS exceptions or HTTP errors',result.errors.length===0&&result.httpErrors.length===0,{errors:result.errors,httpErrors:result.httpErrors});
})().catch(e=>{result.fatal={message:e.message,stack:e.stack};console.error(e);process.exitCode=1;}).finally(async()=>{
  result.finishedAt=new Date().toISOString();
  fs.writeFileSync(path.join(__dirname,'independent-cristal-results.json'),JSON.stringify(result,null,2));
  await browser?.close();
});
