// Test the actual dashboard and event-note handlers with synthetic records.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
function harness(page='index',overrides={}){
  const nodes=new Map(),requests=[];
  class Element{
    constructor(tag='div'){this.tag=tag;this.children=[];this.dataset={};this.value='';this.classList={toggle(){}};}
    append(...children){this.children.push(...children);}
    replaceChildren(...children){this.children=children;}
    setAttribute(){}
    reset(){}
    showModal(){this.open=true;}
    close(){this.open=false;}
  }
  const root=path.join(__dirname,'photo_enrichment/static');
  const html=fs.readFileSync(path.join(root,page+'.html'),'utf8');
  for(const match of html.matchAll(/id="([^"]+)"/g)){
    assert(!nodes.has(match[1]));nodes.set(match[1],new Element());
  }
  const data={
    '/api/status':{captured_at:Date.now()/1000},
    '/api/config':{csrf:'synthetic',cricket:true,search_index:true},
    '/api/groups':[{id:'story',event:'Picnic',photos:3}],
    '/api/cricket/albums':{albums:[{id:'synthetic-album'}]},
    '/api/dates':[],
    '/api/group-suggestions':{event:'Suggested occasion',location:'Suggested place',tags:['picnic'],photos:1,inferred:true},
    '/api/groups/save':{id:'saved',photos:2},
    ...overrides
  };
  const context=vm.createContext({
    document:{getElementById:id=>{assert(nodes.has(id),'Unknown element '+id);return nodes.get(id);},createElement:tag=>new Element(tag),querySelectorAll:()=>[]},
    URLSearchParams,AbortSignal,setTimeout,clearTimeout,
    fetch:async(url,options)=>{
      requests.push({url,options});const key=url.split('?')[0];assert(key in data,'Unexpected request '+url);
      const result=data[key];if(result instanceof Error)throw result;
      return {ok:true,json:async()=>result};
    }
  });
  vm.runInContext(fs.readFileSync(path.join(root,page==='index'?'app.js':'context.js'),'utf8'),context);
  return {nodes,requests,context,data,run:code=>vm.runInContext(code,context)};
}
const ready=()=>new Promise(resolve=>setImmediate(resolve));
test('dashboard starts with live overview and never requests faces or writes',async()=>{
  const h=harness();await ready();
  assert.equal(h.nodes.get('index-status').textContent,'Up to date');
  assert.equal(h.nodes.get('group-count').textContent,'1');
  assert.equal(h.nodes.get('cricket-count').textContent,'1');
  assert(h.requests.every(r=>!r.options.body&&!r.url.includes('faces')));
});
test('a failed card does not hide other cards or prevent retry',async()=>{
  const h=harness('index',{'/api/groups':new Error('offline')});await ready();
  assert.equal(h.nodes.get('group-count').textContent,'Unavailable');
  assert.equal(h.nodes.get('cricket-count').textContent,'1');
  assert.equal(h.nodes.get('refresh').disabled,false);
  h.data['/api/groups']=[];await h.nodes.get('refresh').onclick();
  assert.equal(h.nodes.get('group-count').textContent,'0');
});
test('missing timestamps and disabled cricket are not presented as healthy',async()=>{
  const h=harness('index',{'/api/status':{},'/api/config':{cricket:false}});await ready();
  assert.equal(h.nodes.get('index-status').textContent,'Not published yet');
  assert.equal(h.nodes.get('cricket-app').hidden,true);
  assert(!h.requests.some(r=>r.url==='/api/cricket/albums'));
});
test('an old snapshot is marked overdue',async()=>{
  const h=harness('index',{'/api/status':{captured_at:Date.now()/1000-3600}});await ready();
  assert.equal(h.nodes.get('index-status').textContent,'Update overdue');
});
test('event notes load without face review and keep manual context over suggestions',async()=>{
  const h=harness('context');await ready();
  h.run("state.selected.add('a.jpg');scheduleGroupSuggestions()");
  await new Promise(resolve=>setTimeout(resolve,350));
  assert.equal(h.nodes.get('location').value,'Suggested place');
  h.nodes.get('location').value='My venue';
  h.run("state.selected.add('b.jpg');scheduleGroupSuggestions()");
  await new Promise(resolve=>setTimeout(resolve,350));
  assert.equal(h.nodes.get('location').value,'My venue');
  assert(h.requests.every(r=>!r.url.includes('faces')&&!r.url.includes('auto-accept')));
});
test('saving event notes retains the explicit cross-page photo selection',async()=>{
  const h=harness('context');await ready();
  h.run("state.selected=new Set(['a.jpg','b.jpg'])");
  h.nodes.get('event').value='Family picnic';h.nodes.get('notes').value='The story we remember';
  h.nodes.get('group-form').onsubmit({preventDefault(){}});await ready();
  const saved=h.requests.find(r=>r.url==='/api/groups/save');
  const body=JSON.parse(saved.options.body);
  assert.deepEqual(body.paths,['a.jpg','b.jpg']);assert.equal(body.notes,'The story we remember');
  assert.equal(saved.options.headers['X-Photo-Token'],'synthetic');
});
