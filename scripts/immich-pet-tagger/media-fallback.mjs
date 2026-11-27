// Separate bounded decoder: inference processes retain their production capacity.
import http from 'node:http';
import fs from 'node:fs/promises';
import crypto from 'node:crypto';
import {recover,error} from './media-fallback-core.mjs';
const base=process.env.IMMICH_URL??'http://immich-server.immich-pilot.svc.cluster.local:2283';
const directory=process.env.MEDIA_CACHE??'/data/frames-v1';await fs.mkdir(directory,{recursive:true});
const token=process.env.WORKER_TOKEN,key=process.env.IMMICH_API_KEY;
if(!token||!key)throw Error('Missing credentials');
let active=0,success=0,failed=0;const waiting=[];const inflight=new Map();
async function acquire(){if(active>=2){if(waiting.length>=24)throw error('decoder_busy',429);await new Promise(resolve=>waiting.push(resolve));}else active++;}
function release(){const next=waiting.shift();if(next)next();else active--;}
function allowed(value){return typeof value==='string'&&value.length===token.length&&crypto.timingSafeEqual(Buffer.from(value),Buffer.from(token));}
async function get(id){
  const cache=directory+'/'+id+'.jpg';try{return {bytes:await fs.readFile(cache),source:'cached_fallback'};}catch(e){if(e.code!=='ENOENT')throw e;}
  if(inflight.has(id))return inflight.get(id);
  const promise=(async()=>{await acquire();try{
    const result=await recover({base,key,id,directory});
    const tmp=cache+'.tmp';await fs.writeFile(tmp,result.bytes);await fs.rename(tmp,cache);
    await fs.writeFile(cache+'.json',JSON.stringify({source:result.source,sha256:result.sha256,created_at:new Date().toISOString()}));success++;return result;
  }finally{release();}})().finally(()=>inflight.delete(id));inflight.set(id,promise);return promise;
}
http.createServer(async(req,res)=>{
  if(req.url==='/healthz'){res.end('ok');return;}
  if(!allowed(req.headers.authorization?.replace(/^Bearer /,''))){res.writeHead(401);res.end();return;}
  const match=/^\/assets\/([0-9a-f-]{36})$/.exec(req.url);
  if(req.method!=='GET'||!match){res.writeHead(404);res.end();return;}
  try{const result=await get(match[1]);res.writeHead(200,{'Content-Type':'image/jpeg','X-Waffles-Media-Source':result.source});res.end(result.bytes);}
  catch(e){failed++;res.writeHead(Number.isInteger(e.status)?e.status:502);res.end('fallback unavailable');console.log(JSON.stringify({event:'fallback_error',reason:/^[a-z0-9_]+$/.test(e.message)?e.message:'internal_error',active,queued:waiting.length}));}
}).listen(9201);
setInterval(()=>console.log(JSON.stringify({event:'progress',success,failed,active,queued:waiting.length})),15000).unref();
console.log(JSON.stringify({event:'start',concurrency:2,maximum_queue:24,maximum_source_bytes:134217728}));
