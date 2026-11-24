// Read-only search diagnostics. Credentials remain inside the existing sync pod.
import fs from 'node:fs/promises';
const key=(await fs.readFile('/credentials/api-key','utf8')).trim();
for(const [mode,query] of [['description','hike'],['description','hiking'],['context','hike']]){
 const route=mode==='context'?'/search/smart':'/search/metadata';
 const body=mode==='context'?{query,size:5}:{description:query,size:5};
 const start=Date.now();
 const response=await fetch('http://immich-server:2283/api'+route,{method:'POST',headers:{'x-api-key':key,'Content-Type':'application/json'},body:JSON.stringify(body),signal:AbortSignal.timeout(90000)});
 const result=await response.json();
 console.log(JSON.stringify({mode,query,status:response.status,returned:result.assets?.items?.length,total:result.assets?.total,seconds:(Date.now()-start)/1000,error:response.ok?undefined:result.message}));
}
