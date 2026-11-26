// Exercise the rendered private album. Print aggregate results only.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';

const [timeline, sourcesFile] = process.argv.slice(2);
const {default: puppeteer} = await import(process.env.PUPPETEER_MODULE || 'puppeteer');
const read = async file => JSON.parse(await readFile(file, 'utf8'));
const root = path.dirname(timeline);
const reference = await read(path.join(root, 'album-life-stage-pilot/group-actions/verified-actions.json'));
const current = await read(sourcesFile);
const browser = await puppeteer.launch({executablePath: process.env.CHROME_BIN, headless: true});
try {
  const page = await browser.newPage();
  await page.setRequestInterception(true);
  page.on('request', req => req.url().startsWith('file:') ? req.continue() : req.abort());
  await page.goto(pathToFileURL(timeline).href);
  await Promise.all([page.waitForNavigation(), page.click('#openlabel-pilot a')]);
  let names = 0, verbs = 0;
  const articles = await page.$$('article');
  assert.equal(articles.length, reference.length);
  for (const article of articles) {
    const asset = await article.evaluate(el => el.id);
    const reviewed = reference.find(row => row.asset === asset);
    const scene = await page.evaluate(id => JSON.parse(document.querySelector('#scenes').textContent)
      .find(row => row.asset === id), asset);
    assert.ok(await article.$eval('img', img => img.complete && img.naturalWidth > 0));
    assert.equal(await article.$eval('a', a => a.href), current.album_url + '/photos/' + asset);
    const sentences = await article.$$eval('p', ps => ps.map(p => p.textContent));
    assert.deepEqual(sentences.sort(), Object.entries(reviewed.actions)
      .map(([name, words]) => name + ' ' + words).sort());
    for (const button of await article.$$('button')) {
      await button.click();
      const target = await button.evaluate(b => ({...b.dataset}));
      const selected = await article.$$eval('.box', boxes => boxes.map(el => ({
        id: el.dataset.face, role: el.classList[1],
        box: ['left','top','width','height'].map(key => parseFloat(el.style[key])/100),
      })));
      assert.equal(await button.evaluate(b => b.getAttribute('aria-pressed')), 'true');
      if (target.face) {
        names++;
        assert.deepEqual(selected.map(b => b.id), [target.face]);
        assert.equal(await article.$eval('output', el => el.textContent), scene.faces[target.face].name);
      } else {
        verbs++;
        const sentence = await button.evaluate(b => b.parentElement.textContent);
        const actor = Object.keys(reviewed.actions).find(name => sentence === name+' '+reviewed.actions[name]);
        assert.equal(scene.faces[selected.find(b => b.role === 'actor').id].name, actor);
        if (await button.evaluate(b => b.textContent === 'holds')) {
          const held = scene.faces[selected.find(b => b.role === 'held_person').id].name;
          assert.ok(reviewed.actions[actor].startsWith('holds '+held+' '));
          assert.notEqual(actor, held);
        }
      }
      for (const box of selected) {
        const f = scene.faces[box.id];
        const source = current.regions[asset].find(r => r.namespace === f.face_namespace && r.face_id === f.face_id);
        const [x,y,right,bottom] = source.box;
        const expected = [x,y,right-x,bottom-y];
        assert.ok(box.box.every((v,i) => Math.abs(v-expected[i]) < 0.00001));
      }
    }
  }
  console.log(JSON.stringify({photos: articles.length, name_clicks: names, verb_clicks: verbs}));
} finally {
  await browser.close();
}
