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
const audits = await read(path.join(root, 'album-reviewed-spans.json')).catch(error => {
  if (error.code === 'ENOENT') return {};
  throw error;
});
const affectedRoles = {held:'held_person', hugged:'recipient', comforted:'recipient',
                       kissed:'recipient', target:'recipient'};
const browser = await puppeteer.launch({executablePath: process.env.CHROME_BIN, headless: true});
try {
  const page = await browser.newPage();
  await page.setRequestInterception(true);
  page.on('request', req => req.url().startsWith('file:') ? req.continue() : req.abort());
  await page.goto(pathToFileURL(timeline).href);
  await Promise.all([page.waitForNavigation(), page.click('#openlabel-pilot a')]);
  let names = 0, verbs = 0;
  const articles = await page.$$('article');
  const expectedIds = reference.map(r => r.asset).concat(Object.keys(audits)).sort();
  assert.deepEqual(await page.$$eval('article', els => els.map(el => el.id).sort()), expectedIds);
  if (Object.keys(audits).length) assert.deepEqual(expectedIds, [...current.members].sort());
  for (const article of articles) {
    const asset = await article.evaluate(el => el.id);
    const reviewed = reference.find(row => row.asset === asset);
    const scene = await page.evaluate(id => JSON.parse(document.querySelector('#scenes').textContent)
      .find(row => row.asset === id), asset);
    assert.ok(await article.$eval('img', img => img.complete && img.naturalWidth > 0));
    assert.equal(await article.$eval('a', a => a.href), current.album_url + '/photos/' + asset);
    const sentences = await article.$$eval('p', ps => ps.map(p => p.textContent));
    const audit = audits[asset];
    let subjectName;
    if (audit?.scene) {
      assert.deepEqual(sentences, [audit.scene]);
      assert.equal((await article.$$('button')).length, 0);
      assert.ok((await article.$eval('small', el => el.textContent)).includes(audit.reason));
      continue;
    }
    if (audit) {
      const region = current.regions[asset].find(r => r.namespace === audit.namespace && r.face_id === audit.face_id);
      assert.equal(region.person_id, audit.person_id);
      subjectName = current.names[audit.person_id] || current.names[audit.namespace+':'+audit.face_id] || 'Unnamed person';
      assert.deepEqual(sentences, [subjectName + audit.literal]);
      const tags = await article.$$eval('button[data-action]', bs => bs.map(b => b.textContent));
      assert.deepEqual(tags, audit.spans.map(s => s.words));
      assert.equal((await article.$$('button[data-face]')).length, 1);
    } else {
      assert.deepEqual(sentences.sort(), Object.entries(reviewed.actions)
        .map(([name, words]) => name + ' ' + words).sort());
    }
    // Independently require reviewed phrases to be clickable, including ones
    // the renderer might otherwise leave as plain text after a name or verb.
    for (const p of audit ? [] : await article.$$('p')) {
      const sentence = await p.evaluate(el => el.textContent);
      const tagged = await p.$$eval('button[data-action]', bs => bs.map(b => b.textContent));
      for (const m of sentence.matchAll(/\band (looks to the side|holds the handlebar|smiles|sits)\b|\b(an arm around him|both children in her arms)\b/g)) {
        assert.ok(tagged.includes(m[1] || m[2]), 'Reviewed action phrase missing a tag');
      }
    }
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
        const name = scene.faces[target.face].name;
        const expected = audit ? subjectName + audit.literal : (reviewed.actions[name] ? name + ' ' + reviewed.actions[name] : name);
        assert.equal(await article.$eval('output', el => el.textContent), expected);
      } else {
        verbs++;
        if (audit) {
          const index = await button.evaluate(b => [...b.parentElement.querySelectorAll('button[data-action]')].indexOf(b));
          const span = audit.spans[index];
          assert.deepEqual(selected.map(b => b.role), [affectedRoles[span.sense] || 'actor']);
          assert.ok((await article.$eval('output', el => el.textContent)).includes(subjectName));
        } else {
          const sentence = await button.evaluate(b => b.parentElement.textContent);
          const actor = Object.keys(reviewed.actions).find(name => sentence === name+' '+reviewed.actions[name]);
          assert.equal(scene.faces[selected.find(b => b.role === 'actor').id].name, actor);
          if (await button.evaluate(b => b.textContent === 'holds')) {
            const held = scene.faces[selected.find(b => b.role === 'held_person').id].name;
            assert.ok(reviewed.actions[actor].startsWith('holds '+held+' '));
            assert.notEqual(actor, held);
          }
        }
      }
      for (const box of selected) {
        const f = scene.faces[box.id];
        if (audit) {
          assert.equal(f.face_namespace, audit.namespace);
          assert.equal(f.face_id, audit.face_id);
          assert.equal(f.person_id, audit.person_id);
        }
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
