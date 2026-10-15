const {chromium}=require('/Users/caballero/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const result={startedAt:new Date().toISOString(),scope:'Confirmation of reported battery profile text only',errors:[],styles:[]};
function luminance(rgb){
  return rgb.map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;}).reduce((n,v,i)=>n+v*[.2126,.7152,.0722][i],0);
}
(async()=>{
  const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:['--enable-unsafe-swiftshader']});
  const page=await browser.newPage({viewport:{width:1440,height:900}});
  page.on('pageerror',e=>result.errors.push(e.message));
  try{
    await page.goto('http://127.0.0.1:4173/round-3/bateria/');
    await page.waitForSelector('#map[data-map-ready=true]',{timeout:45000});
    await page.locator('[data-vehicle="auto-1"]').click();
    await page.locator('#profile-toggle-auto-1').focus();
    await page.keyboard.press('Enter');
    await page.waitForFunction(()=>!document.querySelector('#profile-content-auto-1').hidden&&document.querySelector('#profile-content-auto-1').style.height==='auto');
    await page.locator('.profile-point[data-index="9"]').focus();
    await page.keyboard.press('Enter');
    await page.evaluate(()=>new Promise(resolve=>{
      let last='',stable=0;
      const step=()=>{
        const r=document.querySelector('.zmd-pin[aria-label$="(V14)"]').getBoundingClientRect();
        const now=`${r.x.toFixed(2)},${r.y.toFixed(2)}`;
        stable=now===last?stable+1:0;last=now;
        if(stable>=12)return resolve();
        requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    }));
    result.styles=await page.evaluate(()=>['.profile-label','.profile-axis','.profile-plot text','.profile-legend','.profile-note'].map(selector=>{
      const e=document.querySelector(selector),c=getComputedStyle(e);
      let p=e,background;
      while(p){const b=getComputedStyle(p).backgroundColor;if(b!=='rgba(0, 0, 0, 0)'&&b!=='transparent'){background=b;break;}p=p.parentElement;}
      return {selector,color:selector==='.profile-plot text'?c.fill:c.color,background,fontSize:c.fontSize,text:e.textContent.trim()};
    }));
    for(const s of result.styles){
      const fg=s.color.match(/[\d.]+/g).slice(0,3).map(Number),bg=s.background.match(/[\d.]+/g).slice(0,3).map(Number),a=luminance(fg),b=luminance(bg);
      s.ratio=(Math.max(a,b)+.05)/(Math.min(a,b)+.05);
    }
    result.pass=result.errors.length===0&&result.styles.every(s=>s.ratio>=4.5);
    await page.screenshot({path:path.join(__dirname,'independent-bateria-profile-charge-confirmed.png')});
    const baseline=JSON.parse(fs.readFileSync(path.join(__dirname,'baseline-sha256.json'),'utf8'));
    const changed=Object.entries(baseline).filter(([p,h])=>crypto.createHash('sha256').update(fs.readFileSync(path.resolve(__dirname,'../..',p))).digest('hex')!==h).map(([p])=>p);
    result.baseline={count:Object.keys(baseline).length,changed,pass:Object.keys(baseline).length===18&&!changed.length};
    console.log(JSON.stringify({pass:result.pass,styles:result.styles,baseline:result.baseline},null,2));
  }catch(e){result.fatal=e.message;console.error(e);process.exitCode=1;}
  finally{
    result.finishedAt=new Date().toISOString();
    fs.writeFileSync(path.join(__dirname,'independent-bateria-contrast.json'),JSON.stringify(result,null,2));
    await browser.close();
  }
})();
