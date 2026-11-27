// Fenced claims adapted from photo_enrichment/postgres.py; inference is outside transactions.
import crypto from 'node:crypto';
export const WORKERS=['mac','pve','still-fawn','fun-bedbug','chief-horse'];
export const SLOT_LIMITS={mac:1,pve:1,'still-fawn':1,'fun-bedbug':1,'chief-horse':1};
export const BURST_LIMITS={mac:15,pve:1,'still-fawn':3,'fun-bedbug':0,'chief-horse':0};
export const BURST_CPU_LIMITS={mac:0,pve:1,'still-fawn':3,'fun-bedbug':0,'chief-horse':0};
export const THREAD_LIMITS={mac:16,pve:2,'still-fawn':2,'fun-bedbug':2,'chief-horse':2};
// The ready queue is physically ordered by a partial (run_id,ordinal,asset_id)
// index. Resolve the small run list first; never sort the entire asset backlog.
export const READY_SQL=`SELECT j.run_id,j.asset_id FROM waffles.jobs j
 WHERE j.run_id=$1 AND j.status='pending' AND j.attempts<4 AND j.available_at<=now()
 ORDER BY j.ordinal,j.asset_id`;
export const CLAIM_SQL=`WITH candidate AS (${READY_SQL.replaceAll('$1','$5')}
 FOR UPDATE OF j SKIP LOCKED LIMIT 1)
 UPDATE waffles.jobs j SET status='running',claim=$2,worker=$1,pool=$3,device=$4,
 lease_until=now()+interval '90 seconds',attempts=attempts+1
 FROM candidate c WHERE j.run_id=c.run_id AND j.asset_id=c.asset_id RETURNING j.*,
 (SELECT config FROM waffles.runs WHERE id=j.run_id) AS config`;
export const ELIGIBLE_SQL=`SELECT r.id FROM waffles.runs r
 WHERE r.state='running' AND $1=ANY(r.workers)
 AND r.mode=CASE WHEN $2='base' THEN
   CASE WHEN EXISTS(SELECT 1 FROM waffles.runs prod WHERE prod.mode='production'
     AND prod.state='running' AND $1=ANY(prod.workers)) THEN 'production' ELSE 'benchmark' END
 ELSE coalesce((SELECT value->$1->>'mode' FROM waffles.settings WHERE key='burst'),'production') END
 ORDER BY r.created_at,r.id`;

export async function recoverExpired(db) {
  // Recovery is outside the dequeue hot path, every 15 seconds. Bound the batch
  // and skip locked jobs; late heartbeats/results remain fenced by status/token.
  return db.query(`WITH expired AS (SELECT run_id,asset_id FROM waffles.jobs
    WHERE status='running' AND lease_until<now() ORDER BY lease_until
    FOR UPDATE SKIP LOCKED LIMIT 1000)
    UPDATE waffles.jobs j SET status=CASE WHEN attempts>=4 THEN 'failed' ELSE 'pending' END,
    available_at=now(),lease_until=NULL,
    last_error=CASE WHEN attempts>=4 THEN 'lease_exhausted' ELSE last_error END
    FROM expired e WHERE j.run_id=e.run_id AND j.asset_id=e.asset_id`);
}

export async function claim(pool,worker,lane='base',device=worker==='mac'?'mps':'cpu') {
  if(!WORKERS.includes(worker))throw Error('Invalid worker');
  if(!['base','burst'].includes(lane))throw Error('Invalid worker pool');
  if(!['cpu','mps'].includes(device)||(worker!=='mac'&&device!=='cpu'))throw Error('Invalid device');
  const db=await pool.connect();
  try {
    await db.query('BEGIN');
    // Independent baseline/burst caps need independent locks. The cap query
    // gets a fresh READ COMMITTED snapshot after acquiring this pool's lock.
    await db.query("SELECT pg_advisory_xact_lock(244,hashtext($1))",[worker+':'+lane]);
    const {rows:[capacity]}=await db.query(`SELECT
      (SELECT count(*) FROM waffles.jobs WHERE worker=$1 AND pool=$2
       AND status='running' AND lease_until>now()) <
      CASE WHEN $2='base' THEN 1 ELSE coalesce((SELECT (value->$1->>'slots')::int
       FROM waffles.settings WHERE key='burst'),0) END AS available`,[worker,lane]);
    let job=null;
    if(capacity.available) {
      const runs=(await db.query(ELIGIBLE_SQL,[worker,lane])).rows;
      for(const run of runs) {
        job=(await db.query(CLAIM_SQL,[worker,crypto.randomUUID(),lane,device,run.id])).rows[0]??null;
        if(job)break;
      }
    }
    await db.query('COMMIT');return job;
  }catch(e){await db.query('ROLLBACK');throw e;}finally{db.release();}
}

export function validateTuning(worker,slots) {
  if(!WORKERS.includes(worker)||slots!==1)throw Error('Baseline workers must remain at one');
  return {slots};
}

export function validateBurst(worker,slots,mode,cpu=BURST_CPU_LIMITS[worker],device=worker==='mac'?'mps':'cpu',threads=2) {
  if(!WORKERS.includes(worker)||!Number.isInteger(slots)||slots<0||slots>BURST_LIMITS[worker]||!['production','benchmark'].includes(mode))throw Error('Invalid burst policy');
  if(!Number.isInteger(cpu)||cpu<(BURST_CPU_LIMITS[worker]?1:0)||cpu>BURST_CPU_LIMITS[worker])throw Error('Invalid burst CPU parallelism');
  if(!['cpu','mps'].includes(device)||(worker!=='mac'&&device!=='cpu'))throw Error('Invalid burst compute device');
  if(!Number.isInteger(threads)||threads<1||threads>THREAD_LIMITS[worker])throw Error('Invalid extra-worker thread count');
  if((worker!=='mac'||device!=='cpu')&&threads!==2)throw Error('Thread tuning is limited to Mac CPU extras');
  return {slots,mode,cpu_cores:cpu,device,cpu_threads:threads};
}

export function validateResult(value) {
  if(!value || !Number.isFinite(value.seconds) || value.seconds<0 || value.seconds>3600)throw Error('Invalid duration');
  if(!Array.isArray(value.matches) || value.matches.length>100)throw Error('Invalid matches');
  if(!Array.isArray(value.size) || value.size.length!==2 || value.size.some(v=>!Number.isInteger(v)||v<1||v>100000))throw Error('Invalid size');
  for(const match of value.matches) {
    if(!Number.isFinite(match.probability)||match.probability<0.9||match.probability>1)throw Error('Invalid confidence');
    const b=match.box;
    if(!Array.isArray(b)||b.length!==4||b.some(v=>!Number.isFinite(v)||v<0||v>1)||b[0]>=b[2]||b[1]>=b[3])throw Error('Invalid box');
  }
  for(const key of ['unknown','low_confidence','out_of_range'])
    if(!Number.isInteger(value[key])||value[key]<0||value[key]>100)throw Error('Invalid outcome');
  return {seconds:value.seconds,size:value.size,matches:value.matches,
          unknown:value.unknown,low_confidence:value.low_confidence,out_of_range:value.out_of_range};
}

export async function finish(db,job,value) {
  const result=validateResult(value);
  return (await db.query(`UPDATE waffles.jobs j SET
    status=CASE WHEN r.mode='benchmark' THEN 'complete' ELSE 'classified' END,
    result=$4,processing_seconds=$5,lease_until=NULL,
    completed_at=CASE WHEN r.mode='benchmark' THEN now() ELSE NULL END
    FROM waffles.runs r WHERE j.run_id=r.id AND j.run_id=$1 AND j.asset_id=$2 AND j.claim=$3
    AND j.status='running' AND j.lease_until>now() RETURNING j.asset_id`,
    [job.run_id,job.asset_id,job.claim,result,result.seconds])).rowCount===1;
}

export async function fail(db,job) {
  // Four total claims, then retain an asset-level failure and move on.
  // A stale worker cannot consume another attempt or change a newer claim.
  return (await db.query(`UPDATE waffles.jobs SET status=CASE WHEN attempts>=4 THEN 'failed' ELSE 'pending' END,
    available_at=now()+interval '30 seconds',
    last_error=CASE WHEN last_error LIKE 'thumbnail_http_%' THEN last_error ELSE 'inference_failed' END,
    lease_until=NULL
    WHERE run_id=$1 AND asset_id=$2 AND claim=$3 AND status='running' AND lease_until>now()`,
    [job.run_id,job.asset_id,job.claim])).rowCount===1;
}

export async function applyFailure(db,job,added,reason) {
  if(!Number.isInteger(added)||added<0||added>1||!/^apply_(failed|http_[45][0-9]{2})$/.test(reason))throw Error('Invalid apply failure');
  return (await db.query(`UPDATE waffles.jobs SET
    status=CASE WHEN apply_attempts>=3 THEN 'failed' ELSE 'classified' END,
    apply_attempts=apply_attempts+1,available_at=now()+interval '60 seconds',
    last_error=$4,applied=applied+$3
    WHERE run_id=$1 AND asset_id=$2 AND status='classified'`,
    [job.run_id,job.asset_id,added,reason])).rowCount===1;
}
