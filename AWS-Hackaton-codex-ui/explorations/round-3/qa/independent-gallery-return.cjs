const {chromium}=require('/Users/caballero/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs'),path=require('path');
const result={startedAt:new Date().toISOString(),checks:[],errors:[]};
(async()=>{
  const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:['--enable-unsafe-swiftshader']});
  const page=await browser.newPage({viewport:{width:1440,height:900}});
  page.on('pageerror',e=>result.errors.push(e.message));
  try{
    await page.goto('http://127.0.0.1:4173/round-3/');
    for(const [index,url,selector]of[[0,'/round-2/mapa/','a.brand'],[3,'/round-3/esencial/','a.all-designs']]){
      await page.locator(`[data-preview="${index}"]`).click();
      await page.waitForFunction(url=>document.querySelector('#live-preview').contentWindow.location.pathname===url&&document.querySelector('#live-preview').contentDocument.querySelector('#map')?.dataset.mapReady==='true',url,{timeout:45000});
      const frame=page.frames().find(f=>f.url().includes(url)),navigated=[];
      const track=f=>{if(f===frame)navigated.push(f.url());};
      page.on('framenavigated',track);
      await frame.locator(selector).click();
      await page.waitForFunction(()=>!document.querySelector('#comparison').open&&document.querySelector('#live-preview').getAttribute('src')===null);
      const e=await page.evaluate(()=>({parentPath:location.pathname,dialogOpen:document.querySelector('#comparison').open,iframeSrc:document.querySelector('#live-preview').getAttribute('src'),focus:document.activeElement?.dataset.preview}));
      e.navigated=navigated;
      const pass=e.parentPath==='/round-3/'&&!e.dialogOpen&&e.iframeSrc===null&&e.focus===String(index)&&!navigated.some(u=>/^http/.test(u)&&!u.endsWith(url));
      result.checks.push({name:`${url} ${selector} returns to current gallery`,pass,evidence:e});
      page.off('framenavigated',track);
    }
    result.pass=result.errors.length===0&&result.checks.every(c=>c.pass);
    console.log(JSON.stringify(result,null,2));
  }catch(e){result.fatal=e.message;console.error(e);process.exitCode=1;}
  finally{
    result.finishedAt=new Date().toISOString();
    fs.writeFileSync(path.join(__dirname,'independent-gallery-return.json'),JSON.stringify(result,null,2));
    await browser.close();
  }
})();
