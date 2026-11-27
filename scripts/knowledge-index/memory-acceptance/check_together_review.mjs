// Check a private same-photo album against independently frozen subject and asset IDs.
import {checkOcrTags} from './check_ocr_tags.mjs';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';

const [expectationFile, sourceFile] = process.argv.slice(2);
const expected = JSON.parse(await readFile(expectationFile));
const source = JSON.parse(await readFile(sourceFile));
const {default: puppeteer} = await import(process.env.PUPPETEER_MODULE || 'puppeteer');
const browser = await puppeteer.launch({executablePath: process.env.CHROME_BIN, headless: true});
try {
  const page = await browser.newPage();
  await page.setRequestInterception(true);
  page.on('request', req => req.url().startsWith('file:') ? req.continue() : req.abort());
  await page.goto(pathToFileURL(expected.page).href);
  const assets = await page.$$eval('article', cards => cards.map(c => c.id));
  assert.deepEqual(assets, expected.ids);
  const scenes = JSON.parse(await page.$eval('#scenes', e => e.textContent));
  assert.deepEqual(scenes.map(s=>s.asset), assets);
  let clicks = 0;
  for (const scene of scenes) {
    const article = await page.$('article[id="'+scene.asset+'"]');
    assert.equal(await article.$eval('img', e=>e.complete && e.naturalWidth>0), true);
    assert.equal(await article.$eval('a', e=>e.href), source.album_url+'/photos/'+scene.asset);
    const subjects = await article.$$eval('p[data-subject]', ps=>ps.map(p=>p.dataset.subject));
    assert.ok(expected.people.every(id=>subjects.some(s=>scene.faces[s].person_id===id)));
    for (const button of await article.$$('button:not([data-immich-ocr-id])')) {
      await button.click();
      const boxes = await article.$$eval('.box', els=>els.map(el=>({id:el.dataset.face,
        rect:['left','top','width','height'].map(k=>parseFloat(el.style[k])/100)})));
      const {face, immichFaceId, action} = await button.evaluate(b=>({...b.dataset}));
      if (action) {
        const spans = [...scene.claims, ...scene.individual].flatMap(c=>c.spans);
        const span = spans.find(s=>s.id===action);
        const targets = new Set([...Object.values(span.roles), ...(span.participants || []).map(r=>r.face)]);
        assert.deepEqual(new Set(boxes.map(b=>b.id)), targets);
      } else {
        assert.equal(boxes.length, 1);
        if (face) assert.equal(boxes[0].id, face);
        if (immichFaceId) {
          const f = scene.faces[boxes[0].id];
          assert.equal(f.immich_face_id || f.face_id, immichFaceId);
        }
      }
      for (const b of boxes) {
        const f = scene.faces[b.id];
        const native = source.regions[scene.asset].find(r=>r.namespace===f.face_namespace && r.face_id===f.face_id);
        const [x,y,r,bottom] = native.box.map(v=>Math.max(0, Math.min(1,v)));
        assert.ok(b.rect.every((v,i)=>Math.abs(v-[x,y,r-x,bottom-y][i])<0.00001));
      }
      clicks++;
    }
  }
  console.log(JSON.stringify({verified_photos: assets.length, ocr_clicks: await checkOcrTags(page, source.ocr), clicks}));
} finally {
  await browser.close();
}
