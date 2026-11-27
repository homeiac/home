// Run inside the existing Immich sync container. The operator supplies a bounded
// list of frozen UUIDs in items and an operation in mode via the module preamble.
import fs from 'node:fs/promises';
import {createRequire} from 'node:module';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {sourcePacket, scope, ROOT, META_KEY, digest, mapAsset} from '/code/core.mjs';
const require = createRequire('/usr/src/app/server/package.json');
const sharp = require('sharp');
const {Client} = require('pg');
const exec = promisify(execFile);
const key = (await fs.readFile('/credentials/api-key','utf8')).trim();
const base = process.env.IMMICH_URL || 'http://immich-server:2283/api';
const db = new Client();
await db.connect();
const identity = (await db.query("SELECT value FROM immich_sync.state WHERE key='identity'")).rows[0].value;
async function api(route, method='GET', body) {
  const response = await fetch(base+route, {method,headers:{'x-api-key':key,'content-type':'application/json'},
    body:body && JSON.stringify(body),signal:AbortSignal.timeout(40000)});
  if (!response.ok) throw Error('Immich HTTP '+response.status);
  return response;
}
async function one(item) {
  const route='/assets/'+item.id;
  const asset=await (await api(route)).json();
  if (asset.originalPath!==item.path || asset.type!==item.media_type || asset.isOffline || asset.isTrashed ||
      asset.ownerId!==identity.ownerId || Number(asset.exifInfo?.fileSizeInByte)!==item.size) throw Error('asset identity mismatch');
  const records=await (await api(route+'/metadata')).json();
  const health=records.find(x=>x.key==='home.media-health.v1')?.value;
  if (health?.excludeFromProcessing===true) return {state:'excluded',reason:health.state};
  const prior=records.find(x=>x.key===META_KEY)?.value;
  if (asset.exifInfo?.description?.trim() || prior?.summary?.trim()) return {state:'already_described'};
  if (prior) throw Error('existing metadata requires merge');
  const external=asset.originalPath.startsWith(ROOT);
  const path=external?asset.originalPath.slice(ROOT.length):null;
  let stat;
  if (external) {
    if (!scope({path}) || !mapAsset({path,size_bytes:item.size},[asset],identity.ownerId,identity.libraryId).asset) throw Error('source mapping mismatch');
    const real=await fs.realpath(asset.originalPath);
    if (!real.startsWith(ROOT)) throw Error('unexpected source root');
    stat=await fs.stat(real);
    if (stat.size!==item.size) throw Error('source size changed');
  }
  if (mode==='stage') {
    let frames=[],duration=null;
    if (asset.type==='VIDEO') {
      if (!external) throw Error('video outside the verified mount');
      const probe=await exec('ffprobe',['-v','error','-show_entries','format=duration','-of','csv=p=0',asset.originalPath],{timeout:60000});
      duration=Number(probe.stdout.trim());
      if (!(duration>0 && Number.isFinite(duration))) throw Error('unknown video duration');
      const stamps = [.0625,.3125,.6875,.9375].map(f=>duration*f);
      try {
        for (const t of stamps) {
          const frame=await exec('ffmpeg',['-nostdin','-loglevel','error','-threads','2','-ss',String(t),'-i',asset.originalPath,
            '-map','0:V:0','-frames:v','1','-vf','scale=768:768:force_original_aspect_ratio=decrease','-threads','1','-f','image2pipe','-c:v','mjpeg','pipe:1'],{encoding:'buffer',timeout:60000,maxBuffer:8*1024*1024});
          if (!frame.stdout.length) throw Error('empty video frame');
          frames.push(frame.stdout);
        }
      } catch {
        // A container's advertised duration and seek index can both be wrong.
        // Select distinct decoded frames in presentation order and keep their timestamps.
        const result=await exec('ffprobe',['-v','error','-select_streams','V:0','-show_frames','-show_entries',
          'frame=best_effort_timestamp_time','-of','json',asset.originalPath],{timeout:120000,maxBuffer:32*1024*1024});
        const times=JSON.parse(result.stdout).frames??[];
        if (!times.length) throw Error('no decodable video frames');
        const indices=[...new Set([.0625,.3125,.6875,.9375].map(f=>Math.min(times.length-1,Math.floor(f*times.length))))];
        frames=[];
        for (const index of indices) {
          const output=await exec('ffmpeg',['-nostdin','-v','error','-threads','2','-i',asset.originalPath,'-map','0:V:0','-vf',
            'select=eq(n\\,'+index+'),scale=768:768:force_original_aspect_ratio=decrease','-frames:v','1','-threads','1',
            '-f','image2pipe','-c:v','mjpeg','pipe:1'],{encoding:'buffer',timeout:120000,maxBuffer:8*1024*1024});
          if (!output.stdout.length) throw Error('indexed frame is empty');
          frames.push(output.stdout);
        }
        stamps.splice(0,stamps.length,...indices.map(n=>Number(times[n].best_effort_timestamp_time)));
        if (!stamps.every(Number.isFinite)) throw Error('missing video frame timestamps');
      }
      return {state:'staged',mtime:stat.mtime.toISOString(),duration,positions:stamps,frames:frames.map(f=>f.toString('base64'))};
    } else {
      const jpeg=input=>sharp(input).rotate().resize({width:768,height:768,fit:'inside',withoutEnlargement:true}).jpeg({quality:88}).toBuffer();
      try {
        const preview=await api(route+'/thumbnail?size=preview');
        frames=[await jpeg(Buffer.from(await preview.arrayBuffer()))];
      } catch (error) {
        // All CR2-named originals in this frozen cohort have verified JPEG signatures.
        if (!external || !path.toLowerCase().endsWith('.cr2')) throw error;
        frames=[await jpeg(asset.originalPath)];
      }
    }
    return {state:'staged',mtime:stat?.mtime.toISOString()??null,duration,frames:frames.map(f=>f.toString('base64'))};
  }
  if (mode!=='publish' || !item.summary?.trim() || !Array.isArray(item.tags)) throw Error('invalid publication');
  if (external && stat.mtime.toISOString()!==item.mtime) throw Error('source modified after inference');
  const packet=sourcePacket({path:path??asset.originalPath,size_bytes:item.size,mtime:item.mtime,summary:item.summary,
    summary_model:item.model,summary_created_at:item.created,summary_tags:item.tags});
  packet.recovery={run:'historical-waffles-caption-recovery-v1',frames:item.frameCount};
  if (external) {
    const result=await db.query(`INSERT INTO immich_sync.jobs(source_path,source_hash,payload,asset_id,state,cycle_id)
      VALUES ($1,$2,$3,$4,'pending',$5) ON CONFLICT(source_path) DO NOTHING`,[path,digest(packet),packet,item.id,packet.recovery.run]);
    if (!result.rowCount) {
      const existing=(await db.query('SELECT asset_id,source_hash,state FROM immich_sync.jobs WHERE source_path=$1',[path])).rows[0];
      if(existing?.asset_id!==item.id || existing.source_hash!==digest(packet)) throw Error('competing sync job');
    }
    return {state:'queued'};
  }
  // Pilot uploads have no external-library path. Publish only the absent, owned key.
  await api(route+'/metadata','PUT',{items:[{key:META_KEY,value:packet}]});
  const check=await (await api(route+'/metadata')).json();
  if (check.find(x=>x.key===META_KEY)?.value?.summary!==item.summary) throw Error('caption readback mismatch');
  return {state:'verified'};
}
for (const item of items) {
  try { console.log(JSON.stringify({id:item.id,...await one(item)})); }
  catch (e) { console.log(JSON.stringify({id:item.id,state:'error',reason:(e.message||'failure').split('\n')[0].replaceAll(item.path,'[file]').slice(0,130)})); }
}
await db.end();
