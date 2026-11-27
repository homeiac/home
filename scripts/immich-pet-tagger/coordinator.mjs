// Single API writer + PostgreSQL queue. Workers perform inference only.
import http from 'node:http';
import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import {createRequire} from 'node:module';
import {claim,finish,fail,WORKERS,SLOT_LIMITS,BURST_LIMITS,BURST_CPU_LIMITS,validateTuning,validateBurst} from './queue-core.mjs';
import {discover} from './discovery.mjs';
const {Pool}=createRequire('/usr/src/app/server/package.json')('pg');
const pool=new Pool({max:6,connectionTimeoutMillis:10000,idleTimeoutMillis:30000});
const IMMICH=process.env.IMMICH_URL??'http://immich-server.immich-pilot.svc.cluster.local:2283';
const workerToken=process.env.WORKER_TOKEN,adminToken=process.env.ADMIN_TOKEN;
const uuid=/^[0-9a-f-]{36}$/i;
let report='',healthy=false,tagId=null;
const safeEqual=(a,b)=>typeof a==='string'&&typeof b==='string'&&a.length===b.length&&crypto.timingSafeEqual(Buffer.from(a),Buffer.from(b));
async function api(path,method='GET',body) {
  const r=await fetch(IMMICH+'/api'+path,{method,headers:{'x-api-key':process.env.IMMICH_API_KEY,'Content-Type':'application/json'},
    body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(15000)});
  if(!r.ok)throw Object.assign(Error('Immich HTTP '+r.status),{status:r.status});
  return r;
}
async function jsonBody(req) {
  let value='';for await(const chunk of req){value+=chunk;if(value.length>25e6)throw Error('Too large');}
  return JSON.parse(value||'{}');
}
const respond=(res,value,status=200)=>{res.writeHead(status,{'Content-Type':'application/json'});res.end(JSON.stringify(value));};
async function transaction(fn) {
  const db=await pool.connect();try {await db.query('BEGIN');const value=await fn(db);await db.query('COMMIT');return value;}
  catch(e){await db.query('ROLLBACK');throw e;}finally{db.release();}
}

async function writeOne() {
  // Hold one row lock across API writes, never model inference. A crash is
  // recoverable: re-read existing faces before creating one, and reapply review tag.
  return transaction(async db=>{
    const job=(await db.query(`SELECT j.*,r.config FROM waffles.jobs j JOIN waffles.runs r ON r.id=j.run_id
      WHERE j.status='classified' AND j.available_at<=now() AND r.state='running'
      ORDER BY j.ordinal FOR UPDATE OF j SKIP LOCKED LIMIT 1`)).rows[0];
    if(!job)return false;
    let added=0;
    try {
      if(job.result.matches.length) {
        const faces=await (await api('/faces?id='+job.asset_id)).json();
        if(!faces.some(f=>(f.person?.id??f.personId)===job.config.person_id)) {
          const best=[...job.result.matches].sort((a,b)=>b.probability-a.probability)[0];
          const [width,height]=job.result.size,b=best.box;
          await api('/faces','POST',{assetId:job.asset_id,personId:job.config.person_id,
            imageWidth:width,imageHeight:height,x:Math.round(b[0]*width),y:Math.round(b[1]*height),
            width:Math.max(1,Math.round((b[2]-b[0])*width)),height:Math.max(1,Math.round((b[3]-b[1])*height))});
          added=1;
        }
        if(!tagId){const tags=await(await api('/tags','PUT',{tags:['Pets/Review']})).json();tagId=tags.find(t=>t.value==='Pets/Review'||t.name==='Pets/Review')?.id;if(!tagId)throw Error('Review tag unavailable');}
        await api('/tags/'+tagId+'/assets','PUT',{ids:[job.asset_id]});
      }
      await db.query("UPDATE waffles.jobs SET status='complete',completed_at=now(),applied=applied+$3,last_error=NULL WHERE run_id=$1 AND asset_id=$2",[job.run_id,job.asset_id,added]);
    } catch(e) {
      // Retry application without repeating inference; record no private API response.
      await db.query("UPDATE waffles.jobs SET available_at=now()+interval '60 seconds',last_error='apply_failed',applied=applied+$3 WHERE run_id=$1 AND asset_id=$2",[job.run_id,job.asset_id,added]);
      console.error('Immich apply retry:',/^Immich HTTP \d+$/.test(e.message)?e.message:e.constructor.name);
    }
    return true;
  });
}

async function refresh() {
  try {
    await pool.query("UPDATE waffles.jobs SET status='failed',last_error='lease_exhausted' WHERE status='running' AND lease_until<now() AND attempts>=4");
    await pool.query(`UPDATE waffles.runs r SET state='complete',finished_at=now() WHERE r.state='running'
      AND EXISTS(SELECT 1 FROM waffles.jobs j WHERE j.run_id=r.id)
      AND NOT EXISTS(SELECT 1 FROM waffles.jobs j WHERE j.run_id=r.id AND j.status IN ('pending','running','classified'))`);
    const rows=(await pool.query(`SELECT r.id,r.mode,r.state,extract(epoch FROM r.started_at)::float8 started,
      CASE WHEN r.state='complete' THEN (SELECT extract(epoch FROM max(done.completed_at))::float8 FROM waffles.jobs done WHERE done.run_id=r.id) END finished,j.worker,j.status,count(j.asset_id)::int count,
      coalesce(sum(j.processing_seconds),0)::float8 seconds,coalesce(sum(j.applied),0)::int applied
      FROM waffles.runs r LEFT JOIN waffles.jobs j ON j.run_id=r.id GROUP BY r.id,j.worker,j.status`)).rows;
    const devices=(await pool.query("SELECT run_id,worker,pool,coalesce(device,'unknown') device,count(*)::int jobs FROM waffles.jobs WHERE status='complete' GROUP BY run_id,worker,pool,device")).rows;
    const failures=(await pool.query("SELECT run_id,coalesce(last_error,'unknown') reason,count(*)::int jobs FROM waffles.jobs WHERE status='failed' GROUP BY run_id,last_error")).rows;
    const instances=(await pool.query("SELECT *,extract(epoch FROM reported_at)::float8 reported FROM waffles.instances WHERE reported_at>now()-interval '60 seconds'")).rows;
    const burst=(await pool.query("SELECT value FROM waffles.settings WHERE key='burst'")).rows[0]?.value??{};
    await pool.query("DELETE FROM waffles.instances WHERE reported_at<now()-interval '7 days'");
    const metric=(name,value,labels={})=>'waffles_'+name+'{'+Object.entries(labels).map(([k,v])=>k+'='+JSON.stringify(v)).join(',')+'} '+Number(value);
    const lines=[metric('queue_up',1),metric('queue_report_timestamp_seconds',Date.now()/1000)];
    for(const row of devices)lines.push(metric('device_jobs',row.jobs,{run:row.run_id,worker:row.worker,pool:row.pool,device:row.device}));
    for(const row of failures)lines.push(metric('failed_jobs',row.jobs,{run:row.run_id,reason:row.reason}));
    const mac=(await pool.query("SELECT value FROM waffles.settings WHERE key='mac-observation'")).rows[0]?.value;
    if(mac)for(const [name,value] of Object.entries(mac))lines.push(metric('mac_'+name,value));
    const discovery=(await pool.query("SELECT value FROM waffles.settings WHERE key='discovery'")).rows[0]?.value;
    lines.push(metric('discovery_enabled',Number(Boolean(discovery?.enabled))),metric('discovery_error',Number(Boolean(discovery?.error))));
    if(discovery?.last_success)lines.push(metric('discovery_last_success_timestamp_seconds',Date.parse(discovery.last_success)/1000));
    const seen=new Set();
    for(const row of rows) {
      const labels={run:row.id,mode:row.mode};
      if(!seen.has(row.id)) {
        seen.add(row.id);lines.push(metric('run_state',{paused:0,running:1,complete:2}[row.state],labels));
        if(row.started)lines.push(metric('run_started_timestamp_seconds',row.started,labels));
        if(row.finished)lines.push(metric('run_finished_timestamp_seconds',row.finished,labels));
      }
      if(row.status) {
        const label={...labels,worker:row.worker??'unassigned',state:row.status};
        lines.push(metric('jobs',row.count,label),metric('processing_seconds',row.seconds,label),metric('assignments',row.applied,label));
      }
    }
    for(const name of WORKERS) {
      const group=instances.filter(w=>w.worker===name),active=group.filter(w=>w.ready&&!w.draining).length;
      lines.push(metric('worker_ready',Number(active>0),{worker:name}),metric('worker_active_instances',active,{worker:name}),
        metric('worker_desired_instances',1+(burst[name]?.slots??0),{worker:name}),metric('worker_slot_limit',1+BURST_LIMITS[name],{worker:name}));
      for(const lane of ['base','burst']) {
        lines.push(metric('pool_active_instances',group.filter(w=>w.ready&&!w.draining&&w.pool===lane).length,{worker:name,pool:lane}),
          metric('pool_desired_instances',lane==='base'?1:(burst[name]?.slots??0),{worker:name,pool:lane}));
      }
      lines.push(metric('burst_cpu_cores',burst[name]?.cpu_cores??BURST_CPU_LIMITS[name],{worker:name}));
      lines.push(metric('burst_device',(burst[name]?.device??(name==='mac'?'mps':'cpu'))==='mps'?1:0,{worker:name}));
      for(const instance of group.filter(w=>w.pool==='burst')) {
        lines.push(metric('instance_cpu_seconds_total',instance.cpu_seconds,{worker:name,instance:instance.id}),
          metric('instance_accelerator_bytes',instance.accelerator_bytes,{worker:name,instance:instance.id}));
      }
      if(group.length)lines.push(metric('worker_report_timestamp_seconds',Math.max(...group.map(w=>w.reported)),{worker:name}),
        metric('worker_rss_bytes',group.reduce((total,w)=>total+Number(w.rss_bytes??0),0),{worker:name}));
    }
    report=lines.join('\n')+'\n';healthy=true;
  }catch{healthy=false;report='waffles_queue_up{} 0\n';}
}

http.createServer(async(req,res)=>{
  try {
    const url=new URL(req.url,'http://queue');
    if(url.pathname==='/healthz'){respond(res,{ready:healthy},healthy?200:503);return;}
    if(url.pathname==='/metrics'){res.writeHead(200,{'Content-Type':'text/plain; version=0.0.4'});res.end(report);return;}
    const token=req.headers.authorization?.replace(/^Bearer /,'')??req.headers['x-api-key'];
    const admin=safeEqual(token,adminToken);
    if(!admin&&!safeEqual(token,workerToken)){respond(res,{error:'unauthorized'},401);return;}
    if(url.pathname.startsWith('/admin/')&&!admin){respond(res,{error:'forbidden'},403);return;}
    if(req.method==='GET'&&url.pathname==='/api/config') {
      const row=(await pool.query("SELECT value FROM waffles.settings WHERE key='config'")).rows[0];
      respond(res,row?.value??{},row?200:503);return;
    }
    if(req.method==='GET'&&url.pathname==='/api/tuning') {
      respond(res,{workers:Object.fromEntries(WORKERS.map(w=>[w,{slots:1}])),limits:SLOT_LIMITS});return;
    }
    if(req.method==='GET'&&url.pathname==='/api/burst') {
      const stored=(await pool.query("SELECT value FROM waffles.settings WHERE key='burst'")).rows[0]?.value??{};
      respond(res,{workers:Object.fromEntries(WORKERS.map(w=>[w,{slots:0,mode:'production',cpu_cores:BURST_CPU_LIMITS[w],device:w==='mac'?'mps':'cpu',...stored[w]}])),limits:BURST_LIMITS,cpu_limits:BURST_CPU_LIMITS});return;
    }
    if(req.method==='GET'&&/^\/immich\/api\/assets\/[0-9a-f-]{36}\/thumbnail$/.test(url.pathname)) {
      const id=url.pathname.split('/')[4];
      if(!(await pool.query('SELECT 1 FROM waffles.jobs WHERE asset_id=$1 LIMIT 1',[id])).rowCount){respond(res,{},404);return;}
      try {
        const r=await api('/assets/'+id+'/thumbnail?size=preview');
        res.writeHead(200,{'Content-Type':r.headers.get('content-type')??'image/jpeg'});res.end(Buffer.from(await r.arrayBuffer()));
      } catch(error) {
        const status=Number.isInteger(error.status)&&error.status>=400&&error.status<=599?error.status:502;
        await pool.query("UPDATE waffles.jobs SET last_error=$2 WHERE asset_id=$1 AND status='running' AND lease_until>now()",[id,'thumbnail_http_'+status]);
        respond(res,{error:'thumbnail unavailable'},status);
      }
      return;
    }
    const body=await jsonBody(req);
    if(req.method==='POST'&&url.pathname==='/api/heartbeat') {
      if(!WORKERS.includes(body.worker))throw Error('Invalid worker');
      const instance=body.instance??body.worker;
      if(typeof instance!=='string'||!/^[-a-zA-Z0-9._]{1,120}$/.test(instance))throw Error('Invalid instance');
      const lane=body.pool??'base';if(!['base','burst'].includes(lane))throw Error('Invalid pool');
      if(body.worker==='mac'&&body.role==='supervisor'&&lane==='burst'&&body.host_observation) {
        const source=body.host_observation,observation={report_timestamp_seconds:Date.now()/1000};
        for(const key of ['cpu_percent','gpu_percent','pressure','swap_bytes'])if(Number.isFinite(source[key])&&source[key]>=0)observation[key]=source[key];
        await pool.query("INSERT INTO waffles.settings(key,value) VALUES('mac-observation',$1) ON CONFLICT(key) DO UPDATE SET value=excluded.value",[observation]);
      }
      await pool.query(`INSERT INTO waffles.instances(id,worker,device,ready,draining,rss_bytes,exit_code,pool,cpu_seconds,accelerator_bytes,cpu_affinity) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
        ON CONFLICT(id) DO UPDATE SET reported_at=now(),device=excluded.device,ready=excluded.ready,draining=excluded.draining,rss_bytes=excluded.rss_bytes,exit_code=coalesce(excluded.exit_code,waffles.instances.exit_code),pool=excluded.pool,
        cpu_seconds=greatest(excluded.cpu_seconds,waffles.instances.cpu_seconds),accelerator_bytes=excluded.accelerator_bytes,cpu_affinity=excluded.cpu_affinity`,
        [instance,body.worker,String(body.device??'loading').slice(0,20),body.ready===true,body.draining===true,Number(body.rss_bytes)||0,Number.isInteger(body.exit_code)?body.exit_code:null,lane,Number(body.cpu_seconds)||0,Number(body.accelerator_bytes)||0,Number.isInteger(body.cpu_affinity)?body.cpu_affinity:null]);
      await pool.query(`INSERT INTO waffles.workers(name,device,ready,rss_bytes) VALUES($1,$2,$3,$4)
        ON CONFLICT(name) DO UPDATE SET reported_at=now(),device=excluded.device,ready=excluded.ready,rss_bytes=excluded.rss_bytes WHERE $5<> 'supervisor'`,
        [body.worker,String(body.device??'loading').slice(0,20),body.ready===true,Number(body.rss_bytes)||0,body.role??'inference']);
      if(body.claim)await pool.query("UPDATE waffles.jobs SET lease_until=now()+interval '90 seconds' WHERE run_id=$1 AND asset_id=$2 AND claim=$3 AND worker=$4 AND status='running' AND lease_until>now()",[body.run_id,body.asset_id,body.claim,body.worker]);
      respond(res,{ok:true});return;
    }
    if(req.method==='POST'&&url.pathname==='/api/claim') {respond(res,await claim(pool,body.worker,body.pool??'base',body.device??(body.worker==='mac'?'mps':'cpu')));return;}
    if(req.method==='POST'&&url.pathname==='/api/finish') {respond(res,{accepted:await finish(pool,body,body.result)});return;}
    if(req.method==='POST'&&url.pathname==='/api/fail') {
      respond(res,{ok:await fail(pool,body)});return;
    }
    if(req.method==='POST'&&url.pathname==='/admin/config') {
      if(!uuid.test(body.person_id)||body.names?.[0]!=='Waffles'||!body.scaler||!body.model)throw Error('Invalid config');
      if((await pool.query("SELECT 1 FROM waffles.runs WHERE state='running' LIMIT 1")).rowCount)throw Error('Pause and drain before changing classifier');
      await pool.query("INSERT INTO waffles.settings VALUES('config',$1) ON CONFLICT(key) DO UPDATE SET value=excluded.value",[body]);respond(res,{ok:true});return;
    }
    if(req.method==='POST'&&url.pathname==='/admin/discovery') {
      if(typeof body.enabled!=='boolean'||!Number.isFinite(Date.parse(body.since)))throw Error('Invalid discovery settings');
      await pool.query("INSERT INTO waffles.settings VALUES('discovery',$1) ON CONFLICT(key) DO UPDATE SET value=excluded.value",[{enabled:body.enabled,since:body.since}]);
      respond(res,{ok:true});return;
    }
    if(req.method==='POST'&&url.pathname==='/admin/run') {
      if(!/^[a-z0-9-]{1,60}$/.test(body.id)||!['production','benchmark'].includes(body.mode)||!Array.isArray(body.workers)||!body.workers.length||body.workers.some(w=>!WORKERS.includes(w)))throw Error('Invalid run');
      await transaction(async db=>{
        const config=(await db.query("SELECT value FROM waffles.settings WHERE key='config'")).rows[0].value;
        await db.query('INSERT INTO waffles.runs(id,mode,workers,config) VALUES($1,$2,$3,$4)',[body.id,body.mode,body.workers,config]);
        for(let i=0;i<body.assets.length;i++){
          const a=body.assets[i];if(!uuid.test(a.id)||typeof a.date!=='string')throw Error('Invalid asset');
          await db.query('INSERT INTO waffles.jobs(run_id,asset_id,taken_at,ordinal) VALUES($1,$2,$3,$4)',[body.id,a.id,a.date,i]);
        }
      });respond(res,{created:body.assets.length});return;
    }
    if(req.method==='POST'&&url.pathname==='/admin/state') {
      if(!['paused','running'].includes(body.state))throw Error('Invalid state');
      await pool.query("UPDATE waffles.runs SET state=$2,started_at=CASE WHEN $2='running' THEN coalesce(started_at,now()) ELSE started_at END WHERE id=$1 AND state<>'complete'",[body.id,body.state]);respond(res,{ok:true});return;
    }
    if(req.method==='POST'&&url.pathname==='/admin/workers') {
      if(!Array.isArray(body.workers)||!body.workers.length||body.workers.some(w=>!WORKERS.includes(w)))throw Error('Invalid workers');
      await pool.query('UPDATE waffles.runs SET workers=$2 WHERE id=$1',[body.id,body.workers]);respond(res,{ok:true});return;
    }
    if(req.method==='POST'&&url.pathname==='/admin/tuning') {
      const value=validateTuning(body.worker,body.slots);
      await transaction(async db=>{
        await db.query("INSERT INTO waffles.settings(key,value) VALUES('tuning',jsonb_build_object($1::text,$2::jsonb)) ON CONFLICT(key) DO UPDATE SET value=jsonb_set(waffles.settings.value,ARRAY[$1::text],$2::jsonb,true)",[body.worker,value]);
        await db.query('INSERT INTO waffles.tuning_events(worker,slots,note) VALUES($1,$2,$3)',[body.worker,body.slots,String(body.note??'').slice(0,200)]);
      });respond(res,{worker:body.worker,...value});return;
    }
    if(req.method==='POST'&&url.pathname==='/admin/burst') {
      const stored=(await pool.query("SELECT value FROM waffles.settings WHERE key='burst'")).rows[0]?.value??{};
      const value=validateBurst(body.worker,body.slots,body.mode,body.cpu_cores??stored[body.worker]?.cpu_cores??BURST_CPU_LIMITS[body.worker],body.device??stored[body.worker]?.device??(body.worker==='mac'?'mps':'cpu'));
      await transaction(async db=>{
        await db.query("INSERT INTO waffles.settings(key,value) VALUES('burst',jsonb_build_object($1::text,$2::jsonb)) ON CONFLICT(key) DO UPDATE SET value=jsonb_set(waffles.settings.value,ARRAY[$1::text],$2::jsonb,true)",[body.worker,value]);
        await db.query('INSERT INTO waffles.tuning_events(worker,slots,note) VALUES($1,$2,$3)',[body.worker,body.slots,`burst ${value.mode} ${value.device} cpu=${value.cpu_cores}: `+String(body.note??'').slice(0,150)]);
      });respond(res,{worker:body.worker,...value});return;
    }
    if(req.method==='GET'&&url.pathname==='/admin/status') {
      const runs=(await pool.query(`SELECT r.id,r.mode,r.state,r.workers,r.started_at,r.finished_at,j.worker,j.status,count(*)::int jobs,
        sum(j.processing_seconds)::float8 processing_seconds,sum(j.applied)::int assignments FROM waffles.runs r JOIN waffles.jobs j ON j.run_id=r.id GROUP BY r.id,j.worker,j.status ORDER BY r.created_at,j.worker,j.status`)).rows;
      const workers=(await pool.query(`SELECT w.name,coalesce(max(i.device) FILTER(WHERE i.ready AND NOT i.draining),w.device) device,max(i.reported_at) reported_at,
        count(i.id) FILTER(WHERE i.ready AND NOT i.draining)::int active_instances,
        count(i.id) FILTER(WHERE i.ready AND NOT i.draining AND i.pool='base')::int base_instances,
        count(i.id) FILTER(WHERE i.ready AND NOT i.draining AND i.pool='burst')::int burst_instances,
        array_agg(DISTINCT i.cpu_affinity) FILTER(WHERE i.ready AND NOT i.draining AND i.pool='burst') burst_cpu_affinity,
        array_agg(DISTINCT i.device) FILTER(WHERE i.ready AND NOT i.draining AND i.pool='burst') burst_devices,
        count(i.id) FILTER(WHERE i.ready AND NOT i.draining)>0 AS ready,
        coalesce(sum(i.rss_bytes),0)::bigint rss_bytes,
        (SELECT count(*)::int FROM waffles.instances dead WHERE dead.worker=w.name AND dead.exit_code<>0 AND NOT dead.draining) unexpected_exits
        FROM waffles.workers w LEFT JOIN waffles.instances i ON i.worker=w.name AND i.reported_at>now()-interval '60 seconds'
        GROUP BY w.name,w.device`)).rows;
      respond(res,{runs,workers,discovery:(await pool.query("SELECT value FROM waffles.settings WHERE key='discovery'")).rows[0]?.value});return;
    }
    respond(res,{error:'not found'},404);
  }catch(e){console.error('Queue request failed:',e.code??e.constructor.name);respond(res,{error:'request failed'},400);}
}).listen(9200,'0.0.0.0');
await refresh();setInterval(refresh,15000);
setInterval(()=>discover(pool,api),60000);
for(;;){try{if(!await writeOne())await new Promise(r=>setTimeout(r,1000));}catch{await new Promise(r=>setTimeout(r,5000));}}
