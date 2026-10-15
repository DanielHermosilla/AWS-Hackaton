const { chromium } = require('/Users/caballero/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs = require('fs');
const path = require('path');
(async()=>{
  const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:['--enable-unsafe-swiftshader']});
  const page=await browser.newPage({viewport:{width:1440,height:900}});
  const evidence={startedAt:new Date().toISOString(),trials:[],errors:[]};
  page.on('pageerror',e=>evidence.errors.push(e.message));
  try {
    await page.goto('http://127.0.0.1:4173/round-3/esencial/');
    await page.waitForSelector('#map[data-map-ready=true]',{timeout:45000});
    await page.locator('[data-vehicle="auto-1"]').click();
    async function noPreference() {
      await page.emulateMedia({reducedMotion:'no-preference'});
      await page.waitForFunction(()=>!matchMedia('(prefers-reduced-motion:reduce)').matches);
      await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
    }
    async function monitor() {
      await page.evaluate(()=>{
        window.__independentMotionFrames=[];
        const start=performance.now();
        const step=()=>{
          const e=document.querySelector('#selection');
          window.__independentMotionFrames.push({atMs:performance.now()-start,reduce:matchMedia('(prefers-reduced-motion:reduce)').matches,opacity:getComputedStyle(e).opacity,inlineOpacity:e.style.opacity,transform:getComputedStyle(e).transform,animations:e.getAnimations().length,hidden:e.hidden,inert:e.inert,title:e.querySelector('h3')?.textContent});
          if(performance.now()-start<1000) requestAnimationFrame(step);
          else window.__independentMotionDone=true;
        };
        window.__independentMotionDone=false;
        requestAnimationFrame(step);
      });
    }
    async function finishTrial(name, before, expectedOpen, expectedTitle) {
      await page.waitForFunction(()=>window.__independentMotionDone,null,{polling:'raf',timeout:5000});
      const frames=await page.evaluate(()=>window.__independentMotionFrames);
      const end=frames.at(-1),tail=frames.filter(f=>f.atMs>400);
      const settledCorrectly=tail.length>8&&tail.every(f=>f.opacity===(expectedOpen?'1':'0')&&f.animations===0&&f.hidden!==expectedOpen&&f.inert!==expectedOpen&&(!expectedTitle||f.title===expectedTitle));
      evidence.trials.push({name,before,frames,end,settledCorrectly});
      if(expectedOpen){
        const r=await page.locator('#close-selection').boundingBox();
        await page.mouse.click(r.x+r.width/2,r.y+r.height/2);
        await page.waitForFunction(()=>document.querySelector('#selection').hidden);
      }
    }
    await noPreference();
    await monitor();
    await page.locator('[data-stop="V12"]').click();
    await page.waitForFunction(()=>{const s=document.querySelector('#selection');const o=Number(getComputedStyle(s).opacity);return !s.hidden&&o>0&&o<.99;},null,{polling:'raf',timeout:4000});
    let before=await page.locator('#selection').evaluate(e=>({style:e.style.cssText,opacity:getComputedStyle(e).opacity,animations:e.getAnimations().length}));
    await page.emulateMedia({reducedMotion:'reduce'});
    await finishTrial('Live reduced-motion during entry',before,true,'Local 12');
    await noPreference();
    await page.locator('[data-stop="V12"]').click();
    await page.waitForFunction(()=>getComputedStyle(document.querySelector('#selection')).opacity==='1'&&document.querySelector('#selection').getAnimations().length===0,null,{polling:'raf',timeout:4000});
    await monitor();
    let r=await page.locator('#close-selection').boundingBox();
    await page.mouse.click(r.x+r.width/2,r.y+r.height/2);
    await page.waitForFunction(()=>{const s=document.querySelector('#selection');const o=Number(getComputedStyle(s).opacity);return !s.hidden&&s.inert&&o>0&&o<1;},null,{polling:'raf',timeout:4000});
    before=await page.locator('#selection').evaluate(e=>({style:e.style.cssText,opacity:getComputedStyle(e).opacity,animations:e.getAnimations().length,inert:e.inert}));
    await page.emulateMedia({reducedMotion:'reduce'});
    await finishTrial('Live reduced-motion during exit',before,false);
    await noPreference();
    await page.locator('[data-stop="V12"]').click();
    await page.waitForFunction(()=>getComputedStyle(document.querySelector('#selection')).opacity==='1'&&document.querySelector('#selection').getAnimations().length===0,null,{polling:'raf',timeout:4000});
    await monitor();
    r=await page.locator('#close-selection').boundingBox();
    await page.mouse.click(r.x+r.width/2,r.y+r.height/2);
    await page.waitForFunction(()=>{const s=document.querySelector('#selection');const o=Number(getComputedStyle(s).opacity);return !s.hidden&&s.inert&&o>0&&o<1;},null,{polling:'raf',timeout:4000});
    before=await page.locator('#selection').evaluate(e=>({style:e.style.cssText,opacity:getComputedStyle(e).opacity,animations:e.getAnimations().length,inert:e.inert}));
    await page.locator('[data-stop="V3"]').focus();
    await page.keyboard.press('Enter');
    await finishTrial('Keyboard opens new stop during pointer exit',before,true,'Local 3');
    /*
      Samples above are taken every rendered frame for one second. The final
      600 ms must stay at the requested endpoint, beyond any delayed exit.
    */
    evidence.pass=evidence.trials.every(t=>t.settledCorrectly);
    console.log(JSON.stringify({pass:evidence.pass,trials:evidence.trials.map(t=>({name:t.name,before:t.before,end:t.end,settledCorrectly:t.settledCorrectly}))},null,2));
  }catch(e){evidence.fatal=e.message;console.error(e);process.exitCode=1;}
  finally{
    evidence.finishedAt=new Date().toISOString();
    fs.writeFileSync(path.join(__dirname,'independent-motion-probe.json'),JSON.stringify(evidence,null,2));
    await browser.close();
  }
})();
