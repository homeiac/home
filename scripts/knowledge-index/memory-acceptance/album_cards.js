function element(tag, parent, text) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  parent.append(el);
  return el;
}
const journey = document.getElementById('journey-scenes');
const journeyCards = new Map();
if (journey) {
  for (const card of document.querySelectorAll('article')) {
    const link = card.querySelector('a[href*="/photos/"]');
    if (link) journeyCards.set(new URL(link.href).pathname.split('/').pop(), card);
  }
}
for (const item of JSON.parse((journey || document.getElementById('scenes')).textContent)) {
  const collage = item.media_type === 'Collage';
  if (collage) {
    document.querySelector('#collage-catalogue').hidden = false;
    document.querySelector('#catalogue-link').hidden = false;
  }
  const article = journey ? journeyCards.get(item.asset) :
    element('article', document.querySelector(collage ? '#collage-items' : 'main'));
  if (!article) continue;
  article.id = item.asset;
  const block = journey ? article.querySelector('.photo-action') : article;
  let figure;
  if (journey) {
    block.replaceChildren();
    const photo = article.querySelector('a > img');
    const original = photo.parentElement;
    figure = document.createElement('figure');
    original.before(figure);
    figure.className = 'journey-photo';
    figure.style.width = Math.min(item.width, 175 * item.width / item.height) + 'px';
    figure.append(original);
    // Preserve the age and provenance. Retire earlier visual wording under a disclosure.
    for (const age of article.querySelectorAll('p > .age-hint')) {
      const p = age.parentElement;
      const siblings = Array.from(p.childNodes).slice(0, Array.from(p.childNodes).indexOf(age));
      const wording = siblings.map(n=>n.textContent).join('').trim();
      if (Object.values(item.faces).some(f => f.depicted_in) && / (?:is|are) in this photo\.$/.test(wording)) {
        siblings.forEach(node => node.remove());
      } else if (wording && !/ (?:is|are) in this photo\.$/.test(wording)) {
        const earlier = document.createElement('details');
        element('summary', earlier, 'Earlier scene description');
        const copy = element('p', earlier);
        copy.append(...siblings);
        p.after(earlier);
      }
    }
  } else {
    figure = element('figure', article);
    const photo = element('img', figure);
    photo.src = item.image;
    photo.alt = 'Album photo from ' + item.date;
    element('h2', article, 'Recorded date · ' + item.date);
  }
  if (item.journey_date_note) element('small', block, item.journey_date_note);
  if (item.date_conflict) {
    const facts = item.date_conflict;
    const year = Number(facts.recorded_date.slice(0, 4));
    const age = year - Number(facts.birth_year);
    const timing = age === 0 ? "The recorded year is the birth year" :
      "Someone born in " + facts.birth_year + " would turn " + age + " in " + year;
    const note = element('aside', block);
    note.className = 'date-conflict';
    element('strong', note, 'Capture date disputed');
    element('div', note, timing + '. The visual review indicates ' +
      facts.visual_stage.replaceAll('_', ' ') + ' age. The capture year is unknown.');
  }
  if (item.date_status === 'composite') element('small', block, 'Composite image · component photos may have different capture dates.');
  if (!item.journey_date_note && item.date_status === 'unresolved') element('small', block, 'Age and capture date could not be checked reliably.');
  const section = element('div', block);
  const claims = [...item.claims, ...item.individual];
  const solo = claims.length === 1 && item.faces[claims[0].subject];
  if (!item.library || claims.length || item.scene) element(journey ? 'strong' : 'h3', section, item.library ? 'Face observations' : item.scene && !claims.length ? 'Scene description' :
    journey && solo ? 'What ' + solo.name + ' is doing' : 'What each person is doing');
  if (item.scene) {
    element('p', section, item.scene);
    element('small', section, 'Original subject action withheld · ' + item.reason);
  }
  const feedback = document.createElement('output');
  feedback.setAttribute('aria-live','polite');
  function select(button, roles, message) {
    figure.querySelectorAll('.box, .ocr-region').forEach(box => box.remove());
    article.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', String(b === button)));
    for (const [role, id] of Object.entries(roles)) {
      const [cx, cy, w, h] = item.faces[id].box;
      const box = element('span', figure);
      box.className = 'box ' + role;
      box.dataset.face = id;
      Object.assign(box.style, {left: (cx-w/2)/item.width*100+'%', top: (cy-h/2)/item.height*100+'%',
                                width: w/item.width*100+'%', height: h/item.height*100+'%'});
    }
    feedback.textContent = message;
  }
  const descriptions = new Map();
  for (const claim of claims) {
    const actor = claim.subject;
    const sentence = claim.spans.map(s => s.text ?? s.verb ?? item.faces[s.face].name).join('');
    descriptions.set(actor, [...(descriptions.get(actor) || []), sentence]);
  }
  for (const claim of claims) {
    const p = element('p', section);
    p.dataset.subject = claim.subject;
    if (item.individual.includes(claim)) p.className = 'individual';
    for (const span of claim.spans) {
      if ('text' in span) { p.append(span.text); continue; }
      const face = item.faces[span.face];
      const b = element('button', p, face ? face.name : span.verb);
      b.type = 'button';
      b.setAttribute('aria-pressed','false');
      if (face) {
        b.dataset.face = span.face;
        b.dataset.immichFaceId = face.immich_face_id || (face.face_namespace === 'immich' ? face.face_id : '');
        if (face.person_id) b.dataset.immichPersonId = face.person_id;
        b.title = b.dataset.immichFaceId ? 'Immich face ID · ' + b.dataset.immichFaceId : face.face_namespace + ' face ID · ' + face.face_id;
        b.onclick = () => {
          const text = descriptions.get(span.face)?.join(' ') || face.name;
          select(b, {person:span.face}, face.unnamed && b.dataset.immichFaceId ? text + ' · ' + b.title : text);
        };
      } else {
        b.dataset.action = span.id;
        b.dataset.savedVerb = span.verb;
        const labels = Object.entries(span.roles).map(([role,id]) =>
          ({actor:'Actor', held_person:'Held person', recipient:'Recipient'}[role] || role) + ' · ' + item.faces[id].name);
        const roles = {...span.roles};
        for (const [i, ref] of (span.participants || []).entries()) {
          if (Object.values(roles).includes(ref.face)) continue;
          roles[ref.role + '-' + i] = ref.face;
          labels.push(ref.role + ' · ' + item.faces[ref.face].name);
        }
        b.onclick = () => select(b, roles, [span.verb, span.code, ...labels].join(' / '));
      }
    }
  }
  // Locate every phrase before inserting buttons so offsets refer to the saved captions.
  for (const p of section.querySelectorAll('p')) {
    if (p.classList.contains('individual')) continue;
    const sentence = p.textContent;
    p.dataset.savedCaption = sentence;
    let offset = 0;
    const nodes = Array.from(p.childNodes, node => {
      const start = offset;
      offset += node.textContent.length;
      return {node, start, end:offset};
    });
    const mentions = item.mentions.filter(m => sentence.includes(m.words))
      .sort((a,b) => sentence.indexOf(b.words) - sentence.indexOf(a.words));
    for (const mention of mentions) {
      const end = sentence.indexOf(mention.words) + mention.words.length;
      const start = end - mention.words.length;
      const covered = nodes.filter(n => n.start < end && n.end > start);
      let anchor = covered.at(-1)?.node;
      if (!anchor) throw Error('Missing caption anchor');
      // Keep a verb button intact when its text also refers to a participant.

      const links = document.createElement('span');
      links.className = 'mention';
      links.dataset.words = mention.words;
      for (const id of mention.faces) {
        const f = item.faces[id];
        const label = f.name;
        const b = element('button', links, label);
        b.type = 'button';
        b.dataset.immichFaceId = f.face_id;
        if (f.person_id) b.dataset.immichPersonId = f.person_id;
        b.title = 'Immich face ID · ' + f.face_id;
        b.setAttribute('aria-pressed','false');
        b.onclick = () => select(b, {person:id}, label + ' · Immich face ' + f.face_id);
      }
      const individual = mention.faces.length === 1 && !mention.reason;
      // Split at the saved offsets, even when the noun starts inside a verb button.
      // Keep a clickable verb whenever shortening it still leaves action words.
      if (individual && covered.every(({node,start:l,end:r}) =>
          node.nodeType === Node.TEXT_NODE || l < start || r > end)) {
        let tail = '';
        for (const {node,start:l} of covered) {
          const text = node.textContent;
          tail += text.slice(Math.max(0,end-l));
          node.textContent = text.slice(0,Math.max(0,start-l));
        }
        const first = covered[0].node;
        if (first.nodeType === Node.ELEMENT_NODE && !first.textContent && tail) {
          first.textContent = tail;
          first.before(links);
        } else {
          first.after(links);
          if (tail) links.after(document.createTextNode(tail));
        }
        links.dataset.replaced = 'true';
        if (/[’']s$/.test(mention.words)) links.append('’s');
      } else {
        if (anchor.nodeType === Node.TEXT_NODE) {
          const last = covered.at(-1);
          if (end-last.start < anchor.length) anchor.splitText(end-last.start);
        }
        anchor.after(links);
      }
      if (mention.reason) element('small', links, mention.reason);
    }
  }
  descriptions.clear();
  for (const p of section.querySelectorAll('p[data-subject]')) {
    const copy = p.cloneNode(true);
    copy.querySelectorAll('.mention:not([data-replaced])').forEach(el=>el.remove());
    descriptions.set(p.dataset.subject, [...(descriptions.get(p.dataset.subject) || []),copy.textContent]);
  }
  if (collage) {
    element('h3', article, item.panels ? 'Collage · ' + item.panels.length + ' photos' : 'Collage · layout pending');
    for (const panel of item.panels || []) {
      const details = element('details', article);
      details.className = 'component';
      const pts = panel.polygon;
      const xs = pts.filter((_,i)=>i%2===0), ys = pts.filter((_,i)=>i%2===1);
      const x = Math.min(...xs), y = Math.min(...ys), w = Math.max(...xs)-x, h = Math.max(...ys)-y;
      element('summary', details, 'Photo ' + panel.number + ' · ' + panel.faces.length + ' face links');
      const crop = element('div', details);
      crop.style.cssText = 'width:100%;position:relative;overflow:hidden;aspect-ratio:'+w+'/'+h;
      crop.style.clipPath = 'polygon('+xs.map((v,i)=>(v-x)/w*100+'% '+(ys[i]-y)/h*100+'%').join(',')+')';
      const piece = element('img',crop);
      piece.src=item.image;
      piece.alt='Component photo '+panel.number;
      Object.assign(piece.style,{position:'absolute',width:item.width/w*100+'%',height:item.height/h*100+'%',
                                 left:-x/w*100+'%',top:-y/h*100+'%'});
      for (const id of panel.faces) {
        const f = item.faces[id];
        const b = element('button',details,f.name);
        b.type='button'; b.dataset.immichFaceId=f.face_id; b.title='Immich face ID · '+f.face_id;
        b.onclick=()=>select(b,{person:id},'Photo '+panel.number+' · Immich face '+f.face_id);
      }
      if (!panel.actions.length) element('div', details, 'No verified human action.');
      for (const action of panel.actions) {
        const line=element('div', details);
        if (!action.actors.length) { line.textContent=action.text; continue; }
        const b=element('button',line,action.text);
        b.type='button'; b.dataset.componentAction=action.code;
        b.onclick=()=>select(b,Object.fromEntries(action.actors.map((id,i)=>['actor-'+i,id])),
                             'Photo '+panel.number+' · '+action.text);
      }
    }
  }
  for (const [id, face] of Object.entries(item.faces)) {
    if (!face.action_withheld) continue;
    const line = element('div', section);
    line.className = 'face-disposition';
    const button = element('button', line, face.name);
    button.type = 'button';
    button.dataset.immichFaceId = face.face_id;
    button.title = 'Immich face ID · ' + face.face_id;
    button.onclick = () => select(button, {person:id}, button.title);
    line.append(' · ' + face.action_withheld);
  }
  block.append(feedback);
  if (item.ocr?.length) {
    const details = element('details', block);
    details.className = 'ocr-tags';
    const summary = element('summary', details);
    element('strong', summary, 'OCR');
    summary.append(' · ' + item.ocr[0].text);
    element('small', details, 'Text recognized by Immich. Select a line to highlight it.');
    for (const region of item.ocr) {
      const button = element('button', details, region.text);
      button.type = 'button';
      button.dataset.immichOcrId = region.id;
      button.setAttribute('aria-pressed', 'false');
      button.onclick = () => {
        select(button, {}, region.text);
        const overlay = element('span', figure);
        overlay.className = 'ocr-region';
        overlay.setAttribute('aria-hidden', 'true');
        overlay.dataset.immichOcrId = region.id;
        const points = [];
        for (let i = 0; i < region.polygon.length; i += 2) {
          points.push(region.polygon[i] * 100 + '% ' + region.polygon[i + 1] * 100 + '%');
        }
        overlay.style.clipPath = 'polygon(' + points.join(',') + ')';
      };
    }
    details.addEventListener('toggle', () => {
      if (!details.open && figure.querySelector('.ocr-region')) {
        figure.querySelector('.ocr-region').remove();
        details.querySelector('[aria-pressed="true"]')?.setAttribute('aria-pressed', 'false');
        feedback.textContent = '';
      }
    });
  }
  if (item.caption_sources) {
    const history = element('details', block);
    element('summary', history, 'Caption sources');
    element('div', history, 'Earlier marked-face caption · ' + 'The marked person ' + item.caption_sources.source_literal.trim());
    element('div', history, 'Later participant review · ' + item.caption_sources.review);
  }
  for (const b of block.querySelectorAll('button[data-immich-face-id]')) {
    const id = b.dataset.immichFaceId;
    if (id && Object.values(item.faces).some(f=>f.face_id === id && f.unnamed)) {
      b.dataset.shortFaceId = id.slice(0,8);
    }
  }
  if (!journey) element('a', article, 'Open original in Immich').href = item.original;
}
