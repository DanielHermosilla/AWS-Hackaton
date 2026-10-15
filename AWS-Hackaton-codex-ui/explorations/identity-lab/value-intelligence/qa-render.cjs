const {chromium}=require('/Users/caballero/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs');
const path=require('path');
const root=__dirname;

(async()=>{
  const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
  const page=await browser.newPage({viewport:{width:1440,height:1000},deviceScaleFactor:1});
  const errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/*',route=>{
    const url=new URL(route.request().url());
    return ['127.0.0.1','localhost'].includes(url.hostname)?route.continue():route.abort();
  });
  await page.goto('http://127.0.0.1:4173/identity-lab/value-intelligence/qa.html');
  await page.locator('[data-artwork="symbol"]').first().waitFor({state:'visible'});
  await page.evaluate(()=>document.fonts.ready);
  const bounds=await page.evaluate(()=>[...document.querySelectorAll('[data-artwork]')].map(group=>{
    const svg=group.ownerSVGElement;
    const box=group.getBBox();
    const view=svg.viewBox.baseVal;
    const rect=svg.getBoundingClientRect();
    const card=svg.closest('[data-concept]');
    const swatch=svg.closest('[data-theme]');
    return {
      concept:card?.dataset.concept,
      artwork:group.dataset.artwork,
      theme:swatch?.dataset.theme||svg.getAttribute('color'),
      display:{width:rect.width,height:rect.height},
      bounds:{x:box.x,y:box.y,width:box.width,height:box.height},
      viewBox:{x:view.x,y:view.y,width:view.width,height:view.height},
      color:getComputedStyle(group).fill,
      passed:box.width>0&&box.height>0&&box.x>=view.x&&box.y>=view.y&&box.x+box.width<=view.x+view.width&&box.y+box.height<=view.y+view.height
    };
  }));
  const expectedCounts={symbol:72,lockup:24};
  const counts={
    symbol:bounds.filter(b=>b.artwork==='symbol').length,
    lockup:bounds.filter(b=>b.artwork==='lockup').length
  };
  const sizes=[20,32,80].map(size=>({
    size,
    count:bounds.filter(b=>b.artwork==='symbol'&&b.display.width===size&&b.display.height===size).length,
    passed:bounds.filter(b=>b.artwork==='symbol'&&b.display.width===size&&b.display.height===size).length===24
  }));
  const colorChecks={
    light:bounds.filter(b=>b.artwork==='symbol'&&b.theme==='light').every(b=>b.color==='rgb(35, 50, 41)'),
    dark:bounds.filter(b=>b.artwork==='symbol'&&b.theme==='dark').every(b=>b.color==='rgb(245, 247, 243)')
  };
  for(const family of ['value','intelligence']){
    await page.evaluate(family=>{
      for(const card of document.querySelectorAll('[data-concept]')) card.hidden=!card.dataset.concept.startsWith(family+'-');
      for(const divider of document.querySelectorAll('.divider')) divider.hidden=true;
      document.querySelector('h1').textContent=(family==='value'?'Ahorro / valor':'Inteligencia / IA')+' — QA a 20, 32 y 80 px';
      window.scrollTo(0,0);
    },family);
    await page.screenshot({path:path.join(root,`qa-${family}.png`),fullPage:true});
  }
  const result={
    timestampUtc:new Date().toISOString(),
    browser:'Google Chrome',
    playwright:'1.62.1',
    errors,
    expectedCounts,
    counts,
    sizes,
    colorChecks,
    bounds,
    passed:errors.length===0&&counts.symbol===expectedCounts.symbol&&counts.lockup===expectedCounts.lockup&&sizes.every(s=>s.passed)&&colorChecks.light&&colorChecks.dark&&bounds.every(b=>b.passed)
  };
  fs.writeFileSync(path.join(root,'qa-render.json'),JSON.stringify(result,null,2)+'\n');
  console.log(JSON.stringify({passed:result.passed,counts,sizes,colorChecks,failedBounds:bounds.filter(b=>!b.passed),errors}));
  await browser.close();
})().catch(error=>{console.error(error);process.exitCode=1});
