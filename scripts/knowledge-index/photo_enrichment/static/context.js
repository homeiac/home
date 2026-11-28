'use strict';
const $ = id => document.getElementById(id);
const state = {csrf:'', frigate:false, date:null, offset:0, total:0, search:'', photos:[], selected:new Set(), busy:false};
const timezone = () => $('timezone').value.trim();
function status(message, error=false) { $('status').textContent=message; $('status').classList.toggle('error',error); }
function element(tag, text, className) { const node=document.createElement(tag); if(text!==undefined) node.textContent=text; if(className) node.className=className; return node; }
function button(text, fn, className='secondary') { const node=element('button',text,className); node.type='button'; node.onclick=()=>run(fn); return node; }
function query(path, params) { return path+'?'+new URLSearchParams(params); }
async function api(path, body) {
  const response=await fetch(path, body===undefined ? {signal:AbortSignal.timeout(20000)} : {signal:AbortSignal.timeout(20000),method:'POST', headers:{'Content-Type':'application/json','X-Photo-Token':state.csrf},body:JSON.stringify(body)});
  const result=await response.json(); if(!response.ok) throw new Error(result.error||'Request failed'); return result;
}
async function run(fn) {
  if(state.busy) return;
  state.busy=true; document.querySelectorAll('button').forEach(b=>b.disabled=true);
  try { await fn(); } catch(error) { status(error.message,true); }
  finally {state.busy=false;document.querySelectorAll('button').forEach(b=>b.disabled=false);pagination();}
}
function pagination() { $('previous').disabled=state.offset===0; $('next').disabled=state.offset+state.photos.length>=state.total; }
function selected() { scheduleGroupSuggestions(); $('selected').textContent=state.selected.size; document.querySelectorAll('.photo-card').forEach(card=>{const yes=state.selected.has(card.dataset.path);card.classList.toggle('chosen',yes);card.querySelector('input').checked=yes;}); }
function clearForm() { autoGroupValues={}; $('delete-group').dataset.confirm='';$('delete-group').textContent='Delete this group'; $('group-form').reset();$('group-id').value='';$('delete-group').hidden=true;$('save').textContent='Save group context'; }
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
    const node=button(date.date,async()=>{state.date=date.date;state.search='';$('photo-search').value='';state.offset=0;state.selected.clear();clearForm();await loadPhotos();});
    node.dataset.date=date.date;node.append(element('span',String(date.photos)));$('dates').append(node);
  }
  if(!state.date||!dates.some(d=>d.date===state.date)) state.date=dates[0]?.date||null;
  await loadPhotos();await loadGroups();
}
async function loadPhotos() {
  if(!state.date&&!state.search){$('photos').replaceChildren(element('p','No photos found in the index.'));status('No indexed photos yet.');return;}
  const data=await api(query(state.search?'/api/search':'/api/photos',{date:state.date,q:state.search,timezone:timezone(),offset:state.offset}));state.photos=data.photos;state.total=data.total;
  $('date-title').textContent=state.search?'Search: '+state.search:state.date==='unknown'?'Capture date unknown':state.date;
  $('count').textContent=data.total+' photos · '+timezone();$('photos').replaceChildren();
  for(const photo of state.photos) {
    const card=element('article',undefined,'photo-card');card.dataset.path=photo.path;
    const image=element('img');image.loading='lazy';image.src=query('/api/thumbnail',{path:photo.path});image.alt='Photo '+photo.name;
    const label=element('label',undefined,'check');const check=element('input');check.type='checkbox';check.setAttribute('aria-label','Select '+photo.name);
    check.onchange=()=>{if(check.checked)state.selected.add(photo.path);else state.selected.delete(photo.path);selected();};label.append(check);
    const body=element('div',undefined,'card-body');body.append(element('span',photo.latitude!==null?'GPS available':'Location unknown','badge'));
    if(photo.suggested_location)body.append(element('span',photo.suggested_location,'badge'));
    for(const person of photo.saved_people||[])body.append(element('span',person,'badge'));
    if(photo.context_summary)body.append(element('span','Enriched caption','badge'));
    body.append(element('p',photo.context_summary||photo.summary||'No model caption yet','card-caption'));body.append(button('View context',()=>showPhoto(photo.path)));
    card.append(image,label,body);$('photos').append(card);
  }
  document.querySelectorAll('#dates button').forEach(b=>b.classList.toggle('active',b.dataset.date===state.date));selected();pagination();
  status('Showing '+state.photos.length+' of '+state.total+' photos. Select a few to add shared context.');
}
async function showPhoto(path) {
  const photo=await api(query('/api/photo',{path}));$('detail-image').src=query('/api/thumbnail',{path});$('detail-name').textContent=path;
  $('caption').textContent=photo.primary_description||photo.context_summary||photo.summary||'No model caption saved yet.';
  $('caption-status').hidden=photo.description_source!=='confirmed_faces';$('metadata').replaceChildren();
  const fields=[['Captured',photo.capture_ts != null ? new Date(photo.capture_ts*1000).toLocaleString(undefined,{timeZone:timezone()})+' ('+timezone()+')':'Unknown'],
    ['Date source',photo.capture_source||'Unknown'],['GPS',Number.isFinite(photo.latitude)&&Number.isFinite(photo.longitude)?photo.latitude.toFixed(6)+', '+photo.longitude.toFixed(6):'Unknown'],
    ['GPS source',photo.gps_source||'Unknown'],['Camera',[photo.camera_make,photo.camera_model].filter(Boolean).join(' ')||'Not extracted'],
    ['Extraction',photo.extraction_error||photo.extraction_version||'Not run'],['Caption model',photo.summary_model||'None']];
  const place=photo.place_evidence;
  if(place) {
    if(place.status==='known' || place.status==='multiple') {
      fields.push([place.status==='multiple'?'Competing saved places':'Place',place.labels.join(' · ')],
        ['Place source',place.source==='user'?'Your group annotations':'Immich · '+place.precision]);
    } else {
      const label=place.status==='coordinates'?'Coordinates recorded':place.status==='unavailable'?'Source unavailable':'Unknown';
      fields.push(['Place',label]);
      if(place.place_lookup_unavailable)fields.push(['Place source','Immich snapshot unavailable']);
    }
  }
  if(photo.description_source!=='model' && photo.summary)fields.push(['Original model caption',photo.summary]);
  if(photo.description_source==='context')fields.push(['Context caption model',photo.context_model]);
  for(const [key,value] of fields) $('metadata').append(element('dt',key),element('dd',value));
  if(photo.location_context){
    const context=photo.location_context;
    $('metadata').append(element('dt','Nearby places (not confirmed subjects)'));
    const sources=element('dd');
    for(const candidate of context.candidates||[]){
      const link=element('a',candidate.title+' ');link.href=candidate.url;link.target='_blank';link.rel='noopener noreferrer';sources.append(link);
    }
    sources.append(element('p',context.attribution||'Wikipedia / Wikidata','muted'));$('metadata').append(sources);
  }
  $('photo-groups').replaceChildren(...(photo.groups.length?photo.groups.map(g=>element('p',[g.event,g.location,g.venue,g.notes,g.tags.join(', ')].filter(Boolean).join(' · '))):[element('p','No user annotations yet.','muted')]));
  if(!$('detail').open)$('detail').showModal();
}
let autoGroupValues={},suggestionTimer=null,suggestionRevision=0;
function scheduleGroupSuggestions(){
  clearTimeout(suggestionTimer);const revision=++suggestionRevision;
  if(!state.contextSuggestions||$('group-id').value||!state.selected.size)return;
  suggestionTimer=setTimeout(async()=>{
    try{
      const data=await api('/api/group-suggestions',{paths:[...state.selected],timezone:timezone()});
      if(revision!==suggestionRevision||$('group-id').value)return;
      for(const [key,value] of Object.entries({event:data.event,location:data.location,tags:data.tags.join(', ')})){
        if(!$(key).value||$(key).value===autoGroupValues[key]){$(key).value=value;autoGroupValues[key]=value;}
      }
      $('group-suggestion-note').textContent=data.photos?(data.inferred?'Nearby GPS places are inferred; review before saving. ':'')+'Indexed context for '+data.photos+' selected photos.':'Search index is updating; your edits can still be saved.';
    }catch(error){$('group-suggestion-note').textContent='Could not load indexed context: '+error.message;}
  },300);
}
$('photo-search-form').onsubmit=event=>{event.preventDefault();run(async()=>{state.search=$('photo-search').value.trim();state.offset=0;state.selected.clear();clearForm();await loadPhotos();});};
$('clear-search').onclick=()=>run(async()=>{state.search='';$('photo-search').value='';state.offset=0;state.selected.clear();clearForm();await loadPhotos();});
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
$('delete-group').onclick=()=>run(async()=>{if($('delete-group').dataset.confirm!=='yes'){$('delete-group').dataset.confirm='yes';$('delete-group').textContent='Confirm deletion';status('Click Confirm deletion to remove this group annotation.');return;}await api('/api/groups/delete',{id:$('group-id').value});clearForm();await loadGroups();status('Group annotation deleted.');});

run(async()=>{
  const config=await api('/api/config');state.csrf=config.csrf;state.contextSuggestions=config.search_index;
  $('photo-search-form').hidden=!config.search_index;
  await loadDates();
});
