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
const mediaTypes = await read(path.join(root,"album-life-stage-pilot/composite-types.json"));
const stages = await read(path.join(root, 'album-life-stage-pilot/review-results.json'));
const birthYear = (await read(path.join(root, 'timeline-age-evidence.json'))).birth_year;
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
  const collageIds = expected => expected.filter(id=>mediaTypes[id]?.type === 'Collage');
  const originalTimeline = await page.$$eval('article a[href*="/photos/"]', links=>links.map(a=>a.href.split('/').pop()));
  assert.equal(collageIds(originalTimeline).length, 0);
  await Promise.all([page.waitForNavigation(), page.click('#openlabel-pilot a')]);
  let names = 0, verbs = 0, conflicts = 0;
  const articles = await page.$$('article');
  const expectedIds = reference.map(r => r.asset).concat(Object.keys(audits)).sort();
  assert.deepEqual(await page.$$eval('article', els => els.map(el => el.id).sort()), expectedIds);
  if (Object.keys(audits).length) assert.deepEqual(expectedIds, [...current.members].sort());
  const catalogueIds = await page.$$eval('#collage-items article',els=>els.map(el=>el.id).sort());
  assert.deepEqual(catalogueIds, collageIds(expectedIds).sort());
  assert.deepEqual([...new Set(originalTimeline)].sort(), expectedIds.filter(id=>!catalogueIds.includes(id)).sort());
  let participantClicks = 0, panelCount = 0, panelFaceClicks = 0, panelActionClicks = 0;
  for (const article of articles) {
    const asset = await article.evaluate(el => el.id);
    const reviewed = reference.find(row => row.asset === asset);
    const scene = await page.evaluate(id => JSON.parse(document.querySelector('#scenes').textContent)
      .find(row => row.asset === id), asset);
    assert.ok(await article.$eval('img', img => img.complete && img.naturalWidth > 0));
    const isCollage = catalogueIds.includes(asset);
    const originalBase = isCollage ? current.album_url.split('/albums/')[0] : current.album_url;
    assert.equal(await article.$eval('a', a => a.href), originalBase + '/photos/' + asset);
    if (isCollage) {
      const layout = await read(path.join(root,'collage-layouts',asset+'.json'));
      const panels = await article.$$('details.component');
      assert.equal(panels.length,layout.panels.length);
      for (const [i,detail] of panels.entries()) {
        panelCount++;
        const expected = layout.panels[i], stored = scene.panels[i];
        assert.deepEqual(stored.polygon,expected.polygon.flatMap(([x,y])=>[x*scene.width,y*scene.height]));
        await (await detail.$('summary')).click();
        assert.ok(await detail.$eval('img',im=>im.complete && im.naturalWidth>0));
        for (const b of await detail.$$('button[data-immich-face-id]')) {
          const id = await b.evaluate(el=>el.dataset.immichFaceId);
          assert.ok(current.regions[asset].some(f=>f.namespace==='immich' && f.face_id===id));
          await b.click();
          const uid = await article.$eval('.box',el=>el.dataset.face);
          assert.ok(stored.faces.includes(uid));
          assert.equal(scene.faces[uid].face_id,id);
          panelFaceClicks++;
        }
        for (const b of await detail.$$('button[data-component-action]')) {
          const text=await b.evaluate(el=>el.textContent);
          const action=expected.actions.find(a=>a.text===text);
          await b.click();
          const ids=await article.$$eval('.box',els=>els.map(el=>el.dataset.face));
          assert.deepEqual(ids.map(uid=>scene.faces[uid].face_id).sort(), [...action.actors].sort());
          panelActionClicks++;
        }
        await (await detail.$('summary')).click();
      }
    }
    const sentences = await article.$$eval('p', ps => ps.map(p => {
      const copy = p.cloneNode(true);
      copy.querySelectorAll('.mention').forEach(el => el.replaceWith(el.dataset.replaced ? el.dataset.words : ''));
      return copy.textContent;
    }));
    const decision = await read(path.join(root, 'caption-participants', asset + '.json')).catch(error => {
      if (error.code === 'ENOENT') return {mentions:[]};
      throw error;
    });
    const notes = await article.$$('.mention');
    assert.equal(notes.length, decision.mentions.length);
    for (const note of notes) {
      const words = await note.evaluate(el => el.dataset.words);
      const reviewedMention = decision.mentions.find(m => m.words === words);
      assert.ok(reviewedMention);
      const buttons = await note.$$('button');
      assert.equal(buttons.length, reviewedMention.faces.length);
      for (const [i, button] of buttons.entries()) {
        const raw = reviewedMention.faces[i];
        const source = current.regions[asset].find(f => f.namespace === 'immich' && f.face_id === raw.face_id);
        assert.deepEqual(source.box, raw.box);
        assert.equal(await button.evaluate(b=>b.dataset.immichFaceId), source.face_id);
        await button.click();
        const hit = await article.$$eval('.box', boxes => boxes.map(el => ({id:el.dataset.face,
          box:['left','top','width','height'].map(k=>parseFloat(el.style[k])/100)})));
        assert.equal(hit.length, 1);
        assert.equal(scene.faces[hit[0].id].face_id, source.face_id);
        const [x,y,r,b] = source.box;
        assert.ok(hit[0].box.every((v,k) => Math.abs(v-[x,y,r-x,b-y][k]) < .00001));
        participantClicks++;
      }
      if (reviewedMention.reason) assert.ok((await note.evaluate(el=>el.textContent)).includes(reviewedMention.reason));
    }
    const audit = audits[asset];
    const review = stages.photos.find(row => row.asset === asset);
    const warning = await article.$('.date-conflict');
    assert.equal(Boolean(warning), review.status === 'conflict');
    if (warning) {
      conflicts++;
      const text = await warning.evaluate(el => el.textContent);
      assert.ok(text.includes(review.accepted.stage.replaceAll('_', ' ')));
      assert.ok(text.includes('capture year is unknown'));
      assert.equal(scene.date_conflict.birth_year, String(birthYear));
      assert.equal(scene.date_conflict.recorded_date, review.date);
    }
    let subjectName, rendered, mentions;
    if (audit?.scene) {
      assert.deepEqual(sentences, [audit.scene]);
      assert.equal((await article.$$('button[data-action]')).length, 0);
      assert.ok(await article.$$eval('small', (els,reason) => els.some(el=>el.textContent.includes(reason)), audit.reason));
      continue;
    }
    if (audit) {
      const region = current.regions[asset].find(r => r.namespace === audit.namespace && r.face_id === audit.face_id);
      assert.equal(region.person_id, audit.person_id);
      subjectName = current.names[audit.person_id] || current.names[audit.namespace+':'+audit.face_id] || 'Unnamed person';
      mentions = audit.spans.map(s => s.recipient).filter(Boolean);
      let literal = audit.literal;
      for (const m of [...mentions].reverse()) {
        assert.equal(literal.slice(m.start, m.end), m.words);
        literal = literal.slice(0, m.start) + (current.names[m.person_id] || m.description) + literal.slice(m.end);
      }
      rendered = subjectName + literal;
      assert.deepEqual(sentences, [rendered]);
      const tags = await article.$$eval('button[data-action]', bs => bs.map(b => b.dataset.savedVerb));
      assert.deepEqual(tags, audit.spans.map(s => s.words));
      assert.equal((await article.$$('button[data-face]')).length, 1 + mentions.length);
    } else {
      assert.deepEqual(sentences.sort(), Object.entries(reviewed.actions)
        .map(([name, words]) => name + ' ' + words).sort());
    }
    // Independently require reviewed phrases to be clickable, including ones
    // the renderer might otherwise leave as plain text after a name or verb.
    for (const p of audit ? [] : await article.$$('p')) {
      const sentence = await p.evaluate(el => { const copy=el.cloneNode(true); copy.querySelectorAll('.mention').forEach(n=>n.remove()); return copy.textContent; });
      const tagged = await p.$$eval('button[data-action]', bs => bs.map(b => b.dataset.savedVerb));
      for (const m of sentence.matchAll(/\band (looks to the side|holds the handlebar|smiles|sits)\b|\b(an arm around him|both children in her arms)\b/g)) {
        assert.ok(tagged.includes(m[1] || m[2]), 'Reviewed action phrase missing a tag');
      }
    }
    for (const button of await article.$$('button[data-face],button[data-action]')) {
      await button.click();
      const target = await button.evaluate(b => ({...b.dataset}));
      const selected = await article.$$eval('.box', boxes => boxes.map(el => ({
        id: el.dataset.face, role: el.classList[1],
        box: ['left','top','width','height'].map(key => parseFloat(el.style[key])/100),
      })));
      assert.equal(await button.evaluate(b => b.getAttribute('aria-pressed')), 'true');
      const expectedFaces = new Map();
      if (target.face) {
        names++;
        assert.deepEqual(selected.map(b => b.id), [target.face]);
        const name = scene.faces[target.face].name;
        if (audit) {
          const index = await button.evaluate(b => [...b.parentElement.querySelectorAll('[data-face]')].indexOf(b));
          expectedFaces.set('person', [audit, ...mentions][index]);
        }
        assert.ok((await button.evaluate(b => b.title)).includes(scene.faces[target.face].face_id));
        let enriched = rendered;
        if (audit && !audit.scene) {
          for (const m of decision.mentions) {
            if (m.faces.length !== 1 || m.reason) continue;
            const f = m.faces[0];
            const display = current.names[f.person_id] || f.description || 'Face ' + f.face_id.slice(0,8);
            enriched = enriched.replace(m.words, display + (/[’']s$/.test(m.words) ? '’s' : ''));
          }
        }
        const expected = audit ? (expectedFaces.get('person') === audit ? enriched : name) : (reviewed.actions[name] ? name + ' ' + reviewed.actions[name] : name);
        assert.equal(await article.$eval('output', el => el.textContent), expected);
      } else {
        verbs++;
        if (audit) {
          const index = await button.evaluate(b => [...b.parentElement.querySelectorAll('button[data-action]')].indexOf(b));
          const span = audit.spans[index];
          expectedFaces.set(affectedRoles[span.sense] || 'actor', audit);
          if (span.recipient) expectedFaces.set('recipient', span.recipient);
          const extra = decision.mentions.flatMap(m => (m.actions || []).filter(a=>a[0] === span.words)
            .flatMap(([,role])=>m.faces.map(f=>({role, f}))));
          const baseIds = new Set([...expectedFaces.values()].map(f=>f.face_id));
          for (const {role,f} of extra) {
            if (baseIds.has(f.face_id)) continue;
            const actual = selected.find(b=>b.role.startsWith(role+'-') && scene.faces[b.id].face_id === f.face_id);
            assert.ok(actual);
            expectedFaces.set(actual.role, f);
            baseIds.add(f.face_id);
          }
          assert.deepEqual(selected.map(b => b.role).sort(), [...expectedFaces.keys()].sort());
          assert.ok((await article.$eval('output', el => el.textContent)).includes(subjectName));
        } else {
          const sentence = await button.evaluate(b => { const copy=b.parentElement.cloneNode(true); copy.querySelectorAll(".mention").forEach(n=>n.remove()); return copy.textContent; });
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
          const ref = expectedFaces.get(box.role);
          assert.equal(f.face_namespace, ref.namespace);
          assert.equal(f.face_id, ref.face_id);
          assert.equal(f.person_id, ref.person_id || "");
        }
        const source = current.regions[asset].find(r => r.namespace === f.face_namespace && r.face_id === f.face_id);
        const [x,y,right,bottom] = source.box;
        const expected = [x,y,right-x,bottom-y];
        assert.ok(box.box.every((v,i) => Math.abs(v-expected[i]) < 0.00001));
      }
    }
  }
  console.log(JSON.stringify({photos: articles.length, name_clicks: names, verb_clicks: verbs, date_conflicts: conflicts, participant_clicks: participantClicks, component_photos: panelCount, component_face_clicks:panelFaceClicks, component_action_clicks:panelActionClicks}));
} finally {
  await browser.close();
}
