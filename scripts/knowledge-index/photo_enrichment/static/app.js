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
  if(!state.date){$('photos').replaceChildren(element('p','No photos found in the index.'));status('No indexed photos yet.');return;}
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
    if(photo.description_source==='confirmed_faces')body.append(element('span','Scene description pending','badge'));
    if(photo.description_source==='context')body.append(element('span','Enriched caption','badge'));
    body.append(element('p',photo.primary_description||'No model caption yet','card-caption'));body.append(button('Review photo',()=>showPhoto(photo.path)));
    card.append(image,label,body);$('photos').append(card);
  }
  document.querySelectorAll('#dates button').forEach(b=>b.classList.toggle('active',b.dataset.date===state.date));selected();pagination();
  status('Showing '+state.photos.length+' of '+state.total+' photos. Select a few to add shared context.');
}
async function showPhoto(path) {
  const photo=await api(query('/api/photo',{path}));$('detail-image').src=query('/api/thumbnail',{path});$('detail-name').textContent=path;
  $('caption').textContent=photo.primary_description||'No model caption saved yet.';
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
  $('imported-people').textContent='Imported whole-photo tags: '+((photo.people||[]).join(', ')||'none')+'. These are not face assignments.';
  $('faces').replaceChildren();
  if(!photo.faces.length) $('faces').append(element('p','No faces indexed. Select this photo and use “Find faces in selection”.','muted'));
  for(const face of photo.faces) {
    const card=element('div',undefined,'face-card');const img=element('img');img.src=query('/api/thumbnail',{path,face:face.id});img.alt='Detected face crop';
    const title=element('strong',face.person||'Unnamed face');const input=element('input');input.value=face.person||'';input.placeholder='Person’s name';input.setAttribute('aria-label','Name this face');
    card.append(img,title,element('p','Label: '+(face.label_source||'unconfirmed'),'muted'),input);
    appendMatchDetails(card,face);
    card.append(button('Save name',async()=>{await api('/api/faces/label',{id:face.id,person:input.value,revision:face.revision});await showPhoto(path);status('Face label saved from your input.');}));
    const suggestions=element('div');
    card.append(button('Find name suggestions',async()=>{
      const matches=await api(query('/api/suggestions',{face:face.id}));suggestions.replaceChildren();
      if(!matches.length)suggestions.append(element('p','No matching confirmed faces yet. Name a face first.','muted'));
      for(const match of matches){const item=element('div',undefined,'suggestion');item.append(element('span',match.person+' · similarity '+match.score.toFixed(3)+' (not a probability)'));
        item.append(button('Confirm',async()=>{await api('/api/faces/label',{id:face.id,person:match.person,revision:face.revision});await showPhoto(path);status('You confirmed the suggested face label.');}));
        item.append(button('Reject',async()=>{await rejectFace(face,match.reference_id);await showPhoto(path);}));suggestions.append(item);}
    }));
    if(state.frigate)card.append(button('Ask Frigate',async()=>{const match=await api('/api/faces/frigate',{id:face.id});suggestions.replaceChildren();
      const empty={no_face:'Frigate could not detect a face in this crop.',below_threshold:'Frigate found no confident identity match.',no_match:'Frigate returned no match. After startup, its face library may still be warming up.'};
      const item=element('div',undefined,'suggestion');item.append(element('p',match.name?'Frigate suggests '+match.name+' · score '+match.score:(empty[match.reason]||'Frigate returned no match.')));
      if(match.name)item.append(button('Confirm Frigate suggestion',async()=>{await api('/api/faces/label',{id:face.id,person:match.name,revision:face.revision});await showPhoto(path);status('You confirmed the Frigate suggestion.');}));suggestions.append(item);
    }));
    card.append(suggestions);$('faces').append(card);
  }
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
for(const [id,faces] of [['extract',false],['detect',true]])$(id).onclick=()=>run(async()=>{
  if(!state.selected.size)throw new Error('Select photos first.');status(faces?'Detecting faces locally on CPU…':'Reading original photo metadata…');
  const result=await api('/api/extract',{paths:[...state.selected],timezone:timezone(),faces});state.offset=0;await loadDates();
  status('Processed '+result.processed+', already extracted '+result.skipped+', new faces '+result.faces+'. '+result.errors.length+' errors.'+(result.errors[0]?' '+result.errors[0].error:''),result.errors.length>0);
});
$('export').onclick=()=>run(async()=>{const result=await api('/api/export',{});status('Exported '+result.tables.length+' Parquet tables to '+result.directory);});


// Face-first review: labels and actionable collections are always fresh DB reads.
Object.assign(state,{view:'faces',faceStatus:'unreviewed',person:'',faceOffset:0,faceTotal:0,faceItems:[],faceSelection:new Map(),people:[],review:null});
function faceSelection() {
  $('face-selected').textContent=state.faceSelection.size;
  const selected=[...state.faceSelection.values()];const names=new Map();
  for(const face of selected){const name=face.person||'Without a suggestion';names.set(name,(names.get(name)||0)+1);}
  $('face-selection-summary').textContent=[...names].map(([name,count])=>count+' × '+name).join(' · ');
  $('bulk-confirm-suggestions').disabled=state.busy||!selected.length||selected.some(face=>!face.person);
  document.querySelectorAll('.face-tile').forEach(card=>{const chosen=state.faceSelection.has(card.dataset.id);card.classList.toggle('chosen',chosen);card.querySelector('input').checked=chosen;});
}
function selectFace(face) {
  if(state.faceSelection.has(face.id))return;
  // Keep the displayed name and revision: confirmation must not silently use a newer suggestion.
  state.faceSelection.set(face.id,{id:face.id,revision:face.revision,person:face.person?null:face.suggestion?.person||null});
}
async function rejectFace(face,referenceId){
  await api('/api/faces/reject',{id:face.id,reference_id:referenceId});
  state.faceSelection.delete(face.id);
  if(state.review?.id===face.id)$('face-review').close();
  await loadFaces();
  status('Rejected this candidate and removed it from suggested matches. The face remains available in All faces.');
}
function renderPeople() {
  $('people').replaceChildren();const term=$('people-search').value.toLocaleLowerCase();
  for(const person of state.people.filter(p=>p.person.toLocaleLowerCase().includes(term))){
    const node=button(person.person,()=>filterFaces('named',person.person),'collection');node.append(element('span',person.faces));node.classList.toggle('active',state.faceStatus==='named'&&state.person===person.person);$('people').append(node);
  }
}
async function filterFaces(filter,person='',group='') {
  if(filter==='priority'&&state.faceScope!=='priority')state.faceSelection.clear();
  state.faceScope=filter==='priority'?'priority':filter==='ungrouped'?'ungrouped':'repeated';
  state.faceStatus=filter==='ungrouped'?'unreviewed':filter==='priority'?'suggested':filter;
  state.person=person;state.faceGroup=group;$('bulk-person').value='';state.faceOffset=0;await loadFaces();
}
function refreshPendingSuggestions(){
  if(state.view!=='faces')return;
  if(state.busy){state.suggestionRefresh=setTimeout(refreshPendingSuggestions,5000);return;}
  run(loadFaces);
}
async function loadFaces() {
  const data=await api(query('/api/faces',{status:state.faceStatus,person:state.person,offset:state.faceOffset,group:state.faceGroup||'',grouped:state.faceStatus==='unreviewed',scope:state.faceScope||'repeated'}));
  state.faceItems=data.faces;state.faceTotal=data.total;state.people=data.people;state.groupGeneration=data.generation;
  $('face-back-groups').hidden=!state.faceGroup;
  $('face-select-group').hidden=!state.faceGroup;
  if(!data.faces.length&&state.faceOffset>0){state.faceOffset=Math.max(0,state.faceOffset-48);return loadFaces();}
  const priority=state.faceScope==='priority';
  $('face-title').textContent=(state.faceStatus==='suggested'?(priority?'Priority matches':'Suggested matches')+(state.person?' · '+state.person:''):state.person||(state.faceStatus==='unreviewed'?(state.faceGroup?'Review this group':state.faceScope==='ungrouped'?'Ungrouped faces':'Face review groups'):'All faces'));
  $('face-count').textContent=data.grouped?data.total+' review groups · '+(data.counts.ungrouped||0)+' ungrouped faces · '+data.counts.unreviewed+' unnamed detections':data.total+' faces · confirm names individually or together';
  if(data.suggestions_refreshing||data.grouping_refreshing){
    $('face-count').textContent+=' · Calculating closest matches and review groups in the background…';
    clearTimeout(state.suggestionRefresh);
    state.suggestionRefresh=setTimeout(refreshPendingSuggestions,5000);
  }
  $(priority?'priority-count':'suggested-count').textContent=data.suggestions_refreshing?'…':(data.counts.suggested||0);
  $('suggested-people').replaceChildren();
  for(const group of data.suggested_people||[]){const item=button(group.person,()=>filterFaces(priority?'priority':'suggested',group.person),'collection');item.append(element('span',group.faces));item.classList.toggle('active',state.faceStatus==='suggested'&&state.person===group.person);$('suggested-people').append(item);}
  $('filter-priority').classList.toggle('active',priority);
  $('filter-suggested').classList.toggle('active',state.faceStatus==='suggested'&&!priority);
  $('face-select-page').hidden=data.grouped||(!state.faceGroup&&state.faceStatus!=='suggested');
  $('threshold-selection').hidden=state.faceStatus==='named';
  $('selection-scope').textContent=state.faceStatus==='suggested'&&state.person?'All suggestions for '+state.person:priority?'Priority matches only':'All suggested matches in the library';
  $('unreviewed-count').textContent=data.grouping_refreshing?'…':(data.counts.review_groups??data.counts.unreviewed);$('face-total').textContent=data.counts.total;
  $('ungrouped-count').textContent=data.grouping_refreshing?'…':(data.counts.ungrouped||0);
  $('filter-ungrouped').classList.toggle('active',state.faceStatus==='unreviewed'&&state.faceScope==='ungrouped');
  $('known-people').replaceChildren(...data.people.map(p=>{const option=element('option');option.value=p.person;return option;}));renderPeople();
  $('filter-unreviewed').classList.toggle('active',state.faceStatus==='unreviewed'&&state.faceScope!=='ungrouped');$('filter-all').classList.toggle('active',state.faceStatus==='all');
  $('face-grid').replaceChildren();
  if(!data.faces.length&&(data.suggestions_refreshing||data.grouping_refreshing))$('face-grid').append(element('p','Preparing review groups. All detections are retained; this page refreshes automatically.','empty-state'));
  else if(!data.faces.length)$('face-grid').append(element('p',state.faceStatus==='suggested'?'No clear matches yet. Confirm more examples of a person, then refresh. Ambiguous faces stay unnamed.':state.faceStatus==='unreviewed'?(state.faceGroup?'This group has no unnamed faces left. Return to groups to continue.':state.faceScope==='ungrouped'?'No ungrouped faces.':'No repeated groups ready. Ungrouped faces remain available in their collection.'):'No faces in this collection yet.','empty-state'));
  for(const face of data.faces){
    const card=element('article',undefined,'face-tile');card.dataset.id=face.id;
    const crop=button('',()=>face.review_group?filterFaces('unreviewed','',face.review_group.id):reviewFace(face),'face-crop');crop.setAttribute('aria-label','Review '+(face.person||'unnamed face'));
    const img=element('img');img.loading='lazy';img.src=query('/api/thumbnail',{path:face.path,face:face.id});img.alt=face.person||'Unnamed detected face';crop.append(img);
    const check=element('input');check.type='checkbox';check.setAttribute('aria-label','Select '+(face.person||face.suggestion?.person||'unnamed face'));check.onchange=()=>{if(!state.busy){if(check.checked)selectFace(face);else state.faceSelection.delete(face.id);}faceSelection();};
    const label=element('label',undefined,'face-select');label.append(check);label.hidden=Boolean(face.review_group);
    const labelStatus={automatic:'Auto-accepted · editable',immich:'From Immich · editable',user:'Confirmed by you'};
    const body=element('div',undefined,'face-info');body.append(element('strong',face.person||face.suggestion?.person||'Unnamed face'),element('span',face.person?(labelStatus[face.label_source]||'Saved name'):face.suggestion?'Suggested name':face.match_details?.reason==='rejected'?'Rejected candidate':'Needs review','badge'),element('p',face.latitude==null?'Location not recorded':'Location available','muted'));
    appendMatchDetails(body,face);
    if(face.review_group){body.append(element('p',face.review_group.count+(face.review_group.count===1?' face in this review group':' faces in this review group'),'group-size'),button('Review group',()=>filterFaces('unreviewed','',face.review_group.id)));}
    else if(face.suggestion){body.append(button('Not this person',()=>rejectFace(face,face.suggestion.reference_id)));}
    body.append(element('p',face.capture_ts?new Date(face.capture_ts*1000).toLocaleDateString(undefined,{timeZone:timezone()}):'Date unknown','muted'));card.append(crop,label,body);$('face-grid').append(card);
  }
  faceSelection();facePagination();
}
function appendMatchDetails(container,face){
  const match=face.match_details||(face.suggestion?{...face.suggestion,reason:'qualified',qualified:true}:null);
  const reasons={pending:'Closest match is still being calculated.',no_references:'No manually confirmed reference faces yet.',
    no_compatible_references:'No compatible reference faces for this model.',no_other_references:'No other confirmed reference face to compare.',
    invalid_embedding:'Face embedding is missing or invalid.',rejected:'You rejected this candidate.',
    below_threshold:'Below the suggestion threshold.',ambiguous:'Ambiguous: another person has a similar score.',qualified:'Qualifies as a suggestion.'};
  const hasScore=match&&Number.isFinite(match.score);
  container.append(element('p',match?.person?'Closest candidate: '+match.person:'Closest candidate: unavailable','closest-candidate'));
  container.append(element('p',hasScore?'Similarity '+(match.score*100).toFixed(1)+' / 100':'Similarity: unavailable','match-score'));
  let reason=reasons[match?.reason||'pending']||'Match details unavailable.';
  if(match?.reason==='below_threshold')reason+=' Needs '+(match.threshold*100).toFixed(0)+' / 100.';
  if(match?.reason==='ambiguous'&&Number.isFinite(match.margin))reason+=' Lead '+(match.margin*100).toFixed(1)+'; needs '+(match.required_margin*100).toFixed(0)+' points.';
  if(face.person)reason='Saved name retained. '+reason;
  container.append(element('p',reason,'match-reason'));
}
function facePagination(){
  $('face-previous').disabled=state.faceOffset===0;$('face-next').disabled=state.faceOffset+state.faceItems.length>=state.faceTotal;
  const at=state.faceItems.findIndex(f=>f.id===state.review?.id);$('review-previous').disabled=at<=0;$('review-next').disabled=at<0||at>=state.faceItems.length-1;
}
const previousPagination=pagination;
pagination=function(){previousPagination();facePagination();faceSelection();};
async function reviewFace(face){
  state.review=face;$('review-title').textContent=face.person||(face.suggestion?'Suggested: '+face.suggestion.person:'Who is this?');$('review-person').value=face.person||face.suggestion?.person||'';
  $('review-crop').src=query('/api/thumbnail',{path:face.path,face:face.id});$('review-context').src=query('/api/thumbnail',{path:face.path});
  $('review-context-text').textContent=(face.capture_ts?new Date(face.capture_ts*1000).toLocaleString(undefined,{timeZone:timezone()}):'Date unknown')+' · Detection '+Math.round(face.confidence*100)+'%';
  $('review-caption').textContent=face.summary||'No caption available yet.';$('review-suggestions').replaceChildren();$('review-frigate').hidden=!state.frigate;
  appendMatchDetails($('review-suggestions'),face);
  facePagination();if(!$('face-review').open)$('face-review').showModal();
}
async function confirmFace(person){
  const face=state.review;await api('/api/faces/label',{id:face.id,person,revision:face.revision});
  $('face-review').close();state.faceSelection.delete(face.id);await loadFaces();status(person?'Confirmed name: '+person:'Name removed. The face is back in Needs review.');
}
$('close-face-review').onclick=()=>$('face-review').close();
$('review-save').onclick=()=>run(async()=>{const name=$('review-person').value.trim();if(!name)throw new Error('Enter a name, or use Remove name.');await confirmFace(name);});
$('review-clear').onclick=()=>run(()=>confirmFace(''));
$('review-photo-details').onclick=()=>run(async()=>{$('face-review').close();await showPhoto(state.review.path);});
for(const [id,step] of [['review-previous',-1],['review-next',1]])$(id).onclick=()=>run(async()=>{const at=state.faceItems.findIndex(f=>f.id===state.review.id);if(state.faceItems[at+step])await reviewFace(state.faceItems[at+step]);});
$('review-suggest').onclick=()=>run(async()=>{
  const matches=await api(query('/api/suggestions',{face:state.review.id}));$('review-suggestions').replaceChildren();
  if(!matches.length)$('review-suggestions').append(element('p','No matching confirmed faces yet. Name a few faces to build your reference library.','muted'));
  for(const match of matches){const item=element('div',undefined,'suggestion');item.append(element('p',match.person+' · similarity '+match.score.toFixed(3)+' (not a probability)'),button('Confirm',()=>confirmFace(match.person)),button('Reject',()=>rejectFace(state.review,match.reference_id)));$('review-suggestions').append(item);}
});
$('review-frigate').onclick=()=>run(async()=>{
  const match=await api('/api/faces/frigate',{id:state.review.id});$('review-suggestions').replaceChildren(element('p',match.name?'Frigate suggests '+match.name+' · score '+match.score:'No confident Frigate match for this crop.'));
  if(match.name)$('review-suggestions').append(button('Confirm Frigate suggestion',()=>confirmFace(match.name)));
});
async function saveSelectedFaces(person) {
  const faces=[...state.faceSelection.values()];
  if(!faces.length||(!person&&faces.some(face=>!face.person)))throw new Error('Select faces with suggested names first. Unnamed faces need a name before confirmation.');
  let saved=0;
  try {
    for(let offset=0;offset<faces.length;offset+=100){
      const batch=faces.slice(offset,offset+100);
      await api('/api/faces/labels',person?{faces:batch,person}:{faces:batch});
      batch.forEach(face=>state.faceSelection.delete(face.id));saved+=batch.length;
      faceSelection();status('Confirmed '+saved+' of '+faces.length+' selected faces…');
    }
  } catch(error) {
    try{await loadFaces();}catch{/* Keep the remaining selection if the connection is unavailable. */}
    throw new Error('Confirmed '+saved+' of '+faces.length+' before the request failed. '+error.message+'. Refresh before retrying the remaining selection.');
  }
  await loadFaces();status('Confirmed '+saved+' selected faces'+(person?' as '+person:', each with its displayed suggested name')+'.');
}
$('bulk-assign').onclick=()=>run(async()=>{
  const person=$('bulk-person').value.trim();if(!person)throw new Error('Enter a name first.');
  await saveSelectedFaces(person);
});
$('bulk-confirm-suggestions').onclick=()=>run(()=>saveSelectedFaces());
$('face-select-threshold').onclick=()=>run(async()=>{
  const raw=$('minimum-similarity').value.trim();const score=Number(raw);
  if(!raw||!Number.isFinite(score)||score<0||score>100)throw new Error('Enter a similarity score between 0 and 100.');
  const data=await api(query('/api/faces/selection',{threshold:score/100,person:state.faceStatus==='suggested'?state.person:'',scope:state.faceScope||''}));
  state.faceSelection=new Map(data.faces.map(face=>[face.id,face]));faceSelection();
  status('Selected '+data.total+' suggestions with similarity '+score+' or above across all pages. Review the name counts, then click Confirm suggested matches to save.');
});
$('face-back-groups').onclick=()=>run(()=>filterFaces('unreviewed'));
$('face-select-group').onclick=()=>run(async()=>{
  const data=await api(query('/api/faces/group-selection',{group:state.faceGroup,generation:state.groupGeneration}));
  state.faceSelection=new Map(data.faces.map(face=>[face.id,face]));faceSelection();
  status('Selected '+data.total+' faces from this group across all pages. Inspect the group and choose a name before assigning; nothing has been saved.');
});
$('face-clear').onclick=()=>{state.faceSelection.clear();faceSelection();};
$('people-search').oninput=renderPeople;
$('filter-priority').onclick=()=>run(()=>filterFaces('priority'));
$('filter-unreviewed').onclick=()=>run(()=>filterFaces('unreviewed'));
$('filter-ungrouped').onclick=()=>run(()=>filterFaces('ungrouped'));
$('filter-suggested').onclick=()=>run(()=>filterFaces('suggested'));
$('face-select-page').onclick=()=>{state.faceItems.forEach(selectFace);faceSelection();};
$('filter-all').onclick=()=>run(()=>filterFaces('all'));
$('face-previous').onclick=()=>run(async()=>{state.faceOffset=Math.max(0,state.faceOffset-48);await loadFaces();});
$('face-next').onclick=()=>run(async()=>{state.faceOffset+=48;await loadFaces();});
async function switchView(view){
  state.view=view;$('face-workspace').hidden=view!=='faces';$('photo-workspace').hidden=view!=='photos';
  for(const name of ['faces','photos']){$('view-'+name).classList.toggle('active',name===view);$('view-'+name).setAttribute('aria-pressed',String(name===view));}
  if(view==='faces')await loadFaces();else await loadDates();
}
async function loadAutoAccept(){
  if(!state.autoAcceptSupported)return;
  const settings=await api('/api/auto-accept');state.autoAcceptEnabled=settings.enabled;
  $('auto-accept-threshold').value=String(Math.round(settings.threshold*100));
  $('auto-accept-toggle').textContent=settings.enabled?'Pause auto-accept':'Enable auto-accept';
  $('auto-accept-save').hidden=!settings.enabled;
  $('auto-accept-status').textContent=(settings.enabled?'On':'Off')+' · '+settings.accepted+' automatically accepted faces'+(settings.last_pass?.error?' · '+settings.last_pass.error:'');
}
async function saveAutoAccept(enabled){
  const raw=$('auto-accept-threshold').value.trim();const score=Number(raw);
  if(!raw||!Number.isFinite(score)||score<55||score>100)throw new Error('Enter a minimum similarity between 55 and 100.');
  await api('/api/auto-accept',{enabled,threshold:score/100});await loadAutoAccept();
  status(enabled?'Automatic acceptance is enabled. Qualifying suggestions will be processed in the background.':'Automatic acceptance is paused. Existing names are retained.');
}
$('auto-accept-toggle').onclick=()=>run(()=>saveAutoAccept(!state.autoAcceptEnabled));
$('auto-accept-save').onclick=()=>run(()=>saveAutoAccept(true));
$('view-faces').onclick=()=>run(()=>switchView('faces'));$('view-photos').onclick=()=>run(()=>switchView('photos'));
$('refresh').onclick=()=>run(async()=>{state.faceSelection.clear();await switchView(state.view);await loadAutoAccept();status('Library refreshed. Confirmed edits are visible immediately.');});
$('export').onclick=()=>run(async()=>{await api('/api/export',{});status('A complete analytical snapshot is now available.');});
run(async()=>{
  const config=await api('/api/config');state.csrf=config.csrf;state.frigate=config.frigate;state.contextSuggestions=config.search_index;$('photo-search-form').hidden=!config.search_index;
  state.autoAcceptSupported=Boolean(config.auto_accept);$('auto-accept-settings').hidden=!state.autoAcceptSupported;await loadAutoAccept();
  if(config.background_only){$('extract').hidden=true;$('detect').hidden=true;$('export').textContent='Refresh analytics';}
  const health=await api('/api/status');if(health.captured_at)$('freshness').textContent='DuckDB browsing snapshot · your edits update immediately · '+new Date(health.captured_at*1000).toLocaleTimeString();
  $('filter-priority').hidden=!config.priority_review;
  if(config.search_index)for(const pet of config.priority_pet_searches||[]){
    $('priority-pets').append(button('Find '+pet+' photos',async()=>{
      state.search=pet;$('photo-search').value=pet;state.offset=0;state.selected.clear();clearForm();
      await switchView('photos');
    },'collection'));
  }
  if(config.priority_review)await filterFaces('priority');else await loadFaces();
  status(config.priority_review?'Priority matches shows suggestions for the people you selected.':'Use Suggested matches to confirm similar faces together.');
});
