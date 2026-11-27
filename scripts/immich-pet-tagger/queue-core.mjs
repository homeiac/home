// Fenced claims adapted from photo_enrichment/postgres.py; inference is outside transactions.
import crypto from 'node:crypto';
export const WORKERS=['mac','pve','still-fawn','fun-bedbug','chief-horse'];
export const SLOT_LIMITS={mac:1,pve:1,'still-fawn':1,'fun-bedbug':1,'chief-horse':1};
export const BURST_LIMITS={mac:15,pve:1,'still-fawn':3,'fun-bedbug':0,'chief-horse':0};
export const BURST_CPU_LIMITS={mac:0,pve:1,'still-fawn':3,'fun-bedbug':0,'chief-horse':0};
export const CLAIM_SQL=`WITH candidate AS (
 SELECT j.run_id,j.asset_id FROM waffles.jobs j JOIN waffles.runs r ON r.id=j.run_id
 WHERE r.state='running' AND $1=ANY(r.workers)
 AND r.mode=CASE WHEN $3='base' THEN
   CASE WHEN EXISTS(SELECT 1 FROM waffles.runs prod WHERE prod.mode='production' AND prod.state='running' AND $1=ANY(prod.workers)) THEN 'production' ELSE 'benchmark' END
   ELSE coalesce((SELECT value->$1->>'mode' FROM waffles.settings WHERE key='burst'),'production') END
 AND ((j.status='pending' AND j.available_at<=now()) OR (j.status='running' AND j.lease_until<now()))
 AND j.attempts<4
 AND (SELECT count(*) FROM waffles.jobs active WHERE active.worker=$1 AND active.pool=$3 AND active.status='running' AND active.lease_until>now())
     < CASE WHEN $3='base' THEN 1 ELSE coalesce((SELECT (value->$1->>'slots')::int FROM waffles.settings WHERE key='burst'),0) END
 ORDER BY r.created_at,j.ordinal FOR UPDATE OF j SKIP LOCKED LIMIT 1)
 UPDATE waffles.jobs j SET status='running',claim=$2,worker=$1,pool=$3,device=$4,lease_until=now()+interval '90 seconds',attempts=attempts+1
 FROM candidate c WHERE j.run_id=c.run_id AND j.asset_id=c.asset_id RETURNING j.*,
 (SELECT config FROM waffles.runs WHERE id=j.run_id) AS config`;

export async function claim(pool,worker,lane='base',device=worker==='mac'?'mps':'cpu') {
  if(!WORKERS.includes(worker))throw Error('Invalid worker');
  if(!['base','burst'].includes(lane))throw Error('Invalid worker pool');
  if(!['cpu','mps'].includes(device)||(worker!=='mac'&&device!=='cpu'))throw Error('Invalid device');
  const db=await pool.connect();
  try {
    await db.query('BEGIN');
    // Separate statements ensure a fresh READ COMMITTED snapshot after waiting
    // for the per-backend lock. Concurrent processes cannot exceed live slots.
    await db.query("SELECT pg_advisory_xact_lock(244,hashtext($1))",[worker]);
    const job=(await db.query(CLAIM_SQL,[worker,crypto.randomUUID(),lane,device])).rows[0]??null;
    await db.query('COMMIT');return job;
  }catch(e){await db.query('ROLLBACK');throw e;}finally{db.release();}
}

export function validateTuning(worker,slots) {
  if(!WORKERS.includes(worker)||slots!==1)throw Error('Baseline workers must remain at one');
  return {slots};
}

export function validateBurst(worker,slots,mode,cpu=BURST_CPU_LIMITS[worker],device=worker==='mac'?'mps':'cpu') {
  if(!WORKERS.includes(worker)||!Number.isInteger(slots)||slots<0||slots>BURST_LIMITS[worker]||!['production','benchmark'].includes(mode))throw Error('Invalid burst policy');
  if(!Number.isInteger(cpu)||cpu<(BURST_CPU_LIMITS[worker]?1:0)||cpu>BURST_CPU_LIMITS[worker])throw Error('Invalid burst CPU parallelism');
  if(!['cpu','mps'].includes(device)||(worker!=='mac'&&device!=='cpu'))throw Error('Invalid burst compute device');
  return {slots,mode,cpu_cores:cpu,device};
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
