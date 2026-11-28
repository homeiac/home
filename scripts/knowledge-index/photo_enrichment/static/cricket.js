'use strict';
const $ = id => document.getElementById(id);
const state = {csrf:'', albums:[], people:[], assets:[], events:[], editing:null, busy:false};
const initial = new URLSearchParams(location.search);state.focus=initial.get('event');state.visibleLimit=60;
const labels = {four:'Four',six:'Six',boundary_unclear:'Boundary unclear',dismissal:'Dismissal',run_out:'Run-out',other:'Other',unknown:'Result unclear'};
const node = (tag,text) => {const el=document.createElement(tag);if(text!==undefined)el.textContent=text;return el;};
const option = (value,text) => {const el=node('option',text);el.value=value;return el;};
const name = id => state.people.find(p=>p.id===id)?.name || 'Person unclear';
const album = () => state.albums.find(a=>a.id===$('album').value);
const media = asset => '/api/cricket/media?'+new URLSearchParams({album:$('album').value,asset});
const seconds = value => Number(value).toFixed(1)+'s';
async function api(route,body){
  const response=await fetch('/api/cricket/'+route,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Photo-Token':state.csrf},body:JSON.stringify(body)});
  const data=await response.json();if(!response.ok)throw Error(data.error||'Could not save');return data;
}
function notify(message,error=false){$('status').textContent=message;$('status').classList.toggle('error',error);}
function action(text,fn){const el=node('button',text);el.type='button';el.onclick=async()=>{el.disabled=true;try{await fn();}catch(error){notify(error.message,true);}finally{el.disabled=false;}};return el;}
function reviewDetails(event,asset){
  const d=event.data,photo=asset?.kind==='photo',box=node('section');box.className='review-details';
  box.setAttribute('aria-label','Details to confirm');
  box.append(node('h3',event.review_state==='confirmed'?'Details you confirmed':'Check these details'));
  const list=node('dl');
  const field=(label,value)=>{const row=node('div');row.append(node('dt',label),node('dd',value));list.append(row);};
  let player=d.actor?name(d.actor):'Unknown — choose a player if you recognize them';
  if(event.review_state==='suggested'&&event.evidence.identity_basis==='user_album_rule')player+=' — assumed for batting; check this is the batter you want';
  field('Player',player);
  field('Activity',({batting:'Batting',bowling:'Bowling',other:'Other activity',unknown:'Unknown — check what the player is doing'})[d.role]);
  if(!photo){
    field('Result',d.outcome==='unknown'?'Unknown — no four, six or dismissal selected':d.outcome==='dismissal'?(d.role==='batting'?'This batter got out':'A batter got out during this delivery'):d.outcome==='boundary_unclear'?'Boundary — four or six is still unclear':d.outcome==='other'?'No highlight / other result':labels[d.outcome]);
    if(d.role==='bowling'&&['dismissal','run_out'].includes(d.outcome))field('Wicket credit',d.wicket_credit==='bowler'?'Credited to this bowler':d.wicket_credit==='run_out'?'Run-out; not credited to the bowler':'Unknown — bowler credit has not been established');
    field('Clip',seconds(d.start)+' – '+seconds(d.end)+' in the original');
  }
  box.append(list);
  box.append(node('p',photo?'Confirm the player and activity only. A photo does not establish a four, six or wicket.':'Check that the clip includes the delivery and its outcome. Edit the start/end if it cuts off the action.'));
  if(!photo&&d.outcome==='unknown')box.append(node('p','If you can tell what happened, use Edit details to choose Four, Six, Dismissal or another result. Otherwise, Unknown can stay.'));
  box.append(node('p',event.review_state==='confirmed'?'You can still edit these details.':'Confirmation keeps every detail shown, including anything marked Unknown, until you edit it.'));
  return box;
}
function matches(event){
  const filter=$('filter').value,d=event.data;
  if(event.dismissed&&!$('show-dismissed').checked)return false;
  if(state.focus&&event.id!==state.focus)return false;
  const words=[name(d.actor),d.role,labels[d.outcome],event.evidence.reason||'',event.review_state,d.role==='bowling'&&['dismissal','run_out'].includes(d.outcome)?'wicket':''].join(' ').toLowerCase();
  if(!$('search').value.toLowerCase().split(/\s+/).every(word=>words.includes(word)))return false;
  if(filter==='all')return true;
  if(album()?.default_batter && d.actor!==album().default_batter && !(d.actor===null&&d.role==='bowling'&&['bowling','bowling_wicket'].includes(filter)))return false;
  if(filter==='batting'||filter==='bowling')return d.role===filter;
  if(filter==='batting_out')return d.role==='batting'&&['dismissal','run_out'].includes(d.outcome);
  if(filter==='bowling_wicket')return d.role==='bowling'&&['dismissal','run_out'].includes(d.outcome);
  return d.role==='batting'&&d.outcome===filter;
}
async function change(event,operation){
  const updated=await api('revise',{id:event.id,revision:event.revision,...operation});
  state.events=state.events.map(e=>e.id===updated.id?updated:e);render();
  notify(operation.action==='accept'?'Shown details confirmed. Any unknown details remain unknown.':operation.action==='dismiss'?'Moment hidden. The original is unchanged.':'Saved.');
  $('status').append(' ',action('Undo',async()=>change(updated,{action:'undo'})));
}
function render(){
  const visible=state.events.filter(matches);$('cards').replaceChildren();
  for(const event of visible.slice(0,state.visibleLimit)){
    const card=node('article');card.className='card';card.dataset.event=event.id;
    const asset=state.assets.find(a=>a.id===event.asset),d=event.data;
    const preview=node(asset?.kind==='photo'?'img':'video');
    if(asset?.kind==='photo'){preview.src=media(event.asset)+'&preview=true';preview.alt='Cricket activity';preview.loading='lazy';}
    else{
      preview.controls=true;preview.preload='none';preview.src=media(event.asset)+'#t='+d.start+','+d.end;
      if(asset?.preview)preview.poster=media(event.asset)+'&preview=true';
      preview.addEventListener('loadedmetadata',()=>{preview.currentTime=d.start;});
      preview.addEventListener('play',()=>{if(preview.currentTime<d.start||preview.currentTime>=d.end)preview.currentTime=d.start;});
      preview.addEventListener('timeupdate',()=>{if(preview.currentTime>=d.end)preview.pause();});
    }
    const title=node('h2',name(d.actor)+' · '+(d.role==='unknown'?'Activity unclear':d.role)+' · '+labels[d.outcome]);
    const badge=node('span',event.dismissed?'Dismissed':event.review_state==='suggested'?'Suggested':event.review_state==='confirmed'?'Confirmed':'Corrected');badge.className='badge';
    const details=node('p',asset?.kind==='video'?seconds(d.start)+' – '+seconds(d.end):'Photo');details.className='details';
    const reason=node('details');reason.className='details';reason.append(node('summary','Why this was suggested'),node('p',event.evidence.reason||event.evidence.confidence||'Best-effort suggestion. Check the details against the original.'));
    const controls=node('div');controls.className='actions';
    if(!event.dismissed&&event.review_state!=='confirmed')controls.append(action('Confirm shown details',()=>change(event,{action:'accept'})));
    controls.append(action('Edit details',()=>edit(event)),action(event.dismissed?'Restore':'Hide this moment',()=>change(event,{action:event.dismissed?'restore':'dismiss'})));
    const original=node('a',asset?.kind==='video'?'Play full video':'View original');original.href=media(event.asset);original.target='_blank';original.rel='noopener';controls.append(original);
    const link=node('a','Link to moment');link.href='/cricket?'+new URLSearchParams({album:event.album,event:event.id});controls.append(link);
    if(asset?.kind==='video')controls.append(action('Export clip',async()=>{notify('Preparing this clip…');const result=await api('export',{id:event.id,revision:event.revision});const download=node('a','Download clip');download.href=result.url;download.download='cricket-highlight.mp4';controls.append(download);notify('Clip ready to download.');}));
    card.append(preview,title,badge,details,reviewDetails(event,asset),controls,reason);$('cards').append(card);
  }
  if(!visible.length)$('cards').append(node('p','No moments in this view yet. Try another filter or add one below.'));
  $('more').hidden=visible.length<=state.visibleLimit;
  notify(Math.min(visible.length,state.visibleLimit)+' of '+visible.length+' moments · suggestions are included');
}
async function progress(){if(!album())return;const result=await api('status?'+new URLSearchParams({album:album().id}));const count=(kind,done)=>result.jobs.filter(r=>r.kind===kind&&(!done||r.state==='complete')).reduce((n,r)=>n+r.assets,0);$('progress').textContent=count('video',true)+' / '+count('video',false)+' videos analyzed · '+count('photo',true)+' / '+count('photo',false)+' photos analyzed';}
async function load(){
  if(!album()){notify('No cricket album has been imported yet.');return;}
  const q=new URLSearchParams({album:$('album').value,dismissed:'true'});
  const [events,assets]=await Promise.all([api('events?'+q),api('assets?'+q)]);
  state.events=events.events;state.assets=assets.assets;
  $('original').replaceChildren(...state.assets.map((a,i)=>option(a.id,(a.name||(a.kind==='video'?'Video ':'Photo ')+(i+1))+(a.duration?' · '+Math.round(a.duration)+' seconds':''))));
  $('add').disabled=!state.assets.length;render();
  await progress();
}
function edit(event){
  const asset=state.assets.find(a=>a.id===event.asset);if(!asset)throw Error('Original is no longer in this album');
  state.editing=structuredClone(event);const d=event.data,video=asset.kind==='video';
  $('person').replaceChildren(option('','Person unclear'),...state.people.map(p=>option(p.id,p.name)));
  if(d.actor&&!state.people.some(p=>p.id===d.actor))$('person').append(option(d.actor,'Unresolved person'));
  $('person').value=d.actor||'';$('role').value=d.role;$('outcome').value=d.outcome;$('credit').value=d.wicket_credit;
  $('start').value=d.start??0;$('end').value=d.end??0;$('start').max=asset.duration;$('end').max=asset.duration;
  $('timing').hidden=!video;$('start').required=video;$('end').required=video;$('outcome').disabled=!video;$('credit').disabled=!video;
  $('edit-video').hidden=!video;$('edit-image').hidden=video;
  if(video){$('edit-video').src=media(event.asset);$('edit-video').onloadedmetadata=()=>{$('edit-video').currentTime=d.start||0;};}
  else $('edit-image').src=media(event.asset)+'&preview=true';
  $('edit-title').textContent=event.id?'Correct highlight':'Add highlight';$('save').textContent=event.id?'Save correction':'Add highlight';$('save-status').textContent='';$('editor').showModal();
  $('edit-help').textContent=video?'Choose who is batting or bowling and what happened. Leave uncertain fields as Unclear. Set the clip to include about 10 seconds before the run-up when available, through the outcome and reactions.':'Check the player and activity in this photo. Result and clip timing do not apply to photos.';
}
function closeEditor(){$('edit-video').pause();$('editor').close();}
$('cancel').onclick=closeEditor;$('editor').addEventListener('close',()=>$('edit-video').pause());
$('start-now').onclick=()=>{$('start').value=$('edit-video').currentTime.toFixed(1);};
$('end-now').onclick=()=>{$('end').value=$('edit-video').currentTime.toFixed(1);};
$('outcome').onchange=()=>{if($('outcome').value==='run_out')$('credit').value='run_out';else if($('outcome').value!=='dismissal')$('credit').value='unknown';};
$('role').onchange=()=>{if($('role').value!=='bowling'&&$('credit').value==='bowler')$('credit').value='unknown';};
$('edit-form').onsubmit=async event=>{
  event.preventDefault();if(state.busy)return;state.busy=true;$('save').disabled=true;
  try{
    const current=state.editing,asset=state.assets.find(a=>a.id===current.asset),video=asset.kind==='video';
    const data={...current.data,actor:$('person').value||null,role:$('role').value,outcome:video?$('outcome').value:'unknown',wicket_credit:video?$('credit').value:'unknown',start:video?Number($('start').value):null,end:video?Number($('end').value):null};
    const patch=Object.fromEntries(Object.entries(data).filter(([key,value])=>value!==current.data[key]));
    if(current.id){if(!Object.keys(patch).length){closeEditor();return;}await change(current,{patch});}
    else{const saved=await api('create',{album:$('album').value,asset:current.asset,data});state.events.push(saved);render();notify('Highlight added.');}
    closeEditor();
  }catch(error){$('save-status').textContent='Not saved: '+error.message;$('save-status').className='error';}
  finally{state.busy=false;$('save').disabled=false;}
};
$('add').onclick=()=>{const asset=state.assets.find(a=>a.id===$('original').value);if(!asset)return;edit({asset:asset.id,data:{actor:album()?.default_batter||null,role:'batting',outcome:'unknown',wicket_credit:'unknown',start:asset.kind==='video'?0:null,end:asset.kind==='video'?Math.min(30,asset.duration):null,delivery_start:null,outcome_end:null}});};
function filterChanged(){state.focus=null;state.visibleLimit=60;const query=new URLSearchParams({album:$('album').value,filter:$('filter').value});if($('search').value)query.set('q',$('search').value);history.replaceState(null,'','/cricket?'+query);render();}
$('filter').onchange=filterChanged;$('search').oninput=filterChanged;$('show-dismissed').onchange=render;
$('more').onclick=()=>{state.visibleLimit+=60;render();};
$('album').onchange=()=>load().catch(e=>notify(e.message,true));$('refresh').onclick=()=>load().catch(e=>notify(e.message,true));
(async()=>{const response=await fetch('/api/config');const config=await response.json();state.csrf=config.csrf;
  const [albums,people]=await Promise.all([api('albums'),api('people')]);state.albums=albums.albums;state.people=people.people;
  $('album').replaceChildren(...state.albums.map((a,i)=>option(a.id,name(a.default_batter)+' · Cricket'+(state.albums.length>1?' '+(i+1):''))));
  if(state.albums.some(a=>a.id===initial.get('album')))$('album').value=initial.get('album');
  if([...$('filter').options].some(o=>o.value===initial.get('filter')))$('filter').value=initial.get('filter');
  $('search').value=(initial.get('q')||'').slice(0,200);
  await load();
  setInterval(()=>progress().catch(()=>{}),15000);
})().catch(error=>notify(error.message,true));
