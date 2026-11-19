'use strict';
const $ = id => document.getElementById(id);
const state = {csrf:'', frigate:false, date:null, offset:0, total:0, photos:[], selected:new Set(), busy:false};
const timezone = () => $('timezone').value.trim();
function status(message, error=false) { $('status').textContent=message; $('status').classList.toggle('error',error); }
function element(tag, text, className) { const node=document.createElement(tag); if(text!==undefined) node.textContent=text; if(className) node.className=className; return node; }
function button(text, fn, className='secondary') { const node=element('button',text,className); node.type='button'; node.onclick=()=>run(fn); return node; }
function query(path, params) { return path+'?'+new URLSearchParams(params); }
async function api(path, body) {
  const response=await fetch(path, body===undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json','X-Photo-Token':state.csrf},body:JSON.stringify(body)});
  const result=await response.json(); if(!response.ok) throw new Error(result.error||'Request failed'); return result;
}
async function run(fn) {
  if(state.busy) return;
  state.busy=true; document.querySelectorAll('button').forEach(b=>b.disabled=true);
  try { await fn(); } catch(error) { status(error.message,true); }
  finally {state.busy=false;document.querySelectorAll('button').forEach(b=>b.disabled=false);pagination();}
}
function pagination() { $('previous').disabled=state.offset===0; $('next').disabled=state.offset+state.photos.length>=state.total; }
function selected() { $('selected').textContent=state.selected.size; document.querySelectorAll('.photo-card').forEach(card=>{const yes=state.selected.has(card.dataset.path);card.classList.toggle('chosen',yes);card.querySelector('input').checked=yes;}); }
function clearForm() { $('group-form').reset();$('group-id').value='';$('delete-group').hidden=true;$('save').textContent='Save group context'; }
async function loadGroups() {
  const groups=await api('/api/groups');$('groups').replaceChildren();
  for(const group of groups) $('groups').append(button((group.event||group.location||'Untitled group')+' · '+group.photos, async()=>{
    const data=await api(query('/api/group',{id:group.id}));clearForm();$('group-id').value=data.id;
    for(const key of ['event','location','venue','notes']) $(key).value=data[key]||'';
    $('tags').value=data.tags.join(', ');$('timezone').value=data.timezone;
    state.selected=new Set(data.paths);await loadDates();selected();$('delete-group').hidden=false;$('save').textContent='Update group context';
    status('Editing saved group: '+data.paths.length+' photos. Selection includes all saved members, even on other dates.');
  }));
}
async function loadDates() {
  const dates=await api(query('/api/dates',{timezone:timezone()}));$('dates').replaceChildren();
  for(const date of dates) {
    const node=button(date.date,async()=>{state.date=date.date;state.offset=0;state.selected.clear();clearForm();await loadPhotos();});
    node.dataset.date=date.date;node.append(element('span',String(date.photos)));$('dates').append(node);
  }
  if(!state.date||!dates.some(d=>d.date===state.date)) state.date=dates[0]?.date||null;
  await loadPhotos();await loadGroups();
}
async function loadPhotos() {
  if(!state.date){$('photos').replaceChildren(element('p','No photos found in the index.'));status('No indexed photos yet.');return;}
  const data=await api(query('/api/photos',{date:state.date,timezone:timezone(),offset:state.offset}));state.photos=data.photos;state.total=data.total;
  $('date-title').textContent=state.date==='unknown'?'Capture date unknown':state.date;
  $('count').textContent=data.total+' photos · '+timezone();$('photos').replaceChildren();
  for(const photo of state.photos) {
    const card=element('article',undefined,'photo-card');card.dataset.path=photo.path;
    const image=element('img');image.loading='lazy';image.src=query('/api/thumbnail',{path:photo.path});image.alt='Photo '+photo.name;
    const label=element('label',undefined,'check');const check=element('input');check.type='checkbox';check.setAttribute('aria-label','Select '+photo.name);
    check.onchange=()=>{if(check.checked)state.selected.add(photo.path);else state.selected.delete(photo.path);selected();};label.append(check);
    const body=element('div',undefined,'card-body');body.append(element('span',photo.latitude!==null?'GPS available':'Location unknown','badge'));
    body.append(element('p',photo.summary||'No model caption yet','card-caption'));body.append(button('Review photo',()=>showPhoto(photo.path)));
    card.append(image,label,body);$('photos').append(card);
  }
  document.querySelectorAll('#dates button').forEach(b=>b.classList.toggle('active',b.dataset.date===state.date));selected();pagination();
  status('Showing '+state.photos.length+' of '+state.total+' photos. Select a few to add shared context.');
}
async function showPhoto(path) {
  const photo=await api(query('/api/photo',{path}));$('detail-image').src=query('/api/thumbnail',{path});$('detail-name').textContent=path;
  $('caption').textContent=photo.summary||'No model caption saved yet.';$('metadata').replaceChildren();
  const fields=[['Captured',photo.capture_ts ? new Date(photo.capture_ts*1000).toLocaleString(undefined,{timeZone:timezone()})+' ('+timezone()+')':'Unknown'],
    ['Date source',photo.capture_source||'Unknown'],['GPS',photo.latitude===null?'Unknown':photo.latitude.toFixed(6)+', '+photo.longitude.toFixed(6)],
    ['GPS source',photo.gps_source||'Unknown'],['Camera',[photo.camera_make,photo.camera_model].filter(Boolean).join(' ')||'Not extracted'],
    ['Extraction',photo.extraction_error||photo.extraction_version||'Not run'],['Caption model',photo.summary_model||'None']];
  for(const [key,value] of fields) $('metadata').append(element('dt',key),element('dd',value));
  $('photo-groups').replaceChildren(...(photo.groups.length?photo.groups.map(g=>element('p',[g.event,g.location,g.venue,g.notes,g.tags.join(', ')].filter(Boolean).join(' · '))):[element('p','No user annotations yet.','muted')]));
  $('imported-people').textContent='Imported whole-photo tags: '+((photo.people||[]).join(', ')||'none')+'. These are not face assignments.';
  $('faces').replaceChildren();
  if(!photo.faces.length) $('faces').append(element('p','No faces indexed. Select this photo and use “Find faces in selection”.','muted'));
  for(const face of photo.faces) {
    const card=element('div',undefined,'face-card');const img=element('img');img.src=query('/api/thumbnail',{path,face:face.id});img.alt='Detected face crop';
    const title=element('strong',face.person||'Unnamed face');const input=element('input');input.value=face.person||'';input.placeholder='Person’s name';input.setAttribute('aria-label','Name this face');
    card.append(img,title,element('p','Label: '+(face.label_source||'unconfirmed'),'muted'),input);
    card.append(button('Save name',async()=>{await api('/api/faces/label',{id:face.id,person:input.value});await showPhoto(path);status('Face label saved from your input.');}));
    const suggestions=element('div');
    card.append(button('Find name suggestions',async()=>{
      const matches=await api(query('/api/suggestions',{face:face.id}));suggestions.replaceChildren();
      if(!matches.length)suggestions.append(element('p','No matching confirmed faces yet. Name a face first.','muted'));
      for(const match of matches){const item=element('div',undefined,'suggestion');item.append(element('span',match.person+' · similarity '+match.score.toFixed(3)+' (not a probability)'));
        item.append(button('Confirm',async()=>{await api('/api/faces/label',{id:face.id,person:match.person});await showPhoto(path);status('You confirmed the suggested face label.');}));
        item.append(button('Reject',async()=>{await api('/api/faces/reject',{id:face.id,reference_id:match.reference_id});item.remove();status('Suggestion rejected.');}));suggestions.append(item);}
    }));
    if(state.frigate)card.append(button('Ask Frigate',async()=>{const match=await api('/api/faces/frigate',{id:face.id});suggestions.replaceChildren();
      const empty={no_face:'Frigate could not detect a face in this crop.',below_threshold:'Frigate found no confident identity match.',no_match:'Frigate returned no match. After startup, its face library may still be warming up.'};
      const item=element('div',undefined,'suggestion');item.append(element('p',match.name?'Frigate suggests '+match.name+' · score '+match.score:(empty[match.reason]||'Frigate returned no match.')));
      if(match.name)item.append(button('Confirm Frigate suggestion',async()=>{await api('/api/faces/label',{id:face.id,person:match.name});await showPhoto(path);status('You confirmed the Frigate suggestion.');}));suggestions.append(item);
    }));
    card.append(suggestions);$('faces').append(card);
  }
  if(!$('detail').open)$('detail').showModal();
}
$('close-detail').onclick=()=>$('detail').close();
$('refresh').onclick=()=>run(async()=>{state.offset=0;state.selected.clear();clearForm();await loadDates();});
$('select-page').onclick=()=>{state.photos.forEach(p=>state.selected.add(p.path));selected();};
$('clear').onclick=()=>{state.selected.clear();selected();};
$('new-group').onclick=()=>{clearForm();status('New group: your current photo selection is retained.');};
$('previous').onclick=()=>run(async()=>{state.offset=Math.max(0,state.offset-100);await loadPhotos();});
$('next').onclick=()=>run(async()=>{state.offset+=100;await loadPhotos();});
$('group-form').onsubmit=event=>{event.preventDefault();run(async()=>{
  const body={paths:[...state.selected],timezone:timezone(),tags:$('tags').value.split(',').map(s=>s.trim()).filter(Boolean)};
  for(const key of ['event','location','venue','notes'])body[key]=$(key).value;
  if($('group-id').value)body.id=$('group-id').value;
  const saved=await api('/api/groups/save',body);$('group-id').value=saved.id;$('delete-group').hidden=false;$('save').textContent='Update group context';await loadGroups();status('Saved your context for '+saved.photos+' selected photos.');
});};
$('delete-group').onclick=()=>run(async()=>{if(!confirm('Delete this group annotation? Original photos and captions remain intact.'))return;await api('/api/groups/delete',{id:$('group-id').value});clearForm();await loadGroups();status('Group annotation deleted.');});
for(const [id,faces] of [['extract',false],['detect',true]])$(id).onclick=()=>run(async()=>{
  if(!state.selected.size)throw new Error('Select photos first.');status(faces?'Detecting faces locally on CPU…':'Reading original photo metadata…');
  const result=await api('/api/extract',{paths:[...state.selected],timezone:timezone(),faces});state.offset=0;await loadDates();
  status('Processed '+result.processed+', already extracted '+result.skipped+', new faces '+result.faces+'. '+result.errors.length+' errors.'+(result.errors[0]?' '+result.errors[0].error:''),result.errors.length>0);
});
$('export').onclick=()=>run(async()=>{const result=await api('/api/export',{});status('Exported '+result.tables.length+' Parquet tables to '+result.directory);});
run(async()=>{const config=await api('/api/config');state.csrf=config.csrf;state.frigate=config.frigate;await loadDates();});
