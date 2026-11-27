// Independently deployed scanner. Never consumes or pauses inference capacity.
import {createRequire} from 'node:module';
import {SCHEMA,NEXT,probe,save} from './preview-preflight-core.mjs';
const {Pool}=createRequire('/usr/src/app/server/package.json')('pg');
const run=process.env.PREFLIGHT_RUN??'historical-waffles';
const concurrency=Number(process.env.PREFLIGHT_CONCURRENCY??4);
const rate=Number(process.env.PREFLIGHT_REQUESTS_PER_SECOND??10);
if(!Number.isInteger(concurrency)||concurrency<1||concurrency>8||!Number.isFinite(rate)||rate<1||rate>40)throw Error('Invalid preflight capacity');
const base=process.env.IMMICH_URL??'http://immich-server.immich-pilot.svc.cluster.local:2283';
const pool=new Pool({max:concurrency+1,statement_timeout:10000,connectionTimeoutMillis:10000});
let stopping=false;process.on('SIGTERM',()=>{stopping=true;});process.on('SIGINT',()=>{stopping=true;});
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
let lastLog=0,checked=0,removed=0,unknown=0,lock;
function progress(event,extra={}) {console.log(JSON.stringify({at:new Date().toISOString(),event,checked_this_process:checked,removed_this_process:removed,unresolved_this_process:unknown,...extra}));lastLog=Date.now();}
async function totals() {return (await lock.query(`SELECT state,count(*)::int jobs,sum(attempts)::int http_attempts,
  count(*) FILTER(WHERE removed)::int removed FROM waffles.preview_checks WHERE run_id=$1 GROUP BY state`,[run])).rows;}
try {
  progress('start',{concurrency,requests_per_second:rate,retries:4,retry_delay_seconds:30});
  if(!process.env.IMMICH_API_KEY)throw Error('missing_credential');
  lock=await pool.connect();
  if(!(await lock.query('SELECT pg_try_advisory_lock(244,244404) AS acquired')).rows[0].acquired)throw Error('scanner_already_running');
  await lock.query(SCHEMA);
  await lock.query(`INSERT INTO waffles.preview_checks(run_id,asset_id,ordinal)
    SELECT j.run_id,j.asset_id,j.ordinal FROM waffles.jobs j JOIN waffles.runs r ON r.id=j.run_id
    WHERE j.run_id=$1 AND j.status='pending' AND r.mode='production' ON CONFLICT DO NOTHING`,[run]);
  while(!stopping) {
    const started=Date.now();
    const jobs=(await lock.query(NEXT,[run,concurrency])).rows;
    if(!jobs.length) {
      const remaining=Number((await lock.query(`SELECT count(*) AS n FROM waffles.preview_checks p
        JOIN waffles.jobs j USING(run_id,asset_id) WHERE p.run_id=$1 AND p.state='pending' AND j.status='pending'`,[run])).rows[0].n);
      if(!remaining)break;
      if(Date.now()-lastLog>=15000)progress('waiting_for_retries',{remaining,totals:await totals()});
      await sleep(1000);continue;
    }
    await Promise.all(jobs.map(async job=>{
      let status=0;
      try {status=await probe(base,process.env.IMMICH_API_KEY,job.asset_id);} catch { /* bounded transport failures remain unresolved */ }
      if(status===401||status===403){stopping=true;throw Error('authentication');}
      const db=await pool.connect();
      try {const result=await save(db,job,status);checked++;if(result.removed)removed++;if(result.state==='unresolved')unknown++;}
      finally {db.release();}
    }));
    if(Date.now()-lastLog>=15000)progress('progress',{totals:await totals()});
    // Rate cap also bounds successful probes, which otherwise finish very quickly.
    await sleep(Math.max(0,jobs.length*1000/rate-(Date.now()-started)));
  }
  progress(stopping?'interrupted':'complete',{totals:await totals()});
} catch(error) {
  // Never log URLs, photo identifiers, keys or raw network exceptions.
  const safe=['authentication','missing_credential','scanner_already_running'].includes(error.message)?error.message:error.code??'scanner_failed';
  progress('error',{reason:safe});process.exitCode=1;
} finally {if(lock)lock.release();await pool.end();}
