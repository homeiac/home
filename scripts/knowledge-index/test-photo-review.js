// Exercise the actual UI handlers using synthetic records and a small DOM stand-in.
// Run: node --test scripts/knowledge-index/test-photo-review.js
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');

function harness(){
  const nodes=new Map();
  class Element {
    constructor(tag='div'){this.tag=tag;this.children=[];this.dataset={};this.value='';this.classList={toggle(){}};}
    append(...children){this.children.push(...children);}
    replaceChildren(...children){this.children=children;}
    setAttribute(){}
    querySelector(tag){return this.children.find(child=>child.tag===tag)||this.children.map(child=>child.querySelector?.(tag)).find(Boolean);}
  }
  const html=fs.readFileSync(path.join(__dirname,'photo_enrichment/static/index.html'),'utf8');
  for(const match of html.matchAll(/id="([^"]+)"/g)){
    assert(!nodes.has(match[1]),'Duplicate HTML id: '+match[1]);nodes.set(match[1],new Element());
  }
  const document={getElementById:id=>{assert(nodes.has(id),'Unknown element '+id);return nodes.get(id);},
    createElement:tag=>new Element(tag),querySelectorAll:selector=>selector==='.face-tile'?nodes.get('face-grid').children.filter(node=>node.dataset.id):[]};
  const posts=[];
  const offered=[];
  let automatic={enabled:false,threshold:.9,accepted:0};
  const rows=[{id:'a',revision:'r1',person:null,suggestion:{person:'Synthetic G',score:.8},path:'a.jpg',confidence:.9},
    {id:'b',revision:'r2',person:null,suggestion:{person:'Synthetic Asha',score:.8},path:'b.jpg',confidence:.9},
    {id:'c',revision:'r3',person:null,suggestion:null,path:'c.jpg',confidence:.9}];
  const context=vm.createContext({document,URLSearchParams,AbortSignal,setTimeout,clearTimeout,fetch:async(url,options)=>{
    let result={};
    if(options?.body){
      const body=JSON.parse(options.body);posts.push(body);
      if(url==='/api/auto-accept'){automatic={...automatic,...body};result=automatic;}else result={saved:true};
    }
    else if(url==='/api/config')result={csrf:'synthetic',auto_accept:true};
    else if(url==='/api/auto-accept')result=automatic;
    else if(url.startsWith('/api/faces/selection?')){
      const params=new URLSearchParams(url.split('?')[1]);
      const faces=offered.filter(face=>face.score>=Number(params.get('threshold'))&&(!params.get('person')||face.person===params.get('person')));
      result={faces:faces.map(({score,...face})=>face),total:faces.length};
    }
    else if(url.startsWith('/api/faces?')){
      const params=new URLSearchParams(url.split('?')[1]);
      const faces=rows.filter(face=>!params.get('person')||face.suggestion?.person===params.get('person'));
      result={faces,total:faces.length,people:[],counts:{total:3,unreviewed:3,suggested:2},suggested_people:[]};
    }
    return {ok:true,json:async()=>result};
  }});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'photo_enrichment/static/app.js'),'utf8'),context);
  return {nodes,posts,rows,offered,context,run:code=>vm.runInContext(code,context)};
}
async function ready(h){await new Promise(resolve=>setImmediate(resolve));assert.equal(h.run('state.busy'),false);}

test('mixed selections survive collections and submit their displayed names',async()=>{
  const h=harness();await ready(h);
  await h.run("filterFaces('suggested','Synthetic G')");
  h.nodes.get('face-select-page').onclick();
  await h.run("filterFaces('suggested','Synthetic Asha')");
  h.nodes.get('face-select-page').onclick();
  assert.equal(h.nodes.get('face-selected').textContent,2);
  assert.equal(h.nodes.get('bulk-confirm-suggestions').disabled,false);
  assert.match(h.nodes.get('face-selection-summary').textContent,/Synthetic G.*Synthetic Asha/);
  // Background refresh must not silently change what the user selected.
  h.rows[0].suggestion.person='Changed suggestion';
  await h.nodes.get('bulk-confirm-suggestions').onclick();
  assert.deepEqual(h.posts,[{faces:[{id:'a',revision:'r1',person:'Synthetic G'},{id:'b',revision:'r2',person:'Synthetic Asha'}]}]);
  assert.equal(h.run('state.faceSelection.size'),0);
  assert.equal(h.nodes.get('bulk-confirm-suggestions').disabled,true);
});

test('unknown faces cannot be bulk-confirmed as suggestions',async()=>{
  const h=harness();await ready(h);
  h.run('state.faceItems.forEach(selectFace);faceSelection()');
  assert.equal(h.nodes.get('bulk-confirm-suggestions').disabled,true);
  await h.nodes.get('bulk-confirm-suggestions').onclick();
  assert.equal(h.posts.length,0);
  assert.equal(h.run('state.faceSelection.size'),3);
});

test('a failed save retains the selection for correction or refresh',async()=>{
  const h=harness();await ready(h);
  h.run('selectFace(state.faceItems[0]);faceSelection()');
  h.context.fetch=async()=>({ok:false,json:async()=>({error:'Edited elsewhere; refresh before saving'})});
  await h.nodes.get('bulk-confirm-suggestions').onclick();
  assert.equal(h.run('state.faceSelection.size'),1);
  assert.match(h.nodes.get('status').textContent,/Edited elsewhere/);
});

test('threshold selection spans all pages and confirms hundreds with their own names',async()=>{
  const h=harness();await ready(h);
  for(let i=0;i<251;i++)h.offered.push({id:'bulk-'+i,revision:'r'+i,person:i%2?'Synthetic G':'Synthetic Asha',score:i===250?.89:.9});
  h.nodes.get('minimum-similarity').value='90';
  await h.nodes.get('face-select-threshold').onclick();
  assert.equal(h.run('state.faceSelection.size'),250);
  assert.equal(h.posts.length,0,'Selecting never saves labels');
  await h.nodes.get('bulk-confirm-suggestions').onclick();
  assert.deepEqual(h.posts.map(body=>body.faces.length),[100,100,50]);
  assert.equal(h.posts.flatMap(body=>body.faces).filter(face=>face.person==='Synthetic G').length,125);
  assert.equal(h.run('state.faceSelection.size'),0);
  assert.match(h.nodes.get('status').textContent,/Confirmed 250 selected faces/);
});

test('a later batch conflict preserves pending faces and reports partial progress',async()=>{
  const h=harness();await ready(h);
  for(let i=0;i<250;i++)h.offered.push({id:'bulk-'+i,revision:'r'+i,person:'Synthetic G',score:.95});
  h.nodes.get('minimum-similarity').value='90';
  await h.nodes.get('face-select-threshold').onclick();
  const original=h.context.fetch;let writes=0;
  h.context.fetch=async(url,options)=>options?.body&&++writes===2?
    {ok:false,json:async()=>({error:'Edited elsewhere'})}:original(url,options);
  await h.nodes.get('bulk-confirm-suggestions').onclick();
  assert.equal(h.posts.length,1);
  assert.equal(h.run('state.faceSelection.size'),150);
  assert.match(h.nodes.get('status').textContent,/Confirmed 100 of 250 before the request failed/);
});

test('automatic acceptance starts off, saves a chosen rule and can be paused',async()=>{
  const h=harness();await ready(h);
  assert.equal(h.posts.length,0,'Loading the page must not enable the rule');
  assert.equal(h.nodes.get('auto-accept-toggle').textContent,'Enable auto-accept');
  h.nodes.get('auto-accept-threshold').value='95';
  await h.nodes.get('auto-accept-toggle').onclick();
  assert.deepEqual(h.posts,[{enabled:true,threshold:.95}]);
  assert.equal(h.nodes.get('auto-accept-toggle').textContent,'Pause auto-accept');
  await h.nodes.get('auto-accept-toggle').onclick();
  assert.deepEqual(h.posts[1],{enabled:false,threshold:.95});
  assert.equal(h.nodes.get('auto-accept-toggle').textContent,'Enable auto-accept');
});
