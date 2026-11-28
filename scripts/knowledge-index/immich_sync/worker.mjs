// Incremental, API-only Immich writes; reconciliation state belongs to its own PG schema.
import fs from 'node:fs/promises';
import {createReadStream} from 'node:fs';
import crypto from 'node:crypto';
import http from 'node:http';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {META_KEY,ROOT,stable,digest,sourcePacket,retainRecoveryCaption,eligible,scope,mapAsset,metadataDecision,faceCandidate,normalizedBox,overlap} from './core.mjs';
const require=createRequire('/usr/src/app/server/package.json');
const {Pool}=require('pg');
const sharp=require('sharp');
const pool=new Pool({max:2,connectionTimeoutMillis:10000,idleTimeoutMillis:30000});
const BASE=process.env.IMMICH_URL??'http://immich-server:2283/api';
const DISCOVERY_VERSION=1; // Bump whenever mapping rules change.
const MODE=process.env.SYNC_MODE??'dry-run';
const MAX_PRESERVED=Number(process.env.SYNC_MAX_PRESERVED??0);
const BATCH=Number(process.env.SYNC_BATCH_SIZE??50);
let counters={source:0,available_summaries:0,last_discovery:0,last_success:0,api_ready:0,cycle_seconds:0};
let gauges='',active=false,phase='idle';
const stageSeconds={};
async function measured(stage, fn) {
 phase=stage;const start=Date.now();log('sync.stage_start',{stage});
 try{return await fn();}finally{stageSeconds[stage]=(Date.now()-start)/1000;log('sync.stage_end',{stage,seconds:stageSeconds[stage]});}
}
const log=(event,fields={})=>console.log(JSON.stringify({time:new Date().toISOString(),event,...fields}));
async function api(route,method='GET',body) {
  const key=(await fs.readFile('/credentials/api-key','utf8')).trim();
  const response=await fetch(BASE+route,{method,headers:{'x-api-key':key,'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(45000)});
  if(!response.ok){const e=Error('Immich HTTP '+response.status);e.status=response.status;throw e;}
  const text=await response.text();return text?JSON.parse(text):null;
}
async function state(db,key,value) {
  if(value===undefined)return (await db.query('SELECT value FROM immich_sync.state WHERE key=$1',[key])).rows[0]?.value;
  await db.query('INSERT INTO immich_sync.state(key,value) VALUES($1,$2) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=now()',[key,value]);
}
async function inventory(libraryId) {
  const byPath=new Map();let cursor, page=1, pages=0;
  const seen=new Set();
  do {
    const result=await api('/search/metadata','POST',cursor?{libraryId,withExif:true,size:1000,cursor}:{libraryId,withExif:true,size:1000,page});
    pages++;
    if(pages>1000)throw Error('Inventory pagination overflow');
    if(pages%10===0)log('sync.inventory_progress',{pages,assets:byPath.size});
    for(const item of result.assets.items){
      if(seen.has(item.id))throw Error('Inventory pagination repeated asset');
      seen.add(item.id);
      const a={id:item.id,ownerId:item.ownerId,libraryId:item.libraryId,isExternal:item.isExternal,isOffline:item.isOffline,isTrashed:item.isTrashed,originalPath:item.originalPath,checksum:item.checksum,exifInfo:{fileSizeInByte:item.exifInfo?.fileSizeInByte}};
      if(!byPath.has(a.originalPath))byPath.set(a.originalPath,[]);
      byPath.get(a.originalPath).push(a);
    }
    cursor=result.assets.nextCursor;
    if(!cursor && !result.assets.nextPage)break;
    if(!cursor)page=Number(result.assets.nextPage);
    if(page>1000)throw Error('Inventory pagination overflow');
  } while(true);
  return byPath;
}
async function discover(db) {
  const me=await api('/users/me');
  const libraries=(await api('/libraries')).filter(x=>x.name==='Existing Google Photos' && x.ownerId===me.id);
  if(libraries.length!==1)throw Error('Library identity ambiguous');
  const libraryId=libraries[0].id;
  const configured=await state(db,'identity');
  if(configured && (configured.ownerId!==me.id || configured.libraryId!==libraryId))throw Error('Library identity changed');
  await state(db,'identity',{ownerId:me.id,libraryId});
  const targets=await measured('inventory',()=>inventory(libraryId));
  const query=await fs.readFile(new URL('./source.sql',import.meta.url),'utf8');
  await db.query('BEGIN ISOLATION LEVEL REPEATABLE READ');
  try {
    // Source tables are SELECT-only for this role. Job discovery commits with its checkpoint.
    const result=await measured('source_query',()=>db.query(query));
    phase='enqueue';
    const savedRecovery=new Map((await db.query("SELECT source_path,asset_id,payload FROM immich_sync.jobs WHERE payload ? 'recovery'")).rows.map(job=>[job.source_path,job]));
    const cycle=crypto.randomUUID();
    counters.source=result.rows.length;counters.available_summaries=result.rows.filter(x=>x.summary).length;
    for(let offset=0;offset<result.rows.length;offset+=250){
      const jobs=[];
      for(const source of result.rows.slice(offset,offset+250)){
        if(!eligible(source))continue;
        const match=mapAsset(source,targets.get(ROOT+source.path)??[],me.id,libraryId);
        const packet=retainRecoveryCaption(sourcePacket(source),match.asset,savedRecovery.get(source.path));
        jobs.push({source_path:source.path,source_hash:digest(packet),payload:packet,asset_id:match.asset?.id??null,
          state:match.asset?'pending':!scope(source)?'excluded':match.reason==='missing_asset'?'missing':'conflict',reason:match.reason??null,cycle_id:cycle});
      }
      if(jobs.length)await db.query(`INSERT INTO immich_sync.jobs(source_path,source_hash,payload,asset_id,state,reason,cycle_id)
        SELECT source_path,source_hash,payload,asset_id,state,reason,cycle_id FROM jsonb_to_recordset($1::jsonb)
        AS x(source_path text,source_hash text,payload jsonb,asset_id text,state text,reason text,cycle_id text)
        ON CONFLICT(source_path) DO UPDATE SET source_hash=excluded.source_hash,payload=excluded.payload,
        asset_id=excluded.asset_id,cycle_id=excluded.cycle_id,
        state=CASE WHEN immich_sync.jobs.asset_id IS NOT NULL AND immich_sync.jobs.asset_id IS DISTINCT FROM excluded.asset_id THEN 'conflict'
          WHEN immich_sync.jobs.source_hash<>excluded.source_hash OR immich_sync.jobs.state IN ('missing','excluded') THEN excluded.state ELSE immich_sync.jobs.state END,
        reason=CASE WHEN immich_sync.jobs.asset_id IS NOT NULL AND immich_sync.jobs.asset_id IS DISTINCT FROM excluded.asset_id THEN 'asset_identity_changed' WHEN immich_sync.jobs.state='conflict' THEN immich_sync.jobs.reason ELSE excluded.reason END,
        updated_at=CASE WHEN immich_sync.jobs.source_hash<>excluded.source_hash THEN now() ELSE immich_sync.jobs.updated_at END
        WHERE NOT (immich_sync.jobs.payload ? 'recovery') OR immich_sync.jobs.state='applied'`,[JSON.stringify(jobs)]);
    }
    await db.query("UPDATE immich_sync.jobs SET state='conflict',reason='source_removed' WHERE cycle_id<>$1 AND state<>'excluded' AND NOT (payload ? 'recovery')",[cycle]);
    await state(db,'checkpoint',{version:DISCOVERY_VERSION,cycle,sourceRows:counters.source,successfulSummaries:counters.available_summaries,capturedAt:new Date().toISOString()});
    await db.query('COMMIT');counters.last_discovery=Date.now()/1000;
    log('sync.discovery',{source:counters.source,available_summaries:counters.available_summaries});
  } catch(e){await db.query('ROLLBACK');throw e;}
}
async function checksum(file) {
  const hash=crypto.createHash('sha256');for await(const chunk of createReadStream(file))hash.update(chunk);return hash.digest('hex');
}
async function verifyFile(job) {
  const file=await fs.realpath(ROOT+job.source_path);
  if(!file.startsWith(ROOT))throw Error('File escaped library');
  const stat=await fs.stat(file);
  if(stat.size!==job.payload.sizeBytes)throw Error('Source size changed');
  const sourceTime=new Date(job.payload.sourceMtime).getTime();
  if(!Number.isFinite(sourceTime) || Math.abs(sourceTime-stat.mtimeMs)>1500)throw Error('Source timestamp changed');
  const hash=await checksum(file);
  if(job.content_sha256 && job.content_sha256!==hash)throw Error('Source content changed');
  return {contentSha256:hash,mtimeMs:stat.mtimeMs};
}
async function sourcePerson(db,name) {
  const saved=(await db.query('SELECT person_id FROM immich_sync.people WHERE source_person=$1',[name])).rows[0];
  if(saved)return saved.person_id;
  // Name equality alone does not prove an existing Immich person's identity.
  // Seed proven mappings from pilot source-face provenance before this step.
  const people=await api('/people?withHidden=true&size=1000');
  if((people.people??people).some(p=>p.name===name))return null;
  // An intent marker makes an interrupted creation reviewable instead of duplicating people.
  const marker=await state(db,'person-intent:'+name);
  if(marker)return null;
  await state(db,'person-intent:'+name,{startedAt:new Date().toISOString()});
  const person=await api('/people','POST',{name});
  await db.query('INSERT INTO immich_sync.people VALUES($1,$2,$3,now()) ON CONFLICT DO NOTHING',[name,person.id,{origin:'new_from_confirmed_source'}]);
  return person.id;
}
async function syncFaces(db,job) {
  const confirmed=job.payload.faces.filter(x=>x.label_source==='user' && x.person);
  if(!confirmed.length)return;
  const dimensions=await sharp(ROOT+job.source_path).metadata();
  const rotated=(dimensions.orientation??1)>=5;
  const width=rotated?dimensions.height:dimensions.width,height=rotated?dimensions.width:dimensions.height;
  let current=await api('/faces?id='+encodeURIComponent(job.asset_id));
  const used=new Set();
  for(const old of confirmed){
    const previous=(await db.query('SELECT * FROM immich_sync.faces WHERE source_face=$1',[old.id])).rows[0];
    const version=digest(old);let candidate=faceCandidate(old,current,used),reason=candidate.reason;
    if(candidate.face && Math.abs(candidate.face.imageWidth/candidate.face.imageHeight-width/height)>0.03)reason='orientation_mismatch';
    const personId=await sourcePerson(db,old.person);
    if(!personId)reason='person_mapping_required';
    if(previous?.state==='applied') {
      const actual=current.find(f=>f.id===previous.face_id);
      if(!actual || actual.person?.id!==previous.person_id)reason='human_face_edit';
    }
    // Never reassign a named target to a different person based on a source label.
    if(candidate.face?.person?.name && candidate.face.person.id!==personId)reason='named_target_conflict';
    if(reason){
      await db.query(`INSERT INTO immich_sync.faces(source_face,source_path,asset_id,source_hash,state,reason) VALUES($1,$2,$3,$4,'conflict',$5)
        ON CONFLICT(source_face) DO UPDATE SET state='conflict',reason=excluded.reason,updated_at=now()`,[old.id,job.source_path,job.asset_id,version,reason]);continue;
    }
    const face=candidate.face;used.add(face.id);
    if(face.person?.id!==personId){
      await db.query(`INSERT INTO immich_sync.faces(source_face,source_path,asset_id,face_id,person_id,source_hash,state) VALUES($1,$2,$3,$4,$5,$6,'pending')
        ON CONFLICT(source_face) DO UPDATE SET face_id=excluded.face_id,person_id=excluded.person_id,source_hash=excluded.source_hash,state='pending'`,[old.id,job.source_path,job.asset_id,face.id,personId,version]);
      await api('/faces/'+personId,'PUT',{id:face.id});
      const after=await api('/faces?id='+job.asset_id);
      if(after.find(f=>f.id===face.id)?.person?.id!==personId)throw Error('Face readback mismatch');
      current=after;
    }
    await db.query(`INSERT INTO immich_sync.faces(source_face,source_path,asset_id,face_id,person_id,source_hash,state) VALUES($1,$2,$3,$4,$5,$6,'applied')
      ON CONFLICT(source_face) DO UPDATE SET face_id=excluded.face_id,person_id=excluded.person_id,source_hash=excluded.source_hash,state='applied',reason=NULL,updated_at=now()`,[old.id,job.source_path,job.asset_id,face.id,personId,version]);
  }
}
async function apply(db,job) {
  const identity=await state(db,'identity');
  const current=await api('/assets/'+job.asset_id);
  const mapped=mapAsset({path:job.source_path,size_bytes:job.payload.sizeBytes},[current],identity.ownerId,identity.libraryId);
  if(!mapped.asset){
    await db.query("UPDATE immich_sync.jobs SET state='conflict',reason=$2,updated_at=now() WHERE source_path=$1",[job.source_path,mapped.reason]);
    log('sync.asset_conflict',{source_id:digest(job.source_path).slice(0,16),reason:mapped.reason});return;
  }
  const file=await verifyFile(job);
  const desired={...job.payload,sourceRevision:job.source_hash,contentSha256:file.contentSha256};
  const metadata=await api('/assets/'+job.asset_id+'/metadata');
  const existing=metadata.find(x=>x.key===META_KEY)?.value??null;
  const decision=metadataDecision(existing,desired,job.applied,job.intent);
  if(decision==='conflict'){
    await db.query("UPDATE immich_sync.jobs SET state='conflict',reason='machine_metadata_edited',updated_at=now() WHERE source_path=$1",[job.source_path]);return;
  }
  await db.query('UPDATE immich_sync.jobs SET intent=$2,content_sha256=$3,file_mtime_ms=$4 WHERE source_path=$1',[job.source_path,desired,file.contentSha256,file.mtimeMs]);
  if(decision!=='unchanged')await api('/assets/'+job.asset_id+'/metadata','PUT',{items:[{key:META_KEY,value:desired}]});
  const after=await api('/assets/'+job.asset_id+'/metadata');
  if(stable(after.find(x=>x.key===META_KEY)?.value)!==stable(desired))throw Error('Metadata readback mismatch');
  // Human-visible description/GPS/date writes deliberately gated for RO libraries.
  // Source groups, tags and every old label are preserved in the owned metadata record.
  if(process.env.ENABLE_FACE_TRANSFER==='true')await syncFaces(db,job);
  await db.query("UPDATE immich_sync.jobs SET applied=$2,intent=NULL,state='applied',reason=NULL,attempts=0,applied_at=now(),verified_at=now(),updated_at=now() WHERE source_path=$1",[job.source_path,desired]);
  counters.last_success=Date.now()/1000;
}
async function metrics(db) {
  const rows=(await db.query('SELECT state,count(*)::int n,count(*) FILTER(WHERE payload->>\'summary\' IS NOT NULL)::int summaries FROM immich_sync.jobs GROUP BY state')).rows;
  const lines=['# TYPE immich_sync_assets gauge','# TYPE immich_sync_summaries gauge'];
  for(const status of ['pending','applied','conflict','error','excluded','missing']){
    const row=rows.find(x=>x.state===status);
    lines.push(`immich_sync_assets{state="${status}"} ${row?.n??0}`,`immich_sync_summaries{state="${status}"} ${row?.summaries??0}`);
  }
  const faces=(await db.query('SELECT state,count(*)::int n FROM immich_sync.faces GROUP BY state')).rows;
  for(const status of ['pending','applied','conflict'])lines.push(`immich_sync_faces{state="${status}"} ${faces.find(x=>x.state===status)?.n??0}`);
  const preserved=(await db.query("SELECT count(*)::int n FROM immich_sync.jobs j CROSS JOIN LATERAL jsonb_array_elements(j.payload->'faces') f WHERE j.state='applied' AND f->>'label_source'='user'")).rows[0].n;
  lines.push(`immich_sync_confirmed_labels_preserved ${preserved}`);
  lines.push(`immich_sync_visible_captions_enabled 0`,`immich_sync_mode{mode="${MODE}"} 1`);
  const age=(await db.query("SELECT coalesce(extract(epoch FROM now()-min(discovered_at)),0)::float age FROM immich_sync.jobs WHERE state IN ('pending','error')")).rows[0].age;
  lines.push(`immich_sync_oldest_pending_seconds ${age}`);
  gauges=lines.join('\n')+'\n';
}
async function cycle() {
  if(active)return;active=true;const started=Date.now();let db;
  try {
    db=await pool.connect();
    const lock=(await db.query('SELECT pg_try_advisory_lock(217,8001) locked')).rows[0].locked;
    if(!lock)return;
    phase='connect';await api('/users/me');counters.api_ready=1;
    // Repair only false removals made by earlier catalog sweeps. Applied snapshots
    // keep their edit protection and are scheduled for a fresh readback audit.
    if (MODE==='apply' && !counters.last_discovery) {
      await db.query(`UPDATE immich_sync.jobs
        SET state=CASE WHEN applied->>'sourceRevision'=source_hash AND intent IS NULL THEN 'applied' ELSE 'pending' END,
            reason=NULL, available_at=now(), verified_at=NULL, updated_at=now()
        WHERE state='conflict' AND reason='source_removed' AND payload ? 'recovery'
          AND asset_id IS NOT NULL AND length(trim(payload->>'summary'))>0`);
    }
    if(!counters.last_discovery){
      const checkpoint=await state(db,'checkpoint');
      if(checkpoint && (checkpoint.version??1)===DISCOVERY_VERSION){
        counters.last_discovery=Date.parse(checkpoint.capturedAt)/1000;
        counters.source=checkpoint.sourceRows;counters.available_summaries=checkpoint.successfulSummaries;
      }
    }
    await metrics(db);
    if(Date.now()/1000-counters.last_discovery>600)await discover(db);
    if(MODE==='apply'){
      const preserved=MAX_PRESERVED?(await db.query("SELECT count(*)::int n FROM immich_sync.jobs WHERE state='applied'")).rows[0].n:0;
      const limit=MAX_PRESERVED?Math.max(0,Math.min(BATCH,MAX_PRESERVED-preserved)):BATCH;
      const jobs=(await db.query("SELECT * FROM immich_sync.jobs WHERE state IN ('pending','error') AND available_at<=now() ORDER BY (payload->>'summary' IS NOT NULL) DESC,discovered_at,source_path LIMIT $1",[limit])).rows;
      for(const job of jobs){
        try{await measured('preserve',()=>apply(db,job));}catch(e){
          const reason=e.status?'http_'+e.status:e.message?.replace(/[^a-zA-Z0-9 _-]/g,'').slice(0,80)??'unknown';
          await db.query("UPDATE immich_sync.jobs SET state='error',reason=$2,attempts=attempts+1,available_at=now()+least(3600,power(2,least(attempts,10))*30)*interval '1 second',updated_at=now() WHERE source_path=$1",[job.source_path,reason]);
          log('sync.asset_error',{source_id:digest(job.source_path).slice(0,16),reason});
        }
      }
      log('sync.batch',{attempted:jobs.length});
      // Detect subsequent user edits/removals without restoring them.
      const audit=(await db.query("SELECT source_path,asset_id,applied FROM immich_sync.jobs WHERE state='applied' AND (verified_at IS NULL OR verified_at<now()-interval '24 hours') ORDER BY verified_at NULLS FIRST LIMIT 5")).rows;
      for(const job of audit){
        const current=await api('/assets/'+job.asset_id+'/metadata');
        const matches=stable(current.find(x=>x.key===META_KEY)?.value)===stable(job.applied);
        await db.query("UPDATE immich_sync.jobs SET verified_at=now(),state=$2,reason=$3 WHERE source_path=$1",[job.source_path,matches?'applied':'conflict',matches?null:'machine_metadata_edited']);
      }
    }
    await metrics(db);
  } catch(e){counters.api_ready=0;log('sync.cycle_error',{phase,reason:e.code??(e.status?'http_'+e.status:'unavailable')});}
  finally{if(db){try{await db.query('SELECT pg_advisory_unlock(217,8001)');}catch{}db.release();}counters.cycle_seconds=(Date.now()-started)/1000;active=false;}
}
http.createServer((req,res)=>{
 if(req.url==='/healthz'){res.end('ok');return;}
 if(req.url!=='/metrics'){res.writeHead(404);res.end();return;}
 res.setHeader('Content-Type','text/plain; version=0.0.4');
 res.end(gauges+Object.entries(stageSeconds).map(([stage,v])=>`immich_sync_stage_seconds{stage="${stage}"} ${v}`).join('\n')+'\n'+Object.entries(counters).map(([k,v])=>`immich_sync_${k} ${v}`).join('\n')+'\n');
}).listen(9200,'0.0.0.0');
await cycle();setInterval(cycle,15000);
