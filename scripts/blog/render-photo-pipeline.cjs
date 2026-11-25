#!/usr/bin/env node
// Render the ten-slide HTML deck for review. Requires Playwright + Chromium.
// PLAYWRIGHT_MODULE can select an existing installation; --preview updates the cover JPEG.
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '../..');
const deck = path.join(root, 'docs/blog/local-photo-pipeline-slides.html');
(async () => {
  const output = fs.mkdtempSync(path.join(os.tmpdir(), 'photo-pipeline-slides-'));
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' });
    await page.goto(pathToFileURL(deck).href);
    const count = await page.locator('.slide').count();
    if (count !== 10) throw new Error(`Expected ten slides, found ${count}`);
    for (let n = 1; n <= count; n++) {
      await page.evaluate(n => { location.hash = '#' + n; }, n);
      await page.waitForFunction(n => document.querySelector('.slide.active').getAttribute('aria-label').startsWith(`Slide ${n}:`), n);
      await page.screenshot({ path: path.join(output, `slide-${n}.png`) });
      const tooTall = await page.locator('.slide.active').evaluate(s => s.getBoundingClientRect().height > innerHeight - 62);
      if (tooTall) throw new Error(`Slide ${n} exceeds the desktop viewport; inspect ${output}`);
      if (n === 1 && process.argv.includes('--preview')) {
        await page.screenshot({ path: path.join(root, 'docs/blog/assets/local-photo-pipeline/slides-preview.jpg'), type: 'jpeg', quality: 85 });
      }
    }
    console.log(`Rendered ${count} slides without vertical overflow: ${output}`);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
