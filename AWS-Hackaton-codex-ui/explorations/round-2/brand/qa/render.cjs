const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('/Users/caballero/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root = path.resolve(__dirname, '..');
const base = 'http://127.0.0.1:4173/round-2/brand/';
const report = {tested_at_utc: new Date().toISOString(), scope: 'Brand round 2 only; isolated local headless Chrome, synthetic gallery, no Kiro/engine/services', checks: [], errors: [], remote_requests: []};
const check = (name, passed, evidence) => report.checks.push({name, passed, evidence});

(async () => {
  const browser = await chromium.launch({headless: true, executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  report.browser = await browser.version();
  const page = await browser.newPage({viewport: {width: 1440, height: 1000}, deviceScaleFactor: 1, reducedMotion: 'reduce'});
  page.on('pageerror', error => report.errors.push(String(error)));
  page.on('request', request => {
    if (!request.url().startsWith('http://127.0.0.1:4173/') && !request.url().startsWith('blob:')) report.remote_requests.push(request.url());
  });
  const response = await page.goto(base, {waitUntil: 'networkidle'});
  check('local_page_200', response.status() === 200, response.status());
  check('12_large_logos', await page.locator('.card:visible').count() === 12, await page.locator('.logo-stage').first().boundingBox());
  await page.screenshot({path: path.join(root, 'qa', 'overview-light.png'), fullPage: true});
  for (const family of ['typographic', 'monogram', 'symbol']) {
    await page.locator(`[data-filter="${family}"]`).click();
    check(`filter_${family}`, await page.locator('.card:visible').count() === 4 && await page.locator('#count').textContent() === '4 propuestas', await page.locator('.card:visible').evaluateAll(cards => cards.map(c => c.dataset.id)));
  }
  await page.locator('[data-filter="all"]').click();
  await page.locator('[data-theme-choice="dark"]').click();
  await page.locator('[data-palette-choice="green"]').click();
  const darkFill = await page.locator('.card').nth(4).locator('svg path').first().evaluate(p => getComputedStyle(p).fill);
  check('dark_green_palette', darkFill === 'rgb(96, 223, 177)', darkFill);
  await page.screenshot({path: path.join(root, 'qa', 'overview-dark-green.png'), fullPage: true});
  await page.locator('[data-palette-choice="black"]').click();
  const blackFill = await page.locator('.card').nth(4).locator('svg path').first().evaluate(p => getComputedStyle(p).fill);
  check('monochrome_dark', blackFill === 'rgb(245, 248, 252)', blackFill);
  await page.locator('[data-theme-choice="light"]').click();
  await page.locator('[data-palette-choice="blue"]').click();
  const trigger = page.locator('.card').nth(4).locator('.detail-link');
  await trigger.focus();
  await page.keyboard.press('Enter');
  check('keyboard_detail', await page.locator('#detail').evaluate(d => d.open) && await page.locator('#detail-title').textContent() === 'Z enchufada', await page.locator('#detail-title').textContent());
  await page.screenshot({path: path.join(root, 'qa', 'detail-z-enchufada.png')});
  const [download] = await Promise.all([page.waitForEvent('download'), page.locator('#download-current').click()]);
  await download.saveAs(path.join(root, 'qa', 'download-test.svg'));
  const saved = fs.readFileSync(path.join(root, 'qa', 'download-test.svg'), 'utf8');
  check('download_current_palette', !saved.includes('var(--logo-') && saved.includes('#126ade'), download.suggestedFilename());
  await page.keyboard.press('Escape');
  check('escape_closes_and_restores_focus', !(await page.locator('#detail').evaluate(d => d.open)) && await trigger.evaluate(b => b === document.activeElement), true);
  const assets = JSON.parse(fs.readFileSync(path.join(root, 'manifest.json'), 'utf8'));
  report.bounds = [];
  for (const item of assets) {
    for (const kind of ['light', 'dark', 'symbol']) {
      const source = fs.readFileSync(path.join(root, item[kind]), 'utf8');
      const bounds = await page.evaluate(source => {
        const holder = document.createElement('div');
        holder.innerHTML = source;
        holder.style.cssText = 'position:absolute;left:0;top:0;visibility:hidden';
        document.body.append(holder);
        const svg = holder.firstElementChild;
        const b = svg.getBBox({fill: true, stroke: true});
        const v = svg.viewBox.baseVal;
        const result = {x: b.x, y: b.y, width: b.width, height: b.height, viewBox: [v.x, v.y, v.width, v.height],
          inside: b.x >= v.x && b.y >= v.y && b.x+b.width <= v.x+v.width && b.y+b.height <= v.y+v.height};
        holder.remove();
        return result;
      }, source);
      report.bounds.push({path: item[kind], ...bounds});
    }
  }
  check('36_svg_bounds', report.bounds.length === 36 && report.bounds.every(b => b.inside), report.bounds.filter(b => !b.inside));
  await page.goto(base + 'qa/small-sizes.html', {waitUntil: 'networkidle'});
  await page.screenshot({path: path.join(root, 'qa', 'small-sizes.png'), fullPage: true});
  await page.goto(base, {waitUntil: 'networkidle'});
  for (const width of [390, 320]) {
    await page.setViewportSize({width, height: 844});
    check(`mobile_${width}_no_overflow`, await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), await page.evaluate(() => ({viewport: innerWidth, scroll_width: document.documentElement.scrollWidth})));
    if (width === 390) {
      await page.screenshot({path: path.join(root, 'qa', 'mobile-light.png'), fullPage: true});
      await page.locator('.card').nth(9).locator('.detail-link').click();
      check('mobile_detail_no_overflow', await page.locator('#detail').evaluate(d => d.scrollWidth <= d.clientWidth), await page.locator('#detail').boundingBox());
      await page.screenshot({path: path.join(root, 'qa', 'mobile-detail.png')});
      await page.keyboard.press('Escape');
    }
  }
  check('no_page_errors', report.errors.length === 0, report.errors);
  check('no_remote_requests', report.remote_requests.length === 0, report.remote_requests);
  report.passed = report.checks.every(c => c.passed);
  fs.writeFileSync(path.join(root, 'qa', 'verification.json'), JSON.stringify(report, null, 2) + '\n');
  await browser.close();
  console.log(JSON.stringify({passed: report.passed, checks: report.checks, errors: report.errors}, null, 2));
  if (!report.passed) process.exitCode = 1;
})().catch(error => {
  report.errors.push(String(error));
  report.passed = false;
  fs.writeFileSync(path.join(root, 'qa', 'verification.json'), JSON.stringify(report, null, 2) + '\n');
  console.error(error);
  process.exitCode = 1;
});
